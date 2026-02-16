"""
Locations router for managing location records.

This module provides CRUD operations for location management including:
- Creating and updating location records
- Listing locations owned by the authenticated user
- Managing location information (address, type, etc.)
- Automatic geocoding of addresses to coordinates

All endpoints require authentication and users can only access their own locations.
"""
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import current_active_user, get_redis, settings, require_breeder
from app.models.location import Location
from app.models.user import User
from app.schemas.location import LocationCreate, LocationRead, LocationUpdate
from app.services.geocoding_service import GeocodingService

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/locations",
    tags=["locations"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized to access this resource"},
        404: {"description": "Location not found"},
    }
)


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


async def geocode_location_address(
    location: Location,
    geocoding_service: GeocodingService
) -> None:
    """
    Automatically geocode a location's address and set coordinates.
    
    Builds full address from location fields and attempts to geocode it.
    If successful, updates the location's coordinates using PostGIS geometry.
    Logs warnings if geocoding fails but doesn't raise exceptions.
    
    Args:
        location: Location object to geocode
        geocoding_service: Geocoding service instance
    """
    try:
        # Build full address string
        address_parts = [location.address1]
        if location.address2:
            address_parts.append(location.address2)
        address_parts.extend([
            location.city,
            location.state,
            location.zipcode,
            location.country
        ])
        full_address = ", ".join(address_parts)
        
        logger.info(f"Geocoding location address: {full_address}")
        
        # Try geocoding by ZIP code first (more reliable)
        try:
            coords = await geocoding_service.geocode_zip(location.zipcode)
            location.set_coordinates(coords.latitude, coords.longitude)
            logger.info(
                f"Successfully geocoded location {location.id} by ZIP: "
                f"{coords.latitude}, {coords.longitude}"
            )
        except Exception as zip_error:
            logger.warning(
                f"ZIP code geocoding failed for {location.zipcode}, "
                f"will use default coordinates: {zip_error}"
            )
            # If ZIP geocoding fails, location will not have coordinates
            # This is acceptable - location can still be created/updated
            
    except Exception as e:
        logger.warning(
            f"Failed to geocode location {location.id}: {e}. "
            f"Location will be saved without coordinates."
        )


@router.post("/", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
async def create_location(
    location_data: LocationCreate,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
) -> Location:
    """
    Create a new location record with automatic geocoding.
    
    The location will be associated with the authenticated user.
    Locations represent physical addresses where pets are kept.
    
    **Automatic Geocoding:**
    - The system automatically converts the address to coordinates
    - Uses ZIP code for accurate geocoding
    - Coordinates are stored in PostGIS geometry column for spatial queries
    - If geocoding fails, location is still created but won't appear in map searches
    
    **Required fields:**
    - name: Location name
    - address1: Primary address line
    - city: City name
    - country: Country name
    
    **Optional fields:**
    - address2: Secondary address line
    - state: State/province
    - zipcode: Postal/ZIP code
    - location_type: Type of location (e.g., "home", "kennel")
    - is_published: Whether location is visible on map (default: True)
    
    **Example:**
    ```json
    {
        "name": "Main Kennel",
        "address1": "123 Main Street",
        "address2": "Suite 100",
        "city": "Springfield",
        "state": "IL",
        "country": "USA",
        "zipcode": "62701",
        "location_type": "kennel",
        "is_published": true
    }
    ```
    
    **Returns:** The created location record with generated ID and coordinates
    """
    # Create new location instance
    location = Location(
        user_id=user.id,
        name=location_data.name,
        address1=location_data.address1,
        address2=location_data.address2,
        city=location_data.city,
        state=location_data.state,
        country=location_data.country,
        zipcode=location_data.zipcode,
        location_type=location_data.location_type,
        is_published=location_data.is_published,
    )
    
    # Add to session first to get an ID
    session.add(location)
    await session.flush()
    
    # Try to automatically geocode the address (non-blocking)
    try:
        await geocode_location_address(location, geocoding_service)
    except Exception as e:
        # Geocoding failed, but that's okay - location can still be created
        logger.warning(f"Geocoding failed for location {location.id}: {e}. Location saved without coordinates.")
    
    # Commit with or without coordinates
    await session.commit()
    await session.refresh(location)
    
    logger.info(
        f"Created location {location.id} for user {user.id} "
        f"with coordinates: {location.latitude}, {location.longitude}"
    )
    
    return location


@router.get("/", response_model=List[LocationRead])
async def list_locations(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    skip: int = 0,
    limit: int = 100,
) -> List[dict]:
    """
    List all locations owned by the authenticated user.
    
    Results are ordered by creation date descending (most recent first).
    Users can only see their own locations.
    Each location includes a list of pets assigned to it.
    """
    from app.models.pet import Pet
    
    # CRITICAL: Filter by user_id to ensure users only see their own locations
    query = (
        select(Location)
        .where(Location.user_id == user.id)
        .offset(skip)
        .limit(limit)
        .order_by(Location.created_at.desc())
    )
    
    result = await session.execute(query)
    locations = result.scalars().all()
    
    # For each location, fetch associated pets
    locations_with_pets = []
    for location in locations:
        pet_query = select(Pet).where(Pet.location_id == location.id)
        pet_result = await session.execute(pet_query)
        pets = pet_result.scalars().all()
        
        # Convert location to dict and add pets
        location_dict = {
            "id": location.id,
            "user_id": location.user_id,
            "name": location.name,
            "address1": location.address1,
            "address2": location.address2,
            "city": location.city,
            "state": location.state,
            "country": location.country,
            "zipcode": location.zipcode,
            "location_type": location.location_type,
            "is_published": location.is_published,
            "created_at": location.created_at,
            "updated_at": location.updated_at,
            "pets": [{"id": pet.id, "name": pet.name} for pet in pets]
        }
        locations_with_pets.append(location_dict)
    
    return locations_with_pets


@router.get("/{location_id}", response_model=LocationRead)
async def get_location(
    location_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Location:
    """
    Get a single location by ID.
    
    The location must be owned by the authenticated user.
    """
    query = select(Location).where(
        Location.id == location_id,
        Location.user_id == user.id
    )
    result = await session.execute(query)
    location = result.scalar_one_or_none()
    
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )
    
    return location


@router.put("/{location_id}", response_model=LocationRead)
async def update_location(
    location_id: int,
    location_update: LocationUpdate,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
) -> Location:
    """
    Update a location record with automatic geocoding.
    
    The location must be owned by the authenticated user.
    Only provided fields will be updated.
    
    **Automatic Geocoding:**
    - If address fields are updated, the system automatically re-geocodes
    - Updates coordinates in PostGIS geometry column
    - If geocoding fails, location is still updated but coordinates remain unchanged
    """
    # Fetch the location
    query = select(Location).where(
        Location.id == location_id,
        Location.user_id == user.id
    )
    result = await session.execute(query)
    location = result.scalar_one_or_none()
    
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )
    
    # Track if address fields changed
    address_changed = False
    update_data = location_update.model_dump(exclude_unset=True)
    
    # Check if any address fields are being updated
    address_fields = {'address1', 'address2', 'city', 'state', 'zipcode', 'country'}
    if any(field in update_data for field in address_fields):
        address_changed = True
    
    # Update fields that were provided
    for field, value in update_data.items():
        setattr(location, field, value)
    
    # Re-geocode if address changed
    if address_changed:
        logger.info(f"Address changed for location {location_id}, re-geocoding...")
        try:
            await geocode_location_address(location, geocoding_service)
        except Exception as e:
            logger.warning(f"Re-geocoding failed for location {location_id}: {e}. Location updated without new coordinates.")
    
    await session.commit()
    await session.refresh(location)
    
    return location


