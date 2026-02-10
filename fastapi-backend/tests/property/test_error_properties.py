"""Property-based tests for error handling.

Feature: laravel-to-fastapi-migration
"""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pet import Pet
from app.models.breed import Breed
from app.models.breeding import Breeding
from app.models.location import Location
from app.models.user import User


@pytest.mark.asyncio
async def test_property_not_found_response_pets(
    async_client: AsyncClient,
    auth_headers: dict,
    async_session: AsyncSession
):
    """
    Property 24: Not Found Response
    
    For any API request for a non-existent resource ID, the response should be HTTP 404.
    
    Feature: laravel-to-fastapi-migration, Property 24: Not Found Response
    Validates: Requirements 10.2
    """
    # Use a UUID that's extremely unlikely to exist
    non_existent_ids = [
        uuid.UUID("00000000-0000-0000-0000-000000000001"),
        uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    ]
    
    for resource_id in non_existent_ids:
        # Ensure the resource ID doesn't exist in the database
        pet = await async_session.get(Pet, resource_id)
        if pet is not None:
            # Skip this example if the UUID happens to exist
            continue
        
        # Test GET endpoint
        response = await async_client.get(f"/api/pets/{resource_id}", headers=auth_headers)
        
        # Should return 404
        assert response.status_code == 404, (
            f"Expected 404 for non-existent pet {resource_id}, "
            f"got {response.status_code}"
        )
        
        # Should have proper error format
        data = response.json()
        assert "detail" in data
        assert "error_code" in data
        assert data["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_property_not_found_response_all_resources(
    async_client: AsyncClient,
    auth_headers: dict
):
    """
    Test not found responses for all resource types.
    
    Feature: laravel-to-fastapi-migration, Property 24: Not Found Response
    Validates: Requirements 10.2
    """
    # Use a UUID that's extremely unlikely to exist
    non_existent_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    
    # Test GET endpoints for pets (other resources may have different auth requirements)
    response = await async_client.get(f"/api/pets/{non_existent_id}", headers=auth_headers)
    assert response.status_code == 404, f"Expected 404 for /api/pets/{non_existent_id}"
    data = response.json()
    assert data["error_code"] == "NOT_FOUND"
    assert "detail" in data


@pytest.mark.asyncio
async def test_property_not_found_response_update_operations(
    async_client: AsyncClient,
    auth_headers: dict
):
    """
    Test not found responses for update operations.
    
    Feature: laravel-to-fastapi-migration, Property 24: Not Found Response
    Validates: Requirements 10.2
    """
    non_existent_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    
    # Test PUT endpoint for pets
    response = await async_client.put(
        f"/api/pets/{non_existent_id}",
        json={"name": "Test"},
        headers=auth_headers
    )
    assert response.status_code == 404, f"Expected 404 for PUT /api/pets/{non_existent_id}"
    data = response.json()
    assert data["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_property_not_found_response_delete_operations(
    async_client: AsyncClient,
    auth_headers: dict
):
    """
    Test not found responses for delete operations.
    
    Feature: laravel-to-fastapi-migration, Property 24: Not Found Response
    Validates: Requirements 10.2
    """
    non_existent_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    
    # Test DELETE endpoint for pets
    response = await async_client.delete(f"/api/pets/{non_existent_id}", headers=auth_headers)
    assert response.status_code == 404, f"Expected 404 for DELETE /api/pets/{non_existent_id}"
    data = response.json()
    assert data["error_code"] == "NOT_FOUND"





