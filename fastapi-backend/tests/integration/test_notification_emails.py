"""In-app notifications for messages/favorites are also emailed (the settings page promises it)."""
import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.notification import NotificationCreate
from app.services import email_service as email_module
from app.services.notification_service import notification_service


@pytest.fixture
def sent_emails(monkeypatch):
    sent = []

    async def fake_send_email(self, to, subject, html, text=None):
        sent.append({"to": to, "subject": subject, "html": html, "text": text})
        return True

    monkeypatch.setattr(email_module.EmailService, "send_email", fake_send_email)
    return sent


@pytest.mark.asyncio
async def test_message_notification_sends_email(async_session: AsyncSession, test_breeder: User, sent_emails):
    await notification_service.create_notification(async_session, NotificationCreate(
        user_id=test_breeder.id,
        type="message_received",
        title="New message about offspring",
        message='Marcus <script>alert(1)</script> sent you a message about Honey',
        related_id=uuid.uuid4(),
        related_type="message",
    ))
    await asyncio.sleep(0.1)  # email is sent in a background task

    assert len(sent_emails) == 1
    email = sent_emails[0]
    assert email["to"] == test_breeder.email
    assert "New message" in email["subject"]
    assert "/messages?messageId=" in email["html"]
    # user-supplied text is escaped, never injected as HTML
    assert "<script>" not in email["html"]
    assert "&lt;script&gt;" in email["html"]


@pytest.mark.asyncio
async def test_other_notification_types_do_not_email(async_session: AsyncSession, test_breeder: User, sent_emails):
    await notification_service.create_notification(async_session, NotificationCreate(
        user_id=test_breeder.id,
        type="account_type_changed",
        title="Account updated",
        message="Your account type changed",
    ))
    await asyncio.sleep(0.1)
    assert sent_emails == []


@pytest.mark.asyncio
async def test_reply_via_respond_endpoint_notifies_and_emails(unauthenticated_client, async_session: AsyncSession,
                                                             test_breeder: User, test_pet_seeker: User, sent_emails):
    """Replies sent from the older message page used to skip the notification entirely."""
    from sqlalchemy import select
    from app.models.message import Message
    from app.models.notification import Notification
    first = Message(sender_id=test_pet_seeker.id, receiver_id=test_breeder.id, thread_id=uuid.uuid4(),
                    content="Hi, is Rosie still available?", is_read=False)
    async_session.add(first)
    await async_session.commit()
    r = await unauthenticated_client.post("/api/auth/jwt/login",
                                          data={"username": test_breeder.email, "password": "testpass123"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = await unauthenticated_client.post(f"/api/messages/{first.id}/respond",
                                          json={"response_text": "Yes she is!"}, headers=headers)
    assert r.status_code == 201, r.text
    await asyncio.sleep(0.1)
    notes = (await async_session.execute(
        select(Notification).where(Notification.user_id == test_pet_seeker.id))).scalars().all()
    assert [n.type for n in notes] == ["message_received"]
    assert [e["to"] for e in sent_emails] == [test_pet_seeker.email]
