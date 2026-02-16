"""Integration tests for guest-to-account conversion flow."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.user import User


class TestGuestToAccountFlow:
    """Test complete guest-to-account conversion flow."""
    
    @pytest.mark.asyncio
    async def test_complete_guest_to_account_flow(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test complete flow: guest sends message → account creation → message linking.
        
        Requirements: 7.1, 7.4, 8.1, 9.1, 9.3
        """
        # Step 1: Guest sends a message to breeder
        guest_email = "guest@example.com"
        guest_name = "Guest User"
        message_text = "I'm interested in your puppies"
        
        message_data = {
            "breeder_id": str(test_user.id),
            "sender_name": guest_name,
            "sender_email": guest_email,
            "message": message_text
        }
        
        response = await unauthenticated_client.post(
            "/api/messages/send",
            json=message_data
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        
        # Verify message was created without pet_seeker_id
        query = select(Message).where(Message.sender_email == guest_email)
        result = await async_session.execute(query)
        guest_message = result.scalar_one()
        
        assert guest_message.sender_name == guest_name
        assert guest_message.sender_email == guest_email
        assert guest_message.message == message_text
        assert guest_message.pet_seeker_id is None
        
        # Step 2: Guest creates account using same email
        registration_data = {
            "email": guest_email,
            "password": "SecurePassword123!",
            "name": "Guest User Account"
        }
        
        response = await unauthenticated_client.post(
            "/api/auth/register/from-message",
            json=registration_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == guest_email
        assert data["user"]["is_breeder"] is False
        assert data["linked_messages_count"] == 1
        
        # Step 3: Verify message is now linked to account
        await async_session.refresh(guest_message)
        assert guest_message.pet_seeker_id is not None
        
        # Verify the linked user is the newly created account
        query = select(User).where(User.email == guest_email)
        result = await async_session.execute(query)
        pet_seeker = result.scalar_one()
        
        assert guest_message.pet_seeker_id == pet_seeker.id
        assert pet_seeker.is_breeder is False
        
        # Step 4: Pet seeker can view their messages in dashboard
        # Create authenticated client with the new pet seeker
        from app.dependencies import current_active_user
        from app.database import get_async_session
        from app.main import app
        from httpx import ASGITransport
        
        async def override_get_async_session():
            yield async_session
        
        async def override_current_active_user():
            return pet_seeker
        
        app.dependency_overrides[get_async_session] = override_get_async_session
        app.dependency_overrides[current_active_user] = override_current_active_user
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as authenticated_client:
            response = await authenticated_client.get("/api/messages/")
            
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["messages"]) == 1
            assert data["messages"][0]["sender_email"] == guest_email
            assert data["messages"][0]["message_preview"] == message_text
        
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_multiple_messages_linked_to_account(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that multiple guest messages with same email are all linked.
        
        Requirements: 9.1, 9.2
        """
        guest_email = "multi@example.com"
        
        # Create another breeder for second message
        breeder2 = User(
            email="breeder2@example.com",
            hashed_password="hashed_password",
            name="Breeder Two",
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=True
        )
        async_session.add(breeder2)
        await async_session.commit()
        await async_session.refresh(breeder2)
        
        # Guest sends multiple messages to different breeders
        message1_data = {
            "breeder_id": str(test_user.id),
            "sender_name": "Guest User",
            "sender_email": guest_email,
            "message": "First message"
        }
        
        message2_data = {
            "breeder_id": str(breeder2.id),
            "sender_name": "Guest User",
            "sender_email": guest_email,
            "message": "Second message"
        }
        
        response1 = await unauthenticated_client.post(
            "/api/messages/send",
            json=message1_data
        )
        assert response1.status_code == 201
        
        response2 = await unauthenticated_client.post(
            "/api/messages/send",
            json=message2_data
        )
        assert response2.status_code == 201
        
        # Verify both messages exist without pet_seeker_id
        query = select(Message).where(Message.sender_email == guest_email)
        result = await async_session.execute(query)
        messages = result.scalars().all()
        
        assert len(messages) == 2
        assert all(msg.pet_seeker_id is None for msg in messages)
        
        # Guest creates account
        registration_data = {
            "email": guest_email,
            "password": "SecurePassword123!",
            "name": "Guest User"
        }
        
        response = await unauthenticated_client.post(
            "/api/auth/register/from-message",
            json=registration_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["linked_messages_count"] == 2
        
        # Verify both messages are now linked
        async_session.expire_all()
        query = select(Message).where(Message.sender_email == guest_email)
        result = await async_session.execute(query)
        messages = result.scalars().all()
        
        assert len(messages) == 2
        assert all(msg.pet_seeker_id is not None for msg in messages)
        assert messages[0].pet_seeker_id == messages[1].pet_seeker_id
    
    @pytest.mark.asyncio
    async def test_message_data_preserved_after_linking(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that message content and metadata are preserved during linking.
        
        Requirements: 9.4
        """
        guest_email = "preserve@example.com"
        original_name = "Original Name"
        original_message = "Original message content"
        
        # Guest sends message
        message_data = {
            "breeder_id": str(test_user.id),
            "sender_name": original_name,
            "sender_email": guest_email,
            "message": original_message
        }
        
        response = await unauthenticated_client.post(
            "/api/messages/send",
            json=message_data
        )
        assert response.status_code == 201
        
        # Get original message data
        query = select(Message).where(Message.sender_email == guest_email)
        result = await async_session.execute(query)
        original_msg = result.scalar_one()
        
        original_created_at = original_msg.created_at
        original_breeder_id = original_msg.breeder_id
        
        # Create account
        registration_data = {
            "email": guest_email,
            "password": "SecurePassword123!"
        }
        
        response = await unauthenticated_client.post(
            "/api/auth/register/from-message",
            json=registration_data
        )
        assert response.status_code == 200
        
        # Verify message data is preserved
        await async_session.refresh(original_msg)
        
        assert original_msg.sender_name == original_name
        assert original_msg.sender_email == guest_email
        assert original_msg.message == original_message
        assert original_msg.created_at == original_created_at
        assert original_msg.breeder_id == original_breeder_id
        assert original_msg.pet_seeker_id is not None  # Only this should change
    
    @pytest.mark.asyncio
    async def test_account_creation_without_prior_messages(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Test that account creation works even without prior guest messages.
        
        Requirements: 8.4, 8.5
        """
        new_email = "newuser@example.com"
        
        # Create account without sending any messages first
        registration_data = {
            "email": new_email,
            "password": "SecurePassword123!",
            "name": "New User"
        }
        
        response = await unauthenticated_client.post(
            "/api/auth/register/from-message",
            json=registration_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == new_email
        assert data["user"]["is_breeder"] is False
        assert data["linked_messages_count"] == 0  # No messages to link
        
        # Verify user was created
        query = select(User).where(User.email == new_email)
        result = await async_session.execute(query)
        user = result.scalar_one()
        
        assert user.email == new_email
        assert user.is_breeder is False
    
    @pytest.mark.asyncio
    async def test_only_unlinked_messages_are_linked(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User
    ):
        """
        Test that only messages without pet_seeker_id are linked.
        
        Requirements: 9.1, 9.2
        """
        guest_email = "selective@example.com"
        
        # Create an existing pet seeker
        existing_pet_seeker = User(
            email="existing@example.com",
            hashed_password="hashed_password",
            name="Existing Pet Seeker",
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        async_session.add(existing_pet_seeker)
        await async_session.commit()
        await async_session.refresh(existing_pet_seeker)
        
        # Create one message already linked to existing pet seeker
        linked_message = Message(
            breeder_id=test_user.id,
            sender_name="Guest User",
            sender_email=guest_email,
            message="Already linked message",
            pet_seeker_id=existing_pet_seeker.id
        )
        async_session.add(linked_message)
        await async_session.commit()
        
        # Guest sends a new message with same email
        message_data = {
            "breeder_id": str(test_user.id),
            "sender_name": "Guest User",
            "sender_email": guest_email,
            "message": "New unlinked message"
        }
        
        response = await unauthenticated_client.post(
            "/api/messages/send",
            json=message_data
        )
        assert response.status_code == 201
        
        # New user creates account with same email
        registration_data = {
            "email": guest_email,
            "password": "SecurePassword123!"
        }
        
        response = await unauthenticated_client.post(
            "/api/auth/register/from-message",
            json=registration_data
        )
        
        assert response.status_code == 200
        data = response.json()
        # Should only link the new unlinked message, not the already-linked one
        assert data["linked_messages_count"] == 1
        
        # Verify the already-linked message still points to original pet seeker
        await async_session.refresh(linked_message)
        assert linked_message.pet_seeker_id == existing_pet_seeker.id
        
        # Verify the new message is linked to new account
        query = select(Message).where(
            Message.sender_email == guest_email,
            Message.message == "New unlinked message"
        )
        result = await async_session.execute(query)
        new_message = result.scalar_one()
        
        assert new_message.pet_seeker_id is not None
        assert new_message.pet_seeker_id != existing_pet_seeker.id
