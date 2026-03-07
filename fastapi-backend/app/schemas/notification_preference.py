"""Notification preference schemas for API request/response validation."""
from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class NotificationPreferenceBase(BaseModel):
    """Base schema for notification preferences."""
    message_received: bool = True
    favorite_added: bool = False


class NotificationPreferenceCreate(NotificationPreferenceBase):
    """Schema for creating notification preferences."""
    pass


class NotificationPreferenceUpdate(BaseModel):
    """Schema for updating notification preferences."""
    message_received: bool | None = None
    favorite_added: bool | None = None


class NotificationPreferenceRead(NotificationPreferenceBase):
    """Schema for reading notification preference data."""
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
