"""Geocoding service with Nominatim integration, caching, and rate limiting."""

import json
import logging
from typing import Optional

import httpx
from aiolimiter import AsyncLimiter
from fastapi import HTTPException
from redis.asyncio import Redis

from app.config import Settings
from app.schemas.geocoding import Address, Coordinates

logger = logging.getLogger(__name__)


class GeocodingService:
    """
    Service for geocoding operations using Nominatim.
    
    Features:
    - Forward geocoding (ZIP code to coordinates)
    - Reverse geocoding (coordinates to address)
    - Rate limiting (1 request per second by default)
    - Redis caching with 24-hour TTL
    """
    
    def __init__(self, settings: Settings, redis_client: Optional[Redis] = None):
        """
        Initialize geocoding service.
        
        Args:
            settings: Application settings
            redis_client: Optional Redis client for caching
        """
        self.settings = settings
        self.redis_client = redis_client
        self.nominatim_url = settings.nominatim_url
        self.user_agent = settings.geocoding_user_agent
        
        # Create rate limiter (requests per second)
        self.rate_limiter = AsyncLimiter(
            max_rate=settings.geocoding_rate_limit,
            time_period=1.0
        )
        
        logger.info(
            f"GeocodingService initialized with rate limit: "
            f"{settings.geocoding_rate_limit} req/s"
        )
    
    async def geocode_zip(self, zip_code: str) -> Coordinates:
        """
        Convert ZIP code to coordinates (forward geocoding).
        
        Checks cache first, then calls Nominatim if needed.
        Results are cached for 24 hours.
        
        Args:
            zip_code: 5-digit US ZIP code
            
        Returns:
            Coordinates object with latitude and longitude
            
        Raises:
            HTTPException: If ZIP code not found or service error
        """
        # Validate ZIP code format
        if not zip_code.isdigit() or len(zip_code) != 5:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid ZIP code format: {zip_code}. Must be 5 digits."
            )
        
        cache_key = f"geocode:zip:{zip_code}"
        
        # Check cache if Redis is available
        if self.redis_client:
            try:
                cached = await self.redis_client.get(cache_key)
                if cached:
                    logger.info(f"Cache hit for ZIP code: {zip_code}")
                    data = json.loads(cached)
                    return Coordinates(**data)
            except Exception as e:
                logger.warning(f"Cache read error: {e}")
        
        # Rate limit the request
        async with self.rate_limiter:
            logger.info(f"Geocoding ZIP code: {zip_code}")
            
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{self.nominatim_url}/search",
                        params={
                            "postalcode": zip_code,
                            "country": "US",
                            "format": "json",
                            "limit": 1
                        },
                        headers={"User-Agent": self.user_agent}
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    if not data:
                        raise HTTPException(
                            status_code=404,
                            detail=f"ZIP code {zip_code} not found"
                        )
                    
                    result = Coordinates(
                        latitude=float(data[0]["lat"]),
                        longitude=float(data[0]["lon"])
                    )
                    
                    # Cache the result if Redis is available
                    if self.redis_client:
                        try:
                            await self.redis_client.setex(
                                cache_key,
                                self.settings.geocoding_cache_ttl,
                                result.model_dump_json()
                            )
                            logger.info(f"Cached result for ZIP code: {zip_code}")
                        except Exception as e:
                            logger.warning(f"Cache write error: {e}")
                    
                    return result
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"Nominatim HTTP error: {e}")
                if e.response.status_code == 429:
                    raise HTTPException(
                        status_code=429,
                        detail="Geocoding rate limit exceeded. Please try again later."
                    )
                raise HTTPException(
                    status_code=502,
                    detail="Geocoding service error"
                )
            except httpx.TimeoutException:
                logger.error("Nominatim request timeout")
                raise HTTPException(
                    status_code=504,
                    detail="Geocoding service timeout"
                )
            except httpx.RequestError as e:
                logger.error(f"Nominatim request error: {e}")
                raise HTTPException(
                    status_code=503,
                    detail="Geocoding service unavailable"
                )
    
    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float
    ) -> Address:
        """
        Convert coordinates to address (reverse geocoding).
        
        Checks cache first, then calls Nominatim if needed.
        Results are cached for 24 hours.
        
        Args:
            latitude: Latitude in decimal degrees (-90 to 90)
            longitude: Longitude in decimal degrees (-180 to 180)
            
        Returns:
            Address object with location details
            
        Raises:
            HTTPException: If coordinates invalid or service error
        """
        # Validate coordinates
        if not (-90 <= latitude <= 90):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid latitude: {latitude}. Must be between -90 and 90."
            )
        if not (-180 <= longitude <= 180):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid longitude: {longitude}. Must be between -180 and 180."
            )
        
        # Round coordinates to 4 decimal places for cache key
        # (about 11 meters precision, good enough for caching)
        lat_rounded = round(latitude, 4)
        lon_rounded = round(longitude, 4)
        cache_key = f"geocode:reverse:{lat_rounded}:{lon_rounded}"
        
        # Check cache if Redis is available
        if self.redis_client:
            try:
                cached = await self.redis_client.get(cache_key)
                if cached:
                    logger.info(f"Cache hit for coordinates: {latitude}, {longitude}")
                    data = json.loads(cached)
                    return Address(**data)
            except Exception as e:
                logger.warning(f"Cache read error: {e}")
        
        # Rate limit the request
        async with self.rate_limiter:
            logger.info(f"Reverse geocoding coordinates: {latitude}, {longitude}")
            
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{self.nominatim_url}/reverse",
                        params={
                            "lat": latitude,
                            "lon": longitude,
                            "format": "json"
                        },
                        headers={"User-Agent": self.user_agent}
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    address_data = data.get("address", {})
                    result = Address(
                        zip_code=address_data.get("postcode"),
                        city=address_data.get("city") or address_data.get("town") or address_data.get("village"),
                        state=address_data.get("state"),
                        country=address_data.get("country")
                    )
                    
                    # Cache the result if Redis is available
                    if self.redis_client:
                        try:
                            await self.redis_client.setex(
                                cache_key,
                                self.settings.geocoding_cache_ttl,
                                result.model_dump_json()
                            )
                            logger.info(f"Cached result for coordinates: {latitude}, {longitude}")
                        except Exception as e:
                            logger.warning(f"Cache write error: {e}")
                    
                    return result
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"Nominatim HTTP error: {e}")
                if e.response.status_code == 429:
                    raise HTTPException(
                        status_code=429,
                        detail="Geocoding rate limit exceeded. Please try again later."
                    )
                raise HTTPException(
                    status_code=502,
                    detail="Geocoding service error"
                )
            except httpx.TimeoutException:
                logger.error("Nominatim request timeout")
                raise HTTPException(
                    status_code=504,
                    detail="Geocoding service timeout"
                )
            except httpx.RequestError as e:
                logger.error(f"Nominatim request error: {e}")
                raise HTTPException(
                    status_code=503,
                    detail="Geocoding service unavailable"
                )
