"""
Messages router for breeder-user communication.

This module provides endpoints for anonymous users to contact breeders
and for breeders to manage their messages.
"""
import logging
import uuid
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import current_active_user
from app.models.message import Message
from app.models.user import User
from app.models.offspring import Offspring
from app.schemas.notification import NotificationCreate
from app.services.notification_service import notification_service
from app.schemas.message import (
    MessageCreate,
    MessageResponse,
    MessageListItem,
    MessageListResponse,
    MessageUpdate,
    MessageResponseCreate,
    UnreadCountResponse,
    MessageSendResponse,
    OffspringMessageCreate,
    ThreadMessageResponse,
    ThreadResponse,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/messages",
    tags=["messages"],
    responses={
        404: {"description": "Message not found"},
    }
)


@router.post("/send", response_model=MessageSendResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    message_data: MessageCreate,
    session: AsyncSession = Depends(get_async_session),
) -> MessageSendResponse:
    """
    Send a message to a breeder (public endpoint - no authentication required).
    
    This endpoint allows anonymous users to contact breeders by providing
    their name, email, and an optional message.
    
    **Request Body:**
    ```json
    {
        "breeder_id": "uuid",
        "sender_name": "John Doe",
        "sender_email": "john@example.com",
        "message": "I'm interested in your puppies..."
    }
    ```
    
    **Validation:**
    - breeder_id must be a valid UUID of an existing user
    - sender_name must be at least 2 characters
    - sender_email must be a valid email address
    - message is optional but limited to 2000 characters
    
    **Returns:** Success confirmation message
    """
    # Verify breeder exists
    breeder_query = select(User).where(User.id == message_data.breeder_id)
    breeder_result = await session.execute(breeder_query)
    breeder = breeder_result.scalar_one_or_none()
    
    if breeder is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Breeder not found"
        )
    
    # Create new message
    message = Message(
        breeder_id=message_data.breeder_id,
        sender_name=message_data.sender_name,
        sender_email=message_data.sender_email,
        message=message_data.message,
        is_read=False,
    )
    
    session.add(message)
    await session.commit()
    await session.refresh(message)
    
    logger.info(
        f"New message created: {message.id} from {message.sender_email} "
        f"to breeder {message.breeder_id}"
    )
    
    return MessageSendResponse()


