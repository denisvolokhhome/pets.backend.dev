"""GET /api/offsprings/public/nearby: suggestions from other breeders close by."""
import pytest

from app.models.breed import Breed
from tests.integration.test_map_offspring_search import _location, _offspring, _other_breeder

URL = "/api/offsprings/public/nearby"
CENTER = {"latitude": 30.20, "longitude": -98.10, "radius": 50}


async def _second_breed(session):
    b = Breed(name="Poodle", kind="dog")
    session.add(b)
    await session.flush()
    return b


@pytest.mark.asyncio
async def test_excludes_viewed_breeder_and_ineligible(unauthenticated_client, async_session, test_breeder, test_breed):
    await _location(async_session, test_breeder)
    await _offspring(async_session, test_breeder, test_breed)  # viewed breeder: excluded

    near = await _other_breeder(async_session, "near@example.com")
    await _location(async_session, near)
    ok = await _offspring(async_session, near, test_breed)
    await _offspring(async_session, near, test_breed, status="Reserved")
    await _offspring(async_session, near, test_breed, published=False)

    far = await _other_breeder(async_session, "far@example.com")
    await _location(async_session, far, lat=40.71, lng=-74.00)  # New York
    await _offspring(async_session, far, test_breed)

    hidden = await _other_breeder(async_session, "hidden@example.com")
    await _location(async_session, hidden, published=False)
    await _offspring(async_session, hidden, test_breed)

    homeless = await _other_breeder(async_session, "homeless@example.com")
    await _offspring(async_session, homeless, test_breed)
    await async_session.commit()

    r = await unauthenticated_client.get(URL, params={**CENTER, "exclude_breeder_id": str(test_breeder.id)})
    assert r.status_code == 200, r.text
    items = r.json()["offsprings"]
    assert [i["id"] for i in items] == [str(ok.id)]
    assert items[0]["breeder_name"] == "Other Kennel"
    assert items[0]["distance"] == float(round(items[0]["distance"])) >= 1


@pytest.mark.asyncio
async def test_same_breed_first_then_distance(unauthenticated_client, async_session, test_breed):
    poodle = await _second_breed(async_session)
    close = await _other_breeder(async_session, "close@example.com")
    await _location(async_session, close, lat=30.20, lng=-98.10)
    close_poodle = await _offspring(async_session, close, poodle)

    farther = await _other_breeder(async_session, "farther@example.com")
    await _location(async_session, farther, lat=30.50, lng=-98.10)
    farther_match = await _offspring(async_session, farther, test_breed)
    await async_session.commit()

    r = await unauthenticated_client.get(URL, params={**CENTER, "breed_id": test_breed.id})
    ids = [i["id"] for i in r.json()["offsprings"]]
    assert ids == [str(farther_match.id), str(close_poodle.id)]

    r = await unauthenticated_client.get(URL, params=CENTER)
    ids = [i["id"] for i in r.json()["offsprings"]]
    assert ids == [str(close_poodle.id), str(farther_match.id)]


@pytest.mark.asyncio
async def test_breeder_with_two_locations_listed_once(unauthenticated_client, async_session, test_breed):
    b = await _other_breeder(async_session)
    await _location(async_session, b, lat=30.20, lng=-98.10)
    await _location(async_session, b, lat=30.30, lng=-98.10)
    o = await _offspring(async_session, b, test_breed)
    await async_session.commit()

    r = await unauthenticated_client.get(URL, params=CENTER)
    assert [i["id"] for i in r.json()["offsprings"]] == [str(o.id)]


@pytest.mark.asyncio
async def test_limit(unauthenticated_client, async_session, test_breed):
    b = await _other_breeder(async_session)
    await _location(async_session, b)
    for _ in range(3):
        await _offspring(async_session, b, test_breed)
    await async_session.commit()

    r = await unauthenticated_client.get(URL, params={**CENTER, "limit": 2})
    assert len(r.json()["offsprings"]) == 2
    assert (await unauthenticated_client.get(URL, params={**CENTER, "limit": 25})).status_code == 422
