"""The public breeder map must not reveal a breeder's exact location."""
import pytest
from geoalchemy2.elements import WKTElement

from app.models.location import Location
from app.models.pet import Pet

EXACT_LAT, EXACT_LNG = 30.1904567, -98.0867891  # someone's front door


@pytest.mark.asyncio
async def test_map_search_returns_only_an_approximate_location(
    unauthenticated_client, async_session, test_breeder, test_breed
):
    loc = Location(
        user_id=test_breeder.id, name="Home kennel", address1="1 Secret Rd", city="Dripping Springs",
        state="TX", country="US", zipcode="78620", location_type="user", is_published=True,
        latitude=EXACT_LAT, longitude=EXACT_LNG,
        coordinates=WKTElement(f"POINT({EXACT_LNG} {EXACT_LAT})", srid=4326),
    )
    async_session.add(loc)
    await async_session.flush()
    async_session.add(Pet(user_id=test_breeder.id, name="Rex", breed_id=test_breed.id, location_id=loc.id))
    await async_session.commit()

    r = await unauthenticated_client.get(
        "/api/search/breeders",
        params={"latitude": 30.20, "longitude": -98.10, "radius": 50},
    )
    assert r.status_code == 200, r.text
    results = r.json()
    assert len(results) == 1
    hit = results[0]
    assert (hit["latitude"], hit["longitude"]) == (30.19, -98.09)
    assert hit["distance"] == float(round(hit["distance"]))  # whole miles only
    assert "1 Secret Rd" not in r.text
