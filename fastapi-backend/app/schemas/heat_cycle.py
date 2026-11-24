"""Schemas for heat cycles, breeder reminders and the breeder calendar."""
import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

NOTES_MAX = 2000


class HeatCycleWrite(BaseModel):
    """Create or replace a cycle. No end date = in progress."""
    start_date: date
    end_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=NOTES_MAX)

    @model_validator(mode="after")
    def _end_after_start(self) -> "HeatCycleWrite":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("End date must be on or after the start date")
        return self


class HeatCycleRead(BaseModel):
    id: uuid.UUID
    pet_id: uuid.UUID
    pet_name: str
    start_date: date
    end_date: Optional[date] = None
    notes: Optional[str] = None
    in_progress: bool
    created_at: datetime
    updated_at: datetime


class ReminderWrite(BaseModel):
    remind_on: date
    note: Optional[str] = Field(None, max_length=NOTES_MAX)


class ReminderRead(BaseModel):
    id: uuid.UUID
    pet_id: uuid.UUID
    pet_name: str
    remind_on: date
    note: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CalendarPet(BaseModel):
    id: uuid.UUID
    name: str
    gender: Optional[str] = None


class CalendarEvent(BaseModel):
    """One dated entry. ``cycle_id`` / ``reminder_id`` point at the record to open."""
    id: str
    type: Literal["heat_start", "heat_end", "reminder"]
    date: date
    pet_id: uuid.UUID
    pet_name: str
    cycle_id: Optional[uuid.UUID] = None
    reminder_id: Optional[uuid.UUID] = None
    in_progress: bool = False
    note: Optional[str] = None


class CalendarHeatSpan(BaseModel):
    """A cycle overlapping the requested range (so a dog still in heat shows even without a start/end that month)."""
    cycle_id: uuid.UUID
    pet_id: uuid.UUID
    pet_name: str
    start_date: date
    end_date: Optional[date] = None
    in_progress: bool


class CalendarRead(BaseModel):
    start: date
    end: date
    pets: list[CalendarPet]
    events: list[CalendarEvent]
    in_heat: list[CalendarHeatSpan] = []
