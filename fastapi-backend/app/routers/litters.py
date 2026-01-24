"""
Litters router for managing litter records.

This module provides CRUD operations for litter management including:
- Creating and updating litter records
- Listing litters with filtering options
- Managing litter information and associations with pets
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.litter import Litter
from app.schemas.litter import LitterCreate, LitterRead, LitterUpdate


router = APIRouter(
    prefix="/api/litters",
    tags=["litters"],
    responses={
        404: {"description": "Litter not found"},
    }
)


@router.post("/", response_model=LitterRead, status_code=status.HTTP_201_CREATED)
async def create_litter(
    litter_data: LitterCreate,
    session: AsyncSession = Depends(get_async_session),
) -> Litter:
    """
    Create a new litter record.
    
    This endpoint is public and does not require authentication.
    A litter represents a group of puppies born together.
    
    **Required fields:**
    - date_of_litter: Date when the litter was born
    
    **Optional fields:**
    - description: Additional information about the litter
    - is_active: Whether the litter is currently active (default: true)
    
    **Example:**
    ```json
    {
        "date_of_litter": "2024-01-15",
        "description": "First litter of 2024",
        "is_active": true
    }
    ```
    
    **Returns:** The created litter record with generated ID
    """
    # Create new litter instance
    litter = Litter(
        date_of_litter=litter_data.date_of_litter,
        description=litter_data.description,
        is_active=litter_data.is_active,
    )
    
    session.add(litter)
    await session.commit()
    await session.refresh(litter)
    
    return litter


@router.get("/", response_model=List[LitterRead])
async def list_litters(
    session: AsyncSession = Depends(get_async_session),
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
) -> List[Litter]:
    """
    List all litters.
    
    This endpoint is public and does not require authentication.
    Results are ordered by date_of_litter descending (most recent first).
    Set active_only=True to filter only active litters.
    """
    query = select(Litter)
    
    if active_only:
        query = query.where(Litter.is_active == True)
    
    query = query.offset(skip).limit(limit).order_by(Litter.date_of_litter.desc())
    
    result = await session.execute(query)
    litters = result.scalars().all()
    
    return list(litters)


@router.get("/{litter_id}", response_model=LitterRead)
async def get_litter(
    litter_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> Litter:
    """
    Get a single litter by ID.
    
    This endpoint is public and does not require authentication.
    """
    query = select(Litter).where(Litter.id == litter_id)
    result = await session.execute(query)
    litter = result.scalar_one_or_none()
    
    if litter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Litter not found"
        )
    
    return litter


@router.put("/{litter_id}", response_model=LitterRead)
async def update_litter(
    litter_id: int,
    litter_update: LitterUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> Litter:
    """
    Update a litter record.
    
    Only provided fields will be updated.
    This endpoint is public and does not require authentication.
    """
    # Fetch the litter
    query = select(Litter).where(Litter.id == litter_id)
    result = await session.execute(query)
    litter = result.scalar_one_or_none()
    
    if litter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Litter not found"
        )
    
    # Update fields that were provided
    update_data = litter_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(litter, field, value)
    
    await session.commit()
    await session.refresh(litter)
    
    return litter


@router.delete("/{litter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_litter(
    litter_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Delete a litter record.
    
    This is a hard delete. The litter will be permanently removed from the database.
    Note: This will fail if there are pets associated with this litter due to foreign key constraints.
    This endpoint is public and does not require authentication.
    """
    # Fetch the litter
    query = select(Litter).where(Litter.id == litter_id)
    result = await session.execute(query)
    litter = result.scalar_one_or_none()
    
    if litter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Litter not found"
        )
    
    # Delete the litter
    await session.delete(litter)
    await session.commit()
