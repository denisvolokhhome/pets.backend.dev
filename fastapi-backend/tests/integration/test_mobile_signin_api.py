"""Instant mobile switch: QR code on desktop signs the phone in as the same user."""
import asyncio
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.middleware.rate_limiter import rate_limiter
from app.models.mobile_signin_token import MobileSigninToken
from app.models.user import User
from app.services import mobile_signin_service as ms


async def _auth(client, user):
    r = await client.post("/api/auth/jwt/login", data={"username": user.email, "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _code(created: dict) -> str:
    return created["url"].split("#", 1)[1]


async def _create(client, headers, target="/breeding/5"):
    r = await client.post("/api/auth/mobile-signin/codes", json={"target_path": target}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(autouse=True)
async def _reset_limits():
    rate_limiter.requests.clear()
    yield
    rate_limiter.requests.clear()


@pytest.mark.asyncio
async def test_scan_continue_signs_phone_in(unauthenticated_client, test_breeder):
    c = unauthenticated_client
    desktop = await _auth(c, test_breeder)
    created = await _create(c, desktop)
    assert created["url"].startswith("http") and "/m#" in created["url"] and created["expires_in"] == 120

    # The phone (not signed in) previews: name + masked email only
    r = await c.post("/api/auth/mobile-signin/preview", json={"code": _code(created)})
    assert r.status_code == 200
    p = r.json()
    assert p["same_account"] is False and p["masked_email"] == "b•••@example.com"
    assert test_breeder.email not in r.text
    st = (await c.get(f"/api/auth/mobile-signin/codes/{created['id']}/status", headers=desktop)).json()
    assert st["status"] == "pending"  # preview doesn't use the code

    r = await c.post("/api/auth/mobile-signin/redeem", json={"code": _code(created)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_path"] == "/breeding/5" and body["token_type"] == "bearer"
    me = await c.get("/api/auth/users/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == test_breeder.email
    st = (await c.get(f"/api/auth/mobile-signin/codes/{created['id']}/status", headers=desktop)).json()
    assert st["status"] == "used"


@pytest.mark.asyncio
async def test_code_works_once(unauthenticated_client, test_breeder):
    c = unauthenticated_client
    created = await _create(c, await _auth(c, test_breeder))
    assert (await c.post("/api/auth/mobile-signin/redeem", json={"code": _code(created)})).status_code == 200
    r = await c.post("/api/auth/mobile-signin/redeem", json={"code": _code(created)})
    assert r.status_code == 410 and "Generate a new one" in r.json()["detail"]
    r = await c.post("/api/auth/mobile-signin/preview", json={"code": _code(created)})
    assert r.status_code == 410


@pytest.mark.asyncio
async def test_expired_and_unknown_codes(unauthenticated_client, async_session, test_breeder):
    c = unauthenticated_client
    created = await _create(c, await _auth(c, test_breeder))
    row = await async_session.get(MobileSigninToken, created["id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await async_session.commit()
    assert (await c.post("/api/auth/mobile-signin/redeem", json={"code": _code(created)})).status_code == 410
    assert (await c.post("/api/auth/mobile-signin/redeem", json={"code": "nope"})).status_code == 404
    st = (await c.get(f"/api/auth/mobile-signin/codes/{created['id']}/status",
                      headers=await _auth(c, test_breeder))).json()
    assert st["status"] == "expired"


@pytest.mark.asyncio
async def test_new_code_cancels_previous(unauthenticated_client, test_breeder):
    c = unauthenticated_client
    h = await _auth(c, test_breeder)
    first = await _create(c, h)
    second = await _create(c, h)
    assert (await c.post("/api/auth/mobile-signin/redeem", json={"code": _code(first)})).status_code == 410
    assert (await c.post("/api/auth/mobile-signin/redeem", json={"code": _code(second)})).status_code == 200


@pytest.mark.asyncio
async def test_only_the_hash_is_stored(unauthenticated_client, async_session, test_breeder):
    c = unauthenticated_client
    created = await _create(c, await _auth(c, test_breeder))
    row = await async_session.get(MobileSigninToken, created["id"])
    assert _code(created) not in row.token_hash and len(row.token_hash) == 64


@pytest.mark.asyncio
async def test_phone_already_signed_in_as_same_user_keeps_code(unauthenticated_client, test_breeder):
    c = unauthenticated_client
    desktop = await _auth(c, test_breeder)
    created = await _create(c, desktop)
    phone = await _auth(c, test_breeder)
    p = (await c.post("/api/auth/mobile-signin/preview", json={"code": _code(created)}, headers=phone)).json()
    assert p["same_account"] is True and p["target_path"] == "/breeding/5"
    st = (await c.get(f"/api/auth/mobile-signin/codes/{created['id']}/status", headers=desktop)).json()
    assert st["status"] == "already_signed_in"


@pytest.mark.asyncio
async def test_phone_signed_in_as_someone_else_sees_switch(unauthenticated_client, test_breeder, test_pet_seeker):
    c = unauthenticated_client
    created = await _create(c, await _auth(c, test_breeder))
    p = (await c.post("/api/auth/mobile-signin/preview", json={"code": _code(created)},
                      headers=await _auth(c, test_pet_seeker))).json()
    assert p["same_account"] is False and p["target_path"] is None
    r = await c.post("/api/auth/mobile-signin/redeem", json={"code": _code(created)})
    me = await c.get("/api/auth/users/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.json()["email"] == test_breeder.email


@pytest.mark.asyncio
async def test_deactivated_account_cannot_use_a_code(unauthenticated_client, async_session, test_breeder):
    c = unauthenticated_client
    created = await _create(c, await _auth(c, test_breeder))
    test_breeder.is_active = False
    await async_session.commit()
    r = await c.post("/api/auth/mobile-signin/redeem", json={"code": _code(created)})
    assert r.status_code == 403 and "deactivated" in r.json()["detail"]


@pytest.mark.asyncio
async def test_status_is_owner_only_and_create_needs_sign_in(unauthenticated_client, test_breeder, test_pet_seeker):
    c = unauthenticated_client
    created = await _create(c, await _auth(c, test_breeder))
    r = await c.get(f"/api/auth/mobile-signin/codes/{created['id']}/status", headers=await _auth(c, test_pet_seeker))
    assert r.status_code == 404
    assert (await c.post("/api/auth/mobile-signin/codes", json={})).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("target,expected", [
    ("/breeding/5?tab=x", "/breeding/5?tab=x"),
    ("https://evil.example/x", "/dashboard"),
    ("//evil.example", "/dashboard"),
    ("/login", "/dashboard"),
    ("/m", "/dashboard"),
    ("/messages", "/messages"),
    (None, "/dashboard"),
])
async def test_target_path_is_sanitised(target, expected):
    assert ms.safe_target(target) == expected


@pytest.mark.asyncio
async def test_failed_redemptions_are_rate_limited(unauthenticated_client):
    c = unauthenticated_client
    for _ in range(ms.REDEEM_FAILURE_LIMIT[0]):
        assert (await c.post("/api/auth/mobile-signin/redeem", json={"code": "guess"})).status_code == 404
    assert (await c.post("/api/auth/mobile-signin/redeem", json={"code": "guess"})).status_code == 429


@pytest.mark.asyncio
async def test_code_creation_is_rate_limited(unauthenticated_client, test_breeder):
    c = unauthenticated_client
    h = await _auth(c, test_breeder)
    for _ in range(ms.CREATE_LIMIT[0]):
        await _create(c, h)
    r = await c.post("/api/auth/mobile-signin/codes", json={}, headers=h)
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_two_phones_scanning_at_once_only_one_signs_in(async_session, test_breeder):
    """Two real connections redeem the same code simultaneously."""
    from starlette.requests import Request
    row, code = await ms.mobile_signin_service.create(async_session, test_breeder, "/dashboard")
    engine = create_async_engine(os.environ.get("TEST_DATABASE_URL",
                                                "postgresql+asyncpg://test:test@localhost:5432/test_db"))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    def fake_request():
        return Request({"type": "http", "headers": [(b"user-agent", b"test-phone")], "client": ("1.2.3.4", 1),
                        "method": "POST", "path": "/"})

    async def attempt():
        async with maker() as s:
            try:
                await ms.mobile_signin_service.redeem(s, fake_request(), code)
                return "ok"
            except HTTPException as e:
                return str(e.status_code)

    try:
        results = await asyncio.gather(attempt(), attempt())
    finally:
        await engine.dispose()
    assert sorted(results) == ["410", "ok"]
    used = (await async_session.execute(select(MobileSigninToken).where(MobileSigninToken.id == row.id)
                                        .execution_options(populate_existing=True))).scalar_one()
    assert used.used_at is not None and used.used_user_agent == "test-phone" and used.used_ip_hash


@pytest.mark.asyncio
async def test_old_records_are_cleaned_up(unauthenticated_client, async_session, test_breeder):
    c = unauthenticated_client
    h = await _auth(c, test_breeder)
    old = await _create(c, h)
    row = await async_session.get(MobileSigninToken, old["id"])
    row.created_at = datetime.now(timezone.utc) - timedelta(days=8)
    await async_session.commit()
    await _create(c, h)
    gone = (await async_session.execute(select(MobileSigninToken).where(MobileSigninToken.id == row.id)
                                        .execution_options(populate_existing=True))).scalar_one_or_none()
    assert gone is None


@pytest.mark.asyncio
async def test_unverified_but_active_users_can_use_it(unauthenticated_client, async_session):
    u = User(email="fresh@example.com", name="Fresh", is_active=True, is_verified=False, account_type="pet_seeker",
             hashed_password=bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode())
    async_session.add(u)
    await async_session.commit()
    c = unauthenticated_client
    created = await _create(c, await _auth(c, u), "/favorites/offsprings")
    r = await c.post("/api/auth/mobile-signin/redeem", json={"code": _code(created)})
    assert r.status_code == 200 and r.json()["target_path"] == "/favorites/offsprings"
