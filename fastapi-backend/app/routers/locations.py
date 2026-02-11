"""
Locations router for managing location records.

This module provides CRUD operations for location management including:
- Creating and updating location records
- Listing locations owned by the authenticated user
- Managing location information (address, type, etc.)

All endpoints require authentication and users can only access their own locations.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import current_active_user
from app.models.location import Location
from app.models.user import User
from app.schemas.location import LocationCreate, LocationRead, LocationUpdate


router = APIRouter(
    prefix="/api/locations",
    tags=["locations"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized to access this resource"},
        404: {"description": "Location not found"},
    }
)


@router.post("/", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
async def create_location(
    location_data: LocationCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Location:
    """
    Create a new location record.
    
    The location will be associated with the authenticated user.
    Locations represent physical addresses where pets are kept.
    
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
        "location_type": "kennel"
    }
    ```
    
    **Returns:** The created location record with generated ID
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
    )
    
    session.add(location)
    await session.commit()
    await session.refresh(location)
    
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
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Location:
    """
    Update a location record.
    
    The location must be owned by the authenticated user.
    Only provided fields will be updated.
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
    
    # Update fields that were provided
    update_data = location_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(location, field, value)
    
    await session.commit()
    await session.refresh(location)
    
    return location


@router.patch("/{location_id}", response_model=LocationRead)
async def patch_location(
    location_id: int,
    location_update: LocationUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Location:
    """
    Partially update a location record (PATCH method).
    
    The location must be owned by the authenticated user.
    Only provided fields will be updated.
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
    
    # Update fields that were provided
    update_data = location_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(location, field, value)
    
    await session.commit()
    await session.refresh(location)
    
    return location


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(
    location_id: int,
    user: User = Depends(current_active_user),
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
