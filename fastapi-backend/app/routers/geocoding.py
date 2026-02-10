"""Geocoding API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.config import Settings
from app.dependencies import get_redis, settings
from app.schemas.geocoding import Address, Coordinates
from app.services.geocoding_service import GeocodingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/geocode")


def get_geocoding_service(
    redis_client: Optional[Redis] = Depends(get_redis)
) -> GeocodingService:
    """
    Dependency to get geocoding service instance.
    
    Args:
        redis_client: Optional Redis client for caching
        
    Returns:
        GeocodingService: Configured geocoding service
    """
    return GeocodingService(settings, redis_client)


@router.get(
    "/zip",
    response_model=Coordinates,
    summary="Geocode ZIP code",
    description="""
    Convert a US ZIP code to geographic coordinates (forward geocoding).
    
    Uses Nominatim geocoding service with caching and rate limiting.
    Results are cached for 24 hours to improve performance and reduce API calls.
    
    **Rate Limit:** 1 request per second
    
    **Cache:** 24 hours TTL
    """,
    responses={
        200: {
            "description": "Successfully geocoded ZIP code",
            "content": {
                "application/json": {
                    "example": {
                        "latitude": 40.7128,
                        "longitude": -74.0060
                    }
                }
            }
        },
        400: {
            "description": "Invalid ZIP code format",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid ZIP code format: abc12. Must be 5 digits."
                    }
                }
            }
        },
        404: {
            "description": "ZIP code not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "ZIP code 99999 not found"
                    }
                }
            }
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Geocoding rate limit exceeded. Please try again later."
                    }
                }
            }
        },
        503: {
            "description": "Geocoding service unavailable"
        }
    }
)
async def geocode_zip(
    zip: str = Query(
        ...,
        regex=r"^\d{5}$",
        description="5-digit US ZIP code",
        example="10001"
    ),
    geocoding_service: GeocodingService = Depends(get_geocoding_service)
) -> Coordinates:
    """
    Convert ZIP code to coordinates.
    
    Args:
        zip: 5-digit US ZIP code
        geocoding_service: Geocoding service instance
        
    Returns:
        Coordinates with latitude and longitude
    """
    logger.info(f"Geocoding ZIP code: {zip}")
    return await geocoding_service.geocode_zip(zip)


@router.get(
    "/reverse",
    response_model=Address,
    summary="Reverse geocode coordinates",
    description="""
    Convert geographic coordinates to address information (reverse geocoding).
    
    Uses Nominatim geocoding service with caching and rate limiting.
    Results are cached for 24 hours to improve performance and reduce API calls.
    
    **Rate Limit:** 1 request per second
    
    **Cache:** 24 hours TTL
    """,
    responses={
        200: {
            "description": "Successfully reverse geocoded coordinates",
            "content": {
                "application/json": {
                    "example": {
                        "zip_code": "10001",
                        "city": "New York",
                        "state": "New York",
                        "country": "United States"
                    }
                }
            }
        },
        400: {
            "description": "Invalid coordinates",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid latitude: 100. Must be between -90 and 90."
                    }
                }
            }
        },
        429: {
            "description": "Rate limit exceeded"
        },
        503: {
            "description": "Geocoding service unavailable"
        }
    }
)
async def reverse_geocode(
    lat: float = Query(
        ...,
        ge=-90,
        le=90,
        description="Latitude in decimal degrees",
        example=40.7128
    ),
    lon: float = Query(
        ...,
        ge=-180,
        le=180,
        description="Longitude in decimal degrees",
        example=-74.0060
    ),
    geocoding_service: GeocodingService = Depends(get_geocoding_service)
) -> Address:
    """
    Convert coordinates to address.
    
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        geocoding_service: Geocoding service instance
        
    Returns:
        Address with location details
    """
    logger.info(f"Reverse geocoding coordinates: {lat}, {lon}")
    return await geocoding_service.reverse_geocode(lat, lon)
