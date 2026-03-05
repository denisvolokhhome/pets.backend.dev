"""Notification schemas for API request/response validation."""
from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class NotificationCreate(BaseModel):
    """Schema for creating a new notification."""
    user_id: uuid.UUID
    type: str = Field(..., max_length=50)
    title: str = Field(..., max_length=255)
    message: Optional[str] = None
    related_id: Optional[uuid.UUID] = None
    related_type: Optional[str] = Field(None, max_length=50)


class NotificationRead(BaseModel):
    """Schema for reading notification data."""
    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    title: str
    message: Optional[str] = None
    related_id: Optional[uuid.UUID] = None
    related_type: Optional[str] = None
    is_read: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
