"""Unit tests for Message model (pure unit tests, no DB)."""
import uuid
from datetime import datetime

import pytest

from app.models.message import Message


class TestMessageModel:
    """Test Message model Python-side logic without database."""

    def _make_message(self, **overrides):
        """Create a Message instance with sensible defaults."""
        defaults = {
            "id": uuid.uuid4(),
            "sender_id": uuid.uuid4(),
            "receiver_id": uuid.uuid4(),
            "thread_id": uuid.uuid4(),
            "content": "Test message",
            "is_read": False,
            "created_at": datetime.utcnow(),
            "read_at": None,
            "deleted_at": None,
            "updated_at": None,
            "context_type": None,
            "context_id": None,
        }
        defaults.update(overrides)
        return Message(**defaults)

    def test_create_message(self):
        """Test creating a message with all required fields."""
        sender_id = uuid.uuid4()
        receiver_id = uuid.uuid4()
        thread_id = uuid.uuid4()

        msg = self._make_message(
            sender_id=sender_id,
            receiver_id=receiver_id,
            thread_id=thread_id,
            content="I'm interested in your puppies",
        )

        assert msg.sender_id == sender_id
        assert msg.receiver_id == receiver_id
        assert msg.thread_id == thread_id
        assert msg.content == "I'm interested in your puppies"
        assert msg.is_read is False

    def test_message_defaults(self):
        """Test message default values for optional fields."""
        msg = self._make_message()

        assert msg.is_read is False
        assert msg.read_at is None
        assert msg.deleted_at is None
        assert msg.updated_at is None
        assert msg.context_type is None
        assert msg.context_id is None

    def test_mark_message_as_read(self):
        """Test mark_as_read sets is_read and read_at."""
        msg = self._make_message(is_read=False, read_at=None)

        msg.mark_as_read()

        assert msg.is_read is True
        assert msg.read_at is not None
        assert isinstance(msg.read_at, datetime)

    def test_mark_already_read_message(self):
        """Test mark_as_read is idempotent."""
        original_read_at = datetime(2024, 1, 1, 12, 0, 0)
        msg = self._make_message(is_read=True, read_at=original_read_at)

        msg.mark_as_read()

        assert msg.is_read is True
        assert msg.read_at == original_read_at

    def test_soft_delete(self):
        """Test soft_delete sets deleted_at."""
        msg = self._make_message()
        assert msg.is_deleted is False

        msg.soft_delete()

        assert msg.deleted_at is not None
        assert isinstance(msg.deleted_at, datetime)
        assert msg.is_deleted is True

    def test_is_deleted_property(self):
        """Test is_deleted property."""
        msg = self._make_message()
        assert msg.is_deleted is False

        msg.deleted_at = datetime.utcnow()
        assert msg.is_deleted is True

    def test_message_repr(self):
        """Test message string representation."""
        msg_id = uuid.uuid4()
        sender_id = uuid.uuid4()
        receiver_id = uuid.uuid4()
        thread_id = uuid.uuid4()

        msg = self._make_message(
            id=msg_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            thread_id=thread_id,
        )

        repr_str = repr(msg)
        assert "Message" in repr_str
        assert str(msg_id) in repr_str
        assert str(sender_id) in repr_str
        assert str(receiver_id) in repr_str
        assert str(thread_id) in repr_str

    def test_message_with_context(self):
        """Test message with context fields."""
        context_id = uuid.uuid4()
        msg = self._make_message(
            context_type="offspring",
            context_id=context_id,
        )

        assert msg.context_type == "offspring"
        assert msg.context_id == context_id
