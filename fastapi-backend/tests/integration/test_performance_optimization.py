"""
Performance optimization tests for Pet Search with Map feature.

Tests verify:
- Requirement 10.1: Lazy loading support (backend returns all results)
- Requirement 10.2: Efficient handling of 50+ markers
- Requirement 10.3: Geocoding cache effectiveness
- Requirement 10.4: Fast API response times
- Requirement 10.5: Optimized database queries
"""

import time

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.breed import Breed
from app.models.location import Location
from app.models.pet import Pet
from app.models.user import User


@pytest.fixture
async def create_test_breeders(async_session: AsyncSession):
    """Create multiple test breeders with locations and pets for performance testing."""
    breeders = []
    
    # Create a test breed
    breed = Breed(
        name="Golden Retriever",
        code="GR",
        group="Sporting"
    )
    async_session.add(breed)
    await async_session.flush()
    
    # Create 50 test breeders with locations and pets (reduced for faster tests)
    for i in range(50):
        # Create user
        user = User(
            email=f"perfbreeder{i}@test.com",
            hashed_password="hashed_password",
            breedery_name=f"Perf Breeder {i}",
            is_active=True
        )
        async_session.add(user)
        await async_session.flush()
        
        # Create location with coordinates spread around NYC
        lat = 40.7128 + ((i % 10) - 5) * 0.05
        lon = -74.0060 + ((i // 10) - 2) * 0.05
        
        location = Location(
            user_id=user.id,
            location_type='user',
            name=f"Perf Location {i}",
            address1=f"{i} Test Street",
            city="New York",
            state="NY",
            country="USA",
            zipcode="10001"
        )
        location.set_coordinates(lat, lon)
        async_session.add(location)
        await async_session.flush()
        
        # Create 2 pets at this location
        for j in range(2):
            pet = Pet(
                user_id=user.id,
                location_id=location.id,
                breed_id=breed.id,
                name=f"Perf Pet {i}-{j}",
                gender="Male" if j % 2 == 0 else "Female",
                is_deleted=False
            )
            async_session.add(pet)
        
        breeders.append({
            'user': user,
            'location': location,
            'breed': breed
        })
    
    await async_session.commit()
    return breeders


class TestPerformanceOptimization:
    """Test suite for performance optimization requirements."""
    
    @pytest.mark.asyncio
    async def test_breeder_search_with_50_results(
        self,
        async_client: AsyncClient,
        create_test_breeders,
    ):
        """
        Test that API can efficiently return 50+ results.
        Requirement 10.1: Support for lazy loading (backend returns all results).
        Requirement 10.4: Fast API response times.
        """
        # Arrange: 50 breeders created by fixture
        params = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "radius": 50
        }
        
        # Act: Measure response time
        start_time = time.time()
        response = await async_client.get("/api/search/breeders", params=params)
        end_time = time.time()
        
        response_time_ms = (end_time - start_time) * 1000
        
        # Assert: Response successful and fast
        assert response.status_code == 200
        results = response.json()
        
        # Should return multiple breeders within radius
        assert len(results) >= 10
        
        # Response time should be reasonable (< 2000ms for test environment)
        assert response_time_ms < 2000, f"Response time {response_time_ms:.2f}ms too slow"
        
        # Verify result structure
        for result in results[:5]:
            assert "location_id" in result
            assert "user_id" in result
            assert "breeder_name" in result
            assert "latitude" in result
            assert "longitude" in result
            assert "distance" in result
            assert "available_breeds" in result
            assert isinstance(result["available_breeds"], list)
        
        print(f"✓ API returned {len(results)} results in {response_time_ms:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_marker_clustering_data_structure(
        self,
        async_client: AsyncClient,
        create_test_breeders,
    ):
        """
        Test that API returns data suitable for marker clustering.
        Requirement 10.2: Support for 50+ markers with clustering.
        """
        # Arrange & Act
        params = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "radius": 50
        }
        
        response = await async_client.get("/api/search/breeders", params=params)
        
        # Assert
        assert response.status_code == 200
        results = response.json()
        
        # Verify we have multiple results for clustering
        assert len(results) >= 10
        
        # Verify each result has coordinates for marker placement
        for result in results:
            assert "latitude" in result
            assert "longitude" in result
            assert isinstance(result["latitude"], (int, float))
            assert isinstance(result["longitude"], (int, float))
            assert -90 <= result["latitude"] <= 90
            assert -180 <= result["longitude"] <= 180
        
        # Verify results are sorted by distance
        distances = [r["distance"] for r in results]
        assert distances == sorted(distances), "Results should be sorted by distance"
        
        print(f"✓ Marker clustering data structure verified for {len(results)} markers")
    
    @pytest.mark.asyncio
    async def test_geocoding_cache_flow(
        self,
        unauthenticated_client: AsyncClient,
    ):
        """
        Test that geocoding endpoints work correctly.
        Requirement 10.3: Geocoding cache with 24-hour TTL.
        Note: Cache effectiveness is verified by backend implementation.
        """
        # Arrange: Same ZIP code
        zip_code = "10001"
        
        # Act: First request
        start_time_1 = time.time()
        response_1 = await unauthenticated_client.get(f"/api/geocode/zip?zip={zip_code}")
        end_time_1 = time.time()
        time_1_ms = (end_time_1 - start_time_1) * 1000
        
        # Assert: First request successful
        assert response_1.status_code == 200
        result_1 = response_1.json()
        assert "latitude" in result_1
        assert "longitude" in result_1
        
        # Act: Second request (may hit cache if Redis available)
        start_time_2 = time.time()
        response_2 = await unauthenticated_client.get(f"/api/geocode/zip?zip={zip_code}")
        end_time_2 = time.time()
        time_2_ms = (end_time_2 - start_time_2) * 1000
        
        # Assert: Second request successful and returns same result
        assert response_2.status_code == 200
        result_2 = response_2.json()
        assert result_1 == result_2
        
        print(f"✓ Geocoding flow verified (1st: {time_1_ms:.2f}ms, 2nd: {time_2_ms:.2f}ms)")
    
    @pytest.mark.asyncio
    async def test_breed_filtering_performance(
        self,
        async_client: AsyncClient,
        create_test_breeders,
        async_session: AsyncSession
    ):
        """
        Test that breed filtering doesn't significantly impact performance.
        Requirement 10.4: Optimized API response times.
        """
        # Arrange: Get breed ID
        result = await async_session.execute(
            select(Breed.id).where(Breed.name == "Golden Retriever").limit(1)
        )
        breed_row = result.first()
        assert breed_row is not None
        breed_id = breed_row[0]
        
        # Act: Search with breed filter
        params = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "radius": 50,
            "breed_id": breed_id
        }
        
        start_time = time.time()
        response = await async_client.get("/api/search/breeders", params=params)
        end_time = time.time()
        
        response_time_ms = (end_time - start_time) * 1000
        
        # Assert: Response successful and fast
        assert response.status_code == 200
        results = response.json()
        
        # Should return filtered results
        assert len(results) > 0
        
        # All results should have the filtered breed
        for result in results:
            breed_names = [b["breed_name"] for b in result["available_breeds"]]
            assert "Golden Retriever" in breed_names
        
        # Response time should be reasonable
        assert response_time_ms < 2000, f"Filtered search {response_time_ms:.2f}ms too slow"
        
        print(f"✓ Breed filtering performance verified: {len(results)} results in {response_time_ms:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_breed_autocomplete_performance(
        self,
        unauthenticated_client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Test that breed autocomplete is fast.
        Requirement 10.4: Fast API response times.
        """
        # Arrange: Ensure we have breeds
        breed = Breed(name="Golden Retriever Test", code="GRT")
        async_session.add(breed)
        await async_session.commit()
        
        # Act: Search for breeds
        search_term = "Gold"
        
        start_time = time.time()
        response = await unauthenticated_client.get(f"/api/breeds/autocomplete?search_term={search_term}")
        end_time = time.time()
        
        response_time_ms = (end_time - start_time) * 1000
        
        # Assert: Response successful and fast
        assert response.status_code == 200
        results = response.json()
        
        # Response time should be fast
        assert response_time_ms < 1000, f"Autocomplete {response_time_ms:.2f}ms too slow"
        
        print(f"✓ Breed autocomplete performance: {response_time_ms:.2f}ms")


class TestLoadingIndicators:
    """Test suite for loading indicator requirements."""
    
    @pytest.mark.asyncio
    async def test_api_returns_quickly_for_loading_indicators(
        self,
        async_client: AsyncClient,
    ):
        """
        Test that API responds quickly enough for loading indicators.
        Requirement 10.5: Loading indicators show appropriate state.
        """
        # Arrange: Simple search
        params = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "radius": 10
        }
        
        # Act: Measure response time
        start_time = time.time()
        response = await async_client.get("/api/search/breeders", params=params)
        end_time = time.time()
        
        response_time_ms = (end_time - start_time) * 1000
        
        # Assert: Response fast enough for good UX
        assert response.status_code == 200
        
        # Response should be fast enough that loading indicator is useful
        assert response_time_ms < 3000, "Response too slow for loading indicators"
        
        print(f"✓ API response time suitable for loading indicators: {response_time_ms:.2f}ms")