@router.patch("/{location_id}", response_model=LocationRead)
async def patch_location(
    location_id: int,
    location_update: LocationUpdate,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
) -> Location:
    """
    Partially update a location record (PATCH method) with automatic geocoding.
    
    The location must be owned by the authenticated user.
    Only provided fields will be updated.
    
    **Automatic Geocoding:**
    - If address fields are updated, the system automatically re-geocodes
    - Updates coordinates in PostGIS geometry column
    - If geocoding fails, location is still updated but coordinates remain unchanged
    """
    # Fetch the location
    query = select(Location).where(
        Location.id == location_id,
        Location.user_id == user.id
    )
    result = await session.execute(query)
    location = result.scalar_one_or_none()
    
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )
    
    # Track if address fields changed
    address_changed = False
    update_data = location_update.model_dump(exclude_unset=True)
    
    # Check if any address fields are being updated
    address_fields = {'address1', 'address2', 'city', 'state', 'zipcode', 'country'}
    if any(field in update_data for field in address_fields):
        address_changed = True
    
    # Update fields that were provided
    for field, value in update_data.items():
        setattr(location, field, value)
    
    # Re-geocode if address changed
    if address_changed:
        logger.info(f"Address changed for location {location_id}, re-geocoding...")
        try:
            await geocode_location_address(location, geocoding_service)
        except Exception as e:
            logger.warning(f"Re-geocoding failed for location {location_id}: {e}. Location updated without new coordinates.")
    
    await session.commit()
    await session.refresh(location)
    
    return location


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(
    location_id: int,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Delete a location record.
    
    The location must be owned by the authenticated user.
    This is a hard delete. The location will be permanently removed from the database.
    
    **Important:** Cannot delete locations that have associated pets.
    You must first remove or reassign all pets from this location.
    """
    from app.models.pet import Pet
    
    # Fetch the location
    query = select(Location).where(
        Location.id == location_id,
        Location.user_id == user.id
    )
    result = await session.execute(query)
    location = result.scalar_one_or_none()
    
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )
    
    # Check if location has associated pets
    pet_query = select(Pet).where(Pet.location_id == location_id)
    pet_result = await session.execute(pet_query)
    associated_pets = pet_result.scalars().all()
    
    if associated_pets:
        pet_names = [pet.name for pet in associated_pets]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Cannot delete location with {len(associated_pets)} associated pet(s). Please remove or reassign all pets from this location first.",
                "pet_count": len(associated_pets),
                "pet_names": pet_names
            }
        )
    
    # Delete the location
    await session.delete(location)
    await session.commit()
