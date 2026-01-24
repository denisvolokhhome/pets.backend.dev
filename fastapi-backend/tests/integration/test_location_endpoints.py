"""Integration tests for locations API endpoints.

Tests the complete location management workflow including:
- Creating locations
- Listing user's locations
- Getting single location
- Updating locations
- Deleting locations
- Authorization (users can only access their own locations)
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database import get_async_session
from app.models.location import Location
from app.models.user import User
from app.dependencies import current_active_user


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


from contextvars import ContextVar

# Context variable to track the current user for each request
_current_test_user: ContextVar[User] = ContextVar('_current_test_user', default=None)


@pytest.fixture
async def authenticated_client(async_session: AsyncSession, test_user: User):
    """Create authenticated test client."""
    
    async def override_get_async_session():
        yield async_session
    
    async def override_current_active_user():
        # Get the user from context variable set by the client
        user = _current_test_user.get()
        if user is None:
            return test_user
        return user
    
    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[current_active_user] = override_current_active_user
    
    transport = ASGITransport(app=app)
    
    class UserAwareClient(AsyncClient):
        """Client that sets the user context before each request."""
        def __init__(self, *args, user=None, **kwargs):
            super().__init__(*args, **kwargs)
            self._user = user
        
        async def request(self, *args, **kwargs):
            # Set the user context for this request
            token = _current_test_user.set(self._user)
            try:
                return await super().request(*args, **kwargs)
            finally:
                _current_test_user.reset(token)
    
    async with UserAwareClient(transport=transport, base_url="http://test", user=test_user) as ac:
        yield ac


@pytest.fixture
async def other_user(async_session: AsyncSession):
    """Create another test user for authorization tests."""
    import uuid
    user = User(
        email=f"other-{uuid.uuid4()}@example.com",
        hashed_password="hashed_password",
        name="Other User",
        is_active=True,
        is_superuser=False,
        is_verified=False
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def other_authenticated_client(async_session: AsyncSession, other_user: User):
    """Create authenticated test client for other user."""
    
    async def override_get_async_session():
        yield async_session
    
    async def override_current_active_user():
        # Get the user from context variable set by the client
        user = _current_test_user.get()
        if user is None:
            return other_user
        return user
    
    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[current_active_user] = override_current_active_user
    
    transport = ASGITransport(app=app)
    
    class UserAwareClient(AsyncClient):
        """Client that sets the user context before each request."""
        def __init__(self, *args, user=None, **kwargs):
            super().__init__(*args, **kwargs)
            self._user = user
        
        async def request(self, *args, **kwargs):
            # Set the user context for this request
            token = _current_test_user.set(self._user)
            try:
                return await super().request(*args, **kwargs)
            finally:
                _current_test_user.reset(token)
    
    async with UserAwareClient(transport=transport, base_url="http://test", user=other_user) as ac:
        yield ac


@pytest.fixture(autouse=True)
async def cleanup_overrides():
    """Clean up dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()
    _current_test_user.set(None)


