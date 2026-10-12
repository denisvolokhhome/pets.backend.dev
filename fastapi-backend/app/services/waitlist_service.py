"""
Waitlist service: requests, manual entries, approval, deposits and settings.

Every breeder-side operation is scoped to the list owner (`_load_owned`, 404 for
anyone else); seeker-side reads only ever return the caller's own entries.
Each change appends a `WaitlistEvent`, and the notification (if any) is sent
after the commit.
"""
import uuid
from datetime import date
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.models.breeding import Breeding
from app.models.breeding_pet import BreedingPet
from app.models.user import User
from app.models.waitlist_entry import WaitlistEntry
from app.models.waitlist_event import WaitlistEvent
from app.schemas.breeding import ApplicationFormRead
from app.schemas.notification import NotificationCreate
from app.schemas.waitlist import (
    BreederWaitlistInfo,
    BreederWaitlistRead,
    DepositUpdate,
    EntryRead,
    ManualEntryCreate,
    SeekerEntryRead,
    WaitlistRequestCreate,
    WaitlistSettingsRead,
    WaitlistSettingsUpdate,
)
from app.services.breeding_planner_service import breeding_label
from app.services.notification_preference_service import notification_preference_service
from app.services.notification_service import notification_service
from app.services.waitlist_rules import ACTIVE_STATUSES, can_transition, order_entries

settings = Settings()

TITLE_MAX = 255
GENERAL_LABEL = "General waitlist"


def _error(code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"code": error_code, "message": message})


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Waitlist entry not found")


def _duplicate() -> HTTPException:
    return _error(status.HTTP_409_CONFLICT, "WAITLIST_DUPLICATE",
                  "This person is already on the waitlist")


def _invalid_transition(action: str) -> HTTPException:
    return _error(status.HTTP_409_CONFLICT, "INVALID_WAITLIST_TRANSITION",
                  f"This entry cannot be {action} in its current state")


def _entry_options() -> list[Any]:
    return [
        selectinload(WaitlistEntry.user),
        selectinload(WaitlistEntry.breeder),
        selectinload(WaitlistEntry.breeding)
        .selectinload(Breeding.breeding_pets)
        .selectinload(BreedingPet.pet),
    ]


def _breedery(breeder: User) -> str:
    return breeder.breedery_name or breeder.name or breeder.email


def _display_name(entry: WaitlistEntry) -> str:
    if entry.user is not None:
        return entry.user.name or entry.user.email
    return entry.contact_name or "Unknown"


def _list_label(entry: WaitlistEntry) -> str:
    if entry.breeding is not None:
        return f"{breeding_label(entry.breeding)}'s litter"
    return GENERAL_LABEL


def _log(entry: WaitlistEntry, type: str, actor_id: Optional[uuid.UUID], **payload: Any) -> None:
    entry.events.append(WaitlistEvent(type=type, actor_id=actor_id, payload=payload))


def _entry_read(entry: WaitlistEntry, position: Optional[int] = None,
                possible_duplicate: bool = False) -> EntryRead:
    read = EntryRead.model_validate(entry)
    return read.model_copy(update={
        "position": position,
        "display_name": _display_name(entry),
        "breeding_label": breeding_label(entry.breeding) if entry.breeding is not None else None,
        "possible_duplicate": possible_duplicate,
    })


def _seeker_read(entry: WaitlistEntry, position: Optional[int]) -> SeekerEntryRead:
    return SeekerEntryRead(
        id=entry.id,
        breeder_id=entry.breeder_id,
        breedery_name=_breedery(entry.breeder),
        status=entry.status,
        list_label=_list_label(entry),
        position=position,
        sex_preference=entry.sex_preference,
        deposit_status=entry.deposit_status,
        deposit_amount=entry.deposit_amount,
    )


def _active_entry_filter(breeder_id: uuid.UUID) -> Any:
    return (WaitlistEntry.breeder_id == breeder_id, WaitlistEntry.status.in_(ACTIVE_STATUSES))


