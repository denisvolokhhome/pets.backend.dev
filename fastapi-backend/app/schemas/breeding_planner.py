"""Breeding planner schemas: matings, progesterone tests, milestones and the planner view."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.validators import NonWhitespaceStr, OptionalNonWhitespaceStr

MatingMethod = Literal["Natural", "AI_Fresh", "AI_Chilled", "AI_Frozen", "Surgical"]
BreederStage = Literal["Mated", "Confirmed", "Missed"]


# ── Matings ───────────────────────────────────────────────────────────────────

class MatingCreate(BaseModel):
    mated_on: date
    method: MatingMethod
    sire_id: Optional[uuid.UUID] = None
    outside_sire_name: OptionalNonWhitespaceStr = Field(None, max_length=255)
    notes: OptionalNonWhitespaceStr = Field(None, max_length=2000)


class MatingUpdate(MatingCreate):
    """Full replacement of a mating (PUT)."""
    pass


class MatingRead(BaseModel):
    id: uuid.UUID
    mated_on: date
    method: str
    sire_id: Optional[uuid.UUID] = None
    sire_name: Optional[str] = None
    outside_sire_name: Optional[str] = None
    notes: Optional[str] = None


# ── Progesterone tests ────────────────────────────────────────────────────────

class ProgesteroneTestCreate(BaseModel):
    tested_on: date
    value_ng_ml: Decimal = Field(..., gt=0, lt=100, decimal_places=2)


class ProgesteroneTestRead(BaseModel):
    id: uuid.UUID
    tested_on: date
    value_ng_ml: float

    model_config = ConfigDict(from_attributes=True)


# ── Milestones ────────────────────────────────────────────────────────────────

class MilestoneCreate(BaseModel):
    """A breeder-added (custom) milestone."""
    title: NonWhitespaceStr = Field(..., max_length=255)
    due_on: date
    remind_on: Optional[date] = None


class MilestoneUpdate(BaseModel):
    """`completed` works on any milestone; the other fields only on custom ones."""
    completed: Optional[bool] = None
    title: OptionalNonWhitespaceStr = Field(None, max_length=255)
    due_on: Optional[date] = None
    remind_on: Optional[date] = None


class MilestoneRead(BaseModel):
    id: uuid.UUID
    key: Optional[str] = None
    title: str
    due_on: date
    remind_on: Optional[date] = None
    completed_at: Optional[datetime] = None
    is_custom: bool
    is_overdue: bool


class MilestoneLocation(BaseModel):
    """Where a milestone lives — used by notification/email links."""
    id: uuid.UUID
    breeding_id: int


class UpcomingMilestoneRead(BaseModel):
    id: uuid.UUID
    breeding_id: int
    breeding_label: str
    title: str
    due_on: date
    is_overdue: bool


# ── Planner ───────────────────────────────────────────────────────────────────

class PlannerUpdate(BaseModel):
    """Send `ovulation_date: null` to clear it; omit the key to leave it unchanged."""
    ovulation_date: Optional[date] = None
    stage: Optional[BreederStage] = None


class PlannerRead(BaseModel):
    breeding_id: int
    stage: str
    status: str
    kind: str
    ovulation_date: Optional[date] = None
    anchor_date: Optional[date] = None
    anchored_on_ovulation: bool = False
    due_date: Optional[date] = None
    due_window_start: Optional[date] = None
    due_window_end: Optional[date] = None
    gestation_day: Optional[int] = None
    allowed_stage_targets: List[str] = []
    matings: List[MatingRead] = []
    progesterone_tests: List[ProgesteroneTestRead] = []
    milestones: List[MilestoneRead] = []
