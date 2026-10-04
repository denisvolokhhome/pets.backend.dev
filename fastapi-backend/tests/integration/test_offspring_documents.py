"""Integration tests for offspring document endpoints."""
import pytest
from httpx import AsyncClient

from app.models.user import User
from app.models.offspring import Offspring


async def _breeder_token(client: AsyncClient, breeder: User) -> str:
    response = await client.post(
        "/api/auth/jwt/login",
        data={"username": breeder.email, "password": "testpass123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_list_offspring_documents_empty(
    unauthenticated_client: AsyncClient,
    test_breeder: User,
    test_offspring: Offspring,
):
    """An offspring with no documents lists as an empty array (regression: was a 500)."""
    token = await _breeder_token(unauthenticated_client, test_breeder)

    response = await unauthenticated_client.get(
        f"/api/offsprings/{test_offspring.id}/documents",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == []
