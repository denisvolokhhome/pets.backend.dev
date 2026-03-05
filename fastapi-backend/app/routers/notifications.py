"""Notifications router for managing breeder notifications."""
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import current_active_user
from app.models.user import User
from app.schemas.notification import NotificationRead
from app.services.notification_service import notification_service


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get(
    "/",
    response_model=List[NotificationRead],
    summary="List notifications",
    description="Get a paginated list of notifications for the authenticated user with optional filtering."
)
async def list_notifications(
    is_read: Optional[bool] = Query(None, description="Filter by read status"),
    type: Optional[str] = Query(None, description="Filter by notification type"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
) -> List[NotificationRead]:
    """
    List notifications for the authenticated user.
    
    Args:
        is_read: Optional filter by read status (true/false)
        type: Optional filter by notification type
        limit: Maximum number of results (1-100, default: 50)
        offset: Number of results to skip (default: 0)
        db: Database session
        current_user: Authenticated user
        
    Returns:
        List of notifications ordered by created_at descending
    """
    notifications = await notification_service.list_notifications(
        db=db,
        user_id=current_user.id,
        is_read=is_read,
        notification_type=type,
        limit=limit,
        offset=offset
    )
    
    return notifications


@router.put(
    "/{notification_id}/read",
    response_model=NotificationRead,
    summary="Mark notification as read",
    description="Mark a specific notification as read for the authenticated user."
)
async def mark_notification_as_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
) -> NotificationRead:
    """
    Mark a notification as read.
    
    Args:
        notification_id: ID of the notification to mark as read
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Updated notification
        
    Raises:
        HTTPException: 404 if notification not found or access denied
    """
    notification = await notification_service.mark_as_read(
        db=db,
        notification_id=notification_id,
        user_id=current_user.id
    )
    
    return notification


@router.get(
    "/unread/count",
    response_model=dict,
    summary="Get unread notification count",
    description="Get the count of unread notifications for the authenticated user."
)
async def get_unread_count(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
) -> dict:
    """
    Get unread notification count.
    
    Args:
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Dictionary with count of unread notifications
    """
    count = await notification_service.get_unread_count(
        db=db,
        user_id=current_user.id
    )
    
    return {"count": count}


@router.put(
    "/read-all",
    response_model=dict,
    summary="Mark all notifications as read",
    description="Mark all unread notifications as read for the authenticated user."
)
async def mark_all_as_read(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
) -> dict:
    """
    Mark all notifications as read.
    
    Args:
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Dictionary with count of notifications marked as read
    """
    count = await notification_service.mark_all_as_read(
        db=db,
        user_id=current_user.id
    )
    
    return {"marked_as_read": count}


@router.get(
    "/{notification_id}",
    response_model=NotificationRead,
    summary="Get notification details",
    description="Get details of a specific notification for the authenticated user."
)
async def get_notification(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
) -> NotificationRead:
    """
    Get notification details.
    
    Args:
        notification_id: ID of the notification
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Notification details
        
    Raises:
        HTTPException: 404 if notification not found or access denied
    """
    notification = await notification_service.get_notification(
        db=db,
        notification_id=notification_id,
        user_id=current_user.id
    )
    
    return notification


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete notification",
    description="Delete a specific notification for the authenticated user."
)
async def delete_notification(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
) -> None:
    """
    Delete a notification.
    
    Args:
        notification_id: ID of the notification to delete
        db: Database session
        current_user: Authenticated user
        
    Raises:
        HTTPException: 404 if notification not found or access denied
    """
    await notification_service.delete_notification(
        db=db,
        notification_id=notification_id,
        user_id=current_user.id
    )
