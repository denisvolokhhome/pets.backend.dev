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
