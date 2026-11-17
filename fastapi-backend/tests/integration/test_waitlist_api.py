"""Waitlist HTTP surface, auth, and the feature flag."""
from datetime import date

import pytest

from app.config import Settings


async def _auth(client, user):
    r = await client.post("/api/auth/jwt/login", data={"username": user.email, "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def flag_on(monkeypatch):
    from app import dependencies
    from app.services import waitlist_service as ws
    monkeypatch.setattr(dependencies.settings, "enable_waitlist", True)
    monkeypatch.setattr(ws.settings, "enable_waitlist", True)


@pytest.fixture
async def seeker(async_session, test_pet_seeker):
    test_pet_seeker.account_type = "pet_seeker"
    await async_session.commit()
    return test_pet_seeker


@pytest.mark.asyncio
async def test_every_route_404s_when_flag_off(unauthenticated_client, test_breeder):
    assert Settings().enable_waitlist is False
    h = await _auth(unauthenticated_client, test_breeder)
    for method, path in [("GET", "/api/waitlist"), ("GET", "/api/waitlist/mine"),
                         ("GET", f"/api/waitlist/breeders/{test_breeder.id}/info"),
                         ("POST", "/api/waitlist/entries"), ("GET", "/api/waitlist/settings")]:
        r = await unauthenticated_client.request(method, path, headers=h, json={})
        assert r.status_code == 404, path


@pytest.mark.asyncio
async def test_request_approve_flow(unauthenticated_client, flag_on, test_breeder, seeker):
    hs = await _auth(unauthenticated_client, seeker)
    hb = await _auth(unauthenticated_client, test_breeder)
    r = await unauthenticated_client.post(f"/api/waitlist/breeders/{test_breeder.id}/requests",
                                          json={"sex_preference": "Female"}, headers=hs)
    assert r.status_code == 201
    entry_id = r.json()["id"]
    r = await unauthenticated_client.get("/api/waitlist", headers=hb)
    assert [e["id"] for e in r.json()["pending"]] == [entry_id]
    r = await unauthenticated_client.post(f"/api/waitlist/entries/{entry_id}/approve", headers=hb)
    assert r.json()["status"] == "active"
    r = await unauthenticated_client.get("/api/waitlist/mine", headers=hs)
    assert r.json()[0]["position"] == 1


@pytest.mark.asyncio
async def test_seeker_view_exposes_only_own_entry(unauthenticated_client, async_session, flag_on, test_breeder, seeker):
    from app.models.user import User
    import bcrypt
    other = User(email="other.seeker@example.com", name="Other Person", is_active=True, is_verified=True,
                 account_type="pet_seeker", hashed_password=bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode())
    async_session.add(other)
    await async_session.commit()
    hb = await _auth(unauthenticated_client, test_breeder)
    for u in (other, seeker):
        h = await _auth(unauthenticated_client, u)
        r = await unauthenticated_client.post(f"/api/waitlist/breeders/{test_breeder.id}/requests", json={}, headers=h)
        await unauthenticated_client.post(f"/api/waitlist/entries/{r.json()['id']}/approve", headers=hb)
    hs = await _auth(unauthenticated_client, seeker)
    body = (await unauthenticated_client.get("/api/waitlist/mine", headers=hs)).text
    assert "Other Person" not in body and "other.seeker@example.com" not in body
    data = (await unauthenticated_client.get("/api/waitlist/mine", headers=hs)).json()
    assert len(data) == 1 and data[0]["position"] == 2


@pytest.mark.asyncio
async def test_seeker_cannot_use_breeder_routes(unauthenticated_client, flag_on, seeker):
    hs = await _auth(unauthenticated_client, seeker)
    r = await unauthenticated_client.get("/api/waitlist", headers=hs)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_settings_round_trip_and_public_info(unauthenticated_client, flag_on, test_breeder):
    hb = await _auth(unauthenticated_client, test_breeder)
    r = await unauthenticated_client.put("/api/waitlist/settings",
                                         json={"deposit_amount": "250.00", "deposit_policy": "Refundable"}, headers=hb)
    assert r.status_code == 200
    r = await unauthenticated_client.get(f"/api/waitlist/breeders/{test_breeder.id}/info")
    assert r.json()["deposit_amount"] == "250.00" and r.json()["has_active_entry"] is False

@pytest.mark.asyncio
async def test_void_breeding_returns_entries_to_general_list(unauthenticated_client, flag_on, test_breeder, test_breeding):
    hb = await _auth(unauthenticated_client, test_breeder)
    r = await unauthenticated_client.post("/api/waitlist/entries", headers=hb,
                                          json={"contact_name": "Walk In", "contact_email": "walkin@example.com"})
    assert r.status_code == 201
    entry_id = r.json()["id"]
    r = await unauthenticated_client.post(f"/api/waitlist/entries/{entry_id}/move", headers=hb,
                                          json={"breeding_id": test_breeding.id})
    assert r.status_code == 200 and r.json()["breeding_id"] == test_breeding.id
    r = await unauthenticated_client.delete(f"/api/breedings/{test_breeding.id}", headers=hb)
    assert r.status_code == 200
    r = await unauthenticated_client.get("/api/waitlist", headers=hb)
    general = {e["id"]: e for e in r.json()["general"]}
    assert entry_id in general and general[entry_id]["breeding_id"] is None


@pytest.mark.asyncio
async def test_void_breeding_still_works_when_flag_off(unauthenticated_client, test_breeder, test_breeding):
    hb = await _auth(unauthenticated_client, test_breeder)
    r = await unauthenticated_client.delete(f"/api/breedings/{test_breeding.id}", headers=hb)
    assert r.status_code == 200
    assert r.json()["status"] == "Voided"
