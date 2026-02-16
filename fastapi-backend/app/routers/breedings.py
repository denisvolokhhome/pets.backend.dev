"""
Litters router for managing breeding records.

This module provides CRUD operations for breeding management including:
- Creating and updating breeding records
- Listing breedings with filtering options
- Managing breeding information and associations with pets
"""
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_session
from app.dependencies import current_active_user, require_breeder
from app.models.user import User
from app.models.breeding import Breeding
from app.models.breeding_pet import BreedingPet
from app.models.pet import Pet
from app.models.breed import Breed
from app.models.location import Location
from app.schemas.breeding import LitterCreate, LitterRead, LitterUpdate, LitterResponse, LitterStatus, PetAssignment, PuppyBatch


router = APIRouter(
    prefix="/api/breedings",
    tags=["breedings"],
    responses={
        404: {"description": "Breeding not found"},
    }
)


@router.post("/", response_model=LitterResponse, status_code=status.HTTP_201_CREATED)
async def create_litter(
    breeding_data: LitterCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> dict:
    """
    Create a new breeding record.
    
    This endpoint is public and does not require authentication.
    A breeding represents a breeding operation tracking parent pets and puppies.
    
    **Optional fields:**
    - description: Additional information about the breeding
    
    **Example:**
    ```json
    {
        "description": "First breeding of 2024"
    }
    ```
    
    **Returns:** The created breeding record with generated ID and status "Started"
    
    **Requirements:** 4.1, 4.3, 4.4, 4.5
    """
    # Create new breeding instance with status "Started"
    breeding = Breeding(
        user_id=current_user.id,
        description=breeding_data.description,
        status=LitterStatus.STARTED.value,
    )
    
    session.add(breeding)
    await session.commit()
    await session.refresh(breeding)
    
    # Return LitterResponse format
    return {
        "id": breeding.id,
        "description": breeding.description,
        "status": breeding.status,
        "created_at": breeding.created_at,
        "updated_at": breeding.updated_at,
        "parent_pets": None,
        "puppies": None
    }


@router.get("/", response_model=List[LitterResponse])
async def list_litters(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
    location_id: Optional[int] = Query(None, description="Filter by location ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    breed_id: Optional[int] = Query(None, description="Filter by breed ID"),
    skip: int = 0,
    limit: int = 100,
) -> List[dict]:
    """
    List all breedings with optional filtering.
    
    This endpoint is public and does not require authentication.
    Results are ordered by created_at descending (most recent first).
    Voided breedings are excluded by default.
    
    **Query Parameters:**
    - location_id: Filter breedings by location (derived from parent pets)
    - status: Filter by breeding status (Started, InProcess, Done, Voided)
    - breed_id: Filter breedings by breed (from parent pets)
    - skip: Number of records to skip (pagination)
    - limit: Maximum number of records to return
    
    **Returns:** List of breedings with nested parent_pets and puppies
    """
    # Start with base query - filter by current user
    query = select(Breeding).where(Breeding.user_id == current_user.id).options(
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.breed),
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.location),
        selectinload(Breeding.pets).selectinload(Pet.breed),
        selectinload(Breeding.pets).selectinload(Pet.location)
    )
    
    # Apply status filter if provided
    if status:
        query = query.where(Breeding.status == status)
    else:
        # Exclude voided breedings by default (only when no status filter is provided)
        query = query.where(Breeding.status != LitterStatus.VOIDED.value)
    
    # Execute query to get breedings
    result = await session.execute(query)
    breedings = result.scalars().all()
    
    # Build response with parent pets and puppies
    response_litters = []
    for breeding in breedings:
        # Get parent pets from breeding_pets junction table
        parent_pets = []
        parent_pet_locations = set()
        parent_pet_breeds = set()
        
        for litter_pet in breeding.breeding_pets:
            pet = litter_pet.pet
            parent_pets.append({
                "id": str(pet.id),
                "name": pet.name,
                "breed_name": pet.breed.name if pet.breed else None,
                "breed_id": pet.breed_id,
                "location_name": pet.location.name if pet.location else None,
                "location_id": pet.location_id,
                "gender": pet.gender
            })
            if pet.location_id:
                parent_pet_locations.add(pet.location_id)
            if pet.breed_id:
                parent_pet_breeds.add(pet.breed_id)
        
        # Apply location filter
        if location_id and location_id not in parent_pet_locations:
            continue
        
        # Apply breed filter
        if breed_id and breed_id not in parent_pet_breeds:
            continue
        
        # Get puppies (pets with this breeding_id)
        puppies = []
        for pet in breeding.pets:
            puppies.append({
                "id": str(pet.id),
                "name": pet.name,
                "gender": pet.gender,
                "birth_date": pet.date_of_birth.isoformat() if pet.date_of_birth else None,
                "microchip": pet.microchip
            })
        
        response_litters.append({
            "id": breeding.id,
            "description": breeding.description,
            "status": breeding.status,
            "created_at": breeding.created_at,
            "updated_at": breeding.updated_at,
            "parent_pets": parent_pets if parent_pets else None,
            "puppies": puppies if puppies else None
        })
    
    # Apply pagination
    response_litters = response_litters[skip:skip + limit]
    
    return response_litters


