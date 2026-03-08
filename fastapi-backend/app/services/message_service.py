"""Message service for handling message operations."""
import uuid
from datetime import datetime
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.user import User
from app.models.offspring import Offspring
from app.schemas.message import MessageCreate, MessageResponse, ConversationResponse, MessageListItem


class MessageService:
    """Service for message operations."""
    
    @staticmethod
    async def create_message(
        db: AsyncSession,
        sender_id: UUID,
        message_data: MessageCreate
    ) -> Message:
        """
        Create a new message.
        
        Args:
            db: Database session
            sender_id: ID of the message sender
            message_data: Message creation data
            
        Returns:
            Created message
        """
        # Generate thread_id if not provided
        thread_id = message_data.thread_id
        if not thread_id:
            # Create new thread_id for new conversation
            thread_id = uuid.uuid4()
        
        message = Message(
            sender_id=sender_id,
            receiver_id=message_data.receiver_id,
            thread_id=thread_id,
            content=message_data.content,
            context_type=message_data.context_type,
            context_id=message_data.context_id,
            is_read=False
        )
        
        db.add(message)
        await db.commit()
        await db.refresh(message)
        
        return message
    
    @staticmethod
    async def get_message(
        db: AsyncSession,
        message_id: UUID,
        user_id: UUID
    ) -> Optional[Message]:
        """
        Get a message by ID.
        
        Args:
            db: Database session
            message_id: Message ID
            user_id: Current user ID (for authorization)
            
        Returns:
            Message if found and user is authorized, None otherwise
        """
        query = select(Message).where(
            Message.id == message_id,
            or_(
                Message.sender_id == user_id,
                Message.receiver_id == user_id
            ),
            Message.deleted_at.is_(None)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_thread_messages(
        db: AsyncSession,
        thread_id: UUID,
        user_id: UUID,
        limit: int = 100
    ) -> List[Message]:
        """
        Get all messages in a thread.
        
        Args:
            db: Database session
            thread_id: Thread ID
            user_id: Current user ID (for authorization)
            limit: Maximum number of messages to return
            
        Returns:
            List of messages in the thread
        """
        # First verify user is participant in this thread
        participant_check = select(Message).where(
            Message.thread_id == thread_id,
            or_(
                Message.sender_id == user_id,
                Message.receiver_id == user_id
            )
        ).limit(1)
        result = await db.execute(participant_check)
        if not result.scalar_one_or_none():
            return []
        
        # Get messages in thread
        query = select(Message).where(
            Message.thread_id == thread_id,
            Message.deleted_at.is_(None)
        ).order_by(Message.created_at.asc()).limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def mark_as_read(
        db: AsyncSession,
        message_id: UUID,
        user_id: UUID
    ) -> Optional[Message]:
        """
        Mark a message as read.
        
        Args:
            db: Database session
            message_id: Message ID
            user_id: Current user ID (must be receiver)
            
        Returns:
            Updated message if successful, None otherwise
        """
        query = select(Message).where(
            Message.id == message_id,
            Message.receiver_id == user_id,
            Message.deleted_at.is_(None)
        )
        result = await db.execute(query)
        message = result.scalar_one_or_none()
        
        if message:
            message.mark_as_read()
            await db.commit()
            await db.refresh(message)
        
        return message
    
    @staticmethod
    async def mark_thread_as_read(
        db: AsyncSession,
        thread_id: UUID,
        user_id: UUID
    ) -> int:
        """
        Mark all messages in a thread as read for the current user.
        
        Args:
            db: Database session
            thread_id: Thread ID
            user_id: Current user ID (must be receiver)
            
        Returns:
            Number of messages marked as read
        """
        query = select(Message).where(
            Message.thread_id == thread_id,
            Message.receiver_id == user_id,
            Message.is_read == False,
            Message.deleted_at.is_(None)
        )
        result = await db.execute(query)
        messages = result.scalars().all()
        
        count = 0
        for message in messages:
            message.mark_as_read()
            count += 1
        
        if count > 0:
            await db.commit()
        
        return count
    
    @staticmethod
    async def get_conversations(
        db: AsyncSession,
        user_id: UUID,
        skip: int = 0,
        limit: int = 20
    ) -> Tuple[List[ConversationResponse], int, int]:
        """
        Get user's conversations with pagination.
        
        Args:
            db: Database session
            user_id: Current user ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            Tuple of (conversations, total_count, unread_count)
        """
        # Subquery to get latest message per thread
        latest_message_subq = (
            select(
                Message.thread_id,
                func.max(Message.created_at).label('last_activity')
            )
            .where(
                or_(
                    Message.sender_id == user_id,
                    Message.receiver_id == user_id
                ),
                Message.deleted_at.is_(None)
            )
            .group_by(Message.thread_id)
            .subquery()
        )
        
        # Get threads with latest message
        query = (
            select(Message)
            .join(
                latest_message_subq,
                and_(
                    Message.thread_id == latest_message_subq.c.thread_id,
                    Message.created_at == latest_message_subq.c.last_activity
                )
            )
            .where(
                or_(
                    Message.sender_id == user_id,
                    Message.receiver_id == user_id
                ),
                Message.deleted_at.is_(None)
            )
            .order_by(latest_message_subq.c.last_activity.desc())
            .offset(skip)
            .limit(limit)
        )
        
        result = await db.execute(query)
        latest_messages = result.scalars().all()
        
        # Build conversation responses
        conversations = []
        for msg in latest_messages:
            # Determine the other participant
            participant_id = msg.receiver_id if msg.sender_id == user_id else msg.sender_id
            
            # Get participant info
            participant_query = select(User).where(User.id == participant_id)
            participant_result = await db.execute(participant_query)
            participant = participant_result.scalar_one_or_none()
            
            if not participant:
                continue
            
            # Count unread messages in this thread
            unread_query = select(func.count()).where(
                Message.thread_id == msg.thread_id,
                Message.receiver_id == user_id,
                Message.is_read == False,
                Message.deleted_at.is_(None)
            )
            unread_result = await db.execute(unread_query)
            unread_count = unread_result.scalar()
            
            # Count total messages in thread
            total_query = select(func.count()).where(
                Message.thread_id == msg.thread_id,
                Message.deleted_at.is_(None)
            )
            total_result = await db.execute(total_query)
            message_count = total_result.scalar()
            
            # Create message preview
            content_preview = msg.content[:100]
            if len(msg.content) > 100:
                content_preview += "..."
            
            conversations.append(ConversationResponse(
                thread_id=msg.thread_id,
                participant_id=participant_id,
                participant_name=participant.name or participant.email,
                participant_email=participant.email,
                participant_is_breeder=participant.is_breeder,
                last_message=MessageListItem(
                    id=msg.id,
                    sender_id=msg.sender_id,
                    receiver_id=msg.receiver_id,
                    thread_id=msg.thread_id,
                    content_preview=content_preview,
                    context_type=msg.context_type,
                    context_id=msg.context_id,
                    is_read=msg.is_read,
                    created_at=msg.created_at,
                    sender_name=msg.sender.name if msg.sender else None
                ),
                unread_count=unread_count,
                message_count=message_count,
                context_type=msg.context_type,
                context_id=msg.context_id,
                last_activity=msg.created_at
            ))
        
        # Get total conversation count
        total_query = select(func.count(func.distinct(Message.thread_id))).where(
            or_(
                Message.sender_id == user_id,
                Message.receiver_id == user_id
            ),
            Message.deleted_at.is_(None)
        )
        total_result = await db.execute(total_query)
        total_count = total_result.scalar()
        
        # Get total unread count
        unread_total_query = select(func.count()).where(
            Message.receiver_id == user_id,
            Message.is_read == False,
            Message.deleted_at.is_(None)
        )
        unread_total_result = await db.execute(unread_total_query)
        unread_total = unread_total_result.scalar()
        
        return conversations, total_count, unread_total
    
    @staticmethod
    async def get_or_create_thread_id(
        db: AsyncSession,
        user1_id: UUID,
        user2_id: UUID,
        context_type: Optional[str] = None,
        context_id: Optional[UUID] = None
    ) -> UUID:
        """
        Get existing thread_id or create new one for a conversation.
        
        Args:
            db: Database session
            user1_id: First participant ID
            user2_id: Second participant ID
            context_type: Optional context type
            context_id: Optional context ID
            
        Returns:
            Thread ID
        """
        # Look for existing conversation
        query = select(Message.thread_id).where(
            or_(
                and_(
                    Message.sender_id == user1_id,
                    Message.receiver_id == user2_id
                ),
                and_(
                    Message.sender_id == user2_id,
                    Message.receiver_id == user1_id
                )
            ),
            Message.deleted_at.is_(None)
        )
        
        if context_type and context_id:
            query = query.where(
                Message.context_type == context_type,
                Message.context_id == context_id
            )
        
        query = query.limit(1)
        result = await db.execute(query)
        thread_id = result.scalar_one_or_none()
        
        if thread_id:
            return thread_id
        
        # Create new thread_id
        return uuid.uuid4()
    
    @staticmethod
    async def delete_message(
        db: AsyncSession,
        message_id: UUID,
        user_id: UUID
    ) -> bool:
        """
        Soft delete a message.
        
        Args:
            db: Database session
            message_id: Message ID
            user_id: Current user ID (must be sender)
            
        Returns:
            True if successful, False otherwise
        """
        query = select(Message).where(
            Message.id == message_id,
            Message.sender_id == user_id,
            Message.deleted_at.is_(None)
        )
        result = await db.execute(query)
        message = result.scalar_one_or_none()
        
        if message:
            message.soft_delete()
            await db.commit()
            return True
        
        return False


# Create singleton instance
message_service = MessageService()
