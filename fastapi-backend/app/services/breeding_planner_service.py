"""
Breeding planner service: matings, progesterone tests, milestones and stages.

Every write follows the same shape: load the breeding (owner only), reject
voided breedings, mutate, regenerate template milestones from the anchor date
(`_sync`), commit, and return the fresh planner view.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.breeding import Breeding
from app.models.breeding_mating import BreedingMating
from app.models.breeding_milestone import BreedingMilestone
from app.models.breeding_pet import BreedingPet
from app.models.breeding_progesterone_test import BreedingProgesteroneTest
from app.models.pet import Pet
from app.models.user import User
from app.schemas.breeding_planner import (
    MatingCreate,
    MatingRead,
    MatingUpdate,
    MilestoneCreate,
    MilestoneLocation,
    MilestoneRead,
    MilestoneUpdate,
    PlannerRead,
    PlannerUpdate,
    ProgesteroneTestCreate,
    ProgesteroneTestRead,
    UpcomingMilestoneRead,
)
from app.services.breeding_planner_rules import (
    REMINDER_STAGES,
    Stage,
    allowed_targets,
    can_set_stage,
    due_window,
    milestone_plan,
    normalize_kind,
)

VOIDED = "Voided"


def planner_load_options() -> list[Any]:
    """Eager-load everything the planner view and regeneration need."""
    return [
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.breed),
        selectinload(Breeding.matings).selectinload(BreedingMating.sire),
        selectinload(Breeding.progesterone_tests),
        selectinload(Breeding.milestones),
    ]


def _not_found(what: str = "Breeding") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


def _parents(breeding: Breeding) -> list[Pet]:
    """Parent pets, dam first."""
    pets = [bp.pet for bp in breeding.breeding_pets if bp.pet is not None]
    return sorted(pets, key=lambda p: p.gender != "Female")


def _kind(breeding: Breeding) -> str:
    for pet in _parents(breeding):
        if pet.breed is not None and pet.breed.kind:
            return normalize_kind(pet.breed.kind)
    return normalize_kind(None)


def _anchor(breeding: Breeding) -> tuple[Optional[date], bool]:
    """(anchor date, anchored on ovulation?) — ovulation date wins over first mating."""
    if breeding.ovulation_date:
        return breeding.ovulation_date, True
    if breeding.matings:
        return min(m.mated_on for m in breeding.matings), False
    return None, False


def _sync(breeding: Breeding) -> None:
    """Regenerate template milestones from the anchor and apply automatic stages."""
    anchor, _ = _anchor(breeding)
    existing = {m.key: m for m in breeding.milestones if m.key}
    if anchor is None:
        for m in existing.values():
            if m.completed_at is None:
                breeding.milestones.remove(m)
    else:
        for planned in milestone_plan(anchor, _kind(breeding)):
            current = existing.get(planned.key)
            if current is None:
                breeding.milestones.append(BreedingMilestone(
                    key=planned.key,
                    title=planned.title,
                    due_on=planned.due_on,
                    remind_on=planned.remind_on,
                ))
            elif current.completed_at is None and current.due_on != planned.due_on:
                current.due_on = planned.due_on
                current.remind_on = planned.remind_on
                current.reminded_at = None  # the date moved, so remind again

    if breeding.stage != Stage.WHELPED.value:
        if not breeding.matings:
            breeding.stage = Stage.PLANNED.value
        elif breeding.stage == Stage.PLANNED.value:
            breeding.stage = Stage.MATED.value


def _reject_future(day: date, today: date, field: str) -> None:
    if day > today:
        raise _unprocessable(f"{field} cannot be in the future")


def _milestone_read(m: BreedingMilestone, today: date) -> MilestoneRead:
    return MilestoneRead(
        id=m.id,
        key=m.key,
        title=m.title,
        due_on=m.due_on,
        remind_on=m.remind_on,
        completed_at=m.completed_at,
        is_custom=m.key is None,
        is_overdue=m.completed_at is None and m.due_on < today,
    )


def breeding_label(breeding: Breeding) -> str:
    """Human name for a breeding: the dam, else a parent, else its description."""
    parents = _parents(breeding)
    if parents:
        return parents[0].name
    return breeding.description or f"Breeding #{breeding.id}"


class BreedingPlannerService:
    """Breeding planner operations; all scoped to the breeding's owner."""

    async def _load(self, db: AsyncSession, breeding_id: int, user: User) -> Breeding:
        result = await db.execute(
            select(Breeding)
            .where(Breeding.id == breeding_id, Breeding.user_id == user.id)
            .options(*planner_load_options())
            .execution_options(populate_existing=True)
        )
        breeding = result.scalar_one_or_none()
        if breeding is None:
            raise _not_found()
        return breeding

    async def _load_writable(self, db: AsyncSession, breeding_id: int, user: User) -> Breeding:
        breeding = await self._load(db, breeding_id, user)
        if breeding.status == VOIDED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "BREEDING_VOIDED", "message": "This breeding has been voided"},
            )
        return breeding

    async def _save(self, db: AsyncSession, breeding: Breeding, user: User, today: date) -> PlannerRead:
        _sync(breeding)
        await db.commit()
        return self._read(await self._load(db, breeding.id, user), today)

    def _read(self, breeding: Breeding, today: date) -> PlannerRead:
        kind = _kind(breeding)
        anchor, on_ovulation = _anchor(breeding)
        due = start = end = None
        if anchor is not None:
            due, start, end = due_window(anchor, kind, on_ovulation)
        tracking = anchor is not None and breeding.stage in REMINDER_STAGES
        return PlannerRead(
            breeding_id=breeding.id,
            stage=breeding.stage,
            status=breeding.status,
            kind=kind,
            ovulation_date=breeding.ovulation_date,
            anchor_date=anchor,
            anchored_on_ovulation=on_ovulation,
            due_date=due,
            due_window_start=start,
            due_window_end=end,
            gestation_day=(today - anchor).days if tracking and anchor else None,
            allowed_stage_targets=allowed_targets(breeding.stage, bool(breeding.matings)),
            matings=[
                MatingRead(
                    id=m.id,
                    mated_on=m.mated_on,
                    method=m.method,
                    sire_id=m.sire_id,
                    sire_name=m.sire.name if m.sire else m.outside_sire_name,
                    outside_sire_name=m.outside_sire_name,
                    notes=m.notes,
                )
                for m in breeding.matings
            ],
            progesterone_tests=[ProgesteroneTestRead.model_validate(t) for t in breeding.progesterone_tests],
            milestones=[_milestone_read(m, today) for m in breeding.milestones],
        )

    async def _validate_sire(self, db: AsyncSession, sire_id: Optional[uuid.UUID], user: User) -> None:
        if sire_id is None:
            return
        sire = await db.get(Pet, sire_id)
        if sire is None or sire.user_id != user.id or sire.is_deleted:
            raise _unprocessable("Sire must be one of your pets")
        if sire.gender != "Male":
            raise _unprocessable("Sire must be a male pet")

    @staticmethod
    def _find(items: list[Any], item_id: uuid.UUID, what: str) -> Any:
        for item in items:
            if item.id == item_id:
                return item
        raise _not_found(what)

    # ── Planner ───────────────────────────────────────────────────────────

    async def get_planner(self, db: AsyncSession, breeding_id: int, user: User, today: date) -> PlannerRead:
        return self._read(await self._load(db, breeding_id, user), today)

    async def update_planner(
        self, db: AsyncSession, breeding_id: int, user: User, data: PlannerUpdate, today: date
    ) -> PlannerRead:
        breeding = await self._load_writable(db, breeding_id, user)
        if "ovulation_date" in data.model_fields_set:
            if data.ovulation_date is not None:
                _reject_future(data.ovulation_date, today, "Ovulation date")
            breeding.ovulation_date = data.ovulation_date
        if data.stage is not None and data.stage != breeding.stage:
            has_matings = bool(breeding.matings)
            if not can_set_stage(breeding.stage, data.stage, has_matings):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "INVALID_STAGE_TRANSITION",
                        "message": f"Cannot change stage from {breeding.stage} to {data.stage}",
                        "allowed": allowed_targets(breeding.stage, has_matings),
                    },
                )
            breeding.stage = data.stage
        return await self._save(db, breeding, user, today)

    # ── Matings ───────────────────────────────────────────────────────────

    async def add_mating(
        self, db: AsyncSession, breeding_id: int, user: User, data: MatingCreate, today: date
    ) -> PlannerRead:
        breeding = await self._load_writable(db, breeding_id, user)
        _reject_future(data.mated_on, today, "Mating date")
        await self._validate_sire(db, data.sire_id, user)
        breeding.matings.append(BreedingMating(**data.model_dump()))
        return await self._save(db, breeding, user, today)

    async def update_mating(
        self, db: AsyncSession, breeding_id: int, user: User, mating_id: uuid.UUID,
        data: MatingUpdate, today: date,
    ) -> PlannerRead:
        breeding = await self._load_writable(db, breeding_id, user)
        mating = self._find(breeding.matings, mating_id, "Mating")
        _reject_future(data.mated_on, today, "Mating date")
        await self._validate_sire(db, data.sire_id, user)
        for field, value in data.model_dump().items():
            setattr(mating, field, value)
        return await self._save(db, breeding, user, today)

    async def delete_mating(
        self, db: AsyncSession, breeding_id: int, user: User, mating_id: uuid.UUID, today: date
    ) -> PlannerRead:
        breeding = await self._load_writable(db, breeding_id, user)
        breeding.matings.remove(self._find(breeding.matings, mating_id, "Mating"))
        return await self._save(db, breeding, user, today)

    # ── Progesterone tests ────────────────────────────────────────────────

    async def add_progesterone_test(
        self, db: AsyncSession, breeding_id: int, user: User, data: ProgesteroneTestCreate, today: date
    ) -> PlannerRead:
        breeding = await self._load_writable(db, breeding_id, user)
        _reject_future(data.tested_on, today, "Test date")
        breeding.progesterone_tests.append(BreedingProgesteroneTest(**data.model_dump()))
        return await self._save(db, breeding, user, today)

    async def delete_progesterone_test(
        self, db: AsyncSession, breeding_id: int, user: User, test_id: uuid.UUID, today: date
    ) -> PlannerRead:
        breeding = await self._load_writable(db, breeding_id, user)
        breeding.progesterone_tests.remove(self._find(breeding.progesterone_tests, test_id, "Test"))
        return await self._save(db, breeding, user, today)

    # ── Milestones ────────────────────────────────────────────────────────

    async def add_milestone(
        self, db: AsyncSession, breeding_id: int, user: User, data: MilestoneCreate, today: date
    ) -> PlannerRead:
        breeding = await self._load_writable(db, breeding_id, user)
        if data.remind_on is not None and data.remind_on > data.due_on:
            raise _unprocessable("Reminder date must be on or before the milestone date")
        breeding.milestones.append(BreedingMilestone(
            key=None, title=data.title.strip(), due_on=data.due_on, remind_on=data.remind_on,
        ))
        return await self._save(db, breeding, user, today)

    async def update_milestone(
        self, db: AsyncSession, breeding_id: int, user: User, milestone_id: uuid.UUID,
        data: MilestoneUpdate, today: date,
    ) -> PlannerRead:
        breeding = await self._load_writable(db, breeding_id, user)
        milestone: BreedingMilestone = self._find(breeding.milestones, milestone_id, "Milestone")
        edits = data.model_dump(exclude_unset=True, exclude={"completed"})
        if edits and milestone.key is not None:
            raise _unprocessable("Only custom milestones can be edited; log matings to move template dates")
        if "title" in edits and edits["title"] is None:
            raise _unprocessable("Title cannot be empty")
        if "due_on" in edits and edits["due_on"] is None:
            raise _unprocessable("Date cannot be empty")
        for field, value in edits.items():
            setattr(milestone, field, value.strip() if field == "title" else value)
        if milestone.remind_on is not None and milestone.remind_on > milestone.due_on:
            raise _unprocessable("Reminder date must be on or before the milestone date")
        if {"due_on", "remind_on"} & edits.keys():
            milestone.reminded_at = None
        if data.completed is not None:
            milestone.completed_at = datetime.now(timezone.utc) if data.completed else None
        return await self._save(db, breeding, user, today)

    async def delete_milestone(
        self, db: AsyncSession, breeding_id: int, user: User, milestone_id: uuid.UUID, today: date
    ) -> PlannerRead:
        breeding = await self._load_writable(db, breeding_id, user)
        milestone: BreedingMilestone = self._find(breeding.milestones, milestone_id, "Milestone")
        if milestone.key is not None:
            raise _unprocessable("Template milestones cannot be deleted; mark them complete instead")
        breeding.milestones.remove(milestone)
        return await self._save(db, breeding, user, today)

    # ── Cross-breeding views ──────────────────────────────────────────────

    async def upcoming(self, db: AsyncSession, user: User, days: int, today: date) -> list[UpcomingMilestoneRead]:
        """Open milestones due within `days` (including overdue ones) on active pregnancies."""
        result = await db.execute(
            select(BreedingMilestone)
            .join(Breeding, Breeding.id == BreedingMilestone.breeding_id)
            .where(
                Breeding.user_id == user.id,
                Breeding.stage.in_(REMINDER_STAGES),
                Breeding.status != VOIDED,
                BreedingMilestone.completed_at.is_(None),
                BreedingMilestone.due_on <= today + timedelta(days=days),
            )
            .options(
                selectinload(BreedingMilestone.breeding)
                .selectinload(Breeding.breeding_pets)
                .selectinload(BreedingPet.pet)
            )
            .order_by(BreedingMilestone.due_on, BreedingMilestone.title)
        )
        return [
            UpcomingMilestoneRead(
                id=m.id,
                breeding_id=m.breeding_id,
                breeding_label=breeding_label(m.breeding),
                title=m.title,
                due_on=m.due_on,
                is_overdue=m.due_on < today,
            )
            for m in result.scalars().all()
        ]

    async def locate_milestone(self, db: AsyncSession, user: User, milestone_id: uuid.UUID) -> MilestoneLocation:
        result = await db.execute(
            select(BreedingMilestone.id, BreedingMilestone.breeding_id)
            .join(Breeding, Breeding.id == BreedingMilestone.breeding_id)
            .where(BreedingMilestone.id == milestone_id, Breeding.user_id == user.id)
        )
        row = result.one_or_none()
        if row is None:
            raise _not_found("Milestone")
        return MilestoneLocation(id=row.id, breeding_id=row.breeding_id)

    # ── Hooks for the breedings router ────────────────────────────────────

    @staticmethod
    def summary(breeding: Breeding) -> tuple[str, Optional[date]]:
        """(stage, due_date) for list/detail responses; needs matings + parents loaded."""
        anchor, on_ovulation = _anchor(breeding)
        if anchor is None:
            return breeding.stage, None
        return breeding.stage, due_window(anchor, _kind(breeding), on_ovulation)[0]

    @staticmethod
    def mark_whelped(breeding: Breeding, birth_date: date) -> None:
        breeding.stage = Stage.WHELPED.value
        if breeding.date_of_litter is None:
            breeding.date_of_litter = birth_date


# Singleton instance
breeding_planner_service = BreedingPlannerService()
