"""Heat cycles, manual reminders and the calendar feed. Everything is scoped to the breeder."""
import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.heat_cycle import BreederReminder, HeatCycle
from app.models.pet import Pet
from app.models.user import User
from app.schemas.heat_cycle import (
    CalendarEvent,
    CalendarHeatSpan,
    CalendarPet,
    CalendarRead,
    HeatCycleRead,
    HeatCycleWrite,
    ReminderRead,
    ReminderWrite,
)

MAX_CALENDAR_DAYS = 120
_OPEN_CYCLE = "This dog already has a heat cycle in progress. End it before starting a new one."


def _not_found(what: str) -> HTTPException:
    # 404 (not 403) for other breeders' records, so ids don't leak
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _cycle_read(c: HeatCycle) -> HeatCycleRead:
    return HeatCycleRead(id=c.id, pet_id=c.pet_id, pet_name=c.pet.name, start_date=c.start_date,
                         end_date=c.end_date, notes=c.notes, in_progress=c.end_date is None,
                         created_at=c.created_at, updated_at=c.updated_at)


def _reminder_read(r: BreederReminder) -> ReminderRead:
    return ReminderRead(id=r.id, pet_id=r.pet_id, pet_name=r.pet.name, remind_on=r.remind_on,
                        note=r.note, created_at=r.created_at, updated_at=r.updated_at)


def _clean(text: Optional[str]) -> Optional[str]:
    text = (text or "").strip()
    return text or None


