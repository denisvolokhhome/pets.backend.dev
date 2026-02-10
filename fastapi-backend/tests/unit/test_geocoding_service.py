"""Unit tests for geocoding service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
import httpx

from app.config import Settings
from app.schemas.geocoding import Address, Coordinates
from app.services.geocoding_service import GeocodingService


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.nominatim_url = "https://nominatim.openstreetmap.org"
    settings.geocoding_user_agent = "TestAgent/1.0"
    settings.geocoding_rate_limit = 1.0
    settings.geocoding_cache_ttl = 86400
    return settings


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()
    return redis_mock


class TestGeocodingServiceForwardGeocoding:
    """Test forward geocoding (ZIP to coordinates)."""
    
    @pytest.mark.asyncio
    async def test_geocode_valid_zip_success(self, mock_settings, mock_redis):
        """Test forward geocoding with valid ZIP code."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"lat": "40.7128", "lon": "-74.0060"}
        ]
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            result = await service.geocode_zip("10001")
            
            assert isinstance(result, Coordinates)
            assert result.latitude == 40.7128
            assert result.longitude == -74.0060
    
    @pytest.mark.asyncio
    async def test_geocode_invalid_zip_format(self, mock_settings, mock_redis):
        """Test forward geocoding with invalid ZIP format."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Test non-numeric ZIP
        with pytest.raises(HTTPException) as exc_info:
            await service.geocode_zip("abc12")
        assert exc_info.value.status_code == 400
        assert "Invalid ZIP code format" in exc_info.value.detail
        
        # Test wrong length
        with pytest.raises(HTTPException) as exc_info:
            await service.geocode_zip("123")
        assert exc_info.value.status_code == 400
    
    @pytest.mark.asyncio
    async def test_geocode_zip_not_found(self, mock_settings, mock_redis):
        """Test forward geocoding when ZIP not found."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock empty API response
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            with pytest.raises(HTTPException) as exc_info:
                await service.geocode_zip("99999")
            
            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_geocode_cache_hit(self, mock_settings, mock_redis):
        """Test forward geocoding with cache hit."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock cached result
        cached_coords = Coordinates(latitude=40.7128, longitude=-74.0060)
        mock_redis.get = AsyncMock(return_value=cached_coords.model_dump_json())
        
        result = await service.geocode_zip("10001")
        
        # Verify result from cache
        assert result.latitude == 40.7128
        assert result.longitude == -74.0060
        
        # Verify cache was read
        mock_redis.get.assert_called_once_with("geocode:zip:10001")
        
        # Verify no API call was made (no setex call)
        mock_redis.setex.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_geocode_cache_miss(self, mock_settings, mock_redis):
        """Test forward geocoding with cache miss."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock cache miss
        mock_redis.get = AsyncMock(return_value=None)
        
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"lat": "40.7128", "lon": "-74.0060"}
        ]
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            result = await service.geocode_zip("10001")
            
            # Verify result
            assert result.latitude == 40.7128
            
            # Verify cache was written
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == "geocode:zip:10001"
            assert call_args[0][1] == 86400


