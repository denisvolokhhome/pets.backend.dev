"""Location schemas for API request/response validation."""
import uuid
from datetime import datetime
from typing import Optional, List

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.validators import NonWhitespaceStr, OptionalNonWhitespaceStr


_PHONE_RE = re.compile(r"^[0-9+()\-. ]{3,32}$")


def _clean_phone(value: Optional[str]) -> Optional[str]:
    """Blank → None; otherwise digits, spaces and + ( ) - . only, max 32 chars."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _PHONE_RE.match(value) or not any(ch.isdigit() for ch in value):
        raise ValueError("Phone may contain only digits, spaces and + ( ) - . (max 32 characters)")
    return value


class LocationBase(BaseModel):
    """Base schema for location data."""
    name: NonWhitespaceStr = Field(..., min_length=1, max_length=255)
    address1: NonWhitespaceStr = Field(..., min_length=1, max_length=255)
    address2: Optional[str] = Field(None, max_length=255)
    city: NonWhitespaceStr = Field(..., min_length=1, max_length=255)
    state: NonWhitespaceStr = Field(..., min_length=1, max_length=255)
    country: NonWhitespaceStr = Field(..., min_length=1, max_length=255)
    zipcode: NonWhitespaceStr = Field(..., min_length=1, max_length=20)
    location_type: NonWhitespaceStr = Field(..., min_length=1, max_length=50)
    is_published: bool = Field(default=True, description="Whether location is published and searchable on map")
    is_default: bool = Field(default=False, description="Whether this is the default location for new pets")
    phone: Optional[str] = Field(None, description="Optional contact phone number")
    show_phone: bool = Field(default=False, description="Whether the phone number is shown to seekers on the map")

    _validate_phone = field_validator("phone", mode="before")(classmethod(lambda cls, v: _clean_phone(v)))


class LocationCreate(LocationBase):
    """Schema for creating a new location."""
    pass


class LocationUpdate(BaseModel):
    """Schema for updating a location."""
    name: OptionalNonWhitespaceStr = Field(None, min_length=1, max_length=255)
    address1: OptionalNonWhitespaceStr = Field(None, min_length=1, max_length=255)
    address2: Optional[str] = Field(None, max_length=255)
    city: OptionalNonWhitespaceStr = Field(None, min_length=1, max_length=255)
    state: OptionalNonWhitespaceStr = Field(None, min_length=1, max_length=255)
    country: OptionalNonWhitespaceStr = Field(None, min_length=1, max_length=255)
    zipcode: OptionalNonWhitespaceStr = Field(None, min_length=1, max_length=20)
    location_type: OptionalNonWhitespaceStr = Field(None, min_length=1, max_length=50)
    is_published: Optional[bool] = Field(None, description="Whether location is published and searchable on map")
    is_default: Optional[bool] = Field(None, description="Whether this is the default location for new pets")
    phone: Optional[str] = Field(None, description="Optional contact phone number")
    show_phone: Optional[bool] = Field(None, description="Whether the phone number is shown to seekers on the map")

    _validate_phone = field_validator("phone", mode="before")(classmethod(lambda cls, v: _clean_phone(v)))


class PetBasicInfo(BaseModel):
    """Basic pet information for location display."""
    id: uuid.UUID
    name: str
    
    model_config = ConfigDict(from_attributes=True)


class LocationRead(LocationBase):
    """Schema for reading location data."""
    id: int
    user_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    pets: List[PetBasicInfo] = []
    
    model_config = ConfigDict(from_attributes=True)
