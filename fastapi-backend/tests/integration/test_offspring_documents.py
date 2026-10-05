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


@pytest.mark.asyncio
async def test_create_offspring_respects_is_published(
    unauthenticated_client: AsyncClient,
    test_breeder: User,
    test_breeding,
):
    """is_published sent at creation is stored (regression: it was silently dropped)."""
    token = await _breeder_token(unauthenticated_client, test_breeder)
    response = await unauthenticated_client.post(
        "/api/offsprings/",
        json={
            "breeding_id": test_breeding.id,
            "name": "Published Pup",
            "gender": "Male",
            "date_of_birth": "2026-01-15",
            "status": "Available",
            "is_published": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["is_published"] is True


@pytest.mark.asyncio
async def test_public_offspring_includes_application_form(
    unauthenticated_client: AsyncClient,
    async_session,
    test_breeder: User,
    test_offspring: Offspring,
):
    """Pet seekers must receive the breeding's application form with a public listing.

    Regression: LitterRead omitted application_form, so the form was never shown.
    """
    token = await _breeder_token(unauthenticated_client, test_breeder)
    auth = {"Authorization": f"Bearer {token}"}
    form = await unauthenticated_client.put(
        f"/api/breedings/{test_offspring.breeding_id}/application-form",
        json={"form_fields": [{"id": "q1", "type": "text", "label": "Do you have a yard?", "required": True}]},
        headers=auth,
    )
    assert form.status_code in (200, 201)
    publish = await unauthenticated_client.put(
        f"/api/offsprings/{test_offspring.id}", json={"is_published": True}, headers=auth
    )
    assert publish.status_code == 200

    # Tests share one session across requests; drop cached objects like a fresh request would
    async_session.expunge_all()
    response = await unauthenticated_client.get(f"/api/offsprings/public/{test_offspring.id}")
    assert response.status_code == 200
    fields = response.json()["breeding"]["application_form"]["form_fields"]
    assert fields[0]["label"] == "Do you have a yard?"
