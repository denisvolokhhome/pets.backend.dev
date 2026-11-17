"""Schemas for breeder waitlists and deposits."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.breeding import ApplicationFormRead
from app.schemas.validators import NonWhitespaceStr, OptionalNonWhitespaceStr

SexPreference = Literal["Male", "Female", "Any"]
DepositStatusLiteral = Literal["none", "requested", "received", "refunded", "forfeited", "applied"]


class WaitlistRequestCreate(BaseModel):
    sex_preference: SexPreference = "Any"
    preference_notes: OptionalNonWhitespaceStr = Field(None, max_length=2000)
    request_breeding_id: Optional[int] = None
    application_answers: Optional[dict[str, str]] = None


class ManualEntryCreate(BaseModel):
    contact_name: NonWhitespaceStr = Field(..., max_length=255)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = Field(None, max_length=50)
    sex_preference: SexPreference = "Any"
    preference_notes: OptionalNonWhitespaceStr = Field(None, max_length=2000)

    @field_validator("contact_phone")
    @classmethod
    def _blank_phone_is_none(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() or None if v is not None else None

    @model_validator(mode="after")
    def _email_or_phone(self) -> "ManualEntryCreate":
        if not self.contact_email and not self.contact_phone:
            raise ValueError("Provide an email or a phone number")
        return self


class DepositUpdate(BaseModel):
    deposit_status: DepositStatusLiteral
    deposit_amount: Optional[Decimal] = Field(None, ge=0)
    deposit_received_on: Optional[date] = None
    deposit_method: Optional[str] = Field(None, max_length=50)

    @model_validator(mode="after")
    def _received_needs_date(self) -> "DepositUpdate":
        if self.deposit_status == "received" and self.deposit_received_on is None:
            raise ValueError("deposit_received_on is required when the deposit is received")
        return self


class MoveRequest(BaseModel):
    breeding_id: Optional[int] = None


class ReorderRequest(BaseModel):
    position: int = Field(..., ge=1)
    note: Optional[str] = Field(None, max_length=255)


class MatchRequest(BaseModel):
    offspring_id: uuid.UUID


class WithdrawRequest(BaseModel):
    deposit_outcome: Optional[Literal["refunded", "forfeited"]] = None


class EntryRead(BaseModel):
    """Breeder view of an entry."""
    id: uuid.UUID
    breeder_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    source: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    breeding_id: Optional[int] = None
    status: str
    sex_preference: str
    preference_notes: Optional[str] = None
    application_answers: Optional[dict[str, Any]] = None
    request_breeding_id: Optional[int] = None
    queue_date: Optional[date] = None
    position_override: Optional[int] = None
    override_note: Optional[str] = None
    deposit_status: str
    deposit_amount: Optional[Decimal] = None
    deposit_received_on: Optional[date] = None
    deposit_method: Optional[str] = None
    offspring_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Computed by the service
    position: Optional[int] = None
    display_name: str = ""
    breeding_label: Optional[str] = None
    possible_duplicate: bool = False

    model_config = ConfigDict(from_attributes=True)


class SeekerEntryRead(BaseModel):
    """Seeker view: own entry and own position only."""
    id: uuid.UUID
    breeder_id: uuid.UUID
    breedery_name: str
    status: str
    list_label: str
    position: Optional[int] = None
    sex_preference: str
    deposit_status: str
    deposit_amount: Optional[Decimal] = None


class BreederWaitlistRead(BaseModel):
    pending: list[EntryRead]
    general: list[EntryRead]
    deposits_to_settle: list[EntryRead] = []  # withdrawn entries still holding a received deposit


class LitterWaitlistRead(BaseModel):
    breeding_id: int
    entries: list[EntryRead]


class WaitlistSettingsRead(BaseModel):
    deposit_amount: Optional[Decimal] = None
    deposit_policy: Optional[str] = None


class WaitlistSettingsUpdate(BaseModel):
    deposit_amount: Optional[Decimal] = Field(None, ge=0)
    deposit_policy: Optional[str] = Field(None, max_length=2000)


class BreederWaitlistInfo(BaseModel):
    breeder_id: uuid.UUID
    breedery_name: str
    deposit_amount: Optional[Decimal] = None
    deposit_policy: Optional[str] = None
    application_form: Optional[ApplicationFormRead] = None
    has_active_entry: bool = False


class EventRead(BaseModel):
    id: uuid.UUID
    type: str
    actor_id: Optional[uuid.UUID] = None
    payload: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
