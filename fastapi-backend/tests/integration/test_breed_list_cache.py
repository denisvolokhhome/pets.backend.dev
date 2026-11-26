"""GET /api/breeds is cached in-process; writes through the API must invalidate it."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.breed import Breed


@pytest.mark.asyncio
async def test_list_is_cached_and_sets_cache_control(
    unauthenticated_client: AsyncClient, async_session: AsyncSession
):
    async_session.add(Breed(name="Akita", kind="dog"))
    await async_session.commit()

    first = await unauthenticated_client.get("/api/breeds/")
    assert first.status_code == 200
    assert first.headers["cache-control"].startswith("public, max-age=")
    assert [b["name"] for b in first.json()] == ["Akita"]

    # Written behind the API's back (like the seed script): served from cache until the TTL
    async_session.add(Breed(name="Basenji", kind="dog"))
    await async_session.commit()
    second = await unauthenticated_client.get("/api/breeds/")
    assert [b["name"] for b in second.json()] == ["Akita"]


@pytest.mark.asyncio
async def test_api_writes_invalidate_the_cache(
    unauthenticated_client: AsyncClient, async_session: AsyncSession
):
    breed = Breed(name="Beagle", kind="dog")
    async_session.add(breed)
    await async_session.commit()
    breed_id = breed.id
    assert [b["name"] for b in (await unauthenticated_client.get("/api/breeds/")).json()] == ["Beagle"]

    updated = await unauthenticated_client.put(f"/api/breeds/{breed_id}", json={"name": "Beagle Harrier"})
    assert updated.status_code == 200
    assert [b["name"] for b in (await unauthenticated_client.get("/api/breeds/")).json()] == ["Beagle Harrier"]

    await unauthenticated_client.delete(f"/api/breeds/{breed_id}")
    assert (await unauthenticated_client.get("/api/breeds/")).json() == []


@pytest.mark.asyncio
async def test_cache_is_keyed_by_query(unauthenticated_client: AsyncClient, async_session: AsyncSession):
    async_session.add_all([Breed(name="Boxer", kind="dog"), Breed(name="Siamese", kind="cat")])
    await async_session.commit()

    cats = await unauthenticated_client.get("/api/breeds/", params={"kind": "cat"})
    dogs = await unauthenticated_client.get("/api/breeds/", params={"kind": "dog"})
    assert [b["name"] for b in cats.json()] == ["Siamese"]
    assert [b["name"] for b in dogs.json()] == ["Boxer"]


@pytest.mark.asyncio
async def test_no_trailing_slash_is_served_without_redirect(unauthenticated_client: AsyncClient):
    resp = await unauthenticated_client.get("/api/breeds", follow_redirects=False)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cache_size_is_bounded(unauthenticated_client: AsyncClient):
    from app.routers import breeds

    for limit in range(1, breeds.LIST_CACHE_MAX_ENTRIES + 10):
        assert (await unauthenticated_client.get("/api/breeds/", params={"limit": limit})).status_code == 200
    await unauthenticated_client.get("/api/breeds/", params={"skip": 5})
    assert len(breeds._list_cache) == breeds.LIST_CACHE_MAX_ENTRIES
    assert all(limit < breeds.LIST_CACHE_MAX_ENTRIES + 1 for limit, _ in breeds._list_cache)
