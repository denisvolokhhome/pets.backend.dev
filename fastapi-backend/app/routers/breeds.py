"""
Breeds router for managing breed records.

This module provides CRUD operations for dog breed management including:
- Creating and updating breed records
- Listing all available breeds
- Managing breed information (name, code, group)
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.breed import Breed
from app.schemas.breed import BreedCreate, BreedRead, BreedUpdate


router = APIRouter(
    prefix="/api/breeds",
    tags=["breeds"],
    responses={
        404: {"description": "Breed not found"},
        400: {"description": "Breed with this name already exists"},
    }
)


@router.post("/", response_model=BreedRead, status_code=status.HTTP_201_CREATED)
async def create_breed(
    breed_data: BreedCreate,
    session: AsyncSession = Depends(get_async_session),
) -> Breed:
    """
    Create a new breed record.
    
    Breed names must be unique across the system.
    This endpoint is public and does not require authentication.
    
    **Required fields:**
    - name: Breed name (must be unique)
    
    **Optional fields:**
    - code: Breed code (e.g., FCI code)
    - group: Breed group classification (e.g., "Sporting", "Working")
    
    **Example:**
    ```json
    {
        "name": "Labrador Retriever",
        "code": "122",
        "group": "Sporting"
    }
    ```
    
    **Returns:** The created breed record with generated ID
    """
    # Check if breed with same name already exists
    query = select(Breed).where(Breed.name == breed_data.name)
    result = await session.execute(query)
    existing_breed = result.scalar_one_or_none()
    
    if existing_breed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Breed with name '{breed_data.name}' already exists"
        )
    
    # Create new breed instance
    breed = Breed(
        name=breed_data.name,
        code=breed_data.code,
        group=breed_data.group,
    )
    
    session.add(breed)
    await session.commit()
    await session.refresh(breed)
    
    return breed


@router.get("/", response_model=List[BreedRead])
async def list_breeds(
    session: AsyncSession = Depends(get_async_session),
    skip: int = 0,
    limit: int = 100,
) -> List[Breed]:
    """
    List all breeds.
    
    This endpoint is public and does not require authentication.
    Results are ordered alphabetically by name.
    
    **Query parameters:**
    - skip: Number of records to skip (default: 0)
    - limit: Maximum number of records to return (default: 100, max: 100)
    
    **Example response:**
    ```json
    [
        {
            "id": 1,
            "name": "Labrador Retriever",
            "code": "122",
            "group": "Sporting",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
    ]
    ```
    """
    query = select(Breed).offset(skip).limit(limit).order_by(Breed.name)
    
    result = await session.execute(query)
    breeds = result.scalars().all()
    
    return list(breeds)


@router.get("/{breed_id}", response_model=BreedRead)
async def get_breed(
    breed_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> Breed:
    """
    Get a single breed by ID.
    
    This endpoint is public and does not require authentication.
    """
    query = select(Breed).where(Breed.id == breed_id)
    result = await session.execute(query)
    breed = result.scalar_one_or_none()
    
    if breed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Breed not found"
        )
    
    return breed


@router.put("/{breed_id}", response_model=BreedRead)
async def update_breed(
    breed_id: int,
    breed_update: BreedUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> Breed:
    """
    Update a breed record.
    
    Only provided fields will be updated.
    Breed names must remain unique.
    """
    # Fetch the breed
    query = select(Breed).where(Breed.id == breed_id)
    result = await session.execute(query)
    breed = result.scalar_one_or_none()
    
    if breed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Breed not found"
        )
    
    # If updating name, check for uniqueness
    if breed_update.name and breed_update.name != breed.name:
        query = select(Breed).where(Breed.name == breed_update.name)
        result = await session.execute(query)
        existing_breed = result.scalar_one_or_none()
        
        if existing_breed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Breed with name '{breed_update.name}' already exists"
            )
    
    # Update fields that were provided
    update_data = breed_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(breed, field, value)
    
    await session.commit()
    await session.refresh(breed)
    
    return breed


@router.delete("/{breed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_breed(
    breed_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Delete a breed record.
    
    This is a hard delete. The breed will be permanently removed from the database.
    Note: This will fail if there are pets associated with this breed due to foreign key constraints.
    """
    # Fetch the breed
    query = select(Breed).where(Breed.id == breed_id)
    result = await session.execute(query)
    breed = result.scalar_one_or_none()
    
    if breed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Breed not found"
        )
    
    # Delete the breed
    await session.delete(breed)
    await session.commit()
