"""Notification service for managing breeder notifications."""
from typing import List, Optional
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.notification import Notification
from app.schemas.notification import NotificationCreate


class NotificationService:
    """Service for managing notifications for breeders."""
    
    async def create_notification(
        self,
        db: AsyncSession,
        notification_data: NotificationCreate
    ) -> Notification:
        """
        Create a new notification.
        
        Args:
            db: Database session
            notification_data: Notification creation data
            
        Returns:
            Created Notification instance
        """
        notification = Notification(
            user_id=notification_data.user_id,
            type=notification_data.type,
            title=notification_data.title,
            message=notification_data.message,
            related_id=notification_data.related_id,
            related_type=notification_data.related_type
        )
        
        db.add(notification)
        await db.commit()
        await db.refresh(notification)
        
        return notification
    
    async def list_notifications(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        is_read: Optional[bool] = None,
        notification_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Notification]:
        """
        List notifications for a user with filtering and pagination.
        
        Args:
            db: Database session
            user_id: ID of the user
            is_read: Optional filter by read status
            notification_type: Optional filter by notification type
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of Notification instances
        """
        query = select(Notification).where(Notification.user_id == user_id)
        
        if is_read is not None:
            query = query.where(Notification.is_read == is_read)
        
        if notification_type:
            query = query.where(Notification.type == notification_type)
        
        # Order by created_at descending (newest first)
        query = query.order_by(Notification.created_at.desc())
        
        # Apply pagination
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        notifications = result.scalars().all()
        
        return list(notifications)
    
    async def mark_as_read(
        self,
        db: AsyncSession,
        notification_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> Notification:
        """
        Mark a notification as read.
        
        Args:
            db: Database session
            notification_id: ID of the notification
            user_id: ID of the user (for authorization)
            
        Returns:
            Updated Notification instance
            
        Raises:
            HTTPException: If notification not found or access denied
        """
        # Get notification with owner verification
        notification_query = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id
        )
        result = await db.execute(notification_query)
        notification = result.scalar_one_or_none()
        
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found or access denied"
            )
        
        notification.is_read = True
        await db.commit()
        await db.refresh(notification)
        
        return notification
    
    async def mark_all_as_read(
        self,
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> int:
        """
        Mark all notifications as read for a user.
        
        Args:
            db: Database session
            user_id: ID of the user
            
        Returns:
            Number of notifications marked as read
        """
        # Get all unread notifications
        unread_query = select(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read == False
        )
        result = await db.execute(unread_query)
        notifications = result.scalars().all()
        
        # Mark all as read
        count = 0
        for notification in notifications:
            notification.is_read = True
            count += 1
        
        await db.commit()
        
        return count
    
    async def get_unread_count(
        self,
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> int:
        """
        Get the count of unread notifications for a user.
        
        Args:
            db: Database session
            user_id: ID of the user
            
        Returns:
            Number of unread notifications
        """
        count_query = select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read == False
        )
        result = await db.execute(count_query)
        count = result.scalar_one()
        
        return count
    
    async def get_notification(
        self,
        db: AsyncSession,
        notification_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> Notification:
        """
        Get a notification by ID with owner verification.
        
        Args:
            db: Database session
            notification_id: ID of the notification
            user_id: ID of the user (for authorization)
            
        Returns:
            Notification instance
            
        Raises:
            HTTPException: If notification not found or access denied
        """
        notification_query = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id
        )
        result = await db.execute(notification_query)
        notification = result.scalar_one_or_none()
        
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found or access denied"
            )
        
        return notification
    
    async def delete_notification(
        self,
        db: AsyncSession,
        notification_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> None:
        """
        Delete a notification.
        
        Args:
            db: Database session
            notification_id: ID of the notification
            user_id: ID of the user (for authorization)
            
        Raises:
            HTTPException: If notification not found or access denied
        """
        # Get notification with owner verification
        notification = await self.get_notification(db, notification_id, user_id)
        
        await db.delete(notification)
        await db.commit()
    
    async def delete_old_notifications(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        days: int = 30
    ) -> int:
        """
        Delete notifications older than specified days.
        
        Useful for cleanup of old read notifications.
        
        Args:
            db: Database session
            user_id: ID of the user
            days: Number of days to keep (default: 30)
            
        Returns:
            Number of notifications deleted
        """
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Get old notifications
        old_query = select(Notification).where(
            Notification.user_id == user_id,
            Notification.created_at < cutoff_date,
            Notification.is_read == True  # Only delete read notifications
        )
        result = await db.execute(old_query)
        notifications = result.scalars().all()
        
        # Delete notifications
        count = 0
        for notification in notifications:
            await db.delete(notification)
            count += 1
        
        await db.commit()
        
        return count


# Singleton instance
notification_service = NotificationService()
