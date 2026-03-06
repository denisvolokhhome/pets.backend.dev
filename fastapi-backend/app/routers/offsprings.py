"""
Offsprings router for managing individual animals from litters.

This module provides CRUD operations for offspring management including:
- Creating and updating offspring records
- Listing offsprings with filtering options
- Managing offspring images
- Public offspring viewing for pet seekers
"""
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_async_session
from app.dependencies import current_active_user, require_breeder, optional_current_user
from app.models.user import User
from app.schemas.offspring import OffspringCreate, OffspringRead, OffspringUpdate, OffspringListResponse
from app.schemas.offspring_image import OffspringImageRead
from app.services.offspring_service import offspring_service
from app.services.offspring_image_service import OffspringImageService
from app.services.favorite_service import favorite_service
from app.services.file_service import FileService


router = APIRouter(
    prefix="/api/offsprings",
    tags=["offsprings"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized to access this resource"},
        404: {"description": "Offspring not found"},
    }
)


def get_file_service() -> FileService:
    """Dependency to get FileService instance."""
    settings = Settings()
    return FileService(settings)


def get_offspring_image_service(
    file_service: FileService = Depends(get_file_service)
) -> OffspringImageService:
    """Dependency to get OffspringImageService instance."""
    return OffspringImageService(file_service)


