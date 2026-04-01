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
            "receiver_id": uuid.uuid4(),
            "content": "I'm interested in your puppies",
        }
        message = MessageCreate(**message_data)

        assert message.content == "I'm interested in your puppies"
        assert message.receiver_id is not None

    def test_message_create_without_optional_fields(self):
        """Test creating message without optional fields."""
        message_data = {
            "receiver_id": uuid.uuid4(),
            "content": "Hello",
        }
        message = MessageCreate(**message_data)

        assert message.thread_id is None
        assert message.context_type is None
        assert message.context_id is None

    def test_message_create_with_empty_content(self):
        """Test that empty content raises validation error."""
        with pytest.raises(ValidationError):
            MessageCreate(
                receiver_id=uuid.uuid4(),
                content="   ",
            )

    def test_message_create_with_invalid_receiver(self):
        """Test that invalid receiver_id raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                receiver_id="not-a-uuid",
                content="Test",
            )

        errors = exc_info.value.errors()
        assert any("receiver_id" in str(error["loc"]) for error in errors)

    def test_message_create_missing_content(self):
        """Test that missing content raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                receiver_id=uuid.uuid4(),
            )

        errors = exc_info.value.errors()
        assert any("content" in str(error["loc"]) for error in errors)

    def test_message_create_missing_receiver(self):
        """Test that missing receiver_id raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                content="Hello",
            )

        errors = exc_info.value.errors()
        assert any("receiver_id" in str(error["loc"]) for error in errors)

    def test_message_create_missing_required_fields(self):
        """Test that missing required fields raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate()

        errors = exc_info.value.errors()
        assert len(errors) >= 2  # receiver_id and content

    def test_message_create_with_long_content(self):
        """Test that content longer than 5000 characters raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                receiver_id=uuid.uuid4(),
                content="x" * 5001,
            )

        errors = exc_info.value.errors()
        assert any("content" in str(error["loc"]) for error in errors)

    def test_message_create_trims_whitespace(self):
        """Test that content is trimmed."""
        message_data = {
            "receiver_id": uuid.uuid4(),
            "content": "  Hello world  ",
        }
        message = MessageCreate(**message_data)

        assert message.content == "Hello world"

    def test_message_create_with_context(self):
        """Test creating message with context fields."""
        message_data = {
            "receiver_id": uuid.uuid4(),
            "content": "About this offspring",
            "context_type": "offspring",
            "context_id": uuid.uuid4(),
        }
        message = MessageCreate(**message_data)

        assert message.context_type == "offspring"
        assert message.context_id is not None


class TestMessageResponseSchema:
    """Test MessageResponse schema."""

    def test_message_response_with_full_data(self):
        """Test message response with all fields."""
        response_data = {
            "id": uuid.uuid4(),
            "sender_id": uuid.uuid4(),
            "receiver_id": uuid.uuid4(),
            "thread_id": uuid.uuid4(),
            "content": "Test message",
            "is_read": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "sender_name": "John Doe",
            "sender_email": "john@example.com",
        }
        response = MessageResponse(**response_data)

        assert response.sender_name == "John Doe"
        assert response.is_read is True
        assert response.content == "Test message"

    def test_message_response_with_null_optional_fields(self):
        """Test message response with null optional fields."""
        response_data = {
            "id": uuid.uuid4(),
            "sender_id": uuid.uuid4(),
            "receiver_id": uuid.uuid4(),
            "thread_id": uuid.uuid4(),
            "content": "Test",
            "is_read": False,
            "created_at": datetime.utcnow(),
            "updated_at": None,
            "sender_name": None,
            "sender_email": None,
            "context_type": None,
            "context_id": None,
            "read_at": None,
        }
        response = MessageResponse(**response_data)

        assert response.sender_name is None
        assert response.read_at is None


class TestMessageListItemSchema:
    """Test MessageListItem schema."""

    def test_message_list_item_with_preview(self):
        """Test message list item with content preview."""
        item_data = {
            "id": uuid.uuid4(),
            "sender_id": uuid.uuid4(),
            "receiver_id": uuid.uuid4(),
            "thread_id": uuid.uuid4(),
            "content_preview": "This is a preview...",
            "is_read": False,
            "created_at": datetime.utcnow(),
        }
        item = MessageListItem(**item_data)

        assert item.content_preview == "This is a preview..."
        assert item.is_read is False

    def test_message_list_item_without_optional_fields(self):
        """Test message list item without optional fields."""
        item_data = {
            "id": uuid.uuid4(),
            "sender_id": uuid.uuid4(),
            "receiver_id": uuid.uuid4(),
            "thread_id": uuid.uuid4(),
            "content_preview": "Preview",
            "is_read": True,
            "created_at": datetime.utcnow(),
        }
        item = MessageListItem(**item_data)

        assert item.sender_name is None
        assert item.receiver_name is None


class TestMessageListResponseSchema:
    """Test MessageListResponse schema."""

    def test_message_list_response_with_messages(self):
        """Test message list response with multiple messages."""
        response_data = {
            "messages": [
                {
                    "id": uuid.uuid4(),
                    "sender_id": uuid.uuid4(),
                    "receiver_id": uuid.uuid4(),
                    "thread_id": uuid.uuid4(),
                    "content_preview": "Preview 1",
                    "is_read": False,
                    "created_at": datetime.utcnow(),
                },
                {
                    "id": uuid.uuid4(),
                    "sender_id": uuid.uuid4(),
                    "receiver_id": uuid.uuid4(),
                    "thread_id": uuid.uuid4(),
                    "content_preview": "Preview 2",
                    "is_read": True,
                    "created_at": datetime.utcnow(),
                },
            ],
            "total": 2,
            "unread_count": 1,
            "limit": 20,
            "offset": 0,
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
            "offset": 0,
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
        assert response.message == "Message sent successfully"

    def test_message_send_response_custom_message(self):
        """Test message send response with custom message."""
        response = MessageSendResponse(
            success=True,
            message="Custom success message"
        )

        assert response.success is True
        assert response.message == "Custom success message"
