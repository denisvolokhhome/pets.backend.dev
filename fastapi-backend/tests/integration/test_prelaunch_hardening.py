"""Sign-in brute-force limits, client IP resolution, sign-up email policy and plan usage."""
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import current_active_user
from app.main import app
from app.middleware.rate_limiter import resolve_client_ip
from app.models.user import User
from app.utils import email_policy

PASSWORD = "SecurePassword123!"


# ── client IP resolution ────────────────────────────────────────────────

def test_client_ip_ignores_client_supplied_forwarded_entries():
    headers = {"X-Forwarded-For": "6.6.6.6, 203.0.113.7"}  # spoofed, then appended by our proxy
    assert resolve_client_ip(headers, "10.0.0.2", "", 1) == "203.0.113.7"


def test_client_ip_counts_proxy_hops_from_the_right():
    headers = {"X-Forwarded-For": "6.6.6.6, 203.0.113.7, 172.18.0.5"}
    assert resolve_client_ip(headers, "172.18.0.9", "", 2) == "203.0.113.7"


def test_client_ip_prefers_edge_header():
    headers = {"CF-Connecting-IP": "198.51.100.4", "X-Forwarded-For": "6.6.6.6, 172.18.0.5"}
    assert resolve_client_ip(headers, "172.18.0.9", "CF-Connecting-IP", 1) == "198.51.100.4"


def test_client_ip_falls_back_to_peer():
    assert resolve_client_ip({}, "192.0.2.1", "CF-Connecting-IP", 1) == "192.0.2.1"
    assert resolve_client_ip({"X-Forwarded-For": "6.6.6.6"}, "192.0.2.1", "", 0) == "192.0.2.1"


# ── sign-in rate limiting ───────────────────────────────────────────────

async def _login(client: AsyncClient, email: str, password: str, xff: str = "203.0.113.1"):
    return await client.post(
        "/api/auth/jwt/login",
        data={"username": email, "password": password},
        headers={"X-Forwarded-For": xff},
    )


@pytest.mark.asyncio
async def test_login_locks_account_after_repeated_failures(unauthenticated_client: AsyncClient):
    email = "bruteforce.target@example.com"
    assert (await unauthenticated_client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD})).status_code == 201

    for i in range(10):
        r = await _login(unauthenticated_client, email, f"wrong-{i}", xff=f"203.0.113.{i}")
        assert r.status_code == 400

    # Limit is per account, so switching IPs doesn't help — and even the right password waits
    r = await _login(unauthenticated_client, email, PASSWORD, xff="198.51.100.1")
    assert r.status_code == 429
    assert "Too many sign-in attempts" in r.json()["detail"]


@pytest.mark.asyncio
async def test_successful_logins_do_not_count(unauthenticated_client: AsyncClient):
    email = "frequent.user@example.com"
    await unauthenticated_client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    for _ in range(12):
        assert (await _login(unauthenticated_client, email, PASSWORD)).status_code == 200


@pytest.mark.asyncio
async def test_spoofed_forwarded_for_does_not_bypass_ip_limit(unauthenticated_client: AsyncClient):
    # A different account and a different spoofed leftmost XFF entry on every attempt;
    # the proxy-appended (rightmost) address is the same, so the per-IP limit still applies.
    for i in range(20):
        r = await _login(unauthenticated_client, f"nobody{i}@example.com", "x",
                         xff=f"6.6.{i}.{i}, 203.0.113.50")
        assert r.status_code == 400
    r = await _login(unauthenticated_client, "nobody99@example.com", "x", xff="6.6.99.99, 203.0.113.50")
    assert r.status_code == 429


# ── sign-up email policy ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reserved_domains_allowed_outside_production(unauthenticated_client: AsyncClient):
    r = await unauthenticated_client.post(
        "/api/auth/register", json={"email": "qa.breeder@sunnymeadow.test", "password": PASSWORD})
    assert r.status_code == 201
    # ...and the same address can use forgot-password (EmailStr) in this environment
    r = await unauthenticated_client.post(
        "/api/auth/forgot-password", json={"email": "qa.breeder@sunnymeadow.test"})
    assert r.status_code == 202


@pytest.mark.asyncio
async def test_reserved_domains_rejected_in_production(unauthenticated_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(email_policy._settings, "environment", "production")

    for path in ("/api/auth/register", "/api/auth/register/pet-seeker"):
        r = await unauthenticated_client.post(
            path, json={"email": "someone@sunnymeadow.test", "password": PASSWORD})
        assert r.status_code == 422, path

    r = await unauthenticated_client.post(
        "/api/auth/register", json={"email": "real.person@example.com", "password": PASSWORD})
    assert r.status_code == 201


# ── subscription usage ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscription_reports_usage(
    async_session: AsyncSession, test_breeder: User, test_breed, test_offspring
):
    from app.models.offspring import Offspring
    from app.models.pet import Pet
    from app.models.plan import Plan
    from app.models.subscription import Subscription

    plan = Plan(name="usage_free", price=0, currency="usd", billing_interval="month",
                max_pets=5, max_published_locations=1, max_simultaneous_offsprings=20,
                is_default=False)
    async_session.add(plan)
    await async_session.flush()
    now = datetime.now(timezone.utc)
    async_session.add(Subscription(user_id=test_breeder.id, plan_id=plan.id, status="active",
                                   current_period_start=now, current_period_end=now))
    async_session.add_all([
        Pet(user_id=test_breeder.id, name="Bella", breed_id=test_breed.id),
        Pet(user_id=test_breeder.id, name="Max", breed_id=test_breed.id),
        Pet(user_id=test_breeder.id, name="Gone", breed_id=test_breed.id, is_deleted=True),
        Offspring(breeding_id=test_offspring.breeding_id, user_id=test_breeder.id,
                  breed_id=test_breed.id, name="Sold one", gender="Female", status="Sold",
                  date_of_birth=test_offspring.date_of_birth),
    ])
    await async_session.commit()

    async def override_session():
        yield async_session

    async def override_user():
        return test_breeder

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[current_active_user] = override_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/billing/subscription")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    # Deleted pets and sold offspring don't count against the plan
    assert r.json()["usage"] == {"pets": 2, "published_locations": 0, "offsprings": 1}
