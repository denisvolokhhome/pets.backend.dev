"""Litter schemas for API request/response validation."""
from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LitterBase(BaseModel):
    """Base schema for litter data."""
    date_of_litter: date
    description: Optional[str] = None
    is_active: bool = True


class LitterCreate(LitterBase):
    """Schema for creating a new litter."""
    pass


class LitterUpdate(BaseModel):
    """Schema for updating a litter."""
    date_of_litter: Optional[date] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class LitterRead(LitterBase):
    """Schema for reading litter data."""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)
