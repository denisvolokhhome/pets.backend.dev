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
from app.services.notification_preference_service import notification_preference_service
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


# DEPRECATED: This endpoint is for anonymous messaging which is not supported in the new Message model
# The new model requires authenticated users (sender_id must be a valid user UUID)
# If anonymous messaging is needed, consider creating a separate AnonymousMessage model
# or using a system user account for anonymous messages

# @router.post("/send", response_model=MessageSendResponse, status_code=status.HTTP_201_CREATED)
# async def send_message(
#     message_data: MessageCreate,
#     session: AsyncSession = Depends(get_async_session),
# ) -> MessageSendResponse:
#     """
#     Send a message to a breeder (public endpoint - no authentication required).
#     DEPRECATED - Use /offspring/{offspring_id} endpoint with authentication instead.
#     """
#     pass


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
    - Shows messages where user is either sender or receiver
    
    **Query Parameters:**
    - status: Filter by read status ('all', 'read', 'unread')
    - skip: Number of records to skip (pagination)
    - limit: Maximum number of records to return (1-100)
    - sort: Sort order ('newest' or 'oldest')
    
    **Returns:** Paginated list of messages with total count and unread count
    """
    # Build base query - user sees messages they sent or received
    query = select(Message).where(
        (Message.sender_id == user.id) | (Message.receiver_id == user.id)
    )
    
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
    
    # Get unread count - messages received by user that are unread
    unread_query = select(func.count()).where(
        Message.receiver_id == user.id,
        Message.is_read == False
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
        content_preview = msg.content[:100] if msg.content else ""
        if msg.content and len(msg.content) > 100:
            content_preview += "..."
        
        # Get sender info
        sender_name = msg.sender.name if msg.sender and msg.sender.name else msg.sender.email if msg.sender else "Unknown"
        
        # Get receiver info
        receiver_name = msg.receiver.name if msg.receiver and msg.receiver.name else msg.receiver.email if msg.receiver else "Unknown"
        
        message_items.append(MessageListItem(
            id=msg.id,
            sender_id=msg.sender_id,
            receiver_id=msg.receiver_id,
            thread_id=msg.thread_id,
            content_preview=content_preview,
            context_type=msg.context_type,
            context_id=msg.context_id,
            is_read=msg.is_read,
            created_at=msg.created_at,
            sender_name=sender_name,
            receiver_name=receiver_name,
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
    Get count of unread messages for the authenticated user.
    
    This endpoint is useful for displaying notification badges in the UI.
    Can be polled periodically to update the notification count.
    
    **Returns:** Count of unread messages where user is the receiver
    """
    query = select(func.count()).where(
        Message.receiver_id == user.id,
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
    
    The message must belong to the authenticated user (either as sender or receiver).
    This endpoint does NOT automatically mark the message as read.
    Use the PATCH /messages/{message_id}/read endpoint to mark as read.
    
    **Returns:** Full message details
    """
    # Allow access if user is the sender OR the receiver
    query = select(Message).where(
        Message.id == message_id,
        (Message.sender_id == user.id) | (Message.receiver_id == user.id)
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
    
    The message must belong to the authenticated user (either as sender or receiver).
    This endpoint is idempotent - marking an already-read message as read has no effect.
    
    **Returns:** Updated message with is_read=True
    """
    # Allow access if user is the sender OR the receiver
    query = select(Message).where(
        Message.id == message_id,
        (Message.sender_id == user.id) | (Message.receiver_id == user.id)
    )
    result = await session.execute(query)
    message = result.scalar_one_or_none()
    
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Mark as read using the model method
    message.mark_as_read()
    
    await session.commit()
    await session.refresh(message)
    
    logger.info(f"Message {message_id} marked as read by user {user.id}")
    
    return message


@router.post("/{message_id}/respond", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def respond_to_message(
    message_id: UUID,
    response_data: MessageResponseCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Message:
    """
    Respond to a message by creating a new message in the same thread.
    
    The original message must have been received by the authenticated user.
    This creates a new message record as a response in the same thread.
    
    **Request Body:**
    ```json
    {
        "response_text": "Thank you for your interest. The puppies will be available..."
    }
    ```
    
    **Returns:** Newly created response message
    """
    # Get the original message
    query = select(Message).where(
        Message.id == message_id,
        Message.receiver_id == user.id  # User must be the receiver of original message
    )
    result = await session.execute(query)
    original_message = result.scalar_one_or_none()
    
    if original_message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found or you are not the receiver"
        )
    
    # Mark original message as read
    original_message.mark_as_read()
    
    # Create response message in same thread
    response_message = Message(
        sender_id=user.id,  # Current user is now the sender
        receiver_id=original_message.sender_id,  # Original sender is now the receiver
        thread_id=original_message.thread_id,
        content=response_data.response_text,
        context_type=original_message.context_type,
        context_id=original_message.context_id,
        is_read=False,
    )
    
    session.add(response_message)
    await session.commit()
    await session.refresh(response_message)
    
    logger.info(
        f"User {user.id} responded to message {message_id} "
        f"with new message {response_message.id} in thread {original_message.thread_id}"
    )
    
    # TODO: Send notification to original sender
    
    return response_message



@router.post("/offspring/{offspring_id}", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_offspring_message(
    offspring_id: UUID,
    message_data: OffspringMessageCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Message:
    """
    Send a message about a specific offspring (authenticated users only).
    
    This endpoint creates a threaded conversation between a pet seeker and breeder
    about a specific offspring.
    
    **Authentication Required:** Yes (logged-in users only)
    
    **Request Body:**
    ```json
    {
        "message": "I'm interested in this puppy. Is it still available?",
        "receiver_id": "uuid-of-receiver",  // Required
        "thread_id": "uuid-of-thread"  // Optional - if not provided, generates new thread
    }
    ```
    
    **Behavior:**
    - If thread_id provided: uses it (continuing existing conversation)
    - If thread_id not provided: generates new thread_id (starting new conversation)
    - Creates notification for receiver
    
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
    
    # Get receiver_id from request or default to offspring owner
    receiver_id = getattr(message_data, 'receiver_id', None) or offspring.user_id
    
    # Get thread_id from request or generate new one
    thread_id = getattr(message_data, 'thread_id', None) or uuid.uuid4()
    
    # Create new message
    message = Message(
        sender_id=user.id,
        receiver_id=receiver_id,
        thread_id=thread_id,
        content=message_data.message,
        context_type="offspring",
        context_id=offspring_id,
        is_read=False,
    )
    
    session.add(message)
    await session.commit()
    await session.refresh(message)
    
    # Create notification for receiver (only if they have it enabled)
    should_notify = await notification_preference_service.should_send_notification(
        db=session,
        user_id=receiver_id,
        notification_type="message_received"
    )
    
    if should_notify:
        sender_name = user.name if user.name else user.email
        notification_data = NotificationCreate(
            user_id=receiver_id,
            type="message_received",
            title="New message about offspring",
            message=f"{sender_name} sent you a message about {offspring.name or 'an offspring'}",
            related_id=message.id,
            related_type="message"
        )
        await notification_service.create_notification(session, notification_data)
    
    logger.info(
        f"Message created: {message.id} from user {user.id} "
        f"to user {receiver_id} about offspring {offspring_id} in thread {thread_id}"
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
    
    Returns all messages in a conversation thread. Only participants can access it.
    
    **Authentication Required:** Yes (logged-in users only)
    
    **Authorization:**
    - User must be either sender or receiver of messages in the thread
    - Returns 404 if thread not found or user is not a participant
    
    **Returns:** Thread details with all messages and context
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
    
    # Verify user is a participant in the thread
    user_is_participant = any(
        msg.sender_id == user.id or msg.receiver_id == user.id
        for msg in messages
    )
    
    if not user_is_participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found or access denied"
        )
    
    # Mark messages as read if user is the receiver
    for msg in messages:
        if msg.receiver_id == user.id and not msg.is_read:
            msg.mark_as_read()
    await session.commit()
    
    # Get context (offspring) details if available
    first_message = messages[0]
    offspring_context = None
    offspring_id = None
    
    if first_message.context_type == "offspring" and first_message.context_id:
        offspring_id = first_message.context_id
        offspring_query = select(Offspring).where(Offspring.id == offspring_id)
        offspring_result = await session.execute(offspring_query)
        offspring = offspring_result.scalar_one_or_none()
        
        if offspring:
            offspring_context = {
                "id": str(offspring.id),
                "name": offspring.name,
                "gender": offspring.gender,
                "age": offspring.age,
                "status": offspring.status,
                "price": float(offspring.price) if offspring.price else None,
                "primary_image_url": offspring.primary_image.image_path if offspring.primary_image else None
            }
    
    # Determine the other participant (breeder/pet_seeker)
    # For backward compatibility with frontend
    other_participant_ids = set()
    for msg in messages:
        if msg.sender_id != user.id:
            other_participant_ids.add(msg.sender_id)
        if msg.receiver_id != user.id:
            other_participant_ids.add(msg.receiver_id)
    
    # Get breeder and pet_seeker IDs for backward compatibility
    breeder_id = None
    pet_seeker_id = None
    
    for participant_id in other_participant_ids:
        participant_query = select(User).where(User.id == participant_id)
        participant_result = await session.execute(participant_query)
        participant = participant_result.scalar_one_or_none()
        if participant:
            if participant.is_breeder:
                breeder_id = participant.id
            else:
                pet_seeker_id = participant.id
    
    # If current user is breeder/pet_seeker, set their ID
    if user.is_breeder and not breeder_id:
        breeder_id = user.id
    elif not user.is_breeder and not pet_seeker_id:
        pet_seeker_id = user.id
    
    # Build thread message responses
    thread_messages = []
    for msg in messages:
        sender_name = msg.sender.name if msg.sender and msg.sender.name else msg.sender.email if msg.sender else "Unknown"
        sender_is_breeder = msg.sender.is_breeder if msg.sender else False
        
        # Get profile image URL
        sender_profile_image_url = None
        if msg.sender and msg.sender.profile_image_path:
            sender_profile_image_url = f"/storage/{msg.sender.profile_image_path}"
        
        thread_messages.append(ThreadMessageResponse(
            id=msg.id,
            sender_id=msg.sender_id,
            sender_name=sender_name,
            sender_is_breeder=sender_is_breeder,
            sender_profile_image_url=sender_profile_image_url,
            message=msg.content,
            created_at=msg.created_at,
            is_read=msg.is_read
        ))
    
    logger.info(f"Thread {thread_id} accessed by user {user.id}")
    
    return ThreadResponse(
        thread_id=thread_id,
        offspring_id=offspring_id or uuid.uuid4(),  # Fallback for non-offspring threads
        breeder_id=breeder_id or uuid.uuid4(),  # Fallback
        pet_seeker_id=pet_seeker_id or uuid.uuid4(),  # Fallback
        messages=thread_messages,
        offspring=offspring_context
    )


@router.get("/threads/offspring/{offspring_id}/check", response_model=dict)
async def check_offspring_thread(
    offspring_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    Check if there's an existing thread for an offspring between current user and breeder.
    
    This endpoint helps avoid creating duplicate threads when a user wants to contact
    a breeder about an offspring they've already messaged about.
    
    **Authentication Required:** Yes (logged-in users only)
    
    **Returns:** 
    - thread_id: UUID of existing thread if found, null otherwise
    - has_thread: boolean indicating if thread exists
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
        Message.context_type == "offspring",
        Message.context_id == offspring_id,
        ((Message.sender_id == user.id) & (Message.receiver_id == offspring.user_id)) |
        ((Message.sender_id == offspring.user_id) & (Message.receiver_id == user.id))
    ).limit(1)
    existing_thread_result = await session.execute(existing_thread_query)
    existing_message = existing_thread_result.scalar_one_or_none()
    
    if existing_message:
        return {
            "has_thread": True,
            "thread_id": str(existing_message.thread_id)
        }
    else:
        return {
            "has_thread": False,
            "thread_id": None
        }



@router.get("/threads/offspring/{offspring_id}/count", response_model=dict)
async def count_offspring_threads(
    offspring_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    Count the number of unique conversation threads for a specific offspring.
    
    This endpoint counts distinct threads (unique conversations with different users)
    rather than individual messages. Useful for showing how many people have inquired
    about a specific offspring.
    
    **Authentication Required:** Yes (breeder only)
    
    **Returns:** 
    - offspring_id: UUID of the offspring
    - thread_count: Number of unique conversation threads
    """
    # Verify offspring exists and belongs to user
    offspring_query = select(Offspring).where(
        Offspring.id == offspring_id,
        Offspring.user_id == user.id
    )
    offspring_result = await session.execute(offspring_query)
    offspring = offspring_result.scalar_one_or_none()
    
    if offspring is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offspring not found or does not belong to you"
        )
    
    # Count distinct thread_ids for this offspring
    thread_count_query = select(func.count(func.distinct(Message.thread_id))).where(
        Message.context_type == "offspring",
        Message.context_id == offspring_id
    )
    thread_count_result = await session.execute(thread_count_query)
    thread_count = thread_count_result.scalar()
    
    return {
        "offspring_id": str(offspring_id),
        "thread_count": thread_count or 0
    }
