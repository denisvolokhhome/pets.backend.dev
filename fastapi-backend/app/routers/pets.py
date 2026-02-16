"""
Pets router for managing pet records.

This module provides CRUD operations for pet management including:
- Creating and updating pet records
- Listing pets by owner or breeder
- Soft deletion of pets
- Image upload and management for pets
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_async_session
from app.dependencies import current_active_user, require_breeder
from app.models.pet import Pet
from app.models.user import User
from app.schemas.pet import PetCreate, PetRead, PetUpdate
from app.services.file_service import FileService


router = APIRouter(
    prefix="/api/pets",
    tags=["pets"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized to access this resource"},
        404: {"description": "Pet not found"},
    }
)


def get_file_service() -> FileService:
    """Dependency to get FileService instance."""
    settings = Settings()
    return FileService(settings)


@router.post("/", response_model=PetRead, status_code=status.HTTP_201_CREATED)
async def create_pet(
    pet_data: PetCreate,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> Pet:
    """
    Create a new pet record.
    
    The pet will be associated with the authenticated user as the owner.
    
    **Required fields:**
    - name: Pet's name
    
    **Optional fields:**
    - breed_id: Reference to breed (must exist)
    - breeding_id: Reference to breeding (must exist)
    - location_id: Reference to location (must exist and be owned by user)
    - date_of_birth: Pet's birth date
    - gender: Pet's gender
    - weight: Pet's weight
    - description: Additional description
    - is_puppy: Whether the pet is a puppy
    - microchip: Microchip number
    - vaccination: Vaccination records
    - health_certificate: Health certificate information
    - deworming: Deworming records
    - birth_certificate: Birth certificate information
    
    **Example:**
    ```json
    {
        "name": "Max",
        "breed_id": 1,
        "date_of_birth": "2023-01-15",
        "gender": "male",
        "is_puppy": true,
        "microchip": "123456789012345"
    }
    ```
    
    **Returns:** The created pet record with generated UUID
    """
    # Create new pet instance
    pet = Pet(
        user_id=user.id,
        name=pet_data.name,
        breed_id=pet_data.breed_id,
        breeding_id=pet_data.breeding_id,
        location_id=pet_data.location_id,
        date_of_birth=pet_data.date_of_birth,
        gender=pet_data.gender,
        weight=pet_data.weight,
        description=pet_data.description,
        is_puppy=pet_data.is_puppy,
        microchip=pet_data.microchip,
        vaccination=pet_data.vaccination,
        health_certificate=pet_data.health_certificate,
        deworming=pet_data.deworming,
        birth_certificate=pet_data.birth_certificate,
        has_microchip=pet_data.has_microchip,
        has_vaccination=pet_data.has_vaccination,
        has_healthcertificate=pet_data.has_healthcertificate,
        has_dewormed=pet_data.has_dewormed,
        has_birthcertificate=pet_data.has_birthcertificate,
    )
    
    session.add(pet)
    await session.commit()
    await session.refresh(pet)
    
    return pet


@router.get("/", response_model=List[PetRead])
async def list_pets(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = False,
) -> List[dict]:
    """
    List all pets owned by the authenticated user.
    
    By default, soft-deleted pets are excluded unless include_deleted=True.
    Each pet includes the location name if assigned to a location.
    """
    query = select(Pet).where(Pet.user_id == user.id)
    
    if not include_deleted:
        query = query.where(Pet.is_deleted == False)
    
    query = query.offset(skip).limit(limit).order_by(Pet.created_at.desc())
    
    result = await session.execute(query)
    pets = result.scalars().all()
    
    # Add location name to each pet
    pets_with_location = []
    for pet in pets:
        pet_dict = {
            "id": pet.id,
            "user_id": pet.user_id,
            "name": pet.name,
            "breed_id": pet.breed_id,
            "breeding_id": pet.breeding_id,
            "location_id": pet.location_id,
            "date_of_birth": pet.date_of_birth,
            "gender": pet.gender,
            "weight": pet.weight,
            "description": pet.description,
            "is_puppy": pet.is_puppy,
            "microchip": pet.microchip,
            "vaccination": pet.vaccination,
            "health_certificate": pet.health_certificate,
            "deworming": pet.deworming,
            "birth_certificate": pet.birth_certificate,
            "has_microchip": pet.has_microchip,
            "has_vaccination": pet.has_vaccination,
            "has_healthcertificate": pet.has_healthcertificate,
            "has_dewormed": pet.has_dewormed,
            "has_birthcertificate": pet.has_birthcertificate,
            "image_path": pet.image_path,
            "image_file_name": pet.image_file_name,
            "is_deleted": pet.is_deleted,
            "error": pet.error,
            "created_at": pet.created_at,
            "updated_at": pet.updated_at,
            "location_name": pet.location.name if pet.location else None
        }
        pets_with_location.append(pet_dict)
    
    return pets_with_location


@router.get("/breeder/{breeder_id}", response_model=List[PetRead])
async def get_pets_by_breeder(
    breeder_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = False,
) -> List[dict]:
    """
    Get all pets owned by a specific breeder.
    
    This endpoint is public and does not require authentication.
    By default, soft-deleted pets are excluded.
    Each pet includes the location name if assigned to a location.
    """
    query = select(Pet).where(Pet.user_id == breeder_id)
    
    if not include_deleted:
        query = query.where(Pet.is_deleted == False)
    
    query = query.offset(skip).limit(limit).order_by(Pet.created_at.desc())
    
    result = await session.execute(query)
    pets = result.scalars().all()
    
    # Add location name to each pet
    pets_with_location = []
    for pet in pets:
        pet_dict = {
            "id": pet.id,
            "user_id": pet.user_id,
            "name": pet.name,
            "breed_id": pet.breed_id,
            "breeding_id": pet.breeding_id,
            "location_id": pet.location_id,
            "date_of_birth": pet.date_of_birth,
            "gender": pet.gender,
            "weight": pet.weight,
            "description": pet.description,
            "is_puppy": pet.is_puppy,
            "microchip": pet.microchip,
            "vaccination": pet.vaccination,
            "health_certificate": pet.health_certificate,
            "deworming": pet.deworming,
            "birth_certificate": pet.birth_certificate,
            "has_microchip": pet.has_microchip,
            "has_vaccination": pet.has_vaccination,
            "has_healthcertificate": pet.has_healthcertificate,
            "has_dewormed": pet.has_dewormed,
            "has_birthcertificate": pet.has_birthcertificate,
            "image_path": pet.image_path,
            "image_file_name": pet.image_file_name,
            "is_deleted": pet.is_deleted,
            "error": pet.error,
            "created_at": pet.created_at,
            "updated_at": pet.updated_at,
            "location_name": pet.location.name if pet.location else None
        }
        pets_with_location.append(pet_dict)
    
    return pets_with_location


@router.get("/{pet_id}", response_model=PetRead)
async def get_pet(
    pet_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Pet:
    """
    Get a single pet by ID.
    
    The pet must be owned by the authenticated user.
    """
    query = select(Pet).where(Pet.id == pet_id, Pet.user_id == user.id)
    result = await session.execute(query)
    pet = result.scalar_one_or_none()
    
    if pet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )
    
    return pet


@router.put("/{pet_id}", response_model=PetRead)
async def update_pet(
    pet_id: uuid.UUID,
    pet_update: PetUpdate,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> Pet:
    """
    Update a pet record.
    
    The pet must be owned by the authenticated user.
    Only provided fields will be updated.
    """
    # Fetch the pet
    query = select(Pet).where(Pet.id == pet_id, Pet.user_id == user.id)
    result = await session.execute(query)
    pet = result.scalar_one_or_none()
    
    if pet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )
    
    # Update fields that were provided
    update_data = pet_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pet, field, value)
    
    await session.commit()
    await session.refresh(pet)
    
    return pet


@router.delete("/{pet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pet(
    pet_id: uuid.UUID,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Soft delete a pet record.
    
    The pet must be owned by the authenticated user.
    This sets is_deleted=True but keeps the record in the database.
    """
    # Fetch the pet
    query = select(Pet).where(Pet.id == pet_id, Pet.user_id == user.id)
    result = await session.execute(query)
    pet = result.scalar_one_or_none()
    
    if pet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )
    
    # Soft delete
    pet.is_deleted = True
    await session.commit()



@router.post("/{pet_id}/image", response_model=PetRead)
async def upload_pet_image(
    pet_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
    file_service: FileService = Depends(get_file_service),
) -> Pet:
    """
    Upload an image for a pet.
    
    The pet must be owned by the authenticated user.
    The image will be processed, resized if needed, and stored.
    """
    # Fetch the pet
    query = select(Pet).where(Pet.id == pet_id, Pet.user_id == user.id)
    result = await session.execute(query)
    pet = result.scalar_one_or_none()
    
    if pet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found"
        )
    
    # Delete old image if exists
    if pet.image_path:
        try:
            await file_service.delete_image(pet.image_path)
        except FileNotFoundError:
            # Old image doesn't exist, continue
            pass
    
    # Save new image
    try:
        image_path, image_file_name = await file_service.save_image(file, pet_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # Update pet record
    pet.image_path = image_path
    pet.image_file_name = image_file_name
    
    await session.commit()
    await session.refresh(pet)
    
    return pet
