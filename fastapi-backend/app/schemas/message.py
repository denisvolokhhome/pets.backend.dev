"""Pydantic schemas for message operations."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


class MessageCreate(BaseModel):
    """Schema for creating a new message."""
    receiver_id: UUID = Field(..., description="UUID of the message receiver")
    content: str = Field(..., min_length=1, max_length=5000, description="Message content")
    thread_id: Optional[UUID] = Field(None, description="Thread ID for conversation grouping")
    context_type: Optional[str] = Field(None, max_length=50, description="Context type (e.g., 'offspring')")
    context_id: Optional[UUID] = Field(None, description="Context entity ID")
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate and clean message content."""
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        return v.strip()


class MessageResponse(BaseModel):
    """Schema for message response."""
    id: UUID
    sender_id: UUID
    receiver_id: UUID
    thread_id: UUID
    content: str
    context_type: Optional[str] = None
    context_id: Optional[UUID] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Sender information (joined from User)
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class MessageListItem(BaseModel):
    """Schema for message list item (summary view)."""
    id: UUID
    sender_id: UUID
    receiver_id: UUID
    thread_id: UUID
    content_preview: str  # First 100 characters
    context_type: Optional[str] = None
    context_id: Optional[UUID] = None
    is_read: bool
    created_at: datetime
    
    # Sender and receiver information
    sender_name: Optional[str] = None
    receiver_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class ConversationResponse(BaseModel):
    """Schema for conversation (thread) response."""
    thread_id: UUID
    participant_id: UUID  # The other participant
    participant_name: str
    participant_email: str
    participant_is_breeder: bool
    last_message: Optional[MessageListItem] = None
    unread_count: int
    message_count: int
    context_type: Optional[str] = None
    context_id: Optional[UUID] = None
    last_activity: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(BaseModel):
    """Schema for paginated conversation list response."""
    conversations: list[ConversationResponse]
    total: int
    unread_total: int
    limit: int
    offset: int


class MessageMarkReadRequest(BaseModel):
    """Schema for marking message as read."""
    message_ids: list[UUID] = Field(..., description="List of message IDs to mark as read")


class UnreadCountResponse(BaseModel):
    """Schema for unread message count response."""
    unread_count: int


class UnreadCountResponse(BaseModel):
    """Schema for unread message count response."""
    unread_count: int


class MessageSendResponse(BaseModel):
    """Schema for successful message send response."""
    success: bool = True
    message: str = "Message sent successfully"


class MessageUpdate(BaseModel):
    """Schema for updating a message."""
    is_read: Optional[bool] = None


class MessageResponseCreate(BaseModel):
    """Schema for creating a message response (deprecated - use MessageCreate instead)."""
    response_text: str = Field(..., min_length=1, max_length=5000, description="Response text")
    
    @field_validator('response_text')
    @classmethod
    def validate_response_text(cls, v: str) -> str:
        """Validate and clean response text."""
        if not v or not v.strip():
            raise ValueError("Response text cannot be empty")
        return v.strip()


class OffspringMessageCreate(BaseModel):
    """Schema for creating a message about a specific offspring."""
    message: str = Field(..., min_length=1, max_length=2000, description="Message content")
    receiver_id: Optional[UUID] = Field(None, description="Receiver user ID (defaults to offspring owner)")
    thread_id: Optional[UUID] = Field(None, description="Thread ID (generates new if not provided)")
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate and clean message content."""
        if not v or not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()


class ThreadMessageResponse(BaseModel):
    """Schema for messages in a thread (deprecated - use MessageResponse instead)."""
    id: UUID
    sender_id: UUID
    sender_name: str
    sender_is_breeder: bool
    sender_profile_image_url: Optional[str] = None
    message: str
    created_at: datetime
    is_read: bool
    
    model_config = ConfigDict(from_attributes=True)


class ThreadResponse(BaseModel):
    """Schema for thread response with offspring context (deprecated - use ThreadMessagesResponse instead)."""
    thread_id: UUID
    offspring_id: UUID
    breeder_id: UUID
    pet_seeker_id: UUID
    messages: list[ThreadMessageResponse]
    offspring: Optional[dict] = None
    
    model_config = ConfigDict(from_attributes=True)


class MessageListResponse(BaseModel):
    """Schema for paginated message list response (deprecated - use ConversationListResponse)."""
    messages: list[MessageListItem]
    total: int
    unread_count: int
    limit: int
    offset: int


class ThreadMessagesResponse(BaseModel):
    """Schema for thread messages response."""
    thread_id: UUID
    messages: list[MessageResponse]
    participant: dict  # Other participant info
    context: Optional[dict] = None  # Context entity info (e.g., offspring details)
    
    model_config = ConfigDict(from_attributes=True)
