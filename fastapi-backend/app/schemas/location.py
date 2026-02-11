"""Location schemas for API request/response validation."""
import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LocationBase(BaseModel):
    """Base schema for location data."""
    name: str = Field(..., min_length=1, max_length=255)
    address1: str = Field(..., min_length=1, max_length=255)
    address2: Optional[str] = Field(None, max_length=255)
    city: str = Field(..., min_length=1, max_length=255)
    state: str = Field(..., min_length=1, max_length=255)
    country: str = Field(..., min_length=1, max_length=255)
    zipcode: str = Field(..., min_length=1, max_length=20)
    location_type: str = Field(..., min_length=1, max_length=50)
    is_published: bool = Field(default=True, description="Whether location is published and searchable on map")
    
    @field_validator('name', 'address1', 'city', 'state', 'country', 'zipcode', 'location_type')
    @classmethod
    def validate_not_whitespace(cls, v: str) -> str:
        """Ensure required fields are not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError('Field cannot be empty or whitespace-only')
        return v


class LocationCreate(LocationBase):
    """Schema for creating a new location."""
    pass


class LocationUpdate(BaseModel):
    """Schema for updating a location."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address1: Optional[str] = Field(None, min_length=1, max_length=255)
    address2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, min_length=1, max_length=255)
    state: Optional[str] = Field(None, min_length=1, max_length=255)
    country: Optional[str] = Field(None, min_length=1, max_length=255)
    zipcode: Optional[str] = Field(None, min_length=1, max_length=20)
    location_type: Optional[str] = Field(None, min_length=1, max_length=50)
    is_published: Optional[bool] = Field(None, description="Whether location is published and searchable on map")
    
    @field_validator('name', 'address1', 'city', 'state', 'country', 'zipcode', 'location_type')
    @classmethod
    def validate_not_whitespace(cls, v: Optional[str]) -> Optional[str]:
        """Ensure fields are not empty or whitespace-only."""
        if v is not None and (not v or not v.strip()):
            raise ValueError('Field cannot be empty or whitespace-only')
        return v


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
