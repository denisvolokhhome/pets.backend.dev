"""GET /api/search/offsprings: available offspring near a point, grouped by breeder."""
import uuid

import pytest

from app.models.breed import Breed
from app.models.breeder_review import BreederReview
from tests.integration.test_map_offspring_search import _location, _offspring, _other_breeder

URL = "/api/search/offsprings"
CENTER = {"latitude": 30.20, "longitude": -98.10, "radius": 50}


@pytest.mark.asyncio
async def test_groups_by_breeder_nearest_first(unauthenticated_client, async_session, test_breeder, test_breed):
    await _location(async_session, test_breeder, lat=30.50, lng=-98.10)       # ~21 mi
    far_pups = [await _offspring(async_session, test_breeder, test_breed) for _ in range(2)]

    near = await _other_breeder(async_session, "near@example.com")
    await _location(async_session, near, lat=30.21, lng=-98.10)             # ~1 mi
    near_pup = await _offspring(async_session, near, test_breed)
    await _offspring(async_session, near, test_breed, status="Reserved")    # not shown
    await _offspring(async_session, near, test_breed, published=False)      # not shown
    await async_session.commit()

    r = await unauthenticated_client.get(URL, params=CENTER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_breeders"] == 2
    g1, g2 = body["groups"]
    assert g1["breeder_id"] == str(near.id) and g1["breeder_name"] == "Other Kennel"
    assert [o["id"] for o in g1["offsprings"]] == [str(near_pup.id)]
    assert g1["available_count"] == 1
    assert g1["distance"] == 1.0
    assert g2["breeder_id"] == str(test_breeder.id)
    assert {o["id"] for o in g2["offsprings"]} == {str(p.id) for p in far_pups}
    assert g2["distance"] == float(round(g2["distance"])) > g1["distance"]


@pytest.mark.asyncio
async def test_excludes_breeders_with_nothing_available_or_outside(unauthenticated_client, async_session, test_breeder, test_breed):
    await _location(async_session, test_breeder)                            # no offspring
    far = await _other_breeder(async_session, "far@example.com")
    await _location(async_session, far, lat=40.71, lng=-74.00)
    await _offspring(async_session, far, test_breed)
    hidden = await _other_breeder(async_session, "hidden@example.com")
    await _location(async_session, hidden, published=False)
    await _offspring(async_session, hidden, test_breed)
    await async_session.commit()

    body = (await unauthenticated_client.get(URL, params=CENTER)).json()
    assert body == {"groups": [], "total_breeders": 0, "limit": 10, "offset": 0}


@pytest.mark.asyncio
async def test_breed_and_kind_filters_are_strict(unauthenticated_client, async_session, test_breeder, test_breed):
    cat = Breed(name="Siamese", kind="cat")
    async_session.add(cat)
    await async_session.flush()
    await _location(async_session, test_breeder)
    dog_pup = await _offspring(async_session, test_breeder, test_breed)
    cat_pup = await _offspring(async_session, test_breeder, cat)
    await async_session.commit()

    by_breed = (await unauthenticated_client.get(URL, params={**CENTER, "breed_id": cat.id})).json()
    assert [o["id"] for o in by_breed["groups"][0]["offsprings"]] == [str(cat_pup.id)]
    assert by_breed["groups"][0]["available_count"] == 1

    by_kind = (await unauthenticated_client.get(URL, params={**CENTER, "animal_kind": test_breed.kind})).json()
    assert [o["id"] for o in by_kind["groups"][0]["offsprings"]] == [str(dog_pup.id)]


@pytest.mark.asyncio
async def test_pages_by_breeder(unauthenticated_client, async_session, test_breed):
    for i in range(3):
        b = await _other_breeder(async_session, f"b{i}@example.com")
        await _location(async_session, b, lat=30.21 + i * 0.1, lng=-98.10)
        await _offspring(async_session, b, test_breed)
    await async_session.commit()

    p1 = (await unauthenticated_client.get(URL, params={**CENTER, "limit": 2})).json()
    p2 = (await unauthenticated_client.get(URL, params={**CENTER, "limit": 2, "offset": 2})).json()
    assert p1["total_breeders"] == p2["total_breeders"] == 3
    assert len(p1["groups"]) == 2 and len(p2["groups"]) == 1
    ids = [g["breeder_id"] for g in p1["groups"] + p2["groups"]]
    assert len(set(ids)) == 3
    assert (await unauthenticated_client.get(URL, params={**CENTER, "limit": 31})).status_code == 422


@pytest.mark.asyncio
async def test_rating_in_header(unauthenticated_client, async_session, test_breeder, test_breed, test_pet_seeker):
    await _location(async_session, test_breeder)
    await _offspring(async_session, test_breeder, test_breed)
    async_session.add(BreederReview(breeder_id=test_breeder.id, reviewer_id=test_pet_seeker.id, thread_id=uuid.uuid4(), rating=4))
    await async_session.commit()

    [g] = (await unauthenticated_client.get(URL, params=CENTER)).json()["groups"]
    assert g["rating"] == 4.0 and g["review_count"] == 1