@router.get("/{breeding_id}", response_model=LitterResponse)
async def get_litter(
    breeding_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> dict:
    """
    Get a single breeding by ID with full details.
    
    Requires authentication. Users can only access their own breedings.
    Returns breeding with nested parent_pets and puppies.
    
    **Returns:** LitterResponse with parent pets and puppies
    
    **Requirements:** 7.2, 7.3, 7.4, 7.5
    """
    # Query breeding with relationships eagerly loaded - filter by user_id
    query = select(Breeding).where(
        Breeding.id == breeding_id,
        Breeding.user_id == current_user.id
    ).options(
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.breed),
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.location),
        selectinload(Breeding.pets).selectinload(Pet.breed),
        selectinload(Breeding.pets).selectinload(Pet.location)
    )
    result = await session.execute(query)
    breeding = result.scalar_one_or_none()
    
    if breeding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Breeding not found"
        )
    
    # Build parent pets list from breeding_pets junction table
    parent_pets = []
    for litter_pet in breeding.breeding_pets:
        pet = litter_pet.pet
        parent_pets.append({
            "id": str(pet.id),
            "name": pet.name,
            "breed_name": pet.breed.name if pet.breed else None,  # Changed from "breed" to "breed_name"
            "breed_id": pet.breed_id,
            "location_name": pet.location.name if pet.location else None,  # Changed from "location" to "location_name"
            "location_id": pet.location_id,
            "gender": pet.gender
        })
    
    # Build puppies list from pets with this breeding_id
    # Query puppies directly to ensure we get them
    puppy_query = select(Pet).where(Pet.breeding_id == breeding.id).options(
        selectinload(Pet.breed),
        selectinload(Pet.location)
    )
    puppy_result = await session.execute(puppy_query)
    puppy_pets = puppy_result.scalars().all()
    
    puppies = []
    for pet in puppy_pets:
        puppies.append({
            "id": str(pet.id),
            "name": pet.name,
            "gender": pet.gender,
            "birth_date": pet.date_of_birth.isoformat() if pet.date_of_birth else None,
            "microchip": pet.microchip
        })
    
    # Return LitterResponse format
    return {
        "id": breeding.id,
        "description": breeding.description,
        "status": breeding.status,
        "created_at": breeding.created_at,
        "updated_at": breeding.updated_at,
        "parent_pets": parent_pets if parent_pets else None,
        "puppies": puppies if puppies else None
    }


@router.put("/{breeding_id}", response_model=LitterResponse)
async def update_litter(
    breeding_id: int,
    litter_update: LitterUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> dict:
    """
    Update a breeding record.
    
    Only provided fields will be updated (currently only description).
    The updated_at timestamp is automatically updated.
    Requires authentication. Users can only update their own breedings.
    
    **Requirements:** 8.1, 8.2, 8.5
    """
    # Fetch the breeding with relationships - filter by user_id
    query = select(Breeding).where(
        Breeding.id == breeding_id,
        Breeding.user_id == current_user.id
    ).options(
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.breed),
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.location),
        selectinload(Breeding.pets).selectinload(Pet.breed),
        selectinload(Breeding.pets).selectinload(Pet.location)
    )
    result = await session.execute(query)
    breeding = result.scalar_one_or_none()
    
    if breeding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Breeding not found"
        )
    
    # Update fields that were provided
    update_data = litter_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(breeding, field, value)
    
    # Commit changes (updated_at will be automatically updated by SQLAlchemy)
    await session.commit()
    await session.refresh(breeding)
    
    # Build parent pets list from breeding_pets junction table
    parent_pets = []
    for litter_pet in breeding.breeding_pets:
        pet = litter_pet.pet
        parent_pets.append({
            "id": str(pet.id),
            "name": pet.name,
            "breed_name": pet.breed.name if pet.breed else None,
            "breed_id": pet.breed_id,
            "location_name": pet.location.name if pet.location else None,
            "location_id": pet.location_id,
            "gender": pet.gender
        })
    
    # Build puppies list from pets with this breeding_id
    puppy_query = select(Pet).where(Pet.breeding_id == breeding.id).options(
        selectinload(Pet.breed),
        selectinload(Pet.location)
    )
    puppy_result = await session.execute(puppy_query)
    puppy_pets = puppy_result.scalars().all()
    
    puppies = []
    for pet in puppy_pets:
        puppies.append({
            "id": str(pet.id),
            "name": pet.name,
            "gender": pet.gender,
            "birth_date": pet.date_of_birth.isoformat() if pet.date_of_birth else None,
            "microchip": pet.microchip
        })
    
    # Return LitterResponse format
    return {
        "id": breeding.id,
        "description": breeding.description,
        "status": breeding.status,
        "created_at": breeding.created_at,
        "updated_at": breeding.updated_at,
        "parent_pets": parent_pets if parent_pets else None,
        "puppies": puppies if puppies else None
    }


@router.post("/{breeding_id}/assign-pets", response_model=LitterResponse)
async def assign_pets_to_litter(
    breeding_id: int,
    pet_assignment: PetAssignment,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> dict:
    """
    Assign parent pets to a breeding.
    
    This endpoint assigns exactly 2 parent pets to a breeding and updates the breeding status to "InProcess".
    Both pets must exist and must have the same location_id.
    Requires authentication. Users can only assign pets to their own breedings.
    
    **Request Body:**
    ```json
    {
        "pet_ids": ["uuid1", "uuid2"]
    }
    ```
    
    **Validation Rules:**
    - Exactly 2 pets must be provided
    - Both pets must exist in the database
    - Both pets must have the same location_id
    - Returns 400 error if validation fails
    
    **Returns:** LitterResponse with updated status "InProcess" and parent_pets
    
    **Requirements:** 3.1, 3.4, 5.1, 5.2, 5.3, 5.4
    """
    # Fetch the breeding - filter by user_id
    query = select(Breeding).where(
        Breeding.id == breeding_id,
        Breeding.user_id == current_user.id
    ).options(
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.breed),
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.location),
        selectinload(Breeding.pets).selectinload(Pet.breed),
        selectinload(Breeding.pets).selectinload(Pet.location)
    )
    result = await session.execute(query)
    breeding = result.scalar_one_or_none()
    
    if breeding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Breeding not found"
        )
    
    # Validate both pets exist
    pet_ids = pet_assignment.pet_ids
    pets_query = select(Pet).where(Pet.id.in_(pet_ids)).options(
        selectinload(Pet.breed),
        selectinload(Pet.location)
    )
    pets_result = await session.execute(pets_query)
    pets = pets_result.scalars().all()
    
    if len(pets) != 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both pets must exist in the database"
        )
    
    # Validate both pets have the same location_id
    pet1, pet2 = pets[0], pets[1]
    if pet1.location_id != pet2.location_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both pets must have the same location"
        )
    
    # Create entries in breeding_pets junction table
    for pet in pets:
        litter_pet = BreedingPet(
            breeding_id=breeding.id,
            pet_id=pet.id
        )
        session.add(litter_pet)
    
    # Update breeding status to "InProcess"
    breeding.status = LitterStatus.IN_PROCESS.value
    
    # Commit changes (updated_at will be automatically updated)
    await session.commit()
    await session.refresh(breeding)
    
    # Reload breeding with relationships to get the newly assigned pets
    query = select(Breeding).where(Breeding.id == breeding_id).options(
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.breed),
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.location),
        selectinload(Breeding.pets).selectinload(Pet.breed),
        selectinload(Breeding.pets).selectinload(Pet.location)
    )
    result = await session.execute(query)
    breeding = result.scalar_one()
    
    # Build parent pets list from breeding_pets junction table
    parent_pets = []
    for litter_pet in breeding.breeding_pets:
        pet = litter_pet.pet
        parent_pets.append({
            "id": str(pet.id),
            "name": pet.name,
            "breed_name": pet.breed.name if pet.breed else None,
            "breed_id": pet.breed_id,
            "location_name": pet.location.name if pet.location else None,
            "location_id": pet.location_id,
            "gender": pet.gender
        })
    
    # Build puppies list from pets with this breeding_id
    puppy_query = select(Pet).where(Pet.breeding_id == breeding.id).options(
        selectinload(Pet.breed),
        selectinload(Pet.location)
    )
    puppy_result = await session.execute(puppy_query)
    puppy_pets = puppy_result.scalars().all()
    
    puppies = []
    for pet in puppy_pets:
        puppies.append({
            "id": str(pet.id),
            "name": pet.name,
            "gender": pet.gender,
            "birth_date": pet.date_of_birth.isoformat() if pet.date_of_birth else None,
            "microchip": pet.microchip
        })
    
    # Return LitterResponse format
    return {
        "id": breeding.id,
        "description": breeding.description,
        "status": breeding.status,
        "created_at": breeding.created_at,
        "updated_at": breeding.updated_at,
        "parent_pets": parent_pets if parent_pets else None,
        "puppies": puppies if puppies else None
    }


@router.post("/{breeding_id}/add-puppies", response_model=LitterResponse)
async def add_puppies_to_litter(
    breeding_id: int,
    puppy_batch: PuppyBatch,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> dict:
    """
    Add puppies to a breeding.
    
    This endpoint creates pet records for each puppy and associates them with the breeding.
    The breeding status is updated to "Done" after puppies are added.
    Location and breed are derived from the parent pets.
    Requires authentication. Users can only add puppies to their own breedings.
    
    **Request Body:**
    ```json
    {
        "puppies": [
            {
                "name": "Puppy 1",
                "gender": "Male",
                "birth_date": "2024-01-15",
                "microchip": "123456789"
            }
        ]
    }
    ```
    
    **Validation Rules:**
    - Breeding must have parent pets assigned
    - At least one puppy must be provided
    - Each puppy must have name, gender, and birth_date
    - Gender must be "Male" or "Female"
    - Returns 400 error if validation fails
    
    **Returns:** LitterResponse with updated status "Done" and puppies
    
    **Requirements:** 6.1, 6.2, 6.3, 6.4, 6.5
    """
    # Fetch the breeding with relationships - filter by user_id
    query = select(Breeding).where(
        Breeding.id == breeding_id,
        Breeding.user_id == current_user.id
    ).options(
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.breed),
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.location),
        selectinload(Breeding.pets).selectinload(Pet.breed),
        selectinload(Breeding.pets).selectinload(Pet.location)
    )
    result = await session.execute(query)
    breeding = result.scalar_one_or_none()
    
    if breeding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Breeding not found"
        )
    
    # Validate breeding has parent pets assigned
    if not breeding.breeding_pets or len(breeding.breeding_pets) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Breeding must have parent pets assigned before adding puppies"
        )
    
    # Derive location and breed from parent pets
    parent_pets = [litter_pet.pet for litter_pet in breeding.breeding_pets]
    
    # Get location from first parent pet (they should all have the same location)
    location_id = parent_pets[0].location_id if parent_pets[0].location_id else None
    
    # Get breed - if both parents have the same breed, use that; otherwise use first parent's breed
    breed_ids = [pet.breed_id for pet in parent_pets if pet.breed_id]
    breed_id = breed_ids[0] if breed_ids else None
    
    # Get user_id from first parent pet
    user_id = parent_pets[0].user_id
    
    # Create pet records for each puppy
    created_puppies = []
    for puppy_input in puppy_batch.puppies:
        puppy = Pet(
            name=puppy_input.name,
            gender=puppy_input.gender,
            date_of_birth=puppy_input.birth_date,
            microchip=puppy_input.microchip,
            breeding_id=breeding.id,
            location_id=location_id,
            breed_id=breed_id,
            user_id=user_id,
            is_puppy=True
        )
        session.add(puppy)
        created_puppies.append(puppy)
    
    # Update breeding status to "Done"
    breeding.status = LitterStatus.DONE.value
    
    # Commit changes (updated_at will be automatically updated)
    await session.commit()
    
    # Refresh all created puppies to get their IDs
    for puppy in created_puppies:
        await session.refresh(puppy)
    
    # Reload breeding with relationships to get the newly added puppies
    query = select(Breeding).where(Breeding.id == breeding_id).options(
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.breed),
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.location),
        selectinload(Breeding.pets).selectinload(Pet.breed),
        selectinload(Breeding.pets).selectinload(Pet.location)
    )
    result = await session.execute(query)
    breeding = result.scalar_one()
    
    # Build parent pets list from breeding_pets junction table
    parent_pets_list = []
    for litter_pet in breeding.breeding_pets:
        pet = litter_pet.pet
        parent_pets_list.append({
            "id": str(pet.id),
            "name": pet.name,
            "breed_name": pet.breed.name if pet.breed else None,
            "breed_id": pet.breed_id,
            "location_name": pet.location.name if pet.location else None,
            "location_id": pet.location_id,
            "gender": pet.gender
        })
    
    # Build puppies list from pets with this breeding_id
    puppy_query = select(Pet).where(Pet.breeding_id == breeding.id).options(
        selectinload(Pet.breed),
        selectinload(Pet.location)
    )
    puppy_result = await session.execute(puppy_query)
    puppy_pets = puppy_result.scalars().all()
    
    puppies = []
    for pet in puppy_pets:
        puppies.append({
            "id": str(pet.id),
            "name": pet.name,
            "gender": pet.gender,
            "birth_date": pet.date_of_birth.isoformat() if pet.date_of_birth else None,
            "microchip": pet.microchip
        })
    
    # Return LitterResponse format
    return {
        "id": breeding.id,
        "description": breeding.description,
        "status": breeding.status,
        "created_at": breeding.created_at,
        "updated_at": breeding.updated_at,
        "parent_pets": parent_pets_list if parent_pets_list else None,
        "puppies": puppies if puppies else None
    }


