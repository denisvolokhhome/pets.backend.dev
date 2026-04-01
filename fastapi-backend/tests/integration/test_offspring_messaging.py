"""Integration tests for offspring messaging endpoints."""
import pytest
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.offspring import Offspring
from app.models.message import Message
from app.models.notification import Notification


@pytest.mark.asyncio
async def test_send_offspring_message_creates_thread(
    unauthenticated_client: AsyncClient,
    test_pet_seeker: User,
    test_breeder: User,
    test_offspring: "Offspring",
    async_session: AsyncSession
):
    """Test sending a message about an offspring creates a new thread."""
    # Login as pet seeker
    login_response = await unauthenticated_client.post(
        "/api/auth/jwt/login",
        data={
            "username": test_pet_seeker.email,
            "password": "testpass123"
        }
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Send message about offspring with auth token
    response = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={
            "message": "I'm interested in this puppy. Is it still available?"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["sender_id"] == str(test_pet_seeker.id)
    assert data["receiver_id"] == str(test_breeder.id)
    assert data["context_type"] == "offspring"
    assert data["context_id"] == str(test_offspring.id)
    assert data["thread_id"] is not None
    assert data["content"] == "I'm interested in this puppy. Is it still available?"
    assert data["is_read"] is False


@pytest.mark.asyncio
async def test_send_offspring_message_reuses_thread(
    unauthenticated_client: AsyncClient,
    test_pet_seeker: User,
    test_breeder: User,
    test_offspring: "Offspring",
    async_session: AsyncSession
):
    """Test sending multiple messages reuses the same thread."""
    # Login as pet seeker
    login_response = await unauthenticated_client.post(
        "/api/auth/jwt/login",
        data={
            "username": test_pet_seeker.email,
            "password": "testpass123"
        }
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Send first message
    response1 = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={
            "message": "First message"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response1.status_code == 201
    thread_id_1 = response1.json()["thread_id"]
    
    # Send second message with same thread_id to reuse thread
    response2 = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={
            "message": "Second message",
            "thread_id": thread_id_1
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response2.status_code == 201
    thread_id_2 = response2.json()["thread_id"]
    
    # Both messages should have the same thread_id
    assert thread_id_1 == thread_id_2


@pytest.mark.asyncio
async def test_send_offspring_message_creates_notification(
    unauthenticated_client: AsyncClient,
    test_pet_seeker: User,
    test_breeder: User,
    test_offspring: "Offspring",
    async_session: AsyncSession
):
    """Test sending a message creates a notification for the breeder."""
    # Login as pet seeker
    login_response = await unauthenticated_client.post(
        "/api/auth/jwt/login",
        data={
            "username": test_pet_seeker.email,
            "password": "testpass123"
        }
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Send message
    response = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={
            "message": "Test message"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201
    
    # Check notification was created
    from sqlalchemy import select
    notification_query = select(Notification).where(
        Notification.user_id == test_breeder.id,
        Notification.type == "message_received"
    )
    result = await async_session.execute(notification_query)
    notification = result.scalar_one_or_none()
    
    assert notification is not None
    assert notification.title == "New message about offspring"
    assert notification.is_read is False


@pytest.mark.asyncio
async def test_send_offspring_message_requires_authentication(
    unauthenticated_client: AsyncClient,
    test_offspring: "Offspring"
):
    """Test sending a message requires authentication."""
    response = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={
            "message": "Test message"
        }
    )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_send_offspring_message_invalid_offspring(
    unauthenticated_client: AsyncClient,
    test_pet_seeker: User
):
    """Test sending a message to non-existent offspring returns 404."""
    # Login as pet seeker
    login_response = await unauthenticated_client.post(
        "/api/auth/jwt/login",
        data={
            "username": test_pet_seeker.email,
            "password": "testpass123"
        }
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Send message to non-existent offspring
    fake_id = uuid4()
    response = await unauthenticated_client.post(
        f"/api/messages/offspring/{fake_id}",
        json={
            "message": "Test message"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Offspring not found"


@pytest.mark.asyncio
async def test_send_offspring_message_validates_message(
    unauthenticated_client: AsyncClient,
    test_pet_seeker: User,
    test_offspring: "Offspring"
):
    """Test message validation."""
    # Login as pet seeker
    login_response = await unauthenticated_client.post(
        "/api/auth/jwt/login",
        data={
            "username": test_pet_seeker.email,
            "password": "testpass123"
        }
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Send empty message
    response = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={
            "message": ""
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_thread_messages(
    unauthenticated_client: AsyncClient,
    test_pet_seeker: User,
    test_breeder: User,
    test_offspring: "Offspring",
    async_session: AsyncSession
):
    """Test getting all messages in a thread."""
    # Login as pet seeker
    login_response = await unauthenticated_client.post(
        "/api/auth/jwt/login",
        data={
            "username": test_pet_seeker.email,
            "password": "testpass123"
        }
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Send first message
    response1 = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={
            "message": "First message"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response1.status_code == 201
    thread_id = response1.json()["thread_id"]
    
    # Send second message in same thread
    response2 = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={
            "message": "Second message",
            "thread_id": thread_id
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response2.status_code == 201
    
    # Get thread messages
    response = await unauthenticated_client.get(
        f"/api/messages/threads/{thread_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["thread_id"] == thread_id
    assert data["offspring_id"] == str(test_offspring.id)
    assert len(data["messages"]) == 2
    assert data["messages"][0]["message"] == "First message"
    assert data["messages"][1]["message"] == "Second message"
    assert data["offspring"] is not None


@pytest.mark.asyncio
async def test_get_thread_messages_marks_as_read_for_breeder(
    unauthenticated_client: AsyncClient,
    test_pet_seeker: User,
    test_breeder: User,
    test_offspring: "Offspring",
    async_session: AsyncSession
):
    """Test that breeder viewing thread marks messages as read."""
    # Login as pet seeker and send message
    login_response = await unauthenticated_client.post(
        "/api/auth/jwt/login",
        data={
            "username": test_pet_seeker.email,
            "password": "testpass123"
        }
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    response = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={
            "message": "Test message"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201
    thread_id = response.json()["thread_id"]
    message_id = response.json()["id"]
    
    # Login as breeder
    login_response = await unauthenticated_client.post(
        "/api/auth/jwt/login",
        data={
            "username": test_breeder.email,
            "password": "testpass123"
        }
    )
    assert login_response.status_code == 200
    breeder_token = login_response.json()["access_token"]
    
    # Get thread messages as breeder
    response = await unauthenticated_client.get(
        f"/api/messages/threads/{thread_id}",
        headers={"Authorization": f"Bearer {breeder_token}"}
    )
    assert response.status_code == 200
    
    # Check message is marked as read
    from sqlalchemy import select
    message_query = select(Message).where(Message.id == message_id)
    result = await async_session.execute(message_query)
    message = result.scalar_one()
    
    assert message.is_read is True


@pytest.mark.asyncio
async def test_get_thread_messages_requires_authentication(
    unauthenticated_client: AsyncClient
):
    """Test getting thread messages requires authentication."""
    fake_thread_id = uuid4()
    
    response = await unauthenticated_client.get(f"/api/messages/threads/{fake_thread_id}")
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_thread_messages_requires_participation(
    unauthenticated_client: AsyncClient,
    test_pet_seeker: User,
    test_breeder: User,
    test_offspring: "Offspring",
    async_session: AsyncSession
):
    """Test that only thread participants can access thread messages."""
    # Login as pet seeker and send message
    login_response = await unauthenticated_client.post(
        "/api/auth/jwt/login",
        data={
            "username": test_pet_seeker.email,
            "password": "testpass123"
        }
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    response = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={
            "message": "Test message"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201
    thread_id = response.json()["thread_id"]
    
    # Create another user
    import bcrypt
    from app.models.user import User as UserModel
    
    hashed_password = bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode('utf-8')
    
    other_user = UserModel(
        email="other@example.com",
        hashed_password=hashed_password,
        is_active=True,
        is_verified=True,
        is_breeder=False
    )
    async_session.add(other_user)
    await async_session.commit()
    await async_session.refresh(other_user)
    
    # Login as other user
    login_response = await unauthenticated_client.post(
        "/api/auth/jwt/login",
        data={
            "username": "other@example.com",
            "password": "testpass123"
        }
    )
    assert login_response.status_code == 200
    other_token = login_response.json()["access_token"]
    
    # Try to access thread
    response = await unauthenticated_client.get(
        f"/api/messages/threads/{thread_id}",
        headers={"Authorization": f"Bearer {other_token}"}
    )
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Thread not found or access denied"


@pytest.mark.asyncio
async def test_get_thread_messages_invalid_thread(
    unauthenticated_client: AsyncClient,
    test_pet_seeker: User
):
    """Test getting messages from non-existent thread returns 404."""
    # Login as pet seeker
    login_response = await unauthenticated_client.post(
        "/api/auth/jwt/login",
        data={
            "username": test_pet_seeker.email,
            "password": "testpass123"
        }
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Try to get non-existent thread
    fake_thread_id = uuid4()
    response = await unauthenticated_client.get(
        f"/api/messages/threads/{fake_thread_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Thread not found"
