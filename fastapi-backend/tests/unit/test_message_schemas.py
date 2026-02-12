"""Unit tests for Message Pydantic schemas."""
import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.message import (
    MessageCreate,
    MessageResponse,
    MessageListItem,
    MessageListResponse,
    MessageUpdate,
    MessageResponseCreate,
    UnreadCountResponse,
    MessageSendResponse,
)


class TestMessageCreateSchema:
    """Test MessageCreate schema validation."""
    
    def test_message_create_with_valid_data(self):
        """Test creating message with all valid fields."""
        message_data = {
            "breeder_id": uuid.uuid4(),
            "sender_name": "John Doe",
            "sender_email": "john@example.com",
            "message": "I'm interested in your puppies"
        }
        message = MessageCreate(**message_data)
        
        assert message.sender_name == "John Doe"
        assert message.sender_email == "john@example.com"
        assert message.message == "I'm interested in your puppies"
    
    def test_message_create_without_message_text(self):
        """Test creating message without optional message text."""
        message_data = {
            "breeder_id": uuid.uuid4(),
            "sender_name": "John Doe",
            "sender_email": "john@example.com"
        }
        message = MessageCreate(**message_data)
        
        assert message.sender_name == "John Doe"
        assert message.message is None
    
    def test_message_create_with_empty_message_text(self):
        """Test that empty message text is converted to None."""
        message_data = {
            "breeder_id": uuid.uuid4(),
            "sender_name": "John Doe",
            "sender_email": "john@example.com",
            "message": "   "
        }
        message = MessageCreate(**message_data)
        
        assert message.message is None
    
    def test_message_create_with_invalid_email(self):
        """Test that invalid email raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                breeder_id=uuid.uuid4(),
                sender_name="John Doe",
                sender_email="not-an-email",
                message="Test"
            )
        
        errors = exc_info.value.errors()
        assert any("email" in str(error["loc"]).lower() for error in errors)
    
    def test_message_create_with_short_name(self):
        """Test that name shorter than 2 characters raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                breeder_id=uuid.uuid4(),
                sender_name="J",
                sender_email="john@example.com"
            )
        
        errors = exc_info.value.errors()
        assert any("sender_name" in str(error["loc"]) for error in errors)
    
    def test_message_create_with_empty_name(self):
        """Test that empty name raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                breeder_id=uuid.uuid4(),
                sender_name="",
                sender_email="john@example.com"
            )
        
        errors = exc_info.value.errors()
        assert any("sender_name" in str(error["loc"]) for error in errors)
    
    def test_message_create_with_whitespace_name(self):
        """Test that whitespace-only name raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                breeder_id=uuid.uuid4(),
                sender_name="   ",
                sender_email="john@example.com"
            )
        
        errors = exc_info.value.errors()
        assert any("cannot be empty" in str(error["msg"]).lower() for error in errors)
    
    def test_message_create_with_long_message(self):
        """Test that message longer than 2000 characters raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                breeder_id=uuid.uuid4(),
                sender_name="John Doe",
                sender_email="john@example.com",
                message="x" * 2001
            )
        
        errors = exc_info.value.errors()
        assert any("message" in str(error["loc"]) for error in errors)
    
    def test_message_create_trims_whitespace(self):
        """Test that sender name is trimmed."""
        message_data = {
            "breeder_id": uuid.uuid4(),
            "sender_name": "  John Doe  ",
            "sender_email": "john@example.com"
        }
        message = MessageCreate(**message_data)
        
        assert message.sender_name == "John Doe"
    
    def test_message_create_missing_required_fields(self):
        """Test that missing required fields raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                breeder_id=uuid.uuid4(),
                sender_name="John Doe"
                # Missing sender_email
            )
        
        errors = exc_info.value.errors()
        assert any("sender_email" in str(error["loc"]) for error in errors)


