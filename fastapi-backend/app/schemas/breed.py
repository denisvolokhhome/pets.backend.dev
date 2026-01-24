"""Breed schemas for API request/response validation."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BreedColourBase(BaseModel):
    """Base schema for breed colour data."""
    code: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    
    @field_validator('code', 'name')
    @classmethod
    def validate_not_whitespace(cls, v: str) -> str:
        """Ensure fields are not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError('Field cannot be empty or whitespace-only')
        return v


class BreedColourCreate(BreedColourBase):
    """Schema for creating a new breed colour."""
    breed_id: int


class BreedColourUpdate(BaseModel):
    """Schema for updating a breed colour."""
    code: Optional[str] = Field(None, min_length=1, max_length=255)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    
    @field_validator('code', 'name')
    @classmethod
    def validate_not_whitespace(cls, v: Optional[str]) -> Optional[str]:
        """Ensure fields are not empty or whitespace-only."""
        if v is not None and (not v or not v.strip()):
            raise ValueError('Field cannot be empty or whitespace-only')
        return v


class BreedColourRead(BreedColourBase):
    """Schema for reading breed colour data."""
    id: int
    breed_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class BreedBase(BaseModel):
    """Base schema for breed data."""
    name: str = Field(..., min_length=1, max_length=255)
    code: Optional[str] = Field(None, max_length=255)
    group: Optional[str] = None  # breed_group field from design, but model uses 'group'
    
    @field_validator('name')
    @classmethod
    def validate_name_not_whitespace(cls, v: str) -> str:
        """Ensure name is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError('Name cannot be empty or whitespace-only')
        return v


class BreedCreate(BreedBase):
    """Schema for creating a new breed."""
    pass


class BreedUpdate(BaseModel):
    """Schema for updating a breed."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    code: Optional[str] = Field(None, max_length=255)
    group: Optional[str] = None
    
    @field_validator('name')
    @classmethod
    def validate_name_not_whitespace(cls, v: Optional[str]) -> Optional[str]:
        """Ensure name is not empty or whitespace-only."""
        if v is not None and (not v or not v.strip()):
            raise ValueError('Name cannot be empty or whitespace-only')
        return v


class BreedRead(BreedBase):
    """Schema for reading breed data."""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)
