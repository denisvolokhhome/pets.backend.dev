"""Unit tests for Message model."""
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.message import Message
from app.models.user import User


class TestMessageModel:
    """Test Message model functionality."""
    
    @pytest.mark.asyncio
    async def test_create_message(self, async_session, test_user):
        """Test creating a message."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="John Doe",
            sender_email="john@example.com",
            message="I'm interested in your puppies",
            is_read=False
        )
        
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        assert message.id is not None
        assert isinstance(message.id, uuid.UUID)
        assert message.breeder_id == test_user.id
        assert message.sender_name == "John Doe"
        assert message.sender_email == "john@example.com"
        assert message.message == "I'm interested in your puppies"
        assert message.is_read is False
        assert message.response_text is None
        assert message.responded_at is None
        assert message.created_at is not None
        assert isinstance(message.created_at, datetime)
    
    @pytest.mark.asyncio
    async def test_create_message_without_message_text(self, async_session, test_user):
        """Test creating a message without message text (optional field)."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="Jane Smith",
            sender_email="jane@example.com",
            message=None,
            is_read=False
        )
        
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        assert message.id is not None
        assert message.message is None
        assert message.sender_name == "Jane Smith"
    
    @pytest.mark.asyncio
    async def test_message_defaults(self, async_session, test_user):
        """Test message default values."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="Test User",
            sender_email="test@example.com"
        )
        
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        assert message.is_read is False
        assert message.response_text is None
        assert message.responded_at is None
        assert message.created_at is not None
        assert message.updated_at is None
    
    @pytest.mark.asyncio
    async def test_mark_message_as_read(self, async_session, test_user):
        """Test marking a message as read."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="Test User",
            sender_email="test@example.com",
            message="Test message",
            is_read=False
        )
        
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        # Mark as read
        message.is_read = True
        await async_session.commit()
        await async_session.refresh(message)
        
        assert message.is_read is True
    
    @pytest.mark.asyncio
    async def test_add_response_to_message(self, async_session, test_user):
        """Test adding a response to a message."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="Test User",
            sender_email="test@example.com",
            message="Test message",
            is_read=False
        )
        
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        # Add response
        response_time = datetime.utcnow()
        message.response_text = "Thank you for your interest!"
        message.responded_at = response_time
        message.is_read = True
        
        await async_session.commit()
        await async_session.refresh(message)
        
        assert message.response_text == "Thank you for your interest!"
        assert message.responded_at is not None
        assert message.is_read is True
    
    @pytest.mark.asyncio
    async def test_message_breeder_relationship(self, async_session, test_user):
        """Test message relationship with breeder (user)."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="Test User",
            sender_email="test@example.com",
            message="Test message"
        )
        
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        # Access breeder through relationship
        assert message.breeder is not None
        assert message.breeder.id == test_user.id
        assert message.breeder.email == test_user.email
    
    @pytest.mark.asyncio
    async def test_user_messages_relationship(self, async_session, test_user):
        """Test user's messages relationship."""
        # Create multiple messages for the user
        message1 = Message(
            breeder_id=test_user.id,
            sender_name="User 1",
            sender_email="user1@example.com",
            message="Message 1"
        )
        message2 = Message(
            breeder_id=test_user.id,
            sender_name="User 2",
            sender_email="user2@example.com",
            message="Message 2"
        )
        
        async_session.add_all([message1, message2])
        await async_session.commit()
        
        # Refresh user to load messages
        await async_session.refresh(test_user)
        
        # Access messages through user relationship
        assert len(test_user.messages_received) == 2
        assert any(msg.sender_name == "User 1" for msg in test_user.messages_received)
        assert any(msg.sender_name == "User 2" for msg in test_user.messages_received)
    
    @pytest.mark.asyncio
    async def test_message_cascade_delete(self, async_session):
        """Test that messages are deleted when breeder is deleted."""
        # Create a new user
        user = User(
            email="temp@example.com",
            hashed_password="hashed_password",
            name="Temp User",
            is_active=True,
            is_superuser=False,
            is_verified=False
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        
        # Create message for this user
        message = Message(
            breeder_id=user.id,
            sender_name="Test User",
            sender_email="test@example.com",
            message="Test message"
        )
        async_session.add(message)
        await async_session.commit()
        message_id = message.id
        
        # Delete the user
        await async_session.delete(user)
        await async_session.commit()
        
        # Verify message was also deleted (cascade)
        query = select(Message).where(Message.id == message_id)
        result = await async_session.execute(query)
        deleted_message = result.scalar_one_or_none()
        
        assert deleted_message is None
    
    @pytest.mark.asyncio
    async def test_message_repr(self, async_session, test_user):
        """Test message string representation."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="Test User",
            sender_email="test@example.com",
            message="Test message",
            is_read=False
        )
        
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        repr_str = repr(message)
        assert "Message" in repr_str
        assert str(message.id) in repr_str
        assert str(test_user.id) in repr_str
        assert "test@example.com" in repr_str
        assert "False" in repr_str
    
    @pytest.mark.asyncio
    async def test_query_unread_messages(self, async_session, test_user):
        """Test querying unread messages."""
        # Create mix of read and unread messages
        message1 = Message(
            breeder_id=test_user.id,
            sender_name="User 1",
            sender_email="user1@example.com",
            message="Unread message 1",
            is_read=False
        )
        message2 = Message(
            breeder_id=test_user.id,
            sender_name="User 2",
            sender_email="user2@example.com",
            message="Read message",
            is_read=True
        )
        message3 = Message(
            breeder_id=test_user.id,
            sender_name="User 3",
            sender_email="user3@example.com",
            message="Unread message 2",
            is_read=False
        )
        
        async_session.add_all([message1, message2, message3])
        await async_session.commit()
        
        # Query unread messages
        query = select(Message).where(
            Message.breeder_id == test_user.id,
            Message.is_read == False
        )
        result = await async_session.execute(query)
        unread_messages = result.scalars().all()
        
        assert len(unread_messages) == 2
        assert all(msg.is_read is False for msg in unread_messages)
    
    @pytest.mark.asyncio
    async def test_query_responded_messages(self, async_session, test_user):
        """Test querying messages with responses."""
        # Create messages with and without responses
        message1 = Message(
            breeder_id=test_user.id,
            sender_name="User 1",
            sender_email="user1@example.com",
            message="Message 1",
            response_text="Response 1",
            responded_at=datetime.utcnow()
        )
        message2 = Message(
            breeder_id=test_user.id,
            sender_name="User 2",
            sender_email="user2@example.com",
            message="Message 2"
        )
        
        async_session.add_all([message1, message2])
        await async_session.commit()
        
        # Query messages with responses
        query = select(Message).where(
            Message.breeder_id == test_user.id,
            Message.responded_at.isnot(None)
        )
        result = await async_session.execute(query)
        responded_messages = result.scalars().all()
        
        assert len(responded_messages) == 1
        assert responded_messages[0].response_text == "Response 1"
    
    @pytest.mark.asyncio
    async def test_message_ordering_by_created_at(self, async_session, test_user):
        """Test ordering messages by creation date."""
        # Create messages at different times
        message1 = Message(
            breeder_id=test_user.id,
            sender_name="User 1",
            sender_email="user1@example.com",
            message="First message"
        )
        async_session.add(message1)
        await async_session.commit()
        
        message2 = Message(
            breeder_id=test_user.id,
            sender_name="User 2",
            sender_email="user2@example.com",
            message="Second message"
        )
        async_session.add(message2)
        await async_session.commit()
        
        # Query messages ordered by created_at descending (newest first)
        query = select(Message).where(
            Message.breeder_id == test_user.id
        ).order_by(Message.created_at.desc())
        
        result = await async_session.execute(query)
        messages = result.scalars().all()
        
        assert len(messages) == 2
        assert messages[0].message == "Second message"
        assert messages[1].message == "First message"