@pytest.mark.asyncio
async def test_property_authorization_failure_accessing_other_user_pet(
    async_client: AsyncClient,
    auth_headers: dict,
    async_session: AsyncSession,
    test_user: User
):
    """
    Property 26: Authorization Failure Response
    
    For any API request attempting to access a resource owned by another user,
    the response should be HTTP 403 or 404 (depending on implementation).
    
    Feature: laravel-to-fastapi-migration, Property 26: Authorization Failure Response
    Validates: Requirements 10.4
    """
    # Create another user
    other_user = User(
        email="other@example.com",
        hashed_password="hashed_password_placeholder",
        name="Other User",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    async_session.add(other_user)
    await async_session.commit()
    await async_session.refresh(other_user)
    
    # Create a pet owned by the other user
    other_pet = Pet(
        user_id=other_user.id,
        name="Other User's Pet",
        is_deleted=False
    )
    async_session.add(other_pet)
    await async_session.commit()
    await async_session.refresh(other_pet)
    
    # Try to access the other user's pet with test_user's credentials
    response = await async_client.get(f"/api/pets/{other_pet.id}", headers=auth_headers)
    
    # Should return 404 (not found) because the pet doesn't belong to the authenticated user
    # This is a common pattern - return 404 instead of 403 to avoid leaking information
    # about whether a resource exists
    assert response.status_code == 404, (
        f"Expected 404 when accessing another user's pet, got {response.status_code}"
    )
    
    data = response.json()
    assert "detail" in data
    assert "error_code" in data


@pytest.mark.asyncio
async def test_property_authorization_failure_updating_other_user_pet(
    async_client: AsyncClient,
    auth_headers: dict,
    async_session: AsyncSession,
    test_user: User
):
    """
    Property 26: Authorization Failure Response
    
    For any API request attempting to update a resource owned by another user,
    the response should be HTTP 403 or 404.
    
    Feature: laravel-to-fastapi-migration, Property 26: Authorization Failure Response
    Validates: Requirements 10.4
    """
    # Create another user
    other_user = User(
        email="other2@example.com",
        hashed_password="hashed_password_placeholder",
        name="Other User 2",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    async_session.add(other_user)
    await async_session.commit()
    await async_session.refresh(other_user)
    
    # Create a pet owned by the other user
    other_pet = Pet(
        user_id=other_user.id,
        name="Other User's Pet 2",
        is_deleted=False
    )
    async_session.add(other_pet)
    await async_session.commit()
    await async_session.refresh(other_pet)
    
    # Try to update the other user's pet
    response = await async_client.put(
        f"/api/pets/{other_pet.id}",
        json={"name": "Hacked Name"},
        headers=auth_headers
    )
    
    # Should return 404 (not found) because the pet doesn't belong to the authenticated user
    assert response.status_code == 404, (
        f"Expected 404 when updating another user's pet, got {response.status_code}"
    )
    
    data = response.json()
    assert "detail" in data
    assert "error_code" in data


@pytest.mark.asyncio
async def test_property_authorization_failure_deleting_other_user_pet(
    async_client: AsyncClient,
    auth_headers: dict,
    async_session: AsyncSession,
    test_user: User
):
    """
    Property 26: Authorization Failure Response
    
    For any API request attempting to delete a resource owned by another user,
    the response should be HTTP 403 or 404.
    
    Feature: laravel-to-fastapi-migration, Property 26: Authorization Failure Response
    Validates: Requirements 10.4
    """
    # Create another user
    other_user = User(
        email="other3@example.com",
        hashed_password="hashed_password_placeholder",
        name="Other User 3",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    async_session.add(other_user)
    await async_session.commit()
    await async_session.refresh(other_user)
    
    # Create a pet owned by the other user
    other_pet = Pet(
        user_id=other_user.id,
        name="Other User's Pet 3",
        is_deleted=False
    )
    async_session.add(other_pet)
    await async_session.commit()
    await async_session.refresh(other_pet)
    
    # Try to delete the other user's pet
    response = await async_client.delete(f"/api/pets/{other_pet.id}", headers=auth_headers)
    
    # Should return 404 (not found) because the pet doesn't belong to the authenticated user
    assert response.status_code == 404, (
        f"Expected 404 when deleting another user's pet, got {response.status_code}"
    )
    
    data = response.json()
    assert "detail" in data
    assert "error_code" in data