@router.post("/", response_model=OffspringRead, status_code=status.HTTP_201_CREATED)
async def create_offspring(
    offspring_data: OffspringCreate,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    Create a new offspring record.
    
    The offspring will be associated with the authenticated breeder.
    Breed is auto-populated from the breeding record.
    
    **Required fields:**
    - breeding_id: Reference to breeding (must exist and belong to user)
    - gender: "Male" or "Female"
    - date_of_birth: Birth date (cannot be in future)
    
    **Optional fields:**
    - name: Offspring name (auto-generated if not provided)
    - status: "Available", "Reserved", "Sold", or "Archived" (default: "Available")
    - price: Price in currency (must be positive)
    - description: Detailed description
    - color_markings: Physical appearance details
    
    **Returns:** The created offspring record with computed fields
    
    **Requirements:** 1.1, 1.2, 1.3, 10.1
    """
    offspring = await offspring_service.create_offspring(
        db=session,
        offspring_data=offspring_data,
        user_id=user.id
    )
    
    # Build response with computed fields
    return await _build_offspring_response(session, offspring, user_id=None)


@router.get("/", response_model=OffspringListResponse)
async def list_offsprings(
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    breed_id: Optional[int] = Query(None, description="Filter by breed ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """
    List all offsprings owned by the authenticated breeder.
    
    Results are ordered by created_at descending (most recent first).
    
    **Query Parameters:**
    - status_filter: Filter by status (Available, Reserved, Sold, Archived)
    - breed_id: Filter by breed ID
    - limit: Maximum number of records to return (1-100)
    - offset: Number of records to skip (pagination)
    
    **Returns:** Paginated list of offsprings with computed fields
    
    **Requirements:** 1.1, 1.2, 10.1
    """
    offsprings = await offspring_service.list_offsprings(
        db=session,
        user_id=user.id,
        status_filter=status_filter,
        breed_id=breed_id,
        limit=limit,
        offset=offset
    )
    
    # Get total count
    total = await offspring_service.count_offsprings(
        db=session,
        user_id=user.id,
        status_filter=status_filter,
        breed_id=breed_id
    )
    
    # Build responses with computed fields
    responses = []
    for offspring in offsprings:
        response = await _build_offspring_response(session, offspring, user_id=None)
        responses.append(response)
    
    return {
        "offsprings": responses,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/{offspring_id}", response_model=OffspringRead)
async def get_offspring(
    offspring_id: uuid.UUID,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    Get a single offspring by ID.
    
    The offspring must be owned by the authenticated breeder.
    
    **Returns:** Offspring details with relationships and computed fields
    
    **Requirements:** 1.1, 10.1, 10.2
    """
    offspring = await offspring_service.get_offspring(
        db=session,
        offspring_id=offspring_id,
        user_id=user.id,
        check_owner=True
    )
    
    return await _build_offspring_response(session, offspring, user_id=None)


@router.put("/{offspring_id}", response_model=OffspringRead)
async def update_offspring(
    offspring_id: uuid.UUID,
    offspring_update: OffspringUpdate,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    Update an offspring record.
    
    The offspring must be owned by the authenticated breeder.
    Only provided fields will be updated.
    Breeding relationship, gender, and date_of_birth are immutable.
    
    **Updatable fields:**
    - name: Offspring name
    - status: Availability status
    - price: Price in currency
    - description: Detailed description
    - color_markings: Physical appearance details
    
    **Returns:** Updated offspring record
    
    **Requirements:** 1.5, 10.1, 10.2
    """
    offspring = await offspring_service.update_offspring(
        db=session,
        offspring_id=offspring_id,
        offspring_data=offspring_update,
        user_id=user.id
    )
    
    return await _build_offspring_response(session, offspring, user_id=None)


@router.delete("/{offspring_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_offspring(
    offspring_id: uuid.UUID,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Delete an offspring record.
    
    The offspring must be owned by the authenticated breeder.
    This permanently deletes the record and associated images.
    
    **Requirements:** 10.1, 10.2, 10.4
    """
    await offspring_service.delete_offspring(
        db=session,
        offspring_id=offspring_id,
        user_id=user.id
    )




# Public endpoints for pet seekers

@router.get("/public/breeder/{breeder_id}", response_model=OffspringListResponse)
async def list_public_offsprings(
    breeder_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: Optional[User] = Depends(optional_current_user),
    breed_id: Optional[int] = Query(None, description="Filter by breed ID"),
    gender: Optional[str] = Query(None, description="Filter by gender (Male/Female)"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """
    List public offsprings for a breeder (excludes Archived).
    
    This endpoint is public and does not require authentication.
    If user is authenticated, favorite status is included in response.
    
    **Query Parameters:**
    - breed_id: Filter by breed ID
    - gender: Filter by gender (Male or Female)
    - status_filter: Filter by status (Available, Reserved, Sold)
    - limit: Maximum number of records to return (1-100)
    - offset: Number of records to skip (pagination)
    
    **Returns:** Paginated list of public offsprings with favorite status if authenticated
    
    **Requirements:** 2.3, 4.1, 4.2, 4.3, 4.4, 10.3, 10.7, 13.1, 13.2, 13.3, 13.4, 13.5
    """
    offsprings = await offspring_service.list_public_offsprings(
        db=session,
        breeder_id=breeder_id,
        breed_id=breed_id,
        gender=gender,
        status_filter=status_filter,
        limit=limit,
        offset=offset
    )
    
    # Get total count
    total = await offspring_service.count_public_offsprings(
        db=session,
        breeder_id=breeder_id,
        breed_id=breed_id,
        gender=gender,
        status_filter=status_filter
    )
    
    # Build responses with computed fields and favorite status
    responses = []
    for offspring in offsprings:
        response = await _build_offspring_response(
            session,
            offspring,
            user_id=user.id if user else None
        )
        responses.append(response)
    
    return {
        "offsprings": responses,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/public/{offspring_id}", response_model=OffspringRead)
async def get_public_offspring(
    offspring_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: Optional[User] = Depends(optional_current_user),
) -> dict:
    """
    Get public offspring details by ID (excludes Archived).
    
    This endpoint is public and does not require authentication.
    If user is authenticated, favorite status is included in response.
    
    **Returns:** Public offspring details with favorite status if authenticated
    
    **Requirements:** 4.1, 4.2, 4.3, 4.4, 10.3
    """
    offspring = await offspring_service.get_public_offspring(
        db=session,
        offspring_id=offspring_id
    )
    
    return await _build_offspring_response(
        session,
        offspring,
        user_id=user.id if user else None
    )


# Image management endpoints

@router.post("/{offspring_id}/images", response_model=OffspringImageRead, status_code=status.HTTP_201_CREATED)
async def upload_offspring_image(
    offspring_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
    image_service: OffspringImageService = Depends(get_offspring_image_service),
) -> OffspringImageRead:
    """
    Upload an image for an offspring.
    
    The offspring must be owned by the authenticated breeder.
    The image will be processed, resized if needed, and stored.
    
    **Returns:** Created OffspringImage record
    
    **Requirements:** 11.1, 11.7
    """
    offspring_image = await image_service.upload_image(
        db=session,
        offspring_id=offspring_id,
        file=file,
        user_id=user.id,
        is_primary=False
    )
    
    return offspring_image


@router.delete("/{offspring_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_offspring_image(
    offspring_id: uuid.UUID,
    image_id: uuid.UUID,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
    image_service: OffspringImageService = Depends(get_offspring_image_service),
) -> None:
    """
    Delete a specific image from an offspring.
    
    The offspring must be owned by the authenticated breeder.
    
    **Requirements:** 11.2, 11.7
    """
    await image_service.delete_image(
        db=session,
        offspring_id=offspring_id,
        image_id=image_id,
        user_id=user.id
    )


@router.put("/{offspring_id}/images/{image_id}/primary", response_model=OffspringImageRead)
async def set_primary_offspring_image(
    offspring_id: uuid.UUID,
    image_id: uuid.UUID,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
    image_service: OffspringImageService = Depends(get_offspring_image_service),
) -> OffspringImageRead:
    """
    Set an image as the primary image for an offspring.
    
    The offspring must be owned by the authenticated breeder.
    Only one image per offspring can be primary.
    
    **Returns:** Updated OffspringImage record
    
    **Requirements:** 11.3, 11.7
    """
    offspring_image = await image_service.set_primary_image(
        db=session,
        offspring_id=offspring_id,
        image_id=image_id,
        user_id=user.id
    )
    
    return offspring_image


@router.put("/{offspring_id}/images/reorder", response_model=List[OffspringImageRead])
async def reorder_offspring_images(
    offspring_id: uuid.UUID,
    image_ids: List[uuid.UUID],
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
    image_service: OffspringImageService = Depends(get_offspring_image_service),
) -> List[OffspringImageRead]:
    """
    Reorder images for an offspring.
    
    The offspring must be owned by the authenticated breeder.
    Provide a list of image IDs in the desired display order.
    
    **Request Body:** List of image IDs in desired order
    
    **Returns:** List of updated OffspringImage records
    
    **Requirements:** 11.8, 11.7
    """
    offspring_images = await image_service.reorder_images(
        db=session,
        offspring_id=offspring_id,
        image_ids=image_ids,
        user_id=user.id
    )
    
    return offspring_images


# Helper functions

async def _build_offspring_response(
    session: AsyncSession,
    offspring,
    user_id: Optional[uuid.UUID] = None
) -> dict:
    """
    Build offspring response with computed fields and relationships.
    
    Args:
        session: Database session
        offspring: Offspring model instance
        user_id: Optional user ID for favorite status
        
    Returns:
        Dictionary with offspring data and computed fields
    """
    # Calculate age
    age = offspring_service.calculate_age(offspring.date_of_birth)
    
    # Use already-loaded relationships instead of making new queries
    favorites_count = len(offspring.favorites) if offspring.favorites else 0
    messages_count = len(offspring.messages) if offspring.messages else 0
    images = offspring.images if offspring.images else []
    
    # Get primary image
    primary_image = next((img for img in images if img.is_primary), images[0] if images else None)
    
    # Use already-loaded relationships
    breeding = offspring.breeding
    breed = offspring.breed
    father = offspring.father
    mother = offspring.mother
    
    # Check favorite status if user is authenticated
    is_favorited = False
    if user_id and offspring.favorites:
        is_favorited = any(fav.user_id == user_id for fav in offspring.favorites)
    
    # Build response
    response = {
        "id": offspring.id,
        "breeding_id": offspring.breeding_id,
        "user_id": offspring.user_id,
        "breed_id": offspring.breed_id,
        "name": offspring.name,
        "gender": offspring.gender,
        "date_of_birth": offspring.date_of_birth,
        "status": offspring.status,
        "price": offspring.price,
        "description": offspring.description,
        "color_markings": offspring.color_markings,
        "created_at": offspring.created_at,
        "updated_at": offspring.updated_at,
        "age": age,
        "favorites_count": favorites_count,
        "messages_count": messages_count,
        "breeding": {
            "id": breeding.id,
            "description": breeding.description,
            "status": breeding.status,
            "created_at": breeding.created_at,
            "updated_at": breeding.updated_at
        } if breeding else None,
        "breed": {
            "id": breed.id,
            "name": breed.name,
            "kind": breed.kind,
            "created_at": breed.created_at,
            "updated_at": breed.updated_at
        } if breed else None,
        "images": [
            {
                "id": img.id,
                "offspring_id": img.offspring_id,
                "image_path": img.image_path,
                "image_url": f"/storage/{img.image_path}",
                "is_primary": img.is_primary,
                "display_order": img.display_order,
                "created_at": img.created_at
            }
            for img in images
        ],
        "primary_image": {
            "id": primary_image.id,
            "offspring_id": primary_image.offspring_id,
            "image_path": primary_image.image_path,
            "image_url": f"/storage/{primary_image.image_path}",
            "is_primary": primary_image.is_primary,
            "display_order": primary_image.display_order,
            "created_at": primary_image.created_at
        } if primary_image else None,
        "father": {
            "id": father.id,
            "user_id": father.user_id,
            "name": father.name,
            "breed_id": father.breed_id,
            "breeding_id": father.breeding_id,
            "location_id": father.location_id,
            "date_of_birth": father.date_of_birth,
            "gender": father.gender,
            "weight": father.weight,
            "description": father.description,
            "microchip": father.microchip,
            "vaccination": father.vaccination,
            "health_certificate": father.health_certificate,
            "deworming": father.deworming,
            "birth_certificate": father.birth_certificate,
            "has_microchip": father.has_microchip,
            "has_vaccination": father.has_vaccination,
            "has_healthcertificate": father.has_healthcertificate,
            "has_dewormed": father.has_dewormed,
            "has_birthcertificate": father.has_birthcertificate,
            "image_path": father.image_path,
            "image_file_name": father.image_file_name,
            "images": [],
            "is_deleted": father.is_deleted,
            "error": None,
            "created_at": father.created_at,
            "updated_at": father.updated_at,
            "location_name": None
        } if father else None,
        "mother": {
            "id": mother.id,
            "user_id": mother.user_id,
            "name": mother.name,
            "breed_id": mother.breed_id,
            "breeding_id": mother.breeding_id,
            "location_id": mother.location_id,
            "date_of_birth": mother.date_of_birth,
            "gender": mother.gender,
            "weight": mother.weight,
            "description": mother.description,
            "microchip": mother.microchip,
            "vaccination": mother.vaccination,
            "health_certificate": mother.health_certificate,
            "deworming": mother.deworming,
            "birth_certificate": mother.birth_certificate,
            "has_microchip": mother.has_microchip,
            "has_vaccination": mother.has_vaccination,
            "has_healthcertificate": mother.has_healthcertificate,
            "has_dewormed": mother.has_dewormed,
            "has_birthcertificate": mother.has_birthcertificate,
            "image_path": mother.image_path,
            "image_file_name": mother.image_file_name,
            "images": [],
            "is_deleted": mother.is_deleted,
            "error": None,
            "created_at": mother.created_at,
            "updated_at": mother.updated_at,
            "location_name": None
        } if mother else None,
    }
    
    # Add favorite status if user is authenticated
    if user_id:
        response["is_favorited"] = is_favorited
    
    return response
