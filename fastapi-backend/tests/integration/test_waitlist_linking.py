"""Manual waitlist entries link to accounts by email; notifications are wired."""
import asyncio
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

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


@pytest.mark.asyncio
async def test_linking_links_at_most_one_entry_per_breeder(async_session, test_breeder, sent_emails):
    # Two unlinked entries for one breeder with the same email (legacy data / case variants).
    for email in ("jane@example.com", "Jane@Example.com"):
        async_session.add(WaitlistEntry(breeder_id=test_breeder.id, source="manual", contact_name="Jane",
                                        contact_email=email, status="active", sex_preference="Any",
                                        deposit_status="none", queue_date=TODAY))
    await async_session.commit()
    jane = await _user(async_session, "jane@example.com")
    # The login hook's session (app.database.async_session_maker) has autoflush=False; mirror it,
    # since the default test session autoflushes and would mask the bug.
    hook_maker = async_sessionmaker(async_session.bind, expire_on_commit=False, autoflush=False)
    async with hook_maker() as hook_session:
        assert await svc.link_by_email(hook_session, jane) == 1
    entries = (await async_session.execute(
        select(WaitlistEntry).execution_options(populate_existing=True))).scalars().all()
    assert sorted(e.user_id is None for e in entries) == [False, True]
    lists = await svc.list_breeder(async_session, test_breeder)
    assert sum(e.possible_duplicate for e in lists.general) == 1


# ── account hooks: only verified emails are linked ───────────────────────

@pytest.fixture
def hook_sessions(async_session, monkeypatch):
    """Point the hooks' own session factory at the test database and turn the flag on."""
    from app import database, dependencies
    monkeypatch.setattr(database, "async_session_maker",
                        async_sessionmaker(async_session.bind, expire_on_commit=False, autoflush=False))
    monkeypatch.setattr(dependencies.settings, "enable_waitlist", True)


def _manager(async_session):
    from fastapi_users.db import SQLAlchemyUserDatabase

    from app import dependencies
    from app.services.user_manager import UserManager
    return UserManager(SQLAlchemyUserDatabase(async_session, User), dependencies.settings)


async def _linked_user_id(db):
    entry = (await db.execute(
        select(WaitlistEntry).execution_options(populate_existing=True))).scalar_one()
    return entry.user_id


@pytest.mark.asyncio
async def test_unverified_login_does_not_link_until_email_verified(
        async_session, test_breeder, sent_emails, hook_sessions, monkeypatch):
    from app.services.user_manager import UserManager
    await svc.add_manual(async_session, test_breeder, ManualEntryCreate(
        contact_name="Jane", contact_email="jane@example.com"), TODAY)
    jane = await _user(async_session, "jane@example.com")  # is_verified defaults to False
    manager = _manager(async_session)
    await manager.on_after_login(jane)
    assert await _linked_user_id(async_session) is None

    tokens = []

    async def capture(self, user, token, request=None):
        tokens.append(token)

    monkeypatch.setattr(UserManager, "on_after_request_verify", capture)
    await manager.request_verify(jane)
    verified = await manager.verify(tokens[0])
    assert verified.is_verified
    assert await _linked_user_id(async_session) == jane.id


def _google(email, oauth_id="g-123"):
    from unittest.mock import AsyncMock, MagicMock

    from app.config import Settings
    settings = Settings(google_oauth_client_id="id", google_oauth_client_secret="secret",
                        google_oauth_redirect_uri="http://test/api/auth/google/callback")
    oauth = MagicMock()
    oauth.get_access_token = AsyncMock(return_value={"access_token": "tok"})
    userinfo = MagicMock()
    userinfo.json.return_value = {"email": email, "id": oauth_id}
    http = MagicMock()
    http.get = AsyncMock(return_value=userinfo)
    http_cls = MagicMock()
    http_cls.return_value.__aenter__ = AsyncMock(return_value=http)
    http_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return settings, oauth, http_cls


@pytest.mark.asyncio
async def test_google_sign_in_of_existing_user_links_entries(
        unauthenticated_client, async_session, test_breeder, test_pet_seeker, sent_emails, hook_sessions):
    from unittest.mock import patch
    await svc.add_manual(async_session, test_breeder, ManualEntryCreate(
        contact_name="Pat", contact_email=test_pet_seeker.email), TODAY)
    settings, oauth, http_cls = _google(test_pet_seeker.email)
    with patch("app.routers.auth.settings", settings), patch("app.routers.auth.google_oauth_client", oauth), \
            patch("httpx.AsyncClient", http_cls):
        r = await unauthenticated_client.get("/api/auth/google/callback?code=c", follow_redirects=False)
    assert "/auth/callback?token=" in r.headers["location"]
    assert await _linked_user_id(async_session) == test_pet_seeker.id


@pytest.mark.asyncio
async def test_google_sign_up_links_entries(
        unauthenticated_client, async_session, test_breeder, sent_emails, hook_sessions):
    from unittest.mock import patch
    await svc.add_manual(async_session, test_breeder, ManualEntryCreate(
        contact_name="New", contact_email="new.google@example.com"), TODAY)
    settings, oauth, http_cls = _google("new.google@example.com")
    with patch("app.routers.auth.settings", settings), patch("app.routers.auth.google_oauth_client", oauth), \
            patch("httpx.AsyncClient", http_cls):
        r = await unauthenticated_client.get("/api/auth/google/callback?code=c", follow_redirects=False)
    assert "/auth/callback?token=" in r.headers["location"]
    new_user = (await async_session.execute(
        select(User).where(User.email == "new.google@example.com"))).scalar_one()
    assert new_user.is_verified
    assert await _linked_user_id(async_session) == new_user.id
