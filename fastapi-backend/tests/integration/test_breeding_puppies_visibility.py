"""Breeding detail/list report whether each puppy is visible to pet seekers."""
import pytest

from tests.integration.test_breeding_planner_api import _auth


@pytest.mark.asyncio
async def test_puppies_carry_is_published(unauthenticated_client, async_session, test_breeder, test_breeding, test_offspring):
    h = await _auth(unauthenticated_client, test_breeder)

    detail = await unauthenticated_client.get(f"/api/breedings/{test_breeding.id}", headers=h)
    assert detail.status_code == 200, detail.text
    assert detail.json()["puppies"][0]["is_published"] is False

    test_offspring.is_published = True
    await async_session.commit()
    listing = await unauthenticated_client.get("/api/breedings/", headers=h)
    assert listing.status_code == 200, listing.text
    [b] = [b for b in listing.json() if b["id"] == test_breeding.id]
    assert b["puppies"][0]["is_published"] is True
