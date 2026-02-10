"""Breeding schemas for API request/response validation."""
from datetime import datetime, date
from typing import Optional, List
from enum import Enum
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LitterStatus(str, Enum):
    """Enum for breeding status values."""
    STARTED = "Started"
    IN_PROCESS = "InProcess"
    DONE = "Done"
    VOIDED = "Voided"


class LitterBase(BaseModel):
    """Base schema for breeding data."""
    description: Optional[str] = None


class LitterCreate(LitterBase):
    """Schema for creating a new breeding."""
    pass


class LitterUpdate(LitterBase):
    """Schema for updating a breeding."""
    pass


class PetAssignment(BaseModel):
    """Schema for assigning parent pets to a breeding."""
    pet_ids: List[uuid.UUID] = Field(..., min_length=2, max_length=2)
    
    @field_validator('pet_ids')
    @classmethod
    def validate_pet_ids(cls, v: List[uuid.UUID]) -> List[uuid.UUID]:
        """Validate exactly 2 pets are provided and they are different."""
        if len(v) != 2:
            raise ValueError('Exactly 2 pets must be assigned')
        if v[0] == v[1]:
            raise ValueError('Cannot assign same pet twice')
        return v


class PuppyInput(BaseModel):
    """Schema for individual puppy data."""
    name: str = Field(..., min_length=1)
    gender: str
    birth_date: date
    microchip: Optional[str] = None
    
    @field_validator('gender')
    @classmethod
    def validate_gender(cls, v: str) -> str:
        """Validate gender is Male or Female."""
        if v not in ['Male', 'Female']:
            raise ValueError('Gender must be Male or Female')
        return v


class PuppyBatch(BaseModel):
    """Schema for batch adding puppies to a breeding."""
    puppies: List[PuppyInput] = Field(..., min_length=1)


class LitterResponse(LitterBase):
    """Schema for breeding response with full details."""
    id: int
    status: LitterStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    parent_pets: Optional[List[dict]] = None
    puppies: Optional[List[dict]] = None
    
    model_config = ConfigDict(from_attributes=True)


# Keep legacy LitterRead for backward compatibility
class LitterRead(LitterBase):
    """Schema for reading breeding data (legacy)."""
    id: int
    status: str = "Started"
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)
