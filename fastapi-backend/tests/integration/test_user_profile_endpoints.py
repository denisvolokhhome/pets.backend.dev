"""Integration tests for user profile endpoints.

Tests the complete user profile management flow including:
- Profile retrieval
- Profile updates
- Profile image upload
- Profile image replacement
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from io import BytesIO
from PIL import Image

from app.main import app
from app.database import get_async_session
from app.config import Settings


@pytest.fixture
async def client(async_session: AsyncSession):
    """Create test client with database session override."""
    
    async def override_get_async_session():
        yield async_session
    
    app.dependency_overrides[get_async_session] = override_get_async_session
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_client(client: AsyncClient):
    """Create authenticated test client with registered user."""
    # Register a user
    registration_data = {
        "email": "profileuser@example.com",
        "password": "SecurePassword123!",
    }
    
    await client.post("/api/auth/register", json=registration_data)
    
    # Login
    login_data = {
        "username": registration_data["email"],
        "password": registration_data["password"],
    }
    
    login_response = await client.post("/api/auth/jwt/login", data=login_data)
    token_data = login_response.json()
    
    # Set authorization header
    client.headers["Authorization"] = f"Bearer {token_data['access_token']}"
    
    return client


def create_test_image(width: int = 100, height: int = 100, format: str = "JPEG") -> BytesIO:
    """Create a test image in memory."""
    image = Image.new('RGB', (width, height), color='blue')
    buffer = BytesIO()
    image.save(buffer, format=format)
    buffer.seek(0)
    return buffer


@pytest.mark.asyncio
async def test_get_current_user_profile(authenticated_client: AsyncClient):
    """
    Test retrieving current user's profile.
    
    Validates: Requirements 8.1
    """
    response = await authenticated_client.get("/api/users/me")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify profile fields are present
    assert "id" in data
    assert "email" in data
    assert data["email"] == "profileuser@example.com"
    assert "breedery_name" in data
    assert "profile_image_path" in data
    assert "breedery_description" in data
    assert "search_tags" in data


@pytest.mark.asyncio
async def test_update_user_profile(authenticated_client: AsyncClient):
    """
    Test updating user profile information.
    
    Validates: Requirements 8.2, 3.6, 3.7
    """
    # Update profile
    update_data = {
        "breedery_name": "Golden Paws Kennel",
        "breedery_description": "Premium Golden Retriever breeder since 2020",
        "search_tags": ["golden-retriever", "puppies", "akc-registered"]
    }
    
    response = await authenticated_client.patch("/api/users/me", json=update_data)
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify updates were applied
    assert data["breedery_name"] == update_data["breedery_name"]
    assert data["breedery_description"] == update_data["breedery_description"]
    assert data["search_tags"] == update_data["search_tags"]
    
    # Verify persistence by fetching again
    get_response = await authenticated_client.get("/api/users/me")
    assert get_response.status_code == 200
    get_data = get_response.json()
    
    assert get_data["breedery_name"] == update_data["breedery_name"]
    assert get_data["breedery_description"] == update_data["breedery_description"]
    assert get_data["search_tags"] == update_data["search_tags"]


@pytest.mark.asyncio
async def test_partial_profile_update(authenticated_client: AsyncClient):
    """
    Test partial profile update (only some fields).
    
    Validates: Requirements 8.2, 3.6
    """
    # Set initial profile
    initial_data = {
        "breedery_name": "Initial Name",
        "breedery_description": "Initial Description",
        "search_tags": ["tag1", "tag2"]
    }
    
    await authenticated_client.patch("/api/users/me", json=initial_data)
    
    # Update only breedery_name
    partial_update = {
        "breedery_name": "Updated Name"
    }
    
    response = await authenticated_client.patch("/api/users/me", json=partial_update)
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify only breedery_name changed
    assert data["breedery_name"] == "Updated Name"
    assert data["breedery_description"] == "Initial Description"
    assert data["search_tags"] == ["tag1", "tag2"]


@pytest.mark.asyncio
async def test_upload_profile_image(authenticated_client: AsyncClient):
    """
    Test uploading a profile image.
    
    Validates: Requirements 8.3, 9.1, 9.2, 9.3, 9.4, 9.5
    """
    # Create test image
    image_buffer = create_test_image(width=200, height=200)
    
    # Upload image
    files = {
        "file": ("test_profile.jpg", image_buffer, "image/jpeg")
    }
    
    response = await authenticated_client.post("/api/users/me/profile-image", files=files)
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response
    assert "profile_image_path" in data
    assert "message" in data
    assert data["message"] == "Profile image uploaded successfully"
    assert data["profile_image_path"].startswith("storage/app/profile_")
    
    # Verify profile was updated
    profile_response = await authenticated_client.get("/api/users/me")
    profile_data = profile_response.json()
    assert profile_data["profile_image_path"] == data["profile_image_path"]
    
    # Verify image file exists
    settings = Settings()
    storage_path = Path(settings.storage_path).parent
    image_path = storage_path / data["profile_image_path"]
    assert image_path.exists()
    
    # Cleanup
    if image_path.exists():
        image_path.unlink()


@pytest.mark.asyncio
async def test_replace_profile_image(authenticated_client: AsyncClient):
    """
    Test replacing an existing profile image.
    
    Validates: Requirements 8.3, 9.7
    """
    settings = Settings()
    storage_path = Path(settings.storage_path).parent
    
    # Upload first image
    first_image = create_test_image(width=150, height=150)
    files1 = {
        "file": ("first.jpg", first_image, "image/jpeg")
    }
    
    response1 = await authenticated_client.post("/api/users/me/profile-image", files=files1)
    assert response1.status_code == 200
    first_path = response1.json()["profile_image_path"]
    first_full_path = storage_path / first_path
    
    # Verify first image exists
    assert first_full_path.exists()
    
    # Upload second image (should replace first)
    second_image = create_test_image(width=200, height=200)
    files2 = {
        "file": ("second.jpg", second_image, "image/jpeg")
    }
    
    response2 = await authenticated_client.post("/api/users/me/profile-image", files=files2)
    assert response2.status_code == 200
    second_path = response2.json()["profile_image_path"]
    second_full_path = storage_path / second_path
    
    # Verify second image exists
    assert second_full_path.exists()
    
    # Verify first image was deleted
    assert not first_full_path.exists(), "Old profile image should be deleted"
    
    # Verify profile points to new image
    profile_response = await authenticated_client.get("/api/users/me")
    profile_data = profile_response.json()
    assert profile_data["profile_image_path"] == second_path
    
    # Cleanup
    if second_full_path.exists():
        second_full_path.unlink()


@pytest.mark.asyncio
async def test_upload_invalid_file_type(authenticated_client: AsyncClient):
    """
    Test that uploading invalid file type is rejected.
    
    Validates: Requirements 9.1
    """
    # Create a text file instead of image
    text_buffer = BytesIO(b"This is not an image")
    
    files = {
        "file": ("test.txt", text_buffer, "text/plain")
    }
    
    response = await authenticated_client.post("/api/users/me/profile-image", files=files)
    
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "Invalid file type" in data["detail"]


@pytest.mark.asyncio
async def test_upload_oversized_image(authenticated_client: AsyncClient):
    """
    Test that uploading oversized image is rejected.
    
    Validates: Requirements 9.2
    """
    # Create a large image (6MB, exceeds 5MB limit)
    # Create a very large image
    large_image = Image.new('RGB', (5000, 5000), color='red')
    buffer = BytesIO()
    large_image.save(buffer, format='JPEG', quality=100)
    buffer.seek(0)
    
    # Verify buffer is larger than 5MB
    buffer_size = len(buffer.getvalue())
    assert buffer_size > 5 * 1024 * 1024, "Test image should be larger than 5MB"
    
    files = {
        "file": ("large.jpg", buffer, "image/jpeg")
    }
    
    response = await authenticated_client.post("/api/users/me/profile-image", files=files)
    
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "exceeds maximum allowed size" in data["detail"]


@pytest.mark.asyncio
async def test_get_profile_image(authenticated_client: AsyncClient):
    """
    Test retrieving profile image.
    
    Validates: Requirements 8.3, 9.6
    """
    # Upload an image first
    image_buffer = create_test_image(width=100, height=100)
    files = {
        "file": ("profile.jpg", image_buffer, "image/jpeg")
    }
    
    upload_response = await authenticated_client.post("/api/users/me/profile-image", files=files)
    assert upload_response.status_code == 200
    image_path = upload_response.json()["profile_image_path"]
    
    # Get the image
    response = await authenticated_client.get("/api/users/me/profile-image")
    
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
    
    # Verify we got image data
    assert len(response.content) > 0
    
    # Cleanup
    settings = Settings()
    storage_path = Path(settings.storage_path).parent
    full_path = storage_path / image_path
    if full_path.exists():
        full_path.unlink()


@pytest.mark.asyncio
async def test_get_profile_image_not_found(authenticated_client: AsyncClient):
    """
    Test getting profile image when user has no image.
    
    Validates: Requirements 8.3
    """
    response = await authenticated_client.get("/api/users/me/profile-image")
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "no profile image" in data["detail"].lower()


@pytest.mark.asyncio
async def test_profile_endpoints_require_authentication(client: AsyncClient):
    """
    Test that profile endpoints require authentication.
    
    Validates: Requirements 8.8
    """
    # Try to get profile without auth
    response1 = await client.get("/api/users/me")
    assert response1.status_code == 401
    
    # Try to update profile without auth
    response2 = await client.patch("/api/users/me", json={"breedery_name": "Test"})
    assert response2.status_code == 401
    
    # Try to upload image without auth
    image_buffer = create_test_image()
    files = {"file": ("test.jpg", image_buffer, "image/jpeg")}
    response3 = await client.post("/api/users/me/profile-image", files=files)
    assert response3.status_code == 401
    
    # Try to get image without auth
    response4 = await client.get("/api/users/me/profile-image")
    assert response4.status_code == 401


@pytest.mark.asyncio
async def test_update_profile_with_empty_tags(authenticated_client: AsyncClient):
    """
    Test updating profile with empty tags array.
    
    Validates: Requirements 3.4, 3.6
    """
    update_data = {
        "breedery_name": "Test Kennel",
        "search_tags": []
    }
    
    response = await authenticated_client.patch("/api/users/me", json=update_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["search_tags"] == []


@pytest.mark.asyncio
async def test_update_profile_with_null_values(authenticated_client: AsyncClient):
    """
    Test updating profile with null values to clear fields.
    
    Validates: Requirements 3.6
    """
    # Set initial values
    initial_data = {
        "breedery_name": "Initial Name",
        "breedery_description": "Initial Description",
        "search_tags": ["tag1"]
    }
    
    await authenticated_client.patch("/api/users/me", json=initial_data)
    
    # Clear values with null
    clear_data = {
        "breedery_name": None,
        "breedery_description": None,
        "search_tags": None
    }
    
    response = await authenticated_client.patch("/api/users/me", json=clear_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["breedery_name"] is None
    assert data["breedery_description"] is None
    assert data["search_tags"] is None


@pytest.mark.asyncio
async def test_profile_update_preserves_other_fields(authenticated_client: AsyncClient):
    """
    Test that profile updates don't affect other user fields.
    
    Validates: Requirements 3.6
    """
    # Get initial user data
    initial_response = await authenticated_client.get("/api/users/me")
    initial_data = initial_response.json()
    initial_email = initial_data["email"]
    initial_id = initial_data["id"]
    
    # Update profile
    update_data = {
        "breedery_name": "New Kennel Name"
    }
    
    await authenticated_client.patch("/api/users/me", json=update_data)
    
    # Verify other fields unchanged
    updated_response = await authenticated_client.get("/api/users/me")
    updated_data = updated_response.json()
    
    assert updated_data["email"] == initial_email
    assert updated_data["id"] == initial_id
    assert updated_data["is_active"] == initial_data["is_active"]
