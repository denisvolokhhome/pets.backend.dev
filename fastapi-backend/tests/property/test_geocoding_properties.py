"""Property-based tests for geocoding service.

Feature: pet-search-map
"""

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.config import Settings
from app.schemas.geocoding import Address, Coordinates
from app.services.geocoding_service import GeocodingService


# Custom strategies for geocoding
valid_zip_code_strategy = st.text(
    min_size=5,
    max_size=5,
    alphabet=st.characters(min_codepoint=ord('0'), max_codepoint=ord('9'))
)

valid_latitude_strategy = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False)
valid_longitude_strategy = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)


def create_mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.nominatim_url = "https://nominatim.openstreetmap.org"
    settings.geocoding_user_agent = "TestAgent/1.0"
    settings.geocoding_rate_limit = 1.0
    settings.geocoding_cache_ttl = 86400
    return settings


def create_mock_redis():
    """Create mock Redis client."""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()
    return redis_mock


class TestGeocodingCacheProperty:
    """
    Property 36: Geocoding Cache Round-Trip
    
    For any geocoding request made, subsequent identical requests within 24 hours
    should return the cached result without calling the external service.
    
    Validates: Requirements 10.3
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(zip_code=valid_zip_code_strategy)
    @pytest.mark.asyncio
    async def test_property_geocode_zip_cache_round_trip(
        self,
        zip_code: str
    ) -> None:
        """
        Property: For any ZIP code geocoded, subsequent requests should return cached result.
        
        Feature: pet-search-map, Property 36: Geocoding Cache Round-Trip
        """
        # Create mocks inside the test
        mock_settings = create_mock_settings()
        mock_redis = create_mock_redis()
        
        # Create service with mock Redis
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock coordinates for this ZIP code
        mock_coords = Coordinates(latitude=40.7128, longitude=-74.0060)
        
        # Mock the HTTP response for first call
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"lat": "40.7128", "lon": "-74.0060"}
        ]
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            # First call - should hit the API and cache the result
            result1 = await service.geocode_zip(zip_code)
            
            # Verify result
            assert result1.latitude == 40.7128
            assert result1.longitude == -74.0060
            
            # Verify cache was written
            cache_key = f"geocode:zip:{zip_code}"
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == cache_key
            assert call_args[0][1] == 86400  # TTL
            
            # Reset mock to track second call
            mock_redis.setex.reset_mock()
            
            # Set up cache to return the cached value
            mock_redis.get = AsyncMock(
                return_value=mock_coords.model_dump_json()
            )
            
            # Second call - should return cached result without hitting API
            result2 = await service.geocode_zip(zip_code)
            
            # Verify result matches first call
            assert result2.latitude == result1.latitude
            assert result2.longitude == result1.longitude
            
            # Verify cache was read but not written again
            mock_redis.get.assert_called_once_with(cache_key)
            mock_redis.setex.assert_not_called()

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        latitude=valid_latitude_strategy,
        longitude=valid_longitude_strategy
    )
    @pytest.mark.asyncio
    async def test_property_reverse_geocode_cache_round_trip(
        self,
        latitude: float,
        longitude: float
    ) -> None:
        """
        Property: For any coordinates reverse geocoded, subsequent requests should return cached result.
        
        Feature: pet-search-map, Property 36: Geocoding Cache Round-Trip
        """
        # Create mocks inside the test
        mock_settings = create_mock_settings()
        mock_redis = create_mock_redis()
        
        # Create service with mock Redis
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock address for these coordinates
        mock_address = Address(
            zip_code="10001",
            city="New York",
            state="New York",
            country="United States"
        )
        
        # Mock the HTTP response for first call
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "address": {
                "postcode": "10001",
                "city": "New York",
                "state": "New York",
                "country": "United States"
            }
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            # First call - should hit the API and cache the result
            result1 = await service.reverse_geocode(latitude, longitude)
            
            # Verify result
            assert result1.zip_code == "10001"
            assert result1.city == "New York"
            
            # Verify cache was written
            lat_rounded = round(latitude, 4)
            lon_rounded = round(longitude, 4)
            cache_key = f"geocode:reverse:{lat_rounded}:{lon_rounded}"
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == cache_key
            assert call_args[0][1] == 86400  # TTL
            
            # Reset mock to track second call
            mock_redis.setex.reset_mock()
            
            # Set up cache to return the cached value
            mock_redis.get = AsyncMock(
                return_value=mock_address.model_dump_json()
            )
            
            # Second call - should return cached result without hitting API
            result2 = await service.reverse_geocode(latitude, longitude)
            
            # Verify result matches first call
            assert result2.zip_code == result1.zip_code
            assert result2.city == result1.city
            assert result2.state == result1.state
            assert result2.country == result1.country
            
            # Verify cache was read but not written again
            mock_redis.get.assert_called_once_with(cache_key)
            mock_redis.setex.assert_not_called()

    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(zip_code=valid_zip_code_strategy)
    @pytest.mark.asyncio
    async def test_property_cache_miss_calls_api(
        self,
        zip_code: str
    ) -> None:
        """
        Property: For any geocoding request with cache miss, the API should be called.
        
        Feature: pet-search-map, Property 36: Geocoding Cache Round-Trip
        """
        # Create mocks inside the test
        mock_settings = create_mock_settings()
        mock_redis = create_mock_redis()
        
        # Create service with mock Redis that always returns None (cache miss)
        mock_redis.get = AsyncMock(return_value=None)
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"lat": "40.7128", "lon": "-74.0060"}
        ]
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get
            
            # Call should hit the API
            result = await service.geocode_zip(zip_code)
            
            # Verify API was called
            mock_get.assert_called_once()
            
            # Verify result was cached
            mock_redis.setex.assert_called_once()

    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        latitude=valid_latitude_strategy,
        longitude=valid_longitude_strategy
    )
    @pytest.mark.asyncio
    async def test_property_graceful_degradation_without_redis(
        self,
        latitude: float,
        longitude: float
    ) -> None:
        """
        Property: For any geocoding request without Redis, service should work without caching.
        
        Feature: pet-search-map, Property 36: Geocoding Cache Round-Trip
        """
        # Create mocks inside the test
        mock_settings = create_mock_settings()
        
        # Create service without Redis (None)
        service = GeocodingService(mock_settings, redis_client=None)
        
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "address": {
                "postcode": "10001",
                "city": "New York",
                "state": "New York",
                "country": "United States"
            }
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get
            
            # Call should work without Redis
            result = await service.reverse_geocode(latitude, longitude)
            
            # Verify result is valid
            assert isinstance(result, Address)
            
            # Verify API was called
            mock_get.assert_called_once()