class TestMessageResponseSchema:
    """Test MessageResponse schema."""
    
    def test_message_response_with_full_data(self):
        """Test message response with all fields."""
        response_data = {
            "id": uuid.uuid4(),
            "breeder_id": uuid.uuid4(),
            "sender_name": "John Doe",
            "sender_email": "john@example.com",
            "message": "Test message",
            "is_read": True,
            "response_text": "Thank you for your interest",
            "responded_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        response = MessageResponse(**response_data)
        
        assert response.sender_name == "John Doe"
        assert response.is_read is True
        assert response.response_text == "Thank you for your interest"
    
    def test_message_response_with_null_optional_fields(self):
        """Test message response with null optional fields."""
        response_data = {
            "id": uuid.uuid4(),
            "breeder_id": uuid.uuid4(),
            "sender_name": "John Doe",
            "sender_email": "john@example.com",
            "message": None,
            "is_read": False,
            "response_text": None,
            "responded_at": None,
            "created_at": datetime.utcnow(),
            "updated_at": None
        }
        response = MessageResponse(**response_data)
        
        assert response.message is None
        assert response.response_text is None
        assert response.responded_at is None


class TestMessageListItemSchema:
    """Test MessageListItem schema."""
    
    def test_message_list_item_with_preview(self):
        """Test message list item with message preview."""
        item_data = {
            "id": uuid.uuid4(),
            "sender_name": "John Doe",
            "sender_email": "john@example.com",
            "message_preview": "This is a preview...",
            "is_read": False,
            "responded_at": None,
            "created_at": datetime.utcnow()
        }
        item = MessageListItem(**item_data)
        
        assert item.message_preview == "This is a preview..."
        assert item.is_read is False
    
    def test_message_list_item_without_preview(self):
        """Test message list item without message preview."""
        item_data = {
            "id": uuid.uuid4(),
            "sender_name": "John Doe",
            "sender_email": "john@example.com",
            "message_preview": None,
            "is_read": True,
            "responded_at": datetime.utcnow(),
            "created_at": datetime.utcnow()
        }
        item = MessageListItem(**item_data)
        
        assert item.message_preview is None
        assert item.responded_at is not None


class TestMessageListResponseSchema:
    """Test MessageListResponse schema."""
    
    def test_message_list_response_with_messages(self):
        """Test message list response with multiple messages."""
        response_data = {
            "messages": [
                {
                    "id": uuid.uuid4(),
                    "sender_name": "User 1",
                    "sender_email": "user1@example.com",
                    "message_preview": "Preview 1",
                    "is_read": False,
                    "responded_at": None,
                    "created_at": datetime.utcnow()
                },
                {
                    "id": uuid.uuid4(),
                    "sender_name": "User 2",
                    "sender_email": "user2@example.com",
                    "message_preview": "Preview 2",
                    "is_read": True,
                    "responded_at": datetime.utcnow(),
                    "created_at": datetime.utcnow()
                }
            ],
            "total": 2,
            "unread_count": 1,
            "limit": 20,
            "offset": 0
        }
        response = MessageListResponse(**response_data)
        
        assert len(response.messages) == 2
        assert response.total == 2
        assert response.unread_count == 1
        assert response.limit == 20
        assert response.offset == 0
    
    def test_message_list_response_empty(self):
        """Test message list response with no messages."""
        response_data = {
            "messages": [],
            "total": 0,
            "unread_count": 0,
            "limit": 20,
            "offset": 0
        }
        response = MessageListResponse(**response_data)
        
        assert len(response.messages) == 0
        assert response.total == 0
        assert response.unread_count == 0


class TestMessageUpdateSchema:
    """Test MessageUpdate schema."""
    
    def test_message_update_mark_as_read(self):
        """Test marking message as read."""
        update_data = {"is_read": True}
        update = MessageUpdate(**update_data)
        
        assert update.is_read is True
    
    def test_message_update_mark_as_unread(self):
        """Test marking message as unread."""
        update_data = {"is_read": False}
        update = MessageUpdate(**update_data)
        
        assert update.is_read is False


class TestMessageResponseCreateSchema:
    """Test MessageResponseCreate schema."""
    
    def test_response_create_with_valid_text(self):
        """Test creating response with valid text."""
        response_data = {
            "response_text": "Thank you for your interest in our puppies!"
        }
        response = MessageResponseCreate(**response_data)
        
        assert response.response_text == "Thank you for your interest in our puppies!"
    
    def test_response_create_with_empty_text(self):
        """Test that empty response text raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageResponseCreate(response_text="")
        
        errors = exc_info.value.errors()
        assert any("response_text" in str(error["loc"]) for error in errors)
    
    def test_response_create_with_whitespace_text(self):
        """Test that whitespace-only response text raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageResponseCreate(response_text="   ")
        
        errors = exc_info.value.errors()
        assert any("cannot be empty" in str(error["msg"]).lower() for error in errors)
    
    def test_response_create_with_long_text(self):
        """Test that response text longer than 5000 characters raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageResponseCreate(response_text="x" * 5001)
        
        errors = exc_info.value.errors()
        assert any("response_text" in str(error["loc"]) for error in errors)
    
    def test_response_create_trims_whitespace(self):
        """Test that response text is trimmed."""
        response_data = {
            "response_text": "  Thank you!  "
        }
        response = MessageResponseCreate(**response_data)
        
        assert response.response_text == "Thank you!"
    
    def test_response_create_at_max_length(self):
        """Test response text at maximum length (5000 characters)."""
        response_data = {
            "response_text": "x" * 5000
        }
        response = MessageResponseCreate(**response_data)
        
        assert len(response.response_text) == 5000


class TestUnreadCountResponseSchema:
    """Test UnreadCountResponse schema."""
    
    def test_unread_count_response_with_count(self):
        """Test unread count response."""
        response_data = {"unread_count": 5}
        response = UnreadCountResponse(**response_data)
        
        assert response.unread_count == 5
    
    def test_unread_count_response_zero(self):
        """Test unread count response with zero."""
        response_data = {"unread_count": 0}
        response = UnreadCountResponse(**response_data)
        
        assert response.unread_count == 0


class TestMessageSendResponseSchema:
    """Test MessageSendResponse schema."""
    
    def test_message_send_response_defaults(self):
        """Test message send response with default values."""
        response = MessageSendResponse()
        
        assert response.success is True
        assert response.message == "Your message has been sent to the breeder"
    
    def test_message_send_response_custom_message(self):
        """Test message send response with custom message."""
        response = MessageSendResponse(
            success=True,
            message="Custom success message"
        )
        
        assert response.success is True
        assert response.message == "Custom success message"
