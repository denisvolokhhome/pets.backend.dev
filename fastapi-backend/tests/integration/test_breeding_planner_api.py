"""HTTP surface of the breeding planner."""
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.models.breeding_pet import BreedingPet
from app.models.pet import Pet


async def _auth(client: AsyncClient, user) -> dict:
    r = await client.post("/api/auth/jwt/login", data={"username": user.email, "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def parents(async_session, test_breeder, test_breed, test_breeding):
    dam = Pet(user_id=test_breeder.id, name="Honey", gender="Female", breed_id=test_breed.id)
    sire = Pet(user_id=test_breeder.id, name="Rex", gender="Male", breed_id=test_breed.id)
    async_session.add_all([dam, sire])
    await async_session.flush()
    async_session.add_all([BreedingPet(breeding_id=test_breeding.id, pet_id=dam.id),
                           BreedingPet(breeding_id=test_breeding.id, pet_id=sire.id)])
    await async_session.commit()
    # same session as the app under test: drop the stale (empty) parents collection
    async_session.expire(test_breeding, ["breeding_pets"])
    return dam, sire


@pytest.mark.asyncio
async def test_planner_round_trip(unauthenticated_client, test_breeder, test_breeding, parents):
    h = await _auth(unauthenticated_client, test_breeder)
    mated = (date.today() - timedelta(days=30)).isoformat()
    r = await unauthenticated_client.post(f"/api/breedings/{test_breeding.id}/matings",
                                          json={"mated_on": mated, "method": "AI_Chilled",
                                                "sire_id": str(parents[1].id)}, headers=h)
    assert r.status_code == 201
    body = r.json()
    assert body["stage"] == "Mated" and body["due_date"] and body["matings"][0]["sire_name"] == "Rex"

    r = await unauthenticated_client.patch(f"/api/breedings/{test_breeding.id}/planner",
                                           json={"stage": "Confirmed"}, headers=h)
    assert r.json()["stage"] == "Confirmed"

    milestone_id = body["milestones"][0]["id"]
    r = await unauthenticated_client.get(f"/api/breedings/milestones/{milestone_id}", headers=h)
    assert r.json() == {"id": milestone_id, "breeding_id": test_breeding.id}

    r = await unauthenticated_client.get("/api/breedings/milestones/upcoming?days=30", headers=h)
    assert r.status_code == 200 and len(r.json()) >= 1

    r = await unauthenticated_client.get("/api/breedings/", headers=h)
    row = next(b for b in r.json() if b["id"] == test_breeding.id)
    assert row["stage"] == "Confirmed" and row["due_date"]


@pytest.mark.asyncio
async def test_mating_rejects_foreign_or_female_sire(unauthenticated_client, async_session, test_breeder,
                                                     test_breeding, parents):
    h = await _auth(unauthenticated_client, test_breeder)
    url = f"/api/breedings/{test_breeding.id}/matings"
    payload = {"mated_on": date.today().isoformat(), "method": "Natural"}
    r = await unauthenticated_client.post(url, json={**payload, "sire_id": str(parents[0].id)}, headers=h)
    assert r.status_code == 422
    from app.models.user import User
    other = User(email="o@example.com", hashed_password="x", name="O", is_active=True, is_breeder=True)
    async_session.add(other)
    await async_session.flush()
    stranger = Pet(user_id=other.id, name="Stud", gender="Male")
    async_session.add(stranger)
    await async_session.commit()
    r = await unauthenticated_client.post(url, json={**payload, "sire_id": str(stranger.id)}, headers=h)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_invalid_stage_is_409(unauthenticated_client, test_breeder, test_breeding):
    h = await _auth(unauthenticated_client, test_breeder)
    r = await unauthenticated_client.patch(f"/api/breedings/{test_breeding.id}/planner",
                                           json={"stage": "Confirmed"}, headers=h)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "INVALID_STAGE_TRANSITION"


@pytest.mark.asyncio
async def test_add_puppies_marks_whelped(unauthenticated_client, test_breeder, test_breeding, parents):
    h = await _auth(unauthenticated_client, test_breeder)
    r = await unauthenticated_client.post(f"/api/breedings/{test_breeding.id}/add-puppies",
                                          json={"puppies": [{"name": "P1", "gender": "Male",
                                                             "birth_date": date.today().isoformat()}]}, headers=h)
    assert r.status_code == 200
    r = await unauthenticated_client.get(f"/api/breedings/{test_breeding.id}/planner", headers=h)
    assert r.json()["stage"] == "Whelped"


@pytest.mark.asyncio
async def test_pet_seeker_forbidden(unauthenticated_client, async_session, test_pet_seeker, test_breeding):
    test_pet_seeker.account_type = "pet_seeker"
    await async_session.commit()
    h = await _auth(unauthenticated_client, test_pet_seeker)
    r = await unauthenticated_client.get(f"/api/breedings/{test_breeding.id}/planner", headers=h)
    assert r.status_code == 403
