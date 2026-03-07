"""Notification preferences router for managing user notification settings."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import current_active_user
from app.models.user import User
from app.schemas.notification_preference import (
    NotificationPreferenceRead,
    NotificationPreferenceUpdate
)
from app.services.notification_preference_service import notification_preference_service


router = APIRouter(prefix="/api/notification-preferences", tags=["notification-preferences"])


@router.get(
    "/",
    response_model=NotificationPreferenceRead,
    summary="Get notification preferences",
    description="Get the notification preferences for the authenticated user."
)
async def get_notification_preferences(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
) -> NotificationPreferenceRead:
    """
    Get notification preferences for the authenticated user.
    Creates default preferences if none exist.
    
    Args:
        db: Database session
        current_user: Authenticated user
        
    Returns:
        User's notification preferences
    """
    preferences = await notification_preference_service.get_or_create_preferences(
        db=db,
        user_id=current_user.id
    )
    
    return preferences


@router.put(
    "/",
    response_model=NotificationPreferenceRead,
    summary="Update notification preferences",
    description="Update the notification preferences for the authenticated user."
)
async def update_notification_preferences(
    preference_data: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
) -> NotificationPreferenceRead:
    """
    Update notification preferences for the authenticated user.
    
    Args:
        preference_data: Preference update data
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Updated notification preferences
    """
    preferences = await notification_preference_service.update_preferences(
        db=db,
        user_id=current_user.id,
        preference_data=preference_data
    )
    
    return preferences
