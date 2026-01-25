"""Pet schemas for API request/response validation."""
import uuid
from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PetBase(BaseModel):
    """Base schema for pet data."""
    name: str = Field(..., min_length=1, max_length=255)
    
    @field_validator('name')
    @classmethod
    def validate_name_not_whitespace(cls, v: str) -> str:
        """Ensure name is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError('Name cannot be empty or whitespace-only')
        return v
    breed_id: Optional[int] = None
    litter_id: Optional[int] = None
    location_id: Optional[int] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=50)
    weight: Optional[float] = Field(None, ge=0)
    description: Optional[str] = None
    is_puppy: Optional[bool] = None
    
    # Health records
    microchip: Optional[str] = Field(None, max_length=255)
    vaccination: Optional[str] = None
    health_certificate: Optional[str] = None
    deworming: Optional[str] = None
    birth_certificate: Optional[str] = None
    
    # Legacy boolean fields
    has_microchip: Optional[bool] = None
    has_vaccination: Optional[bool] = None
    has_healthcertificate: Optional[bool] = None
    has_dewormed: Optional[bool] = None
    has_birthcertificate: Optional[bool] = None


class PetCreate(PetBase):
    """Schema for creating a new pet."""
    pass


class PetUpdate(BaseModel):
    """Schema for updating a pet."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    
    @field_validator('name')
    @classmethod
    def validate_name_not_whitespace(cls, v: Optional[str]) -> Optional[str]:
        """Ensure name is not empty or whitespace-only."""
        if v is not None and (not v or not v.strip()):
            raise ValueError('Name cannot be empty or whitespace-only')
        return v
    breed_id: Optional[int] = None
    litter_id: Optional[int] = None
    location_id: Optional[int] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=50)
    weight: Optional[float] = Field(None, ge=0)
    description: Optional[str] = None
    is_puppy: Optional[bool] = None
    
    # Health records
    microchip: Optional[str] = Field(None, max_length=255)
    vaccination: Optional[str] = None
    health_certificate: Optional[str] = None
    deworming: Optional[str] = None
    birth_certificate: Optional[str] = None
    
    # Legacy boolean fields
    has_microchip: Optional[bool] = None
    has_vaccination: Optional[bool] = None
    has_healthcertificate: Optional[bool] = None
    has_dewormed: Optional[bool] = None
    has_birthcertificate: Optional[bool] = None


class PetRead(PetBase):
    """Schema for reading pet data."""
    id: uuid.UUID
    user_id: uuid.UUID
    image_path: Optional[str] = None
    image_file_name: Optional[str] = None
    is_deleted: bool
    error: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    location_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
