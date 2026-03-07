"""Notification preference service for managing user notification settings."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_preference import NotificationPreference
from app.schemas.notification_preference import NotificationPreferenceUpdate


class NotificationPreferenceService:
    """Service for managing notification preferences."""
    
    async def get_or_create_preferences(
        self,
        db: AsyncSession,
        user_id: uuid.UUID
    ) -> NotificationPreference:
        """
        Get user's notification preferences or create default ones.
        
        Args:
            db: Database session
            user_id: ID of the user
            
        Returns:
            NotificationPreference instance
        """
        # Try to get existing preferences
        query = select(NotificationPreference).where(
            NotificationPreference.user_id == user_id
        )
        result = await db.execute(query)
        preferences = result.scalar_one_or_none()
        
        # Create default preferences if none exist
        if not preferences:
            preferences = NotificationPreference(
                user_id=user_id,
                message_received=True,  # Enabled by default
                favorite_added=False    # Disabled by default
            )
            db.add(preferences)
            await db.commit()
            await db.refresh(preferences)
        
        return preferences
    
    async def update_preferences(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        preference_data: NotificationPreferenceUpdate
    ) -> NotificationPreference:
        """
        Update user's notification preferences.
        
        Args:
            db: Database session
            user_id: ID of the user
            preference_data: Preference update data
            
        Returns:
            Updated NotificationPreference instance
        """
        # Get or create preferences
        preferences = await self.get_or_create_preferences(db, user_id)
        
        # Update fields if provided
        if preference_data.message_received is not None:
            preferences.message_received = preference_data.message_received
        if preference_data.favorite_added is not None:
            preferences.favorite_added = preference_data.favorite_added
        
        await db.commit()
        await db.refresh(preferences)
        
        return preferences
    
    async def should_send_notification(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        notification_type: str
    ) -> bool:
        """
        Check if a notification should be sent based on user preferences.
        
        Args:
            db: Database session
            user_id: ID of the user
            notification_type: Type of notification (e.g., 'message_received', 'favorite_added')
            
        Returns:
            True if notification should be sent, False otherwise
        """
        preferences = await self.get_or_create_preferences(db, user_id)
        
        # Map notification type to preference field
        if notification_type == "message_received":
            return preferences.message_received
        elif notification_type == "favorite_added":
            return preferences.favorite_added
        
        # Default to True for unknown types (backward compatibility)
        return True


# Singleton instance
notification_preference_service = NotificationPreferenceService()
