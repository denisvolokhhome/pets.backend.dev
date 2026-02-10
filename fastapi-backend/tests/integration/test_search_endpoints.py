"""Integration tests for search API endpoints.

Tests the complete search workflow including:
- Breeder search with various parameters
- Breed autocomplete with various search terms
- Geocoding endpoints
- Error responses
- Response format consistency
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import uuid4

from app.main import app
from app.database import get_async_session
from app.models.breed import Breed
from app.models.user import User
from app.models.location import Location
from app.models.pet import Pet


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
async def test_breeds(async_session: AsyncSession):
    """Create test breeds for autocomplete testing."""
    breeds = [
        Breed(name="Labrador Retriever", code="LAB", group="Sporting"),
        Breed(name="Golden Retriever", code="GOLD", group="Sporting"),
        Breed(name="German Shepherd", code="GSD", group="Herding"),
        Breed(name="Beagle", code="BGL", group="Hound"),
        Breed(name="Bulldog", code="BULL", group="Non-Sporting"),
    ]
    
    for breed in breeds:
        async_session.add(breed)
    
    await async_session.commit()
    
    # Refresh to get IDs
    for breed in breeds:
        await async_session.refresh(breed)
    
    return breeds


@pytest.fixture
async def test_breeder_with_location(async_session: AsyncSession, test_breeds):
    """Create a test breeder with location and pets."""
    # Create user
    user = User(
        id=uuid4(),
        email="breeder@test.com",
        hashed_password="hashed",
        breedery_name="Happy Paws Kennel",
        is_active=True
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    
    # Create location with coordinates (New York area)
    location = Location(
        user_id=user.id,
        name="Main Facility",
        address1="123 Main St",
        city="New York",
        state="NY",
        country="USA",
        zipcode="10001",
        location_type="user"
    )
    # Set coordinates using helper method
    location.set_coordinates(40.7128, -74.0060)
    
    async_session.add(location)
    await async_session.commit()
    await async_session.refresh(location)
    
    # Create pets at this location
    pets = []
    for i, breed in enumerate(test_breeds[:2]):  # Add 2 breeds
        pet = Pet(
            id=uuid4(),
            user_id=user.id,
            location_id=location.id,
            breed_id=breed.id,
            name=f"Pet {i}",
            gender="male" if i % 2 == 0 else "female",
            is_deleted=False
        )
        async_session.add(pet)
        pets.append(pet)
    
    await async_session.commit()
    
    return {
        "user": user,
        "location": location,
        "pets": pets
    }


class TestBreederSearch:
    """Integration tests for breeder search endpoint."""

    @pytest.mark.asyncio
    async def test_search_breeders_with_valid_parameters(
        self,
        client: AsyncClient,
        test_breeder_with_location
    ):
        """
        Test breeder search with valid latitude, longitude, and radius.
        
        Validates: Requirements 13.1, 13.3, 13.4
        """
        # Search near New York (where test breeder is located)
        response = await client.get(
            "/api/search/breeders",
            params={
                "latitude": 40.7128,
                "longitude": -74.0060,
                "radius": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return a list
        assert isinstance(data, list)
        
        # Should find at least our test breeder
        assert len(data) >= 1
        
        # Verify response structure
        breeder = data[0]
        assert "location_id" in breeder
        assert "user_id" in breeder
        assert "breeder_name" in breeder
        assert "latitude" in breeder
        assert "longitude" in breeder
        assert "distance" in breeder
        assert "available_breeds" in breeder
        assert "thumbnail_url" in breeder
        assert "location_description" in breeder
        assert "rating" in breeder
        
        # Verify breeder name matches
        assert breeder["breeder_name"] == "Happy Paws Kennel"
        
        # Verify distance is within radius
        assert breeder["distance"] <= 10
        
        # Verify available_breeds is a list
        assert isinstance(breeder["available_breeds"], list)
        assert len(breeder["available_breeds"]) >= 1

    @pytest.mark.asyncio
    async def test_search_breeders_with_breed_filter(
        self,
        client: AsyncClient,
        test_breeder_with_location,
        test_breeds
    ):
        """
        Test breeder search with breed filter.
        
        Validates: Requirements 13.1, 13.3, 13.4
        """
        # Get the first breed ID (Labrador Retriever)
        breed_id = test_breeds[0].id
        
        # Search with breed filter
        response = await client.get(
            "/api/search/breeders",
            params={
                "latitude": 40.7128,
                "longitude": -74.0060,
                "radius": 10,
                "breed_id": breed_id
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return results
        assert isinstance(data, list)
        
        # All results should have the specified breed
        for breeder in data:
            breed_ids = [b["breed_id"] for b in breeder["available_breeds"]]
            assert breed_id in breed_ids

    @pytest.mark.asyncio
    async def test_search_breeders_no_results(self, client: AsyncClient):
        """
        Test breeder search that returns no results.
        
        Validates: Requirements 13.1, 13.3
        """
        # Search in a remote location (middle of ocean)
        response = await client.get(
            "/api/search/breeders",
            params={
                "latitude": 0.0,
                "longitude": 0.0,
                "radius": 1
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return empty list
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_search_breeders_invalid_latitude(self, client: AsyncClient):
        """
        Test breeder search with invalid latitude.
        
        Validates: Requirements 13.1
        """
        response = await client.get(
            "/api/search/breeders",
            params={
                "latitude": 100,  # Invalid: > 90
                "longitude": -74.0060,
                "radius": 10
            }
        )
        
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_search_breeders_invalid_longitude(self, client: AsyncClient):
        """
        Test breeder search with invalid longitude.
        
        Validates: Requirements 13.1
        """
        response = await client.get(
            "/api/search/breeders",
            params={
                "latitude": 40.7128,
                "longitude": 200,  # Invalid: > 180
                "radius": 10
            }
        )
        
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_search_breeders_invalid_radius(self, client: AsyncClient):
        """
        Test breeder search with invalid radius.
        
        Validates: Requirements 13.1
        """
        response = await client.get(
            "/api/search/breeders",
            params={
                "latitude": 40.7128,
                "longitude": -74.0060,
                "radius": 0  # Invalid: must be > 0
            }
        )
        
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_search_breeders_missing_parameters(self, client: AsyncClient):
        """
        Test breeder search with missing required parameters.
        
        Validates: Requirements 13.1
        """
        response = await client.get(
            "/api/search/breeders",
            params={
                "latitude": 40.7128
                # Missing longitude and radius
            }
        )
        
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_search_results_sorted_by_distance(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_breeds
    ):
        """
        Test that search results are sorted by distance (nearest first).
        
        Validates: Requirements 7.6
        """
        # Create multiple breeders at different distances
        breeders = []
        locations_data = [
            (40.7128, -74.0060, "Breeder A"),  # New York
            (40.7589, -73.9851, "Breeder B"),  # Slightly north
            (40.6782, -73.9442, "Breeder C"),  # Brooklyn
        ]
        
        for lat, lon, name in locations_data:
            user = User(
                id=uuid4(),
                email=f"{name.lower().replace(' ', '')}@test.com",
                hashed_password="hashed",
                breedery_name=name,
                is_active=True
            )
            async_session.add(user)
            await async_session.commit()
            await async_session.refresh(user)
            
            location = Location(
                user_id=user.id,
                name=f"{name} Location",
                address1="123 Test St",
                city="New York",
                state="NY",
                country="USA",
                zipcode="10001",
                location_type="user"
            )
            location.set_coordinates(lat, lon)
            async_session.add(location)
            await async_session.commit()
            await async_session.refresh(location)
            
            # Add a pet
            pet = Pet(
                id=uuid4(),
                user_id=user.id,
                location_id=location.id,
                breed_id=test_breeds[0].id,
                name=f"Pet at {name}",
                gender="male",
                is_deleted=False
            )
            async_session.add(pet)
            
            breeders.append((user, location))
        
        await async_session.commit()
        
        # Search from New York
        response = await client.get(
            "/api/search/breeders",
            params={
                "latitude": 40.7128,
                "longitude": -74.0060,
                "radius": 20
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify results are sorted by distance
        distances = [breeder["distance"] for breeder in data]
        assert distances == sorted(distances), "Results should be sorted by distance"


class TestBreedAutocomplete:
    """Integration tests for breed autocomplete endpoint."""

    @pytest.mark.asyncio
    async def test_breed_autocomplete_with_valid_search_term(
        self,
        client: AsyncClient,
        test_breeds
    ):
        """
        Test breed autocomplete with valid search term.
        
        Validates: Requirements 13.5, 13.6, 13.7
        """
        response = await client.get(
            "/api/breeds/autocomplete",
            params={"search_term": "lab"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return a list
        assert isinstance(data, list)
        
        # Should find Labrador Retriever
        assert len(data) >= 1
        
        # Verify response structure
        breed = data[0]
        assert "id" in breed
        assert "name" in breed
        assert "code" in breed
        
        # Verify it matches search term
        assert "lab" in breed["name"].lower() or (breed["code"] and "lab" in breed["code"].lower())

    @pytest.mark.asyncio
    async def test_breed_autocomplete_case_insensitive(
        self,
        client: AsyncClient,
        test_breeds
    ):
        """
        Test that breed autocomplete is case-insensitive.
        
        Validates: Requirements 13.5, 13.6
        """
        # Search with uppercase
        response1 = await client.get(
            "/api/breeds/autocomplete",
            params={"search_term": "LAB"}
        )
        
        # Search with lowercase
        response2 = await client.get(
            "/api/breeds/autocomplete",
            params={"search_term": "lab"}
        )
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Should return same results
        assert len(data1) == len(data2)

    @pytest.mark.asyncio
    async def test_breed_autocomplete_partial_match(
        self,
        client: AsyncClient,
        test_breeds
    ):
        """
        Test that breed autocomplete matches partial names.
        
        Validates: Requirements 13.5, 13.6
        """
        response = await client.get(
            "/api/breeds/autocomplete",
            params={"search_term": "retriever"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should find both Labrador and Golden Retriever
        assert len(data) >= 2
        
        # All results should contain "retriever"
        for breed in data:
            assert "retriever" in breed["name"].lower()

    @pytest.mark.asyncio
    async def test_breed_autocomplete_no_results(
        self,
        client: AsyncClient,
        test_breeds
    ):
        """
        Test breed autocomplete with no matching results.
        
        Validates: Requirements 13.5, 13.6
        """
        response = await client.get(
            "/api/breeds/autocomplete",
            params={"search_term": "xyz123"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return empty list
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_breed_autocomplete_limited_to_10_results(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Test that breed autocomplete limits results to 10.
        
        Validates: Requirements 13.5
        """
        # Create 15 breeds with similar names
        for i in range(15):
            breed = Breed(
                name=f"Test Breed {i}",
                code=f"TEST{i}",
                group="Test"
            )
            async_session.add(breed)
        
        await async_session.commit()
        
        # Search for "test"
        response = await client.get(
            "/api/breeds/autocomplete",
            params={"search_term": "test"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return at most 10 results
        assert len(data) <= 10

    @pytest.mark.asyncio
    async def test_breed_autocomplete_search_term_too_short(
        self,
        client: AsyncClient
    ):
        """
        Test breed autocomplete with search term too short.
        
        Validates: Requirements 13.5
        """
        response = await client.get(
            "/api/breeds/autocomplete",
            params={"search_term": "a"}  # Only 1 character
        )
        
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_breed_autocomplete_missing_search_term(
        self,
        client: AsyncClient
    ):
        """
        Test breed autocomplete with missing search term.
        
        Validates: Requirements 13.5
        """
        response = await client.get("/api/breeds/autocomplete")
        
        assert response.status_code == 422  # Validation error


class TestResponseFormatConsistency:
    """Integration tests for response format consistency."""

    @pytest.mark.asyncio
    async def test_breeder_search_response_format(
        self,
        client: AsyncClient,
        test_breeder_with_location
    ):
        """
        Test that breeder search response format is consistent.
        
        Validates: Requirements 13.4
        """
        response = await client.get(
            "/api/search/breeders",
            params={
                "latitude": 40.7128,
                "longitude": -74.0060,
                "radius": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all breeders have consistent format
        for breeder in data:
            # Required fields
            assert isinstance(breeder["location_id"], int)
            assert isinstance(breeder["user_id"], str)  # UUID as string
            assert isinstance(breeder["breeder_name"], str)
            assert isinstance(breeder["latitude"], (int, float))
            assert isinstance(breeder["longitude"], (int, float))
            assert isinstance(breeder["distance"], (int, float))
            assert isinstance(breeder["available_breeds"], list)
            
            # Optional fields (can be null)
            assert breeder["thumbnail_url"] is None or isinstance(breeder["thumbnail_url"], str)
            assert breeder["location_description"] is None or isinstance(breeder["location_description"], str)
            assert breeder["rating"] is None or isinstance(breeder["rating"], (int, float))
            
            # Verify available_breeds structure
            for breed in breeder["available_breeds"]:
                assert "breed_id" in breed
                assert "breed_name" in breed
                assert "pet_count" in breed

    @pytest.mark.asyncio
    async def test_breed_autocomplete_response_format(
        self,
        client: AsyncClient,
        test_breeds
    ):
        """
        Test that breed autocomplete response format is consistent.
        
        Validates: Requirements 13.7
        """
        response = await client.get(
            "/api/breeds/autocomplete",
            params={"search_term": "lab"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all breeds have consistent format
        for breed in data:
            assert isinstance(breed["id"], int)
            assert isinstance(breed["name"], str)
            assert breed["code"] is None or isinstance(breed["code"], str)
            assert "created_at" in breed