@router.delete("/{breeding_id}", response_model=LitterResponse)
async def delete_litter(
    breeding_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> dict:
    """
    Void/cancel a breeding record (soft delete).
    
    This endpoint updates the breeding status to "Voided" and maintains the breeding record
    for historical tracking. The breeding will be excluded from default listings but
    can still be retrieved by ID or by explicitly filtering for voided breedings.
    Requires authentication. Users can only void their own breedings.
    
    **Returns:** LitterResponse with updated status "Voided"
    
    **Requirements:** 9.1, 9.2, 9.3, 9.4, 9.5
    """
    # Fetch the breeding with relationships - filter by user_id
    query = select(Breeding).where(
        Breeding.id == breeding_id,
        Breeding.user_id == current_user.id
    ).options(
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.breed),
        selectinload(Breeding.breeding_pets).selectinload(BreedingPet.pet).selectinload(Pet.location),
        selectinload(Breeding.pets).selectinload(Pet.breed),
        selectinload(Breeding.pets).selectinload(Pet.location)
    )
    result = await session.execute(query)
    breeding = result.scalar_one_or_none()
    
    if breeding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Breeding not found"
        )
    
    # Update breeding status to "Voided" (soft delete)
    breeding.status = LitterStatus.VOIDED.value
    
    # Commit changes (updated_at will be automatically updated)
    await session.commit()
    await session.refresh(breeding)
    
    # Build parent pets list from breeding_pets junction table
    parent_pets = []
    for litter_pet in breeding.breeding_pets:
        pet = litter_pet.pet
        parent_pets.append({
            "id": str(pet.id),
            "name": pet.name,
            "breed_name": pet.breed.name if pet.breed else None,
            "breed_id": pet.breed_id,
            "location_name": pet.location.name if pet.location else None,
            "location_id": pet.location_id,
            "gender": pet.gender
        })
    
    # Build puppies list from pets with this breeding_id
    puppy_query = select(Pet).where(Pet.breeding_id == breeding.id).options(
        selectinload(Pet.breed),
        selectinload(Pet.location)
    )
    puppy_result = await session.execute(puppy_query)
    puppy_pets = puppy_result.scalars().all()
    
    puppies = []
    for pet in puppy_pets:
        puppies.append({
            "id": str(pet.id),
            "name": pet.name,
            "gender": pet.gender,
            "birth_date": pet.date_of_birth.isoformat() if pet.date_of_birth else None,
            "microchip": pet.microchip
        })
    
    # Return LitterResponse format
    return {
        "id": breeding.id,
        "description": breeding.description,
        "status": breeding.status,
        "created_at": breeding.created_at,
        "updated_at": breeding.updated_at,
        "parent_pets": parent_pets if parent_pets else None,
        "puppies": puppies if puppies else None
    }
