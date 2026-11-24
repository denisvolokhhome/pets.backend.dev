"""Heat cycles, reminders and the calendar: validation, one open cycle, privacy."""
import bcrypt
import pytest

from app.models.pet import Pet
from app.models.user import User


async def _auth(client, user):
    r = await client.post("/api/auth/jwt/login", data={"username": user.email, "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def dam(async_session, test_breeder):
    p = Pet(user_id=test_breeder.id, name="Bella", gender="Female", is_deleted=False)
    async_session.add(p)
    await async_session.commit()
    return p


@pytest.fixture
async def hb(unauthenticated_client, test_breeder):
    return await _auth(unauthenticated_client, test_breeder)


@pytest.mark.asyncio
async def test_record_cycle_find_in_calendar_edit_there(unauthenticated_client, dam, hb):
    c = unauthenticated_client
    r = await c.post(f"/api/pets/{dam.id}/heat-cycles", json={"start_date": "2026-03-03", "notes": "light"},
                     headers=hb)
    assert r.status_code == 201, r.text
    cycle = r.json()
    assert cycle["in_progress"] is True and cycle["start_date"] == "2026-03-03"

    cal = (await c.get("/api/calendar?start=2026-03-01&end=2026-03-31", headers=hb)).json()
    starts = [e for e in cal["events"] if e["type"] == "heat_start"]
    assert len(starts) == 1 and starts[0]["date"] == "2026-03-03" and starts[0]["pet_name"] == "Bella"
    assert starts[0]["cycle_id"] == cycle["id"] and starts[0]["in_progress"] is True
    assert [p["name"] for p in cal["pets"]] == ["Bella"]

    # Edit from the calendar (same record) -> shows in Heat History
    r = await c.put(f"/api/heat-cycles/{cycle['id']}",
                    json={"start_date": "2026-03-04", "end_date": "2026-03-21", "notes": "ended"}, headers=hb)
    assert r.status_code == 200 and r.json()["in_progress"] is False
    history = (await c.get(f"/api/pets/{dam.id}/heat-cycles", headers=hb)).json()
    assert history == [r.json()]
    cal = (await c.get("/api/calendar?start=2026-03-01&end=2026-03-31", headers=hb)).json()
    assert [(e["type"], e["date"]) for e in cal["events"]] == [("heat_start", "2026-03-04"),
                                                              ("heat_end", "2026-03-21")]


@pytest.mark.asyncio
async def test_dates_stay_calendar_dates(unauthenticated_client, dam, hb):
    r = await unauthenticated_client.post(f"/api/pets/{dam.id}/heat-cycles",
                                          json={"start_date": "2026-12-31", "end_date": "2027-01-01"}, headers=hb)
    assert r.json()["start_date"] == "2026-12-31" and r.json()["end_date"] == "2027-01-01"


@pytest.mark.asyncio
async def test_end_before_start_rejected(unauthenticated_client, dam, hb):
    r = await unauthenticated_client.post(f"/api/pets/{dam.id}/heat-cycles",
                                          json={"start_date": "2026-03-10", "end_date": "2026-03-09"}, headers=hb)
    assert r.status_code == 422
    r = await unauthenticated_client.post(f"/api/pets/{dam.id}/heat-cycles",
                                          json={"start_date": "2026-03-10", "end_date": "2026-03-10"}, headers=hb)
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_only_one_open_cycle_per_dog(unauthenticated_client, dam, hb):
    c = unauthenticated_client
    first = (await c.post(f"/api/pets/{dam.id}/heat-cycles", json={"start_date": "2026-01-01"}, headers=hb)).json()
    r = await c.post(f"/api/pets/{dam.id}/heat-cycles", json={"start_date": "2026-06-01"}, headers=hb)
    assert r.status_code == 409
    # A closed past cycle is fine while one is open
    r = await c.post(f"/api/pets/{dam.id}/heat-cycles",
                     json={"start_date": "2025-06-01", "end_date": "2025-06-20"}, headers=hb)
    assert r.status_code == 201
    # Re-opening the closed one while another is open is refused
    r = await c.put(f"/api/heat-cycles/{r.json()['id']}", json={"start_date": "2025-06-01", "end_date": None},
                    headers=hb)
    assert r.status_code == 409
    # End the open one, then a new open cycle is allowed
    await c.put(f"/api/heat-cycles/{first['id']}", json={"start_date": "2026-01-01", "end_date": "2026-01-18"},
                headers=hb)
    r = await c.post(f"/api/pets/{dam.id}/heat-cycles", json={"start_date": "2026-06-01"}, headers=hb)
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_male_dog_has_no_heat_cycles(unauthenticated_client, async_session, test_breeder, hb):
    stud = Pet(user_id=test_breeder.id, name="Max", gender="Male", is_deleted=False)
    async_session.add(stud)
    await async_session.commit()
    r = await unauthenticated_client.post(f"/api/pets/{stud.id}/heat-cycles", json={"start_date": "2026-01-01"},
                                          headers=hb)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_reminders_crud_and_calendar_filter(unauthenticated_client, async_session, test_breeder, dam, hb):
    c = unauthenticated_client
    other_dog = Pet(user_id=test_breeder.id, name="Zoe", gender="Female", is_deleted=False)
    async_session.add(other_dog)
    await async_session.commit()
    r = await c.post(f"/api/pets/{dam.id}/reminders", json={"remind_on": "2026-04-10", "note": "Progesterone"},
                     headers=hb)
    assert r.status_code == 201
    rid = r.json()["id"]
    await c.post(f"/api/pets/{other_dog.id}/reminders", json={"remind_on": "2026-04-11"}, headers=hb)

    cal = (await c.get(f"/api/calendar?start=2026-04-01&end=2026-04-30&pet_id={dam.id}", headers=hb)).json()
    assert [(e["type"], e["pet_name"], e["note"]) for e in cal["events"]] == [("reminder", "Bella", "Progesterone")]
    cal = (await c.get("/api/calendar?start=2026-04-01&end=2026-04-30", headers=hb)).json()
    assert len(cal["events"]) == 2

    r = await c.put(f"/api/reminders/{rid}", json={"remind_on": "2026-04-12", "note": ""}, headers=hb)
    assert r.json()["remind_on"] == "2026-04-12" and r.json()["note"] is None
    assert (await c.delete(f"/api/reminders/{rid}", headers=hb)).status_code == 204
    assert (await c.get(f"/api/pets/{dam.id}/reminders", headers=hb)).json() == []


@pytest.mark.asyncio
async def test_calendar_range_limits(unauthenticated_client, hb):
    r = await unauthenticated_client.get("/api/calendar?start=2026-01-01&end=2026-12-31", headers=hb)
    assert r.status_code == 422
    r = await unauthenticated_client.get("/api/calendar?start=2026-02-01&end=2026-01-01", headers=hb)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_other_accounts_cannot_access(unauthenticated_client, async_session, dam, hb):
    c = unauthenticated_client
    cycle = (await c.post(f"/api/pets/{dam.id}/heat-cycles", json={"start_date": "2026-03-03"}, headers=hb)).json()
    reminder = (await c.post(f"/api/pets/{dam.id}/reminders", json={"remind_on": "2026-03-05"}, headers=hb)).json()

    intruder = User(email="nosy.breeder@example.com", name="Nosy", is_active=True, is_verified=True,
                    is_breeder=True, account_type="breeder",
                    hashed_password=bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode())
    async_session.add(intruder)
    await async_session.commit()
    hi = await _auth(c, intruder)
    assert (await c.get(f"/api/pets/{dam.id}/heat-cycles", headers=hi)).status_code == 404
    assert (await c.get(f"/api/pets/{dam.id}/reminders", headers=hi)).status_code == 404
    assert (await c.post(f"/api/pets/{dam.id}/heat-cycles", json={"start_date": "2026-05-01"},
                         headers=hi)).status_code == 404
    assert (await c.put(f"/api/heat-cycles/{cycle['id']}", json={"start_date": "2026-03-01"},
                        headers=hi)).status_code == 404
    assert (await c.delete(f"/api/heat-cycles/{cycle['id']}", headers=hi)).status_code == 404
    assert (await c.put(f"/api/reminders/{reminder['id']}", json={"remind_on": "2026-03-01"},
                        headers=hi)).status_code == 404
    cal = (await c.get("/api/calendar?start=2026-03-01&end=2026-03-31", headers=hi)).json()
    assert cal["events"] == [] and cal["pets"] == []
    # Unauthenticated
    assert (await c.get(f"/api/pets/{dam.id}/heat-cycles")).status_code == 401


@pytest.mark.asyncio
async def test_calendar_lists_cycle_spanning_the_month(unauthenticated_client, dam, hb):
    """A dog still in heat from last month has no start/end event this month but shows in in_heat."""
    c = unauthenticated_client
    await c.post(f"/api/pets/{dam.id}/heat-cycles", json={"start_date": "2026-11-28"}, headers=hb)
    cal = (await c.get("/api/calendar?start=2026-12-01&end=2026-12-31", headers=hb)).json()
    assert cal["events"] == []
    assert [(h["pet_name"], h["start_date"], h["in_progress"]) for h in cal["in_heat"]] == [
        ("Bella", "2026-11-28", True)]
    cal = (await c.get("/api/calendar?start=2026-10-01&end=2026-10-31", headers=hb)).json()
    assert cal["in_heat"] == []