class WaitlistService:
    # ── loading ──────────────────────────────────────────────────────────

    async def _fetch(self, db: AsyncSession, entry_id: uuid.UUID) -> WaitlistEntry:
        result = await db.execute(
            select(WaitlistEntry).where(WaitlistEntry.id == entry_id)
            .options(*_entry_options()).execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def _load_owned(self, db: AsyncSession, breeder: User, entry_id: uuid.UUID) -> WaitlistEntry:
        result = await db.execute(
            select(WaitlistEntry)
            .where(WaitlistEntry.id == entry_id, WaitlistEntry.breeder_id == breeder.id)
            .options(*_entry_options()).execution_options(populate_existing=True)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            raise _not_found()
        return entry

    async def _get_breeder(self, db: AsyncSession, breeder_id: uuid.UUID) -> User:
        breeder = await db.get(User, breeder_id)
        if breeder is None or not breeder.is_breeder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Breeder not found")
        return breeder

    async def _commit(self, db: AsyncSession) -> None:
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _duplicate()

    async def _positions(self, db: AsyncSession, breeder_id: uuid.UUID,
                         breeding_id: Optional[int]) -> dict[uuid.UUID, int]:
        """1-based pick order of the active entries on one list (general or a breeding)."""
        list_filter = (WaitlistEntry.breeding_id.is_(None) if breeding_id is None
                       else WaitlistEntry.breeding_id == breeding_id)
        result = await db.execute(
            select(WaitlistEntry)
            .where(WaitlistEntry.breeder_id == breeder_id, WaitlistEntry.status == "active", list_filter)
            .execution_options(populate_existing=True)
        )
        ordered = order_entries(list(result.scalars().all()))
        return {e.id: i for i, e in enumerate(ordered, start=1)}

    async def _notify(self, db: AsyncSession, entry: WaitlistEntry, *, to_breeder: bool,
                      type: str, title: str, message: str) -> None:
        """Notify the entry's seeker (or the breeder); manual unlinked entries have nobody to notify."""
        user_id = entry.breeder_id if to_breeder else entry.user_id
        if user_id is None:
            return
        if not await notification_preference_service.should_send_notification(db, user_id, type):
            return
        await notification_service.create_notification(db, NotificationCreate(
            user_id=user_id,
            type=type,
            title=title[:TITLE_MAX],
            message=message,
            related_id=entry.id,
            related_type="waitlist_entry_breeder" if to_breeder else "waitlist_entry_seeker",
        ))

    # ── public info / settings ───────────────────────────────────────────

    async def get_info(self, db: AsyncSession, breeder_id: uuid.UUID, breeding_id: Optional[int],
                       user: Optional[User]) -> BreederWaitlistInfo:
        breeder = await self._get_breeder(db, breeder_id)
        form = None
        if breeding_id is not None:
            result = await db.execute(
                select(Breeding).where(Breeding.id == breeding_id, Breeding.user_id == breeder_id)
                .options(selectinload(Breeding.application_form))
                .execution_options(populate_existing=True)
            )
            breeding = result.scalar_one_or_none()
            if breeding is not None and breeding.application_form is not None:
                form = ApplicationFormRead.model_validate(breeding.application_form, from_attributes=True)
        has_active = False
        if user is not None:
            existing = await db.execute(
                select(func.count()).select_from(WaitlistEntry).where(
                    *_active_entry_filter(breeder_id), WaitlistEntry.user_id == user.id)
            )
            has_active = existing.scalar_one() > 0
        return BreederWaitlistInfo(
            breeder_id=breeder.id,
            breedery_name=_breedery(breeder),
            deposit_amount=breeder.waitlist_deposit_amount,
            deposit_policy=breeder.waitlist_deposit_policy,
            application_form=form,
            has_active_entry=has_active,
        )

    def get_settings(self, breeder: User) -> WaitlistSettingsRead:
        return WaitlistSettingsRead(deposit_amount=breeder.waitlist_deposit_amount,
                                    deposit_policy=breeder.waitlist_deposit_policy)

    async def update_settings(self, db: AsyncSession, breeder: User,
                              data: WaitlistSettingsUpdate) -> WaitlistSettingsRead:
        breeder.waitlist_deposit_amount = data.deposit_amount
        breeder.waitlist_deposit_policy = data.deposit_policy
        db.add(breeder)
        await db.commit()
        await db.refresh(breeder)
        return self.get_settings(breeder)

    # ── requests and manual entries ──────────────────────────────────────

    async def _validated_answers(self, db: AsyncSession, breeder_id: uuid.UUID,
                                 data: WaitlistRequestCreate) -> Optional[dict[str, str]]:
        if data.request_breeding_id is None:
            return None
        result = await db.execute(
            select(Breeding).where(Breeding.id == data.request_breeding_id)
            .options(selectinload(Breeding.application_form))
            .execution_options(populate_existing=True)
        )
        breeding = result.scalar_one_or_none()
        if breeding is None or breeding.user_id != breeder_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="Breeding does not belong to this breeder")
        if breeding.application_form is None:
            return None
        answers = data.application_answers or {}
        fields = breeding.application_form.form_fields or []
        for f in fields:
            if f.get("required") and not (answers.get(f["id"]) or "").strip():
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail=f"Please answer: {f.get('label', f['id'])}")
        known = {f["id"] for f in fields}
        return {k: v for k, v in answers.items() if k in known} or None

    async def request_spot(self, db: AsyncSession, breeder_id: uuid.UUID, seeker: User,
                           data: WaitlistRequestCreate, today: date) -> SeekerEntryRead:
        breeder = await self._get_breeder(db, breeder_id)
        if seeker.id == breeder.id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="You cannot join your own waitlist")
        existing = await db.execute(
            select(func.count()).select_from(WaitlistEntry).where(
                *_active_entry_filter(breeder.id), WaitlistEntry.user_id == seeker.id)
        )
        if existing.scalar_one() > 0:
            raise _duplicate()
        answers = await self._validated_answers(db, breeder.id, data)
        amount = breeder.waitlist_deposit_amount
        entry = WaitlistEntry(
            breeder_id=breeder.id, user_id=seeker.id, source="request", status="pending",
            sex_preference=data.sex_preference, preference_notes=data.preference_notes,
            application_answers=answers, request_breeding_id=data.request_breeding_id,
            deposit_status="requested" if amount is not None else "none", deposit_amount=amount,
        )
        _log(entry, "requested", seeker.id, request_breeding_id=data.request_breeding_id)
        db.add(entry)
        await self._commit(db)
        entry = await self._fetch(db, entry.id)
        await self._notify(db, entry, to_breeder=True, type="waitlist_request",
                           title=f"New waitlist request — {seeker.name or seeker.email}",
                           message=f"{seeker.name or seeker.email} asked to join your waitlist.")
        return _seeker_read(entry, None)

    async def add_manual(self, db: AsyncSession, breeder: User, data: ManualEntryCreate,
                         today: date) -> EntryRead:
        email = str(data.contact_email).strip().lower() if data.contact_email else None
        if email:
            dup_manual = await db.execute(
                select(func.count()).select_from(WaitlistEntry).where(
                    *_active_entry_filter(breeder.id), WaitlistEntry.contact_email == email)
            )
            dup_user = await db.execute(
                select(func.count()).select_from(WaitlistEntry).join(User, User.id == WaitlistEntry.user_id)
                .where(*_active_entry_filter(breeder.id), func.lower(User.email) == email)
            )
            if dup_manual.scalar_one() > 0 or dup_user.scalar_one() > 0:
                raise _duplicate()
        entry = WaitlistEntry(
            breeder_id=breeder.id, user_id=None, source="manual", status="active",
            contact_name=data.contact_name, contact_email=email, contact_phone=data.contact_phone,
            sex_preference=data.sex_preference, preference_notes=data.preference_notes,
            queue_date=today, deposit_status="none",
        )
        _log(entry, "added_manually", breeder.id)
        db.add(entry)
        await self._commit(db)
        entry = await self._fetch(db, entry.id)
        positions = await self._positions(db, breeder.id, None)
        return _entry_read(entry, positions.get(entry.id))

    # ── breeder actions ──────────────────────────────────────────────────

    async def approve(self, db: AsyncSession, breeder: User, entry_id: uuid.UUID,
                      today: date) -> EntryRead:
        entry = await self._load_owned(db, breeder, entry_id)
        if not can_transition(entry.status, "approve", entry.breeding_id is not None):
            raise _invalid_transition("approved")
        entry.status = "active"
        entry.queue_date = entry.queue_date or today
        _log(entry, "approved", breeder.id)
        await self._commit(db)
        entry = await self._fetch(db, entry.id)
        await self._notify(db, entry, to_breeder=False, type="waitlist_update",
                           title=f"You're on {_breedery(breeder)}'s waitlist",
                           message=f"{_breedery(breeder)} approved your waitlist request.")
        positions = await self._positions(db, breeder.id, entry.breeding_id)
        return _entry_read(entry, positions.get(entry.id))

    async def decline(self, db: AsyncSession, breeder: User, entry_id: uuid.UUID) -> EntryRead:
        entry = await self._load_owned(db, breeder, entry_id)
        if not can_transition(entry.status, "decline", entry.breeding_id is not None):
            raise _invalid_transition("declined")
        entry.status = "declined"
        _log(entry, "declined", breeder.id)
        await self._commit(db)
        entry = await self._fetch(db, entry.id)
        await self._notify(db, entry, to_breeder=False, type="waitlist_update",
                           title=f"Your waitlist request to {_breedery(breeder)}",
                           message=f"{_breedery(breeder)} declined your waitlist request.")
        return _entry_read(entry)

    async def update_deposit(self, db: AsyncSession, breeder: User, entry_id: uuid.UUID,
                             data: DepositUpdate) -> EntryRead:
        entry = await self._load_owned(db, breeder, entry_id)
        if not can_transition(entry.status, "deposit", entry.breeding_id is not None):
            raise _invalid_transition("updated")
        was_received = entry.deposit_status == "received"
        recorded_before = any(e.type == "deposit_recorded" for e in entry.events)
        entry.deposit_status = data.deposit_status
        if data.deposit_amount is not None:
            entry.deposit_amount = data.deposit_amount
        entry.deposit_received_on = data.deposit_received_on
        entry.deposit_method = data.deposit_method
        if data.deposit_status == "received":
            entry.queue_date = data.deposit_received_on
        first_receipt = data.deposit_status == "received" and not recorded_before
        _log(entry, "deposit_recorded" if first_receipt else "deposit_updated", breeder.id, deposit_status=data.deposit_status,
             deposit_amount=str(entry.deposit_amount) if entry.deposit_amount is not None else None)
        await self._commit(db)
        entry = await self._fetch(db, entry.id)
        if data.deposit_status == "received" and not was_received:
            await self._notify(db, entry, to_breeder=False, type="waitlist_update",
                               title=f"Deposit recorded — {_breedery(breeder)}",
                               message=f"{_breedery(breeder)} recorded your waitlist deposit.")
        positions = await self._positions(db, breeder.id, entry.breeding_id)
        return _entry_read(entry, positions.get(entry.id))

    # ── lists ────────────────────────────────────────────────────────────

    async def list_breeder(self, db: AsyncSession, breeder: User) -> BreederWaitlistRead:
        result = await db.execute(
            select(WaitlistEntry)
            .where(WaitlistEntry.breeder_id == breeder.id, WaitlistEntry.status.in_(ACTIVE_STATUSES))
            .options(*_entry_options()).execution_options(populate_existing=True)
        )
        entries = list(result.scalars().all())
        linked_emails = {e.user.email.lower() for e in entries
                         if e.status == "active" and e.user is not None}
        pending = sorted((e for e in entries if e.status == "pending"), key=lambda e: e.created_at)
        general = order_entries([e for e in entries if e.status == "active" and e.breeding_id is None])

        def dup(e: WaitlistEntry) -> bool:
            return e.user_id is None and e.contact_email is not None and e.contact_email in linked_emails

        return BreederWaitlistRead(
            pending=[_entry_read(e, None, dup(e)) for e in pending],
            general=[_entry_read(e, i, dup(e)) for i, e in enumerate(general, start=1)],
        )

    async def list_mine(self, db: AsyncSession, seeker: User) -> list[SeekerEntryRead]:
        result = await db.execute(
            select(WaitlistEntry)
            .where(WaitlistEntry.user_id == seeker.id,
                   WaitlistEntry.status.in_(["pending", "active", "matched"]))
            .options(*_entry_options()).execution_options(populate_existing=True)
            .order_by(WaitlistEntry.created_at.desc())
        )
        cache: dict[tuple[uuid.UUID, Optional[int]], dict[uuid.UUID, int]] = {}
        out: list[SeekerEntryRead] = []
        for e in result.scalars().all():
            position = None
            if e.status == "active":
                key = (e.breeder_id, e.breeding_id)
                if key not in cache:
                    cache[key] = await self._positions(db, e.breeder_id, e.breeding_id)
                position = cache[key].get(e.id)
            out.append(_seeker_read(e, position))
        return out


waitlist_service = WaitlistService()
