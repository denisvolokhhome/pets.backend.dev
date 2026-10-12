"""Manual waitlist entries link to accounts by email; notifications are wired."""
import asyncio
from datetime import date

import pytest
from sqlalchemy import select

from app.models.notification import Notification
from app.models.user import User
from app.models.waitlist_entry import WaitlistEntry
from app.schemas.waitlist import ManualEntryCreate, WaitlistRequestCreate
from app.services import email_service as email_module
from app.services.waitlist_service import waitlist_service as svc

TODAY = date(2026, 10, 11)


@pytest.fixture
def sent_emails(monkeypatch):
    sent = []

    async def fake_send_email(self, to, subject, html, text=None):
        sent.append({"to": to, "html": html})
        return True

    monkeypatch.setattr(email_module.EmailService, "send_email", fake_send_email)
    return sent


async def _user(db, email):
    u = User(email=email, hashed_password="x", name="Jane", is_active=True, account_type="pet_seeker")
    db.add(u)
    await db.commit()
    return u


@pytest.mark.asyncio
async def test_linking_ignores_case_and_whitespace(async_session, test_breeder, sent_emails):
    await svc.add_manual(async_session, test_breeder, ManualEntryCreate(
        contact_name="Jane", contact_email="Jane.Doe@Example.com"), TODAY)
    jane = await _user(async_session, "jane.doe@example.com")
    assert await svc.link_by_email(async_session, jane) == 1
    entry = (await async_session.execute(select(WaitlistEntry))).scalar_one()
    assert entry.user_id == jane.id


@pytest.mark.asyncio
async def test_linking_skips_when_seeker_already_on_list(async_session, test_breeder, sent_emails):
    jane = await _user(async_session, "jane@example.com")
    await svc.request_spot(async_session, test_breeder.id, jane, WaitlistRequestCreate(), TODAY)
    # manual entry for the same person can't be created (409), so simulate a pre-existing one
    async_session.add(WaitlistEntry(breeder_id=test_breeder.id, source="manual", contact_name="Jane",
                                    contact_email="jane@example.com", status="active",
                                    sex_preference="Any", deposit_status="none", queue_date=TODAY))
    await async_session.commit()
    assert await svc.link_by_email(async_session, jane) == 0
    lists = await svc.list_breeder(async_session, test_breeder)
    assert any(e.possible_duplicate for e in lists.general)


@pytest.mark.asyncio
async def test_request_notifies_breeder_by_email(async_session, test_breeder, test_pet_seeker, sent_emails):
    test_pet_seeker.account_type = "pet_seeker"
    await async_session.commit()
    await svc.request_spot(async_session, test_breeder.id, test_pet_seeker, WaitlistRequestCreate(), TODAY)
    await asyncio.sleep(0.1)
    notes = (await async_session.execute(select(Notification))).scalars().all()
    assert [n.type for n in notes] == ["waitlist_request"]
    assert sent_emails and "/waitlist" in sent_emails[0]["html"]
