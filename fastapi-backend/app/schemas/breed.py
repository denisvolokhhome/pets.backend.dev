"""Breed schemas for API request/response validation."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.validators import NonWhitespaceStr, OptionalNonWhitespaceStr


class BreedColourBase(BaseModel):
    """Base schema for breed colour data."""
    name: NonWhitespaceStr = Field(..., min_length=1, max_length=255)


class BreedColourCreate(BreedColourBase):
    """Schema for creating a new breed colour."""
    breed_id: int


class BreedColourUpdate(BaseModel):
    """Schema for updating a breed colour."""
    name: OptionalNonWhitespaceStr = Field(None, min_length=1, max_length=255)


class BreedColourRead(BreedColourBase):
    """Schema for reading breed colour data."""
    id: int
    breed_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class BreedBase(BaseModel):
    """Base schema for breed data."""
    name: NonWhitespaceStr = Field(..., min_length=1, max_length=255)
    kind: str = Field(..., pattern="^(dog|cat)$")


class BreedCreate(BreedBase):
    """Schema for creating a new breed."""
    pass


class BreedUpdate(BaseModel):
    """Schema for updating a breed."""
    name: OptionalNonWhitespaceStr = Field(None, min_length=1, max_length=255)
    kind: Optional[str] = Field(None, pattern="^(dog|cat)$")


class BreedRead(BreedBase):
    """Schema for reading breed data."""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)
