"""
Search router for location-based breeder search.

This module provides endpoints for searching breeding locations by geographic proximity
and breed filtering using PostGIS spatial queries.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.schemas.breeder import BreederSearchResult
from app.services.breeder_service import BreederService


router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    responses={
        400: {"description": "Invalid search parameters"},
        500: {"description": "Internal server error"},
    }
)


@router.get("/breeders", response_model=List[BreederSearchResult])
async def search_breeders(
    latitude: float = Query(..., ge=-90, le=90, description="Search center latitude in decimal degrees"),
    longitude: float = Query(..., ge=-180, le=180, description="Search center longitude in decimal degrees"),
    radius: float = Query(..., gt=0, le=100, description="Search radius in miles"),
    breed_id: Optional[int] = Query(None, description="Optional breed ID to filter results"),
    session: AsyncSession = Depends(get_async_session),
) -> List[BreederSearchResult]:
    """
    Search for breeding locations within a radius of a geographic point.
    
    This endpoint uses PostGIS for efficient geospatial queries to find breeders
    near a specified location. Results include distance calculations and available
    breeds at each location.
    
    **Query Parameters:**
    - **latitude**: Search center latitude (-90 to 90)
    - **longitude**: Search center longitude (-180 to 180)
    - **radius**: Search radius in miles (1 to 100)
    - **breed_id**: Optional breed ID to filter results (only locations with this breed)
    
    **Returns:**
    - List of breeding locations within the specified radius
    - Each location includes:
      - Distance from search center (in miles, rounded to 1 decimal)
      - Available breeds at that location
      - Breeder information and contact details
    - Results are sorted by distance (nearest first)
    
    **Example Request:**
    ```
    GET /api/search/breeders?latitude=40.7128&longitude=-74.0060&radius=20&breed_id=1
    ```
    
    **Example Response:**
    ```json
    [
        {
            "location_id": 1,
            "user_id": "123e4567-e89b-12d3-a456-426614174000",
            "breeder_name": "Happy Paws Kennel",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "distance": 5.3,
            "available_breeds": [
                {
                    "breed_id": 1,
                    "breed_name": "Golden Retriever",
                    "pet_count": 3
                }
            ],
            "thumbnail_url": "/storage/profile_image.jpg",
            "location_description": "Main Breeding Facility",
            "rating": null
        }
    ]
    ```
    
    **Requirements Validated:**
    - 13.1: GET endpoint with query parameter validation
    - 13.3: Returns breeding locations within specified radius
    - 13.4: Returns BreederSearchResult schema with all required fields
    """
    try:
        # Create breeder service instance
        breeder_service = BreederService()
        
        # Execute search
        results = await breeder_service.search_nearby_breeding_locations(
            db=session,
            latitude=latitude,
            longitude=longitude,
            radius_miles=radius,
            breed_id=breed_id
        )
        
        return results
        
    except ValueError as e:
        # Handle validation errors from service layer
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Log the error and return generic error message
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in breeder search: {str(e)}", exc_info=True)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while searching for breeders"
        )
