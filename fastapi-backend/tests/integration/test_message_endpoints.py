"""Integration tests for message endpoints."""
import uuid
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.user import User


def _make_db_message(sender_id, receiver_id, content="Test message", is_read=False, thread_id=None):
    """Helper to create a Message with all required fields."""
    return Message(
        id=uuid.uuid4(),
        sender_id=sender_id,
        receiver_id=receiver_id,
        thread_id=thread_id or uuid.uuid4(),
        content=content,
        is_read=is_read,
        created_at=datetime.utcnow(),
    )


class TestListMessagesEndpoint:
    """Test GET /api/messages/ endpoint (protected)."""

    @pytest.mark.asyncio
    async def test_list_messages_success(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        """Test listing messages for authenticated user."""
        other = User(email="other1@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        m1 = _make_db_message(other.id, test_user.id, "Msg 1", is_read=False)
        m2 = _make_db_message(other.id, test_user.id, "Msg 2", is_read=True)
        async_session.add_all([m1, m2])
        await async_session.commit()

        response = await async_client.get("/api/messages/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["unread_count"] == 1

    @pytest.mark.asyncio
    async def test_list_messages_filter_unread(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other2@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        async_session.add_all([
            _make_db_message(other.id, test_user.id, "Unread", is_read=False),
            _make_db_message(other.id, test_user.id, "Read", is_read=True),
        ])
        await async_session.commit()

        response = await async_client.get("/api/messages/?status=unread")
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["is_read"] is False

    @pytest.mark.asyncio
    async def test_list_messages_filter_read(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other3@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        async_session.add_all([
            _make_db_message(other.id, test_user.id, "Unread", is_read=False),
            _make_db_message(other.id, test_user.id, "Read", is_read=True),
        ])
        await async_session.commit()

        response = await async_client.get("/api/messages/?status=read")
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["is_read"] is True

    @pytest.mark.asyncio
    async def test_list_messages_pagination(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other4@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        msgs = [_make_db_message(other.id, test_user.id, f"Msg {i}") for i in range(25)]
        async_session.add_all(msgs)
        await async_session.commit()

        resp1 = await async_client.get("/api/messages/")
        assert resp1.status_code == 200
        assert len(resp1.json()["messages"]) == 20
        assert resp1.json()["total"] == 25

        resp2 = await async_client.get("/api/messages/?skip=20&limit=20")
        assert resp2.status_code == 200
        assert len(resp2.json()["messages"]) == 5

    @pytest.mark.asyncio
    async def test_list_messages_sort_newest(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other5@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        m1 = _make_db_message(other.id, test_user.id, "First message")
        async_session.add(m1)
        await async_session.commit()

        m2 = _make_db_message(other.id, test_user.id, "Second message")
        async_session.add(m2)
        await async_session.commit()

        response = await async_client.get("/api/messages/?sort=newest")
        assert response.status_code == 200
        data = response.json()
        assert "Second message" in data["messages"][0]["content_preview"]

    @pytest.mark.asyncio
    async def test_list_messages_sort_oldest(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other6@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        m1 = _make_db_message(other.id, test_user.id, "First message")
        async_session.add(m1)
        await async_session.commit()

        m2 = _make_db_message(other.id, test_user.id, "Second message")
        async_session.add(m2)
        await async_session.commit()

        response = await async_client.get("/api/messages/?sort=oldest")
        assert response.status_code == 200
        data = response.json()
        assert "First message" in data["messages"][0]["content_preview"]

    @pytest.mark.asyncio
    async def test_list_messages_preview_truncation(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other7@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        m = _make_db_message(other.id, test_user.id, "x" * 150)
        async_session.add(m)
        await async_session.commit()

        response = await async_client.get("/api/messages/")
        assert response.status_code == 200
        preview = response.json()["messages"][0]["content_preview"]
        assert len(preview) == 103  # 100 + "..."
        assert preview.endswith("...")

    @pytest.mark.asyncio
    async def test_list_messages_empty(self, async_client: AsyncClient):
        response = await async_client.get("/api/messages/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["unread_count"] == 0

    @pytest.mark.asyncio
    async def test_list_messages_only_own_messages(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other8@example.com", hashed_password="x", name="Other", is_active=True)
        third = User(email="third@example.com", hashed_password="x", name="Third", is_active=True)
        async_session.add_all([other, third])
        await async_session.commit()
        await async_session.refresh(other)
        await async_session.refresh(third)

        async_session.add_all([
            _make_db_message(other.id, test_user.id, "For test user"),
            _make_db_message(other.id, third.id, "For third user"),
        ])
        await async_session.commit()

        response = await async_client.get("/api/messages/")
        assert response.status_code == 200
        assert response.json()["total"] == 1


class TestGetUnreadCountEndpoint:
    """Test GET /api/messages/unread-count endpoint."""

    @pytest.mark.asyncio
    async def test_get_unread_count_success(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other9@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        async_session.add_all([
            _make_db_message(other.id, test_user.id, "Unread 1", is_read=False),
            _make_db_message(other.id, test_user.id, "Read", is_read=True),
            _make_db_message(other.id, test_user.id, "Unread 2", is_read=False),
        ])
        await async_session.commit()

        response = await async_client.get("/api/messages/unread-count")
        assert response.status_code == 200
        assert response.json()["unread_count"] == 2

    @pytest.mark.asyncio
    async def test_get_unread_count_zero(self, async_client: AsyncClient):
        response = await async_client.get("/api/messages/unread-count")
        assert response.status_code == 200
        assert response.json()["unread_count"] == 0


class TestGetMessageEndpoint:
    """Test GET /api/messages/{message_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_message_success(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other10@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        m = _make_db_message(other.id, test_user.id, "Hello there")
        async_session.add(m)
        await async_session.commit()
        await async_session.refresh(m)

        response = await async_client.get(f"/api/messages/{m.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(m.id)
        assert data["content"] == "Hello there"
        assert data["is_read"] is False

    @pytest.mark.asyncio
    async def test_get_message_not_found(self, async_client: AsyncClient):
        response = await async_client.get(f"/api/messages/{uuid.uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_message_unauthorized_access(
        self, async_client: AsyncClient, async_session: AsyncSession
    ):
        """User cannot access a message they're not part of."""
        u1 = User(email="u1@example.com", hashed_password="x", name="U1", is_active=True)
        u2 = User(email="u2@example.com", hashed_password="x", name="U2", is_active=True)
        async_session.add_all([u1, u2])
        await async_session.commit()
        await async_session.refresh(u1)
        await async_session.refresh(u2)

        m = _make_db_message(u1.id, u2.id, "Private")
        async_session.add(m)
        await async_session.commit()
        await async_session.refresh(m)

        response = await async_client.get(f"/api/messages/{m.id}")
        assert response.status_code == 404


class TestMarkMessageAsReadEndpoint:
    """Test PATCH /api/messages/{message_id}/read endpoint."""

    @pytest.mark.asyncio
    async def test_mark_message_as_read_success(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other11@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        m = _make_db_message(other.id, test_user.id, "Unread msg", is_read=False)
        async_session.add(m)
        await async_session.commit()
        await async_session.refresh(m)

        response = await async_client.patch(f"/api/messages/{m.id}/read")
        assert response.status_code == 200
        assert response.json()["is_read"] is True

    @pytest.mark.asyncio
    async def test_mark_already_read_message(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other12@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        m = _make_db_message(other.id, test_user.id, "Already read", is_read=True)
        async_session.add(m)
        await async_session.commit()
        await async_session.refresh(m)

        response = await async_client.patch(f"/api/messages/{m.id}/read")
        assert response.status_code == 200
        assert response.json()["is_read"] is True

    @pytest.mark.asyncio
    async def test_mark_message_as_read_not_found(self, async_client: AsyncClient):
        response = await async_client.patch(f"/api/messages/{uuid.uuid4()}/read")
        assert response.status_code == 404


class TestRespondToMessageEndpoint:
    """Test POST /api/messages/{message_id}/respond endpoint."""

    @pytest.mark.asyncio
    async def test_respond_to_message_success(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        """Responding creates a new message in the same thread."""
        other = User(email="other13@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        thread_id = uuid.uuid4()
        m = _make_db_message(other.id, test_user.id, "Question?", thread_id=thread_id)
        async_session.add(m)
        await async_session.commit()
        await async_session.refresh(m)

        response = await async_client.post(
            f"/api/messages/{m.id}/respond",
            json={"response_text": "Here's my answer!"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "Here's my answer!"
        assert data["sender_id"] == str(test_user.id)
        assert data["receiver_id"] == str(other.id)
        assert data["thread_id"] == str(thread_id)

    @pytest.mark.asyncio
    async def test_respond_to_message_with_empty_text(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other14@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        m = _make_db_message(other.id, test_user.id, "Q")
        async_session.add(m)
        await async_session.commit()
        await async_session.refresh(m)

        response = await async_client.post(
            f"/api/messages/{m.id}/respond", json={"response_text": ""}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_respond_to_message_with_long_text(
        self, async_client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        other = User(email="other15@example.com", hashed_password="x", name="Other", is_active=True)
        async_session.add(other)
        await async_session.commit()
        await async_session.refresh(other)

        m = _make_db_message(other.id, test_user.id, "Q")
        async_session.add(m)
        await async_session.commit()
        await async_session.refresh(m)

        response = await async_client.post(
            f"/api/messages/{m.id}/respond", json={"response_text": "x" * 5001}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_respond_to_message_not_found(self, async_client: AsyncClient):
        response = await async_client.post(
            f"/api/messages/{uuid.uuid4()}/respond", json={"response_text": "Hi"}
        )
        assert response.status_code == 404
