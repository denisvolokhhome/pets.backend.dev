"""Favorite service for managing offspring favorites."""
from typing import List, Optional
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.offspring_favorite import OffspringFavorite
from app.models.offspring import Offspring
from app.schemas.notification import NotificationCreate


class FavoriteService:
    """Service for managing offspring favorites and related notifications."""
    
    async def add_favorite(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID,
        user_id: uuid.UUID,
        notification_service: Optional[object] = None
    ) -> OffspringFavorite:
        """
        Add an offspring to user's favorites.
        
        Creates a notification for the breeder when a favorite is added.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring to favorite
            user_id: ID of the pet seeker
            notification_service: Optional NotificationService instance for creating notifications
            
        Returns:
            Created OffspringFavorite instance
            
        Raises:
            HTTPException: If offspring not found or already favorited
        """
        # Verify offspring exists and is not archived
        offspring_query = select(Offspring).where(
            Offspring.id == offspring_id,
            Offspring.status != "Archived"
        )
        result = await db.execute(offspring_query)
        offspring = result.scalar_one_or_none()
        
        if not offspring:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offspring not found or not available"
            )
        
        # Create favorite
        favorite = OffspringFavorite(
            offspring_id=offspring_id,
            user_id=user_id
        )
        
        db.add(favorite)
        
        try:
            await db.commit()
            await db.refresh(favorite)
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Offspring already in favorites"
            )
        
        # Create notification for breeder
        if notification_service:
            notification_data = NotificationCreate(
                user_id=offspring.user_id,
                type="favorite_added",
                title="New Favorite",
                message=f"Someone favorited your offspring: {offspring.name or 'Unnamed'}",
                related_id=offspring_id,
                related_type="offspring"
            )
            await notification_service.create_notification(db, notification_data)
        
        return favorite
    
    async def remove_favorite(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> None:
        """
        Remove an offspring from user's favorites.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring to unfavorite
            user_id: ID of the pet seeker
            
        Raises:
            HTTPException: If favorite not found
        """
        # Find favorite
        favorite_query = select(OffspringFavorite).where(
            OffspringFavorite.offspring_id == offspring_id,
            OffspringFavorite.user_id == user_id
        )
        result = await db.execute(favorite_query)
        favorite = result.scalar_one_or_none()
        
        if not favorite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Favorite not found"
            )
        
        await db.delete(favorite)
        await db.commit()
    
    async def check_favorite_status(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> bool:
        """
        Check if an offspring is favorited by a user.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring
            user_id: ID of the user
            
        Returns:
            True if favorited, False otherwise
        """
        favorite_query = select(OffspringFavorite).where(
            OffspringFavorite.offspring_id == offspring_id,
            OffspringFavorite.user_id == user_id
        )
        result = await db.execute(favorite_query)
        favorite = result.scalar_one_or_none()
        
        return favorite is not None
    
    async def list_user_favorites(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[OffspringFavorite]:
        """
        List all favorites for a user with pagination.
        
        Args:
            db: Database session
            user_id: ID of the user
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of OffspringFavorite instances with offspring data
        """
        query = (
            select(OffspringFavorite)
            .where(OffspringFavorite.user_id == user_id)
            .order_by(OffspringFavorite.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        result = await db.execute(query)
        favorites = result.scalars().all()
        
        return list(favorites)
    
    async def get_favorites_count(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID
    ) -> int:
        """
        Get the count of favorites for an offspring.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring
            
        Returns:
            Number of favorites
        """
        count_query = select(func.count(OffspringFavorite.id)).where(
            OffspringFavorite.offspring_id == offspring_id
        )
        result = await db.execute(count_query)
        count = result.scalar_one()
        
        return count
    
    async def get_multiple_favorites_status(
        self,
        db: AsyncSession,
        offspring_ids: List[uuid.UUID],
        user_id: uuid.UUID
    ) -> dict[uuid.UUID, bool]:
        """
        Check favorite status for multiple offsprings at once.
        
        Useful for efficiently checking favorites in list views.
        
        Args:
            db: Database session
            offspring_ids: List of offspring IDs to check
            user_id: ID of the user
            
        Returns:
            Dictionary mapping offspring_id to favorite status
        """
        if not offspring_ids:
            return {}
        
        favorites_query = select(OffspringFavorite.offspring_id).where(
            OffspringFavorite.offspring_id.in_(offspring_ids),
            OffspringFavorite.user_id == user_id
        )
        result = await db.execute(favorites_query)
        favorited_ids = set(result.scalars().all())
        
        return {
            offspring_id: offspring_id in favorited_ids
            for offspring_id in offspring_ids
        }


# Singleton instance
favorite_service = FavoriteService()
