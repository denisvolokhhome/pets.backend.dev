"""Map search: available-offspring count, public phone, has_offspring filter."""
from datetime import date

import pytest
from geoalchemy2.elements import WKTElement

from app.models.breeding import Breeding
from app.models.location import Location
from app.models.offspring import Offspring
from app.models.pet import Pet
from app.models.user import User

LAT, LNG = 30.19, -98.09
SEARCH = {"latitude": 30.20, "longitude": -98.10, "radius": 50}


async def _location(session, user, *, phone=None, show_phone=False, lat=LAT, lng=LNG, published=True):
    loc = Location(
        user_id=user.id, name="Kennel", address1="1 Rd", city="Austin", state="TX",
        country="US", zipcode="78701", location_type="user", is_published=published,
        latitude=lat, longitude=lng, coordinates=WKTElement(f"POINT({lng} {lat})", srid=4326),
        phone=phone, show_phone=show_phone,
    )
    session.add(loc)
    await session.flush()
    return loc


async def _with_parent(session, user, breed, **kw):
    loc = await _location(session, user, **kw)
    session.add(Pet(user_id=user.id, name="Parent", breed_id=breed.id, location_id=loc.id))
    await session.flush()
    return loc


async def _offspring(session, user, breed, *, status="Available", published=True):
    breeding = Breeding(user_id=user.id, date_of_litter=date(2026, 9, 1), is_active=True, status="Started")
    session.add(breeding)
    await session.flush()
    o = Offspring(
        breeding_id=breeding.id, user_id=user.id, breed_id=breed.id, gender="Male",
        date_of_birth=date(2026, 9, 1), status=status, is_published=published,
    )
    session.add(o)
    await session.flush()
    return o


async def _other_breeder(session, email="other@example.com"):
    u = User(email=email, hashed_password="x", name="Other", breedery_name="Other Kennel",
             is_active=True, is_verified=True, is_breeder=True)
    session.add(u)
    await session.flush()
    return u


@pytest.mark.asyncio
async def test_count_includes_only_available_published(unauthenticated_client, async_session, test_breeder, test_breed):
    await _with_parent(async_session, test_breeder, test_breed)
    await _offspring(async_session, test_breeder, test_breed)
    await _offspring(async_session, test_breeder, test_breed)
    await _offspring(async_session, test_breeder, test_breed, status="Reserved")
    await _offspring(async_session, test_breeder, test_breed, published=False)
    await _offspring(async_session, test_breeder, test_breed, status="Archived")
    await async_session.commit()

    r = await unauthenticated_client.get("/api/search/breeders", params=SEARCH)
    assert r.status_code == 200, r.text
    [hit] = r.json()
    assert hit["available_offspring_count"] == 2


@pytest.mark.asyncio
async def test_has_offspring_filter(unauthenticated_client, async_session, test_breeder, test_breed):
    await _with_parent(async_session, test_breeder, test_breed)
    await _offspring(async_session, test_breeder, test_breed)
    empty = await _other_breeder(async_session)
    await _with_parent(async_session, empty, test_breed)
    await async_session.commit()

    all_hits = (await unauthenticated_client.get("/api/search/breeders", params=SEARCH)).json()
    assert {h["available_offspring_count"] for h in all_hits} == {0, 1}

    r = await unauthenticated_client.get("/api/search/breeders", params={**SEARCH, "has_offspring": "true"})
    assert r.status_code == 200, r.text
    hits = r.json()
    assert [h["user_id"] for h in hits] == [str(test_breeder.id)]


@pytest.mark.asyncio
async def test_phone_only_when_shown(unauthenticated_client, async_session, test_breeder, test_breed):
    await _with_parent(async_session, test_breeder, test_breed, phone="512-555-0100", show_phone=False)
    other = await _other_breeder(async_session)
    await _with_parent(async_session, other, test_breed, phone="512-555-0199", show_phone=True)
    await async_session.commit()

    r = await unauthenticated_client.get("/api/search/breeders", params=SEARCH)
    by_user = {h["user_id"]: h for h in r.json()}
    assert by_user[str(test_breeder.id)]["phone"] is None
    assert by_user[str(other.id)]["phone"] == "512-555-0199"
    assert "512-555-0100" not in r.text


@pytest.mark.asyncio
async def test_breeder_without_kennel_name_shows_their_name(unauthenticated_client, async_session, test_breed):
    u = User(email="noname@example.com", hashed_password="x", name="Jane Doe", breedery_name=None,
             is_active=True, is_verified=True, is_breeder=True)
    nameless = User(email="nameless@example.com", hashed_password="x", name=None, breedery_name=None,
                    is_active=True, is_verified=True, is_breeder=True)
    async_session.add_all([u, nameless])
    await async_session.flush()
    await _with_parent(async_session, u, test_breed)
    await _with_parent(async_session, nameless, test_breed, lat=30.21)
    await async_session.commit()

    r = await unauthenticated_client.get("/api/search/breeders", params=SEARCH)
    names = {h["user_id"]: h["breeder_name"] for h in r.json()}
    assert names[str(u.id)] == "Jane Doe"
    assert names[str(nameless.id)] == "Breeder"
    assert "didn't" not in r.text
