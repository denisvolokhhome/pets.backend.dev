"""Schemas for litter applications and the public litter page."""
import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.breeding import ApplicationFormField

ApplicationStatus = Literal["new", "contacted", "waitlisted", "assigned", "declined"]
ManualStatus = Literal["new", "contacted", "waitlisted", "declined"]


class ApplicationSubmit(BaseModel):
    """A family's answers. ``offspring_id`` is set when applying from a puppy page."""
    answers: dict[str, str] = Field(default_factory=dict)
    offspring_id: Optional[uuid.UUID] = None


class ApplicationSubmitted(BaseModel):
    id: uuid.UUID
    breeding_id: int
    status: ApplicationStatus
    created_at: datetime


class ApplicationAnswer(BaseModel):
    field_id: str
    label: str
    value: str


class OffspringBrief(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None
    gender: Optional[str] = None
    status: Optional[str] = None


class ApplicationRead(BaseModel):
    id: uuid.UUID
    breeding_id: int
    source: Literal["litter", "offspring"]
    status: ApplicationStatus
    applicant_id: Optional[uuid.UUID] = None
    applicant_name: Optional[str] = None
    applicant_email: Optional[str] = None
    answers: list[ApplicationAnswer]
    requested_offspring: Optional[OffspringBrief] = None
    assigned_offspring: Optional[OffspringBrief] = None
    assigned_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ApplicationStatusUpdate(BaseModel):
    status: ManualStatus


class ApplicationAssign(BaseModel):
    offspring_id: uuid.UUID


class LitterApplicationsToggle(BaseModel):
    accepting_litter_applications: bool


# ── public litter page ────────────────────────────────────────────────────────

class PublicParent(BaseModel):
    id: uuid.UUID
    name: str
    gender: Optional[str] = None
    breed_name: Optional[str] = None
    image_url: Optional[str] = None


class PublicPuppy(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None
    gender: Optional[str] = None
    status: str
    price: Optional[float] = None
    image_url: Optional[str] = None


class PublicBreeder(BaseModel):
    id: uuid.UUID
    name: str


class PublicLitterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: Optional[str] = None
    stage: str
    date_of_litter: Optional[date] = None
    breeder: PublicBreeder
    parents: list[PublicParent]
    puppies: list[PublicPuppy]
    application_form: Optional[list[ApplicationFormField]] = None
    accepting_applications: bool