class HeatCycleService:

    async def _owned_pet(self, db: AsyncSession, breeder: User, pet_id: uuid.UUID) -> Pet:
        pet = await db.get(Pet, pet_id)
        if pet is None or pet.user_id != breeder.id or pet.is_deleted:
            raise _not_found("Pet")
        return pet

    async def _owned_cycle(self, db: AsyncSession, breeder: User, cycle_id: uuid.UUID) -> HeatCycle:
        result = await db.execute(
            select(HeatCycle).where(HeatCycle.id == cycle_id, HeatCycle.user_id == breeder.id)
            .options(selectinload(HeatCycle.pet)).execution_options(populate_existing=True)
        )
        cycle = result.scalar_one_or_none()
        if cycle is None or cycle.pet is None or cycle.pet.is_deleted:
            raise _not_found("Heat cycle")
        return cycle

    async def _owned_reminder(self, db: AsyncSession, breeder: User, reminder_id: uuid.UUID) -> BreederReminder:
        result = await db.execute(
            select(BreederReminder).where(BreederReminder.id == reminder_id,
                                          BreederReminder.user_id == breeder.id)
            .options(selectinload(BreederReminder.pet)).execution_options(populate_existing=True)
        )
        reminder = result.scalar_one_or_none()
        if reminder is None or reminder.pet is None or reminder.pet.is_deleted:
            raise _not_found("Reminder")
        return reminder

    async def _has_other_open(self, db: AsyncSession, pet_id: uuid.UUID,
                              exclude: Optional[uuid.UUID] = None) -> bool:
        stmt = select(HeatCycle.id).where(HeatCycle.pet_id == pet_id, HeatCycle.end_date.is_(None))
        if exclude is not None:
            stmt = stmt.where(HeatCycle.id != exclude)
        return (await db.execute(stmt.limit(1))).first() is not None

    async def _commit_cycle(self, db: AsyncSession) -> None:
        try:
            await db.commit()
        except IntegrityError:  # the one-open-cycle index, under a race
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_OPEN_CYCLE)

    # ── cycles ───────────────────────────────────────────────────────────

    async def list_cycles(self, db: AsyncSession, breeder: User, pet_id: uuid.UUID) -> list[HeatCycleRead]:
        await self._owned_pet(db, breeder, pet_id)
        result = await db.execute(
            select(HeatCycle).where(HeatCycle.pet_id == pet_id, HeatCycle.user_id == breeder.id)
            .options(selectinload(HeatCycle.pet))
            .order_by(HeatCycle.start_date.desc(), HeatCycle.created_at.desc())
        )
        return [_cycle_read(c) for c in result.scalars().all()]

    async def create_cycle(self, db: AsyncSession, breeder: User, pet_id: uuid.UUID,
                           data: HeatCycleWrite) -> HeatCycleRead:
        pet = await self._owned_pet(db, breeder, pet_id)
        if (pet.gender or "").lower() == "male":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="Heat cycles can only be recorded for female dogs")
        if data.end_date is None and await self._has_other_open(db, pet_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_OPEN_CYCLE)
        cycle = HeatCycle(pet_id=pet_id, user_id=breeder.id, start_date=data.start_date,
                          end_date=data.end_date, notes=_clean(data.notes))
        db.add(cycle)
        await self._commit_cycle(db)
        return _cycle_read(await self._owned_cycle(db, breeder, cycle.id))

    async def update_cycle(self, db: AsyncSession, breeder: User, cycle_id: uuid.UUID,
                           data: HeatCycleWrite) -> HeatCycleRead:
        cycle = await self._owned_cycle(db, breeder, cycle_id)
        if data.end_date is None and await self._has_other_open(db, cycle.pet_id, exclude=cycle.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_OPEN_CYCLE)
        cycle.start_date = data.start_date
        cycle.end_date = data.end_date
        cycle.notes = _clean(data.notes)
        await self._commit_cycle(db)
        return _cycle_read(await self._owned_cycle(db, breeder, cycle.id))

    async def delete_cycle(self, db: AsyncSession, breeder: User, cycle_id: uuid.UUID) -> None:
        cycle = await self._owned_cycle(db, breeder, cycle_id)
        await db.delete(cycle)
        await db.commit()

    # ── reminders ────────────────────────────────────────────────────────

    async def list_reminders(self, db: AsyncSession, breeder: User, pet_id: uuid.UUID) -> list[ReminderRead]:
        await self._owned_pet(db, breeder, pet_id)
        result = await db.execute(
            select(BreederReminder)
            .where(BreederReminder.pet_id == pet_id, BreederReminder.user_id == breeder.id)
            .options(selectinload(BreederReminder.pet))
            .order_by(BreederReminder.remind_on.desc(), BreederReminder.created_at.desc())
        )
        return [_reminder_read(r) for r in result.scalars().all()]

    async def create_reminder(self, db: AsyncSession, breeder: User, pet_id: uuid.UUID,
                              data: ReminderWrite) -> ReminderRead:
        await self._owned_pet(db, breeder, pet_id)
        reminder = BreederReminder(pet_id=pet_id, user_id=breeder.id, remind_on=data.remind_on,
                                   note=_clean(data.note))
        db.add(reminder)
        await db.commit()
        return _reminder_read(await self._owned_reminder(db, breeder, reminder.id))

    async def update_reminder(self, db: AsyncSession, breeder: User, reminder_id: uuid.UUID,
                              data: ReminderWrite) -> ReminderRead:
        reminder = await self._owned_reminder(db, breeder, reminder_id)
        reminder.remind_on = data.remind_on
        reminder.note = _clean(data.note)
        await db.commit()
        return _reminder_read(await self._owned_reminder(db, breeder, reminder.id))

    async def delete_reminder(self, db: AsyncSession, breeder: User, reminder_id: uuid.UUID) -> None:
        reminder = await self._owned_reminder(db, breeder, reminder_id)
        await db.delete(reminder)
        await db.commit()

    # ── calendar ─────────────────────────────────────────────────────────

    async def calendar(self, db: AsyncSession, breeder: User, start: date, end: date,
                       pet_id: Optional[uuid.UUID]) -> CalendarRead:
        if end < start:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="end must be on or after start")
        if end - start > timedelta(days=MAX_CALENDAR_DAYS):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail=f"Ask for at most {MAX_CALENDAR_DAYS} days at a time")

        pets_result = await db.execute(
            select(Pet).where(Pet.user_id == breeder.id, Pet.is_deleted.is_(False)).order_by(Pet.name)
        )
        pets = [CalendarPet(id=p.id, name=p.name, gender=p.gender) for p in pets_result.scalars().all()]

        # Every cycle overlapping the range: starts/ends inside it become events, and all of
        # them (including one that began earlier and is still going) are listed in in_heat
        cycle_stmt = select(HeatCycle).where(
            HeatCycle.user_id == breeder.id,
            HeatCycle.start_date <= end,
            or_(HeatCycle.end_date.is_(None), HeatCycle.end_date >= start),
        ).options(selectinload(HeatCycle.pet))
        reminder_stmt = select(BreederReminder).where(
            BreederReminder.user_id == breeder.id,
            BreederReminder.remind_on.between(start, end),
        ).options(selectinload(BreederReminder.pet))
        if pet_id is not None:
            cycle_stmt = cycle_stmt.where(HeatCycle.pet_id == pet_id)
            reminder_stmt = reminder_stmt.where(BreederReminder.pet_id == pet_id)

        events: list[CalendarEvent] = []
        in_heat: list[CalendarHeatSpan] = []
        for c in (await db.execute(cycle_stmt)).scalars().all():
            if c.pet is None or c.pet.is_deleted:
                continue
            in_heat.append(CalendarHeatSpan(cycle_id=c.id, pet_id=c.pet_id, pet_name=c.pet.name,
                                            start_date=c.start_date, end_date=c.end_date,
                                            in_progress=c.end_date is None))
            if start <= c.start_date <= end:
                events.append(CalendarEvent(
                    id=f"heat_start:{c.id}", type="heat_start", date=c.start_date, pet_id=c.pet_id,
                    pet_name=c.pet.name, cycle_id=c.id, in_progress=c.end_date is None, note=c.notes))
            if c.end_date is not None and start <= c.end_date <= end:
                events.append(CalendarEvent(
                    id=f"heat_end:{c.id}", type="heat_end", date=c.end_date, pet_id=c.pet_id,
                    pet_name=c.pet.name, cycle_id=c.id, note=c.notes))
        for r in (await db.execute(reminder_stmt)).scalars().all():
            if r.pet is None or r.pet.is_deleted:
                continue
            events.append(CalendarEvent(
                id=f"reminder:{r.id}", type="reminder", date=r.remind_on, pet_id=r.pet_id,
                pet_name=r.pet.name, reminder_id=r.id, note=r.note))

        order = {"heat_start": 0, "heat_end": 1, "reminder": 2}
        events.sort(key=lambda e: (e.date, order[e.type], e.pet_name.lower()))
        in_heat.sort(key=lambda h: (h.start_date, h.pet_name.lower()))
        return CalendarRead(start=start, end=end, pets=pets, events=events, in_heat=in_heat)


heat_cycle_service = HeatCycleService()