@router.get("/", response_model=MessageListResponse)
async def list_messages(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    status_filter: Optional[str] = Query(
        "all",
        description="Filter by status: 'all', 'read', or 'unread'",
        alias="status"
    ),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of records to return"),
    sort: str = Query("newest", description="Sort order: 'newest' or 'oldest'"),
) -> MessageListResponse:
    """
    List all messages for the authenticated user.
    
    Returns paginated list of messages with filtering and sorting options.
    - Breeders see messages they received (filtered by breeder_id)
    - Pet seekers see messages they sent (filtered by pet_seeker_id)
    
    **Query Parameters:**
    - status: Filter by read status ('all', 'read', 'unread')
    - skip: Number of records to skip (pagination)
    - limit: Maximum number of records to return (1-100)
    - sort: Sort order ('newest' or 'oldest')
    
    **Returns:** Paginated list of messages with total count and unread count
    """
    # Build base query based on user type
    if user.is_breeder:
        # Breeders see messages they received
        query = select(Message).where(Message.breeder_id == user.id)
    else:
        # Pet seekers see messages they sent
        query = select(Message).where(Message.pet_seeker_id == user.id)
    
    # Apply status filter
    if status_filter == "read":
        query = query.where(Message.is_read == True)
    elif status_filter == "unread":
        query = query.where(Message.is_read == False)
    # 'all' means no filter
    
    # Apply sorting
    if sort == "oldest":
        query = query.order_by(Message.created_at.asc())
    else:  # newest (default)
        query = query.order_by(Message.created_at.desc())
    
    # Get total count before pagination
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar()
    
    # Get unread count based on user type
    if user.is_breeder:
        unread_query = select(func.count()).where(
            Message.breeder_id == user.id,
            Message.is_read == False
        )
    else:
        # Pet seekers see unread messages based on whether breeder has responded
        unread_query = select(func.count()).where(
            Message.pet_seeker_id == user.id,
            Message.responded_at.is_(None)
        )
    unread_result = await session.execute(unread_query)
    unread_count = unread_result.scalar()
    
    # Apply pagination
    query = query.offset(skip).limit(limit)
    
    # Execute query
    result = await session.execute(query)
    messages = result.scalars().all()
    
    # Build response with message previews
    message_items = []
    for msg in messages:
        # Create preview (first 100 characters)
        message_preview = None
        if msg.message:
            message_preview = msg.message[:100]
            if len(msg.message) > 100:
                message_preview += "..."
        
        message_items.append(MessageListItem(
            id=msg.id,
            sender_name=msg.sender_name,
            sender_email=msg.sender_email,
            message_preview=message_preview,
            is_read=msg.is_read,
            responded_at=msg.responded_at,
            created_at=msg.created_at,
        ))
    
    return MessageListResponse(
        messages=message_items,
        total=total,
        unread_count=unread_count,
        limit=limit,
        offset=skip,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> UnreadCountResponse:
    """
    Get count of unread messages for the authenticated breeder.
    
    This endpoint is useful for displaying notification badges in the UI.
    Can be polled periodically to update the notification count.
    
    **Returns:** Count of unread messages
    """
    query = select(func.count()).where(
        Message.breeder_id == user.id,
        Message.is_read == False
    )
    result = await session.execute(query)
    unread_count = result.scalar()
    
    return UnreadCountResponse(unread_count=unread_count)


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Message:
    """
    Get a single message by ID.
    
    The message must belong to the authenticated breeder.
    This endpoint does NOT automatically mark the message as read.
    Use the PATCH /messages/{message_id}/read endpoint to mark as read.
    
    **Returns:** Full message details including response if exists
    """
    query = select(Message).where(
        Message.id == message_id,
        Message.breeder_id == user.id
    )
    result = await session.execute(query)
    message = result.scalar_one_or_none()
    
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    return message


@router.patch("/{message_id}/read", response_model=MessageResponse)
async def mark_message_as_read(
    message_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Message:
    """
    Mark a message as read.
    
    The message must belong to the authenticated breeder.
    This endpoint is idempotent - marking an already-read message as read has no effect.
    
    **Returns:** Updated message with is_read=True
    """
    query = select(Message).where(
        Message.id == message_id,
        Message.breeder_id == user.id
    )
    result = await session.execute(query)
    message = result.scalar_one_or_none()
    
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Mark as read
    message.is_read = True
    
    await session.commit()
    await session.refresh(message)
    
    logger.info(f"Message {message_id} marked as read by breeder {user.id}")
    
    return message


@router.post("/{message_id}/respond", response_model=MessageResponse)
async def respond_to_message(
    message_id: UUID,
    response_data: MessageResponseCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Message:
    """
    Respond to a message.
    
    The message must belong to the authenticated breeder.
    This endpoint saves the response text and timestamp.
    The message is automatically marked as read when responded to.
    
    **Request Body:**
    ```json
    {
        "response_text": "Thank you for your interest. The puppies will be available..."
    }
    ```
    
    **Note:** This endpoint only saves the response in the database.
    Actual email sending to the user should be implemented separately.
    
    **Returns:** Updated message with response_text and responded_at timestamp
    """
    query = select(Message).where(
        Message.id == message_id,
        Message.breeder_id == user.id
    )
    result = await session.execute(query)
    message = result.scalar_one_or_none()
    
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Save response
    message.response_text = response_data.response_text
    message.responded_at = datetime.utcnow()
    message.is_read = True  # Automatically mark as read when responding
    
    await session.commit()
    await session.refresh(message)
    
    logger.info(
        f"Breeder {user.id} responded to message {message_id} "
        f"from {message.sender_email}"
    )
    
    # TODO: Send email notification to sender
    # This would require an email service integration
    
    return message



@router.post("/offspring/{offspring_id}", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_offspring_message(
    offspring_id: UUID,
    message_data: OffspringMessageCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Message:
    """
    Send a message to a breeder about a specific offspring (authenticated users only).
    
    This endpoint creates a threaded conversation between a pet seeker and breeder
    about a specific offspring. If this is the first message about this offspring
    from this user, a new thread is created. Otherwise, the message is added to
    the existing thread.
    
    **Authentication Required:** Yes (logged-in users only)
    
    **Request Body:**
    ```json
    {
        "message": "I'm interested in this puppy. Is it still available?"
    }
    ```
    
    **Behavior:**
    - Auto-generates thread_id for new conversations
    - Links message to offspring and thread
    - Creates notification for breeder
    - Associates message with authenticated user (pet_seeker_id)
    
    **Returns:** Created message with thread_id
    """
    # Verify offspring exists
    offspring_query = select(Offspring).where(Offspring.id == offspring_id)
    offspring_result = await session.execute(offspring_query)
    offspring = offspring_result.scalar_one_or_none()
    
    if offspring is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offspring not found"
        )
    
    # Check if there's an existing thread between this user and breeder for this offspring
    existing_thread_query = select(Message).where(
        Message.offspring_id == offspring_id,
        Message.pet_seeker_id == user.id,
        Message.breeder_id == offspring.user_id,
        Message.thread_id.isnot(None)
    ).limit(1)
    existing_thread_result = await session.execute(existing_thread_query)
    existing_message = existing_thread_result.scalar_one_or_none()
    
    # Use existing thread_id or generate new one
    thread_id = existing_message.thread_id if existing_message else uuid.uuid4()
    
    # Create new message
    message = Message(
        breeder_id=offspring.user_id,
        pet_seeker_id=user.id,
        offspring_id=offspring_id,
        thread_id=thread_id,
        sender_name=user.name if user.name else user.email,
        sender_email=user.email,
        message=message_data.message,
        is_read=False,
    )
    
    session.add(message)
    await session.commit()
    await session.refresh(message)
    
    # Create notification for breeder
    notification_data = NotificationCreate(
        user_id=offspring.user_id,
        type="message_received",
        title="New message about offspring",
        message=f"{message.sender_name} sent you a message about {offspring.name or 'an offspring'}",
        related_id=message.id,
        related_type="message"
    )
    await notification_service.create_notification(session, notification_data)
    
    logger.info(
        f"New offspring message created: {message.id} from user {user.id} "
        f"to breeder {offspring.user_id} about offspring {offspring_id} in thread {thread_id}"
    )
    
    return message


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread_messages(
    thread_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> ThreadResponse:
    """
    Get all messages in a thread (authenticated users only).
    
    Returns all messages in a conversation thread between a pet seeker and breeder
    about a specific offspring. Only participants in the thread can access it.
    
    **Authentication Required:** Yes (logged-in users only)
    
    **Authorization:**
    - User must be either the breeder or pet seeker in the thread
    - Returns 404 if thread not found or user is not a participant
    
    **Returns:** Thread details with all messages and offspring context
    """
    # Get all messages in the thread
    messages_query = select(Message).where(
        Message.thread_id == thread_id
    ).order_by(Message.created_at.asc())
    messages_result = await session.execute(messages_query)
    messages = messages_result.scalars().all()
    
    if not messages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )
    
    # Get first message to determine participants and offspring
    first_message = messages[0]
    breeder_id = first_message.breeder_id
    pet_seeker_id = first_message.pet_seeker_id
    offspring_id = first_message.offspring_id
    
    # Verify user is a participant in the thread
    if user.id != breeder_id and user.id != pet_seeker_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found or access denied"
        )
    
    # Mark messages as read if user is the breeder
    if user.id == breeder_id:
        for msg in messages:
            if not msg.is_read:
                msg.is_read = True
        await session.commit()
    
    # Get offspring details for context
    offspring_query = select(Offspring).where(Offspring.id == offspring_id)
    offspring_result = await session.execute(offspring_query)
    offspring = offspring_result.scalar_one_or_none()
    
    # Build thread message responses
    thread_messages = []
    for msg in messages:
        # Determine sender info
        sender_is_breeder = msg.breeder_id == msg.pet_seeker_id if msg.pet_seeker_id else False
        if msg.pet_seeker_id:
            # Message from authenticated user
            sender_query = select(User).where(User.id == msg.pet_seeker_id)
            sender_result = await session.execute(sender_query)
            sender = sender_result.scalar_one_or_none()
            sender_id = msg.pet_seeker_id
            sender_name = msg.sender_name
            sender_is_breeder = sender.is_breeder if sender else False
        else:
            # Anonymous message (shouldn't happen in threads, but handle it)
            sender_id = msg.breeder_id
            sender_name = msg.sender_name
            sender_is_breeder = False
        
        thread_messages.append(ThreadMessageResponse(
            id=msg.id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_is_breeder=sender_is_breeder,
            message=msg.message or "",
            created_at=msg.created_at,
            is_read=msg.is_read
        ))
    
    # Build offspring context
    offspring_context = None
    if offspring:
        offspring_context = {
            "id": str(offspring.id),
            "name": offspring.name,
            "gender": offspring.gender,
            "age": offspring.age,
            "status": offspring.status,
            "price": float(offspring.price) if offspring.price else None,
            "primary_image_url": offspring.primary_image.image_url if offspring.primary_image else None
        }
    
    logger.info(f"Thread {thread_id} accessed by user {user.id}")
    
    return ThreadResponse(
        thread_id=thread_id,
        offspring_id=offspring_id,
        breeder_id=breeder_id,
        pet_seeker_id=pet_seeker_id,
        messages=thread_messages,
        offspring=offspring_context
    )
