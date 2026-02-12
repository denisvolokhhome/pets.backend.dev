"""Integration tests for message endpoints."""
import uuid
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.user import User


class TestSendMessageEndpoint:
    """Test POST /api/messages/send endpoint (public)."""
    
    @pytest.mark.asyncio
    async def test_send_message_success(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test successfully sending a message to a breeder."""
        message_data = {
            "breeder_id": str(test_user.id),
            "sender_name": "John Doe",
            "sender_email": "john@example.com",
            "message": "I'm interested in your puppies"
        }
        
        response = await unauthenticated_client.post(
            "/api/messages/send",
            json=message_data
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "sent to the breeder" in data["message"]
        
        # Verify message was created in database
        query = select(Message).where(Message.breeder_id == test_user.id)
        result = await async_session.execute(query)
        messages = result.scalars().all()
        
        assert len(messages) == 1
        assert messages[0].sender_name == "John Doe"
        assert messages[0].sender_email == "john@example.com"
        assert messages[0].message == "I'm interested in your puppies"
        assert messages[0].is_read is False
    
    @pytest.mark.asyncio
    async def test_send_message_without_message_text(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test sending a message without message text (optional field)."""
        message_data = {
            "breeder_id": str(test_user.id),
            "sender_name": "Jane Smith",
            "sender_email": "jane@example.com"
        }
        
        response = await unauthenticated_client.post(
            "/api/messages/send",
            json=message_data
        )
        
        assert response.status_code == 201
        
        # Verify message was created
        query = select(Message).where(Message.breeder_id == test_user.id)
        result = await async_session.execute(query)
        message = result.scalar_one()
        
        assert message.sender_name == "Jane Smith"
        assert message.message is None
    
    @pytest.mark.asyncio
    async def test_send_message_to_nonexistent_breeder(
        self,
        unauthenticated_client: AsyncClient
    ):
        """Test sending message to non-existent breeder returns 404."""
        fake_breeder_id = str(uuid.uuid4())
        message_data = {
            "breeder_id": fake_breeder_id,
            "sender_name": "John Doe",
            "sender_email": "john@example.com",
            "message": "Test message"
        }
        
        response = await unauthenticated_client.post(
            "/api/messages/send",
            json=message_data
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_send_message_with_invalid_email(
        self,
        unauthenticated_client: AsyncClient,
        test_user: User
    ):
        """Test sending message with invalid email returns 422."""
        message_data = {
            "breeder_id": str(test_user.id),
            "sender_name": "John Doe",
            "sender_email": "not-an-email",
            "message": "Test message"
        }
        
        response = await unauthenticated_client.post(
            "/api/messages/send",
            json=message_data
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_send_message_with_short_name(
        self,
        unauthenticated_client: AsyncClient,
        test_user: User
    ):
        """Test sending message with name shorter than 2 characters returns 422."""
        message_data = {
            "breeder_id": str(test_user.id),
            "sender_name": "J",
            "sender_email": "john@example.com",
            "message": "Test message"
        }
        
        response = await unauthenticated_client.post(
            "/api/messages/send",
            json=message_data
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_send_message_with_long_message(
        self,
        unauthenticated_client: AsyncClient,
        test_user: User
    ):
        """Test sending message longer than 2000 characters returns 422."""
        message_data = {
            "breeder_id": str(test_user.id),
            "sender_name": "John Doe",
            "sender_email": "john@example.com",
            "message": "x" * 2001
        }
        
        response = await unauthenticated_client.post(
            "/api/messages/send",
            json=message_data
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_send_message_missing_required_fields(
        self,
        unauthenticated_client: AsyncClient,
        test_user: User
    ):
        """Test sending message with missing required fields returns 422."""
        message_data = {
            "breeder_id": str(test_user.id),
            "sender_name": "John Doe"
            # Missing sender_email
        }
        
        response = await unauthenticated_client.post(
            "/api/messages/send",
            json=message_data
        )
        
        assert response.status_code == 422


class TestListMessagesEndpoint:
    """Test GET /api/messages/ endpoint (protected)."""
    
    @pytest.mark.asyncio
    async def test_list_messages_success(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test listing messages for authenticated breeder."""
        # Create test messages
        message1 = Message(
            breeder_id=test_user.id,
            sender_name="User 1",
            sender_email="user1@example.com",
            message="Message 1",
            is_read=False
        )
        message2 = Message(
            breeder_id=test_user.id,
            sender_name="User 2",
            sender_email="user2@example.com",
            message="Message 2",
            is_read=True
        )
        async_session.add_all([message1, message2])
        await async_session.commit()
        
        response = await async_client.get("/api/messages/")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 2
        assert data["total"] == 2
        assert data["unread_count"] == 1
        assert data["limit"] == 20
        assert data["offset"] == 0
    
    @pytest.mark.asyncio
    async def test_list_messages_filter_unread(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test filtering messages by unread status."""
        # Create mix of read and unread messages
        message1 = Message(
            breeder_id=test_user.id,
            sender_name="User 1",
            sender_email="user1@example.com",
            message="Unread message",
            is_read=False
        )
        message2 = Message(
            breeder_id=test_user.id,
            sender_name="User 2",
            sender_email="user2@example.com",
            message="Read message",
            is_read=True
        )
        async_session.add_all([message1, message2])
        await async_session.commit()
        
        response = await async_client.get("/api/messages/?status=unread")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["is_read"] is False
    
    @pytest.mark.asyncio
    async def test_list_messages_filter_read(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test filtering messages by read status."""
        # Create mix of read and unread messages
        message1 = Message(
            breeder_id=test_user.id,
            sender_name="User 1",
            sender_email="user1@example.com",
            message="Unread message",
            is_read=False
        )
        message2 = Message(
            breeder_id=test_user.id,
            sender_name="User 2",
            sender_email="user2@example.com",
            message="Read message",
            is_read=True
        )
        async_session.add_all([message1, message2])
        await async_session.commit()
        
        response = await async_client.get("/api/messages/?status=read")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["is_read"] is True
    
    @pytest.mark.asyncio
    async def test_list_messages_pagination(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test pagination of messages."""
        # Create 25 messages
        messages = [
            Message(
                breeder_id=test_user.id,
                sender_name=f"User {i}",
                sender_email=f"user{i}@example.com",
                message=f"Message {i}"
            )
            for i in range(25)
        ]
        async_session.add_all(messages)
        await async_session.commit()
        
        # Get first page (default limit 20)
        response = await async_client.get("/api/messages/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 20
        assert data["total"] == 25
        
        # Get second page
        response = await async_client.get("/api/messages/?skip=20&limit=20")
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 5
        assert data["total"] == 25
    
    @pytest.mark.asyncio
    async def test_list_messages_sort_newest(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test sorting messages by newest first."""
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
        
        response = await async_client.get("/api/messages/?sort=newest")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 2
        # Newest should be first
        assert "Second message" in (data["messages"][0]["message_preview"] or "")
    
    @pytest.mark.asyncio
    async def test_list_messages_sort_oldest(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test sorting messages by oldest first."""
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
        
        response = await async_client.get("/api/messages/?sort=oldest")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 2
        # Oldest should be first
        assert "First message" in (data["messages"][0]["message_preview"] or "")
    
    @pytest.mark.asyncio
    async def test_list_messages_preview_truncation(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test that message preview is truncated to 100 characters."""
        long_message = "x" * 150
        message = Message(
            breeder_id=test_user.id,
            sender_name="User 1",
            sender_email="user1@example.com",
            message=long_message
        )
        async_session.add(message)
        await async_session.commit()
        
        response = await async_client.get("/api/messages/")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1
        preview = data["messages"][0]["message_preview"]
        assert len(preview) == 103  # 100 chars + "..."
        assert preview.endswith("...")
    
    @pytest.mark.asyncio
    async def test_list_messages_empty(
        self,
        async_client: AsyncClient
    ):
        """Test listing messages when there are none."""
        response = await async_client.get("/api/messages/")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 0
        assert data["total"] == 0
        assert data["unread_count"] == 0
    
    @pytest.mark.asyncio
    async def test_list_messages_only_own_messages(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test that breeder only sees their own messages."""
        # Create another user
        other_user = User(
            email="other@example.com",
            hashed_password="hashed_password",
            name="Other User",
            is_active=True,
            is_superuser=False,
            is_verified=False
        )
        async_session.add(other_user)
        await async_session.commit()
        await async_session.refresh(other_user)
        
        # Create messages for both users
        message1 = Message(
            breeder_id=test_user.id,
            sender_name="User 1",
            sender_email="user1@example.com",
            message="Message for test user"
        )
        message2 = Message(
            breeder_id=other_user.id,
            sender_name="User 2",
            sender_email="user2@example.com",
            message="Message for other user"
        )
        async_session.add_all([message1, message2])
        await async_session.commit()
        
        # Test user should only see their own message
        response = await async_client.get("/api/messages/")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["sender_name"] == "User 1"


class TestGetUnreadCountEndpoint:
    """Test GET /api/messages/unread-count endpoint (protected)."""
    
    @pytest.mark.asyncio
    async def test_get_unread_count_success(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test getting unread message count."""
        # Create mix of read and unread messages
        message1 = Message(
            breeder_id=test_user.id,
            sender_name="User 1",
            sender_email="user1@example.com",
            message="Unread 1",
            is_read=False
        )
        message2 = Message(
            breeder_id=test_user.id,
            sender_name="User 2",
            sender_email="user2@example.com",
            message="Read",
            is_read=True
        )
        message3 = Message(
            breeder_id=test_user.id,
            sender_name="User 3",
            sender_email="user3@example.com",
            message="Unread 2",
            is_read=False
        )
        async_session.add_all([message1, message2, message3])
        await async_session.commit()
        
        response = await async_client.get("/api/messages/unread-count")
        
        assert response.status_code == 200
        data = response.json()
        assert data["unread_count"] == 2
    
    @pytest.mark.asyncio
    async def test_get_unread_count_zero(
        self,
        async_client: AsyncClient
    ):
        """Test getting unread count when there are no messages."""
        response = await async_client.get("/api/messages/unread-count")
        
        assert response.status_code == 200
        data = response.json()
        assert data["unread_count"] == 0


class TestGetMessageEndpoint:
    """Test GET /api/messages/{message_id} endpoint (protected)."""
    
    @pytest.mark.asyncio
    async def test_get_message_success(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test getting a single message."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="John Doe",
            sender_email="john@example.com",
            message="Test message",
            is_read=False
        )
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        response = await async_client.get(f"/api/messages/{message.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(message.id)
        assert data["sender_name"] == "John Doe"
        assert data["sender_email"] == "john@example.com"
        assert data["message"] == "Test message"
        assert data["is_read"] is False
    
    @pytest.mark.asyncio
    async def test_get_message_not_found(
        self,
        async_client: AsyncClient
    ):
        """Test getting non-existent message returns 404."""
        fake_id = uuid.uuid4()
        response = await async_client.get(f"/api/messages/{fake_id}")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_message_unauthorized_access(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession
    ):
        """Test that breeder cannot access another breeder's message."""
        # Create another user
        other_user = User(
            email="other@example.com",
            hashed_password="hashed_password",
            name="Other User",
            is_active=True,
            is_superuser=False,
            is_verified=False
        )
        async_session.add(other_user)
        await async_session.commit()
        await async_session.refresh(other_user)
        
        # Create message for other user
        message = Message(
            breeder_id=other_user.id,
            sender_name="John Doe",
            sender_email="john@example.com",
            message="Test message"
        )
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        # Try to access with test_user (should fail)
        response = await async_client.get(f"/api/messages/{message.id}")
        
        assert response.status_code == 404


class TestMarkMessageAsReadEndpoint:
    """Test PATCH /api/messages/{message_id}/read endpoint (protected)."""
    
    @pytest.mark.asyncio
    async def test_mark_message_as_read_success(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test marking a message as read."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="John Doe",
            sender_email="john@example.com",
            message="Test message",
            is_read=False
        )
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        response = await async_client.patch(f"/api/messages/{message.id}/read")
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_read"] is True
        
        # Verify in database
        await async_session.refresh(message)
        assert message.is_read is True
    
    @pytest.mark.asyncio
    async def test_mark_already_read_message(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test marking an already-read message (idempotent)."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="John Doe",
            sender_email="john@example.com",
            message="Test message",
            is_read=True
        )
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        response = await async_client.patch(f"/api/messages/{message.id}/read")
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_read"] is True
    
    @pytest.mark.asyncio
    async def test_mark_message_as_read_not_found(
        self,
        async_client: AsyncClient
    ):
        """Test marking non-existent message returns 404."""
        fake_id = uuid.uuid4()
        response = await async_client.patch(f"/api/messages/{fake_id}/read")
        
        assert response.status_code == 404


class TestRespondToMessageEndpoint:
    """Test POST /api/messages/{message_id}/respond endpoint (protected)."""
    
    @pytest.mark.asyncio
    async def test_respond_to_message_success(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test responding to a message."""
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
        
        response_data = {
            "response_text": "Thank you for your interest!"
        }
        
        response = await async_client.post(
            f"/api/messages/{message.id}/respond",
            json=response_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["response_text"] == "Thank you for your interest!"
        assert data["responded_at"] is not None
        assert data["is_read"] is True  # Auto-marked as read
        
        # Verify in database
        await async_session.refresh(message)
        assert message.response_text == "Thank you for your interest!"
        assert message.responded_at is not None
        assert message.is_read is True
    
    @pytest.mark.asyncio
    async def test_respond_to_message_with_empty_text(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test responding with empty text returns 422."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="John Doe",
            sender_email="john@example.com",
            message="Test message"
        )
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        response_data = {
            "response_text": ""
        }
        
        response = await async_client.post(
            f"/api/messages/{message.id}/respond",
            json=response_data
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_respond_to_message_with_long_text(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test responding with text longer than 5000 characters returns 422."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="John Doe",
            sender_email="john@example.com",
            message="Test message"
        )
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        response_data = {
            "response_text": "x" * 5001
        }
        
        response = await async_client.post(
            f"/api/messages/{message.id}/respond",
            json=response_data
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_respond_to_message_not_found(
        self,
        async_client: AsyncClient
    ):
        """Test responding to non-existent message returns 404."""
        fake_id = uuid.uuid4()
        response_data = {
            "response_text": "Thank you!"
        }
        
        response = await async_client.post(
            f"/api/messages/{fake_id}/respond",
            json=response_data
        )
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_update_existing_response(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """Test updating an existing response."""
        message = Message(
            breeder_id=test_user.id,
            sender_name="John Doe",
            sender_email="john@example.com",
            message="Test message",
            response_text="Original response",
            responded_at=datetime.utcnow()
        )
        async_session.add(message)
        await async_session.commit()
        await async_session.refresh(message)
        
        response_data = {
            "response_text": "Updated response"
        }
        
        response = await async_client.post(
            f"/api/messages/{message.id}/respond",
            json=response_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["response_text"] == "Updated response"
        
        # Verify in database
        await async_session.refresh(message)
        assert message.response_text == "Updated response"