class TestLocationCreation:
    """Integration tests for location creation."""

    @pytest.mark.asyncio
    async def test_create_location_with_all_fields(self, authenticated_client: AsyncClient):
        """
        Test creating a location with all fields populated.
        
        Validates: Requirements 8.1, 13.5
        """
        location_data = {
            "name": "Main Kennel",
            "address1": "123 Main Street",
            "address2": "Suite 100",
            "city": "Springfield",
            "state": "Illinois",
            "country": "USA",
            "zipcode": "62701",
            "location_type": "user"
        }
        
        response = await authenticated_client.post("/api/locations/", json=location_data)
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify response contains all fields
        assert "id" in data
        assert data["name"] == location_data["name"]
        assert data["address1"] == location_data["address1"]
        assert data["address2"] == location_data["address2"]
        assert data["city"] == location_data["city"]
        assert data["state"] == location_data["state"]
        assert data["country"] == location_data["country"]
        assert data["zipcode"] == location_data["zipcode"]
        assert data["location_type"] == location_data["location_type"]
        assert "user_id" in data
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_location_without_address2(self, authenticated_client: AsyncClient):
        """
        Test creating a location without optional address2 field.
        
        Validates: Requirements 8.1, 13.5
        """
        location_data = {
            "name": "Secondary Location",
            "address1": "456 Oak Avenue",
            "city": "Chicago",
            "state": "Illinois",
            "country": "USA",
            "zipcode": "60601",
            "location_type": "pet"
        }
        
        response = await authenticated_client.post("/api/locations/", json=location_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["name"] == location_data["name"]
        assert data["address2"] is None

    @pytest.mark.asyncio
    async def test_create_location_missing_required_field_fails(self, authenticated_client: AsyncClient):
        """
        Test that creating a location without required fields fails validation.
        
        Validates: Requirements 8.1, 13.5
        """
        location_data = {
            "name": "Incomplete Location",
            "address1": "123 Test St"
            # Missing city, state, country, zipcode, location_type
        }
        
        response = await authenticated_client.post("/api/locations/", json=location_data)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_location_requires_authentication(self, client: AsyncClient):
        """
        Test that creating a location requires authentication.
        
        Validates: Requirements 8.1, 13.5
        """
        location_data = {
            "name": "Test Location",
            "address1": "123 Test St",
            "city": "Test City",
            "state": "Test State",
            "country": "Test Country",
            "zipcode": "12345",
            "location_type": "user"
        }
        
        response = await client.post("/api/locations/", json=location_data)
        # Should fail without authentication
        assert response.status_code in [401, 403]


class TestLocationListing:
    """Integration tests for listing locations."""

    @pytest.mark.asyncio
    async def test_list_locations_empty(self, authenticated_client: AsyncClient):
        """
        Test listing locations when user has no locations.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        response = await authenticated_client.get("/api/locations/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_locations_with_data(self, authenticated_client: AsyncClient):
        """
        Test listing locations with multiple locations for user.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        # Create multiple locations
        locations_data = [
            {
                "name": "Location 1",
                "address1": "123 First St",
                "city": "City1",
                "state": "State1",
                "country": "Country1",
                "zipcode": "11111",
                "location_type": "user"
            },
            {
                "name": "Location 2",
                "address1": "456 Second Ave",
                "city": "City2",
                "state": "State2",
                "country": "Country2",
                "zipcode": "22222",
                "location_type": "pet"
            },
            {
                "name": "Location 3",
                "address1": "789 Third Blvd",
                "city": "City3",
                "state": "State3",
                "country": "Country3",
                "zipcode": "33333",
                "location_type": "user"
            }
        ]
        
        created_ids = []
        for location_data in locations_data:
            response = await authenticated_client.post("/api/locations/", json=location_data)
            assert response.status_code == 201
            created_ids.append(response.json()["id"])
        
        # List all locations
        response = await authenticated_client.get("/api/locations/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) >= len(locations_data)
        
        # Verify our created locations are in the list
        location_ids = [l["id"] for l in data]
        for location_id in created_ids:
            assert location_id in location_ids

    @pytest.mark.asyncio
    async def test_list_locations_only_shows_user_locations(
        self,
        authenticated_client: AsyncClient,
        other_authenticated_client: AsyncClient
    ):
        """
        Test that users can only see their own locations.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        # Create location for first user
        user1_location = {
            "name": "User 1 Location",
            "address1": "123 User1 St",
            "city": "City1",
            "state": "State1",
            "country": "Country1",
            "zipcode": "11111",
            "location_type": "user"
        }
        
        response1 = await authenticated_client.post("/api/locations/", json=user1_location)
        assert response1.status_code == 201
        user1_location_id = response1.json()["id"]
        
        # Create location for second user
        user2_location = {
            "name": "User 2 Location",
            "address1": "456 User2 Ave",
            "city": "City2",
            "state": "State2",
            "country": "Country2",
            "zipcode": "22222",
            "location_type": "user"
        }
        
        response2 = await other_authenticated_client.post("/api/locations/", json=user2_location)
        assert response2.status_code == 201
        user2_location_id = response2.json()["id"]
        
        # List locations for first user
        list_response1 = await authenticated_client.get("/api/locations/")
        assert list_response1.status_code == 200
        user1_locations = list_response1.json()
        user1_location_ids = [l["id"] for l in user1_locations]
        
        # Verify first user sees their location but not second user's
        assert user1_location_id in user1_location_ids
        assert user2_location_id not in user1_location_ids
        
        # List locations for second user
        list_response2 = await other_authenticated_client.get("/api/locations/")
        assert list_response2.status_code == 200
        user2_locations = list_response2.json()
        user2_location_ids = [l["id"] for l in user2_locations]
        
        # Verify second user sees their location but not first user's
        assert user2_location_id in user2_location_ids
        assert user1_location_id not in user2_location_ids

    @pytest.mark.asyncio
    async def test_list_locations_requires_authentication(self, client: AsyncClient):
        """
        Test that listing locations requires authentication.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        response = await client.get("/api/locations/")
        # Should fail without authentication
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_list_locations_pagination(self, authenticated_client: AsyncClient):
        """
        Test location listing with pagination parameters.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        # Create several locations
        for i in range(5):
            location_data = {
                "name": f"Pagination Test Location {i}",
                "address1": f"{i} Test St",
                "city": "Test City",
                "state": "Test State",
                "country": "Test Country",
                "zipcode": f"{i:05d}",
                "location_type": "user"
            }
            await authenticated_client.post("/api/locations/", json=location_data)
        
        # Test with limit
        response = await authenticated_client.get("/api/locations/?limit=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 3
        
        # Test with skip
        response = await authenticated_client.get("/api/locations/?skip=2&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2


class TestLocationRetrieval:
    """Integration tests for retrieving single location."""

    @pytest.mark.asyncio
    async def test_get_location_by_id(self, authenticated_client: AsyncClient):
        """
        Test getting a single location by ID.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        # Create a location
        location_data = {
            "name": "Test Location for Retrieval",
            "address1": "123 Retrieval St",
            "city": "Retrieval City",
            "state": "Retrieval State",
            "country": "Retrieval Country",
            "zipcode": "99999",
            "location_type": "user"
        }
        
        create_response = await authenticated_client.post("/api/locations/", json=location_data)
        assert create_response.status_code == 201
        created_location = create_response.json()
        location_id = created_location["id"]
        
        # Get the location
        response = await authenticated_client.get(f"/api/locations/{location_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == location_id
        assert data["name"] == location_data["name"]
        assert data["address1"] == location_data["address1"]
        assert data["city"] == location_data["city"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_location_returns_404(self, authenticated_client: AsyncClient):
        """
        Test that getting a non-existent location returns 404.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        # Use a very high ID that shouldn't exist
        response = await authenticated_client.get("/api/locations/999999")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_get_other_user_location_returns_404(
        self,
        authenticated_client: AsyncClient,
        other_authenticated_client: AsyncClient
    ):
        """
        Test that users cannot access other users' locations.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        # Create location for other user
        location_data = {
            "name": "Other User Location",
            "address1": "123 Other St",
            "city": "Other City",
            "state": "Other State",
            "country": "Other Country",
            "zipcode": "88888",
            "location_type": "user"
        }
        
        create_response = await other_authenticated_client.post("/api/locations/", json=location_data)
        assert create_response.status_code == 201
        location_id = create_response.json()["id"]
        
        # Try to access with first user
        response = await authenticated_client.get(f"/api/locations/{location_id}")
        
        # Should return 404 (not found) to prevent information disclosure
        assert response.status_code == 404


class TestLocationUpdate:
    """Integration tests for updating locations."""

    @pytest.mark.asyncio
    async def test_update_location_all_fields(self, authenticated_client: AsyncClient):
        """
        Test updating all fields of a location.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        # Create a location
        location_data = {
            "name": "Original Name",
            "address1": "Original Address",
            "city": "Original City",
            "state": "Original State",
            "country": "Original Country",
            "zipcode": "00000",
            "location_type": "user"
        }
        
        create_response = await authenticated_client.post("/api/locations/", json=location_data)
        assert create_response.status_code == 201
        location_id = create_response.json()["id"]
        
        # Update the location
        update_data = {
            "name": "Updated Name",
            "address1": "Updated Address",
            "address2": "Updated Suite",
            "city": "Updated City",
            "state": "Updated State",
            "country": "Updated Country",
            "zipcode": "11111",
            "location_type": "pet"
        }
        
        response = await authenticated_client.put(f"/api/locations/{location_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == location_id
        assert data["name"] == update_data["name"]
        assert data["address1"] == update_data["address1"]
        assert data["address2"] == update_data["address2"]
        assert data["city"] == update_data["city"]
        assert data["state"] == update_data["state"]
        assert data["country"] == update_data["country"]
        assert data["zipcode"] == update_data["zipcode"]
        assert data["location_type"] == update_data["location_type"]

    @pytest.mark.asyncio
    async def test_update_location_partial_fields(self, authenticated_client: AsyncClient):
        """
        Test updating only some fields of a location.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        # Create a location
        location_data = {
            "name": "Partial Update Test",
            "address1": "123 Test St",
            "city": "Test City",
            "state": "Test State",
            "country": "Test Country",
            "zipcode": "12345",
            "location_type": "user"
        }
        
        create_response = await authenticated_client.post("/api/locations/", json=location_data)
        assert create_response.status_code == 201
        created_location = create_response.json()
        location_id = created_location["id"]
        
        # Update only the name and city
        update_data = {
            "name": "Updated Name Only",
            "city": "Updated City Only"
        }
        
        response = await authenticated_client.put(f"/api/locations/{location_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == location_id
        assert data["name"] == update_data["name"]
        assert data["city"] == update_data["city"]
        # Other fields should remain unchanged
        assert data["address1"] == location_data["address1"]
        assert data["state"] == location_data["state"]
        assert data["country"] == location_data["country"]
        assert data["zipcode"] == location_data["zipcode"]
        assert data["location_type"] == location_data["location_type"]

    @pytest.mark.asyncio
    async def test_update_nonexistent_location_returns_404(self, authenticated_client: AsyncClient):
        """
        Test that updating a non-existent location returns 404.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        update_data = {"name": "Updated Name"}
        
        response = await authenticated_client.put("/api/locations/999999", json=update_data)
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_update_other_user_location_returns_404(
        self,
        authenticated_client: AsyncClient,
        other_authenticated_client: AsyncClient
    ):
        """
        Test that users cannot update other users' locations.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        # Create location for other user
        location_data = {
            "name": "Other User Location",
            "address1": "123 Other St",
            "city": "Other City",
            "state": "Other State",
            "country": "Other Country",
            "zipcode": "88888",
            "location_type": "user"
        }
        
        create_response = await other_authenticated_client.post("/api/locations/", json=location_data)
        assert create_response.status_code == 201
        location_id = create_response.json()["id"]
        
        # Try to update with first user
        update_data = {"name": "Hacked Name"}
        response = await authenticated_client.put(f"/api/locations/{location_id}", json=update_data)
        
        # Should return 404 (not found)
        assert response.status_code == 404


class TestLocationDeletion:
    """Integration tests for deleting locations."""

    @pytest.mark.asyncio
    async def test_delete_location(self, authenticated_client: AsyncClient):
        """
        Test deleting a location.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        # Create a location
        location_data = {
            "name": "Location to Delete",
            "address1": "123 Delete St",
            "city": "Delete City",
            "state": "Delete State",
            "country": "Delete Country",
            "zipcode": "77777",
            "location_type": "user"
        }
        
        create_response = await authenticated_client.post("/api/locations/", json=location_data)
        assert create_response.status_code == 201
        location_id = create_response.json()["id"]
        
        # Delete the location
        response = await authenticated_client.delete(f"/api/locations/{location_id}")
        
        assert response.status_code == 204
        
        # Verify location is gone
        get_response = await authenticated_client.get(f"/api/locations/{location_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_location_returns_404(self, authenticated_client: AsyncClient):
        """
        Test that deleting a non-existent location returns 404.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        response = await authenticated_client.delete("/api/locations/999999")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_delete_other_user_location_returns_404(
        self,
        authenticated_client: AsyncClient,
        other_authenticated_client: AsyncClient
    ):
        """
        Test that users cannot delete other users' locations.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        # Create location for other user
        location_data = {
            "name": "Other User Location",
            "address1": "123 Other St",
            "city": "Other City",
            "state": "Other State",
            "country": "Other Country",
            "zipcode": "88888",
            "location_type": "user"
        }
        
        create_response = await other_authenticated_client.post("/api/locations/", json=location_data)
        assert create_response.status_code == 201
        location_id = create_response.json()["id"]
        
        # Try to delete with first user
        response = await authenticated_client.delete(f"/api/locations/{location_id}")
        
        # Should return 404 (not found)
        assert response.status_code == 404
        
        # Verify location still exists for other user
        get_response = await other_authenticated_client.get(f"/api/locations/{location_id}")
        assert get_response.status_code == 200


class TestLocationManagementWorkflow:
    """Integration tests for complete location management workflow."""

    @pytest.mark.asyncio
    async def test_complete_location_lifecycle(self, authenticated_client: AsyncClient):
        """
        Test complete location management workflow: create, read, update, delete.
        
        Validates: Requirements 8.1, 8.4, 13.5
        """
        # Step 1: Create a location
        create_data = {
            "name": "Lifecycle Test Location",
            "address1": "123 Lifecycle St",
            "city": "Lifecycle City",
            "state": "Lifecycle State",
            "country": "Lifecycle Country",
            "zipcode": "55555",
            "location_type": "user"
        }
        
        create_response = await authenticated_client.post("/api/locations/", json=create_data)
        assert create_response.status_code == 201
        created_location = create_response.json()
        location_id = created_location["id"]
        
        assert created_location["name"] == create_data["name"]
        assert created_location["address1"] == create_data["address1"]
        assert created_location["city"] == create_data["city"]
        
        # Step 2: Read the location
        get_response = await authenticated_client.get(f"/api/locations/{location_id}")
        assert get_response.status_code == 200
        retrieved_location = get_response.json()
        
        assert retrieved_location["id"] == location_id
        assert retrieved_location["name"] == create_data["name"]
        
        # Step 3: Verify location appears in list
        list_response = await authenticated_client.get("/api/locations/")
        assert list_response.status_code == 200
        locations_list = list_response.json()
        
        location_ids = [l["id"] for l in locations_list]
        assert location_id in location_ids
        
        # Step 4: Update the location
        update_data = {
            "name": "Updated Lifecycle Location",
            "city": "Updated City"
        }
        
        update_response = await authenticated_client.put(f"/api/locations/{location_id}", json=update_data)
        assert update_response.status_code == 200
        updated_location = update_response.json()
        
        assert updated_location["id"] == location_id
        assert updated_location["name"] == update_data["name"]
        assert updated_location["city"] == update_data["city"]
        assert updated_location["address1"] == create_data["address1"]  # Unchanged
        
        # Step 5: Delete the location
        delete_response = await authenticated_client.delete(f"/api/locations/{location_id}")
        assert delete_response.status_code == 204
        
        # Step 6: Verify location is deleted
        final_get_response = await authenticated_client.get(f"/api/locations/{location_id}")
        assert final_get_response.status_code == 404
        
        # Step 7: Verify location is not in list
        final_list_response = await authenticated_client.get("/api/locations/")
        assert final_list_response.status_code == 200
        final_locations_list = final_list_response.json()
        
        final_location_ids = [l["id"] for l in final_locations_list]
        assert location_id not in final_location_ids
