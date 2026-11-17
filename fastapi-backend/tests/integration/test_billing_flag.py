"""ENABLE_BILLING feature flag: off = pricing routes hidden and no plan limits."""
import pytest
from fastapi import HTTPException

from app.config import Settings
from app.models.plan import Plan
from app.services import billing_service as bs
from app.services.billing_service import billing_service
from app.services.pet_import_service import pet_import_service


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.setattr(bs.settings, "enable_billing", False)


@pytest.fixture
async def zero_limit_free_plan(async_session):
    plan = Plan(
        name="Free", price=0, currency="usd", billing_interval="month",
        max_pets=0, max_published_locations=0, max_simultaneous_offsprings=0,
        is_default=True,
    )
    async_session.add(plan)
    await async_session.commit()
    return plan


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("ENABLE_BILLING", raising=False)
    assert Settings(_env_file=None).enable_billing is False


@pytest.mark.asyncio
async def test_billing_routes_404_when_flag_off(unauthenticated_client, flag_off, test_breeder):
    r = await unauthenticated_client.post(
        "/api/auth/jwt/login", data={"username": test_breeder.email, "password": "testpass123"}
    )
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    for method, path in [
        ("GET", "/api/billing/plans"),
        ("GET", "/api/billing/subscription"),
        ("POST", "/api/billing/subscribe"),
        ("GET", "/api/billing/invoices"),
        ("POST", "/api/billing/create-checkout-session"),
        ("POST", "/api/billing/portal-session"),
        ("GET", "/api/billing/verify-session/cs_test"),
    ]:
        r = await unauthenticated_client.request(method, path, headers=h, json={})
        assert r.status_code == 404, path


@pytest.mark.asyncio
async def test_webhook_still_reachable_when_flag_off(unauthenticated_client, flag_off):
    r = await unauthenticated_client.post("/api/billing/webhook", content=b"{}")
    assert r.status_code != 404


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["pets", "locations", "offsprings"])
async def test_no_usage_limits_when_flag_off(async_session, flag_off, zero_limit_free_plan, test_breeder, resource):
    await billing_service.check_usage(async_session, test_breeder.id, resource)


@pytest.mark.asyncio
async def test_usage_limits_enforced_when_flag_on(async_session, zero_limit_free_plan, test_breeder):
    with pytest.raises(HTTPException) as exc:
        await billing_service.check_usage(async_session, test_breeder.id, "pets")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_import_has_no_pet_cap_when_flag_off(async_session, flag_off, zero_limit_free_plan, test_breeder):
    assert await pet_import_service._get_plan_max_pets(async_session, test_breeder.id) == 999_999