class TestGeocodingServiceReverseGeocoding:
    """Test reverse geocoding (coordinates to address)."""
    
    @pytest.mark.asyncio
    async def test_reverse_geocode_valid_coordinates(self, mock_settings, mock_redis):
        """Test reverse geocoding with valid coordinates."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock successful API response
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
            
            result = await service.reverse_geocode(40.7128, -74.0060)
            
            assert isinstance(result, Address)
            assert result.zip_code == "10001"
            assert result.city == "New York"
            assert result.state == "New York"
            assert result.country == "United States"
    
    @pytest.mark.asyncio
    async def test_reverse_geocode_invalid_latitude(self, mock_settings, mock_redis):
        """Test reverse geocoding with invalid latitude."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Test latitude > 90
        with pytest.raises(HTTPException) as exc_info:
            await service.reverse_geocode(100.0, -74.0060)
        assert exc_info.value.status_code == 400
        assert "Invalid latitude" in exc_info.value.detail
        
        # Test latitude < -90
        with pytest.raises(HTTPException) as exc_info:
            await service.reverse_geocode(-100.0, -74.0060)
        assert exc_info.value.status_code == 400
    
    @pytest.mark.asyncio
    async def test_reverse_geocode_invalid_longitude(self, mock_settings, mock_redis):
        """Test reverse geocoding with invalid longitude."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Test longitude > 180
        with pytest.raises(HTTPException) as exc_info:
            await service.reverse_geocode(40.7128, 200.0)
        assert exc_info.value.status_code == 400
        assert "Invalid longitude" in exc_info.value.detail
        
        # Test longitude < -180
        with pytest.raises(HTTPException) as exc_info:
            await service.reverse_geocode(40.7128, -200.0)
        assert exc_info.value.status_code == 400
    
    @pytest.mark.asyncio
    async def test_reverse_geocode_cache_hit(self, mock_settings, mock_redis):
        """Test reverse geocoding with cache hit."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock cached result
        cached_address = Address(
            zip_code="10001",
            city="New York",
            state="New York",
            country="United States"
        )
        mock_redis.get = AsyncMock(return_value=cached_address.model_dump_json())
        
        result = await service.reverse_geocode(40.7128, -74.0060)
        
        # Verify result from cache
        assert result.zip_code == "10001"
        assert result.city == "New York"
        
        # Verify cache was read
        cache_key = "geocode:reverse:40.7128:-74.006"
        mock_redis.get.assert_called_once_with(cache_key)
        
        # Verify no API call was made
        mock_redis.setex.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_reverse_geocode_partial_address(self, mock_settings, mock_redis):
        """Test reverse geocoding with partial address data."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock API response with missing fields
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "address": {
                "city": "New York",
                "country": "United States"
                # Missing postcode and state
            }
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            result = await service.reverse_geocode(40.7128, -74.0060)
            
            # Verify partial result
            assert result.city == "New York"
            assert result.country == "United States"
            assert result.zip_code is None
            assert result.state is None


class TestGeocodingServiceErrorHandling:
    """Test error handling for geocoding service."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, mock_settings, mock_redis):
        """Test handling of rate limit errors."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock 429 rate limit response
        mock_response = MagicMock()
        mock_response.status_code = 429
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Rate limit exceeded",
                    request=MagicMock(),
                    response=mock_response
                )
            )
            
            with pytest.raises(HTTPException) as exc_info:
                await service.geocode_zip("10001")
            
            assert exc_info.value.status_code == 429
            assert "rate limit" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_timeout_error(self, mock_settings, mock_redis):
        """Test handling of timeout errors."""
        service = GeocodingService(mock_settings, mock_redis)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("Request timeout")
            )
            
            with pytest.raises(HTTPException) as exc_info:
                await service.geocode_zip("10001")
            
            assert exc_info.value.status_code == 504
            assert "timeout" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_network_error(self, mock_settings, mock_redis):
        """Test handling of network errors."""
        service = GeocodingService(mock_settings, mock_redis)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.RequestError("Network error")
            )
            
            with pytest.raises(HTTPException) as exc_info:
                await service.geocode_zip("10001")
            
            assert exc_info.value.status_code == 503
            assert "unavailable" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_http_error(self, mock_settings, mock_redis):
        """Test handling of HTTP errors."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock 500 server error
        mock_response = MagicMock()
        mock_response.status_code = 500
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Server error",
                    request=MagicMock(),
                    response=mock_response
                )
            )
            
            with pytest.raises(HTTPException) as exc_info:
                await service.geocode_zip("10001")
            
            assert exc_info.value.status_code == 502
    
    @pytest.mark.asyncio
    async def test_cache_error_graceful_degradation(self, mock_settings, mock_redis):
        """Test graceful degradation when cache fails."""
        service = GeocodingService(mock_settings, mock_redis)
        
        # Mock cache read error
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))
        
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"lat": "40.7128", "lon": "-74.0060"}
        ]
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            # Should still work despite cache error
            result = await service.geocode_zip("10001")
            
            assert result.latitude == 40.7128
            assert result.longitude == -74.0060


class TestGeocodingServiceWithoutRedis:
    """Test geocoding service without Redis."""
    
    @pytest.mark.asyncio
    async def test_geocode_without_redis(self, mock_settings):
        """Test forward geocoding without Redis."""
        service = GeocodingService(mock_settings, redis_client=None)
        
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"lat": "40.7128", "lon": "-74.0060"}
        ]
        mock_response.raise_for_status = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            result = await service.geocode_zip("10001")
            
            # Should work without Redis
            assert result.latitude == 40.7128
            assert result.longitude == -74.0060
    
    @pytest.mark.asyncio
    async def test_reverse_geocode_without_redis(self, mock_settings):
        """Test reverse geocoding without Redis."""
        service = GeocodingService(mock_settings, redis_client=None)
        
        # Mock successful API response
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
            
            result = await service.reverse_geocode(40.7128, -74.0060)
            
            # Should work without Redis
            assert result.zip_code == "10001"
            assert result.city == "New York"
