"""Pydantic schemas for message operations."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class MessageCreate(BaseModel):
    """Schema for creating a new message (anonymous user contact form)."""
    breeder_id: UUID = Field(..., description="UUID of the breeder to contact")
    sender_name: str = Field(..., min_length=2, max_length=255, description="Full name of the sender")
    sender_email: EmailStr = Field(..., description="Email address of the sender")
    message: Optional[str] = Field(None, max_length=2000, description="Optional message content")
    
    @field_validator('sender_name')
    @classmethod
    def validate_sender_name(cls, v: str) -> str:
        """Validate sender name is not empty or just whitespace."""
        if not v or not v.strip():
            raise ValueError("Sender name cannot be empty")
        return v.strip()
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v: Optional[str]) -> Optional[str]:
        """Validate and clean message content."""
        if v:
            v = v.strip()
            if len(v) == 0:
                return None
        return v


class MessageResponse(BaseModel):
    """Schema for message response."""
    id: UUID
    breeder_id: UUID
    pet_seeker_id: Optional[UUID] = None
    sender_name: str
    sender_email: str
    message: Optional[str]
    is_read: bool
    response_text: Optional[str]
    responded_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]
    is_linked_to_account: bool = False
    
    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Override to compute is_linked_to_account field."""
        if hasattr(obj, 'pet_seeker_id'):
            # Create dict from object
            data = {
                'id': obj.id,
                'breeder_id': obj.breeder_id,
                'pet_seeker_id': obj.pet_seeker_id,
                'sender_name': obj.sender_name,
                'sender_email': obj.sender_email,
                'message': obj.message,
                'is_read': obj.is_read,
                'response_text': obj.response_text,
                'responded_at': obj.responded_at,
                'created_at': obj.created_at,
                'updated_at': obj.updated_at,
                'is_linked_to_account': obj.pet_seeker_id is not None
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)
    
    class Config:
        from_attributes = True


class MessageListItem(BaseModel):
    """Schema for message list item (summary view)."""
    id: UUID
    sender_name: str
    sender_email: str
    message_preview: Optional[str]  # First 100 characters
    is_read: bool
    responded_at: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Schema for paginated message list response."""
    messages: list[MessageListItem]
    total: int
    unread_count: int
    limit: int
    offset: int


class MessageUpdate(BaseModel):
    """Schema for updating message (mark as read)."""
    is_read: bool = Field(..., description="Read status")


class MessageResponseCreate(BaseModel):
    """Schema for breeder response to a message."""
    response_text: str = Field(..., min_length=1, max_length=5000, description="Response text from breeder")
    
    @field_validator('response_text')
    @classmethod
    def validate_response_text(cls, v: str) -> str:
        """Validate response text is not empty or just whitespace."""
        if not v or not v.strip():
            raise ValueError("Response text cannot be empty")
        return v.strip()


class UnreadCountResponse(BaseModel):
    """Schema for unread message count response."""
    unread_count: int


class MessageSendResponse(BaseModel):
    """Schema for successful message send response."""
    success: bool = True
    message: str = "Your message has been sent to the breeder"
