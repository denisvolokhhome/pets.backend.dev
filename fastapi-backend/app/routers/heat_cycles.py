"""Heat history, manual reminders and the breeder calendar (breeder-only, private)."""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_breeder
from app.models.user import User
from app.schemas.heat_cycle import (
    CalendarRead,
    HeatCycleRead,
    HeatCycleWrite,
    ReminderRead,
    ReminderWrite,
)
from app.services.heat_cycle_service import heat_cycle_service as svc

router = APIRouter(prefix="/api", tags=["heat-cycles"])


@router.get("/pets/{pet_id}/heat-cycles", response_model=list[HeatCycleRead])
async def list_heat_cycles(pet_id: uuid.UUID, db: AsyncSession = Depends(get_async_session),
                           breeder: User = Depends(require_breeder)):
    return await svc.list_cycles(db, breeder, pet_id)


@router.post("/pets/{pet_id}/heat-cycles", response_model=HeatCycleRead, status_code=status.HTTP_201_CREATED)
async def create_heat_cycle(pet_id: uuid.UUID, data: HeatCycleWrite,
                            db: AsyncSession = Depends(get_async_session),
                            breeder: User = Depends(require_breeder)):
    return await svc.create_cycle(db, breeder, pet_id, data)


@router.put("/heat-cycles/{cycle_id}", response_model=HeatCycleRead)
async def update_heat_cycle(cycle_id: uuid.UUID, data: HeatCycleWrite,
                            db: AsyncSession = Depends(get_async_session),
                            breeder: User = Depends(require_breeder)):
    return await svc.update_cycle(db, breeder, cycle_id, data)


@router.delete("/heat-cycles/{cycle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_heat_cycle(cycle_id: uuid.UUID, db: AsyncSession = Depends(get_async_session),
                            breeder: User = Depends(require_breeder)):
    await svc.delete_cycle(db, breeder, cycle_id)


@router.get("/pets/{pet_id}/reminders", response_model=list[ReminderRead])
async def list_reminders(pet_id: uuid.UUID, db: AsyncSession = Depends(get_async_session),
                         breeder: User = Depends(require_breeder)):
    return await svc.list_reminders(db, breeder, pet_id)


@router.post("/pets/{pet_id}/reminders", response_model=ReminderRead, status_code=status.HTTP_201_CREATED)
async def create_reminder(pet_id: uuid.UUID, data: ReminderWrite,
                          db: AsyncSession = Depends(get_async_session),
                          breeder: User = Depends(require_breeder)):
    return await svc.create_reminder(db, breeder, pet_id, data)


@router.put("/reminders/{reminder_id}", response_model=ReminderRead)
async def update_reminder(reminder_id: uuid.UUID, data: ReminderWrite,
                          db: AsyncSession = Depends(get_async_session),
                          breeder: User = Depends(require_breeder)):
    return await svc.update_reminder(db, breeder, reminder_id, data)


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(reminder_id: uuid.UUID, db: AsyncSession = Depends(get_async_session),
                          breeder: User = Depends(require_breeder)):
    await svc.delete_reminder(db, breeder, reminder_id)


@router.get("/calendar", response_model=CalendarRead)
async def get_calendar(start: date = Query(...), end: date = Query(...),
                       pet_id: Optional[uuid.UUID] = Query(None),
                       db: AsyncSession = Depends(get_async_session),
                       breeder: User = Depends(require_breeder)):
    """Heat starts, heat ends and reminders between two dates (inclusive), optionally for one dog."""
    return await svc.calendar(db, breeder, start, end, pet_id)
