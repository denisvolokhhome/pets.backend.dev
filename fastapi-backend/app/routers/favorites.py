"""Favorites router for managing offspring favorites."""
from typing import List
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import current_active_user
from app.models.user import User
from app.schemas.offspring_favorite import OffspringFavoriteRead
from app.services.favorite_service import favorite_service
from app.services.notification_service import notification_service


router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.post(
    "/offsprings/{offspring_id}",
    response_model=OffspringFavoriteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add offspring to favorites",
    description="Add an offspring to the authenticated user's favorites list. Creates a notification for the breeder."
)
async def add_favorite(
    offspring_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
) -> OffspringFavoriteRead:
    """
    Add an offspring to favorites.
    
    Args:
        offspring_id: ID of the offspring to favorite
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Created favorite with offspring details
        
    Raises:
        HTTPException: 404 if offspring not found or archived
        HTTPException: 400 if already favorited
    """
    favorite = await favorite_service.add_favorite(
        db=db,
        offspring_id=offspring_id,
        user_id=current_user.id,
        notification_service=notification_service
    )
    
    # Reload the favorite with all relationships using selectinload
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.offspring_favorite import OffspringFavorite
    from app.models.offspring import Offspring
    from app.models.breed import Breed
    from app.models.offspring_image import OffspringImage
    from app.models.breeding import Breeding
    from app.models.pet import Pet
    
    query = (
        select(OffspringFavorite)
        .where(OffspringFavorite.id == favorite.id)
        .options(
            selectinload(OffspringFavorite.offspring).selectinload(Offspring.breed),
            selectinload(OffspringFavorite.offspring).selectinload(Offspring.images),
            selectinload(OffspringFavorite.offspring).selectinload(Offspring.breeding),
            selectinload(OffspringFavorite.offspring).selectinload(Offspring.father),
            selectinload(OffspringFavorite.offspring).selectinload(Offspring.mother),
            selectinload(OffspringFavorite.offspring).selectinload(Offspring.favorites)
        )
    )
    
    result = await db.execute(query)
    favorite_with_relations = result.scalar_one()
    
    return favorite_with_relations


@router.delete(
    "/offsprings/{offspring_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove offspring from favorites",
    description="Remove an offspring from the authenticated user's favorites list."
)
async def remove_favorite(
    offspring_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
) -> None:
    """
    Remove an offspring from favorites.
    
    Args:
        offspring_id: ID of the offspring to unfavorite
        db: Database session
        current_user: Authenticated user
        
    Raises:
        HTTPException: 404 if favorite not found
    """
    await favorite_service.remove_favorite(
        db=db,
        offspring_id=offspring_id,
        user_id=current_user.id
    )


@router.get(
    "/offsprings",
    response_model=List[OffspringFavoriteRead],
    summary="List user's favorites",
    description="Get a paginated list of the authenticated user's favorited offsprings."
)
async def list_favorites(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
) -> List[OffspringFavoriteRead]:
    """
    List user's favorited offsprings.
    
    Args:
        limit: Maximum number of results (default: 50)
        offset: Number of results to skip (default: 0)
        db: Database session
        current_user: Authenticated user
        
    Returns:
        List of favorites with offspring details
    """
    favorites = await favorite_service.list_user_favorites(
        db=db,
        user_id=current_user.id,
        limit=limit,
        offset=offset
    )
    
    return favorites


@router.get(
    "/offsprings/check/{offspring_id}",
    response_model=dict,
    summary="Check favorite status",
    description="Check if an offspring is in the authenticated user's favorites."
)
async def check_favorite_status(
    offspring_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
) -> dict:
    """
    Check if an offspring is favorited by the user.
    
    Args:
        offspring_id: ID of the offspring to check
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Dictionary with is_favorited boolean
    """
    is_favorited = await favorite_service.check_favorite_status(
        db=db,
        offspring_id=offspring_id,
        user_id=current_user.id
    )
    
    return {"is_favorited": is_favorited}
