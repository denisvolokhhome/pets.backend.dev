"""Service for linking guest messages to pet seeker accounts."""
import logging
import uuid
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


logger = logging.getLogger(__name__)


class MessageLinkingService:
    """
    Service for linking guest messages to pet seeker accounts.
    
    When a guest user sends messages and later creates an account,
    this service links their previous messages to the new account.
    """
    
    async def link_messages_to_account(
        self,
        email: str,
        user_id: uuid.UUID,
        session: AsyncSession
    ) -> Dict[str, any]:
        """
        Link all messages sent from an email to a user account.
        
        Finds all messages where:
        - sender_email matches the provided email
        - pet_seeker_id is NULL (not yet linked to an account)
        
        Updates those messages to set pet_seeker_id to the provided user_id.
        
        Args:
            email: Email address used to send guest messages
            user_id: UUID of the pet seeker account to link messages to
            session: Database session for executing queries
            
        Returns:
            Dict containing:
                - linked_count: Number of messages linked
                - message_ids: List of UUIDs of linked messages
                
        Raises:
            Exception: If database operation fails
        """
        try:
            # Query messages table: WHERE sender_email = email AND pet_seeker_id IS NULL
            stmt = select(Message).where(
                Message.sender_email == email,
                Message.pet_seeker_id.is_(None)
            )
            result = await session.execute(stmt)
            messages = result.scalars().all()
            
            # Update matching messages to set pet_seeker_id = user_id
            message_ids = []
            for message in messages:
                message.pet_seeker_id = user_id
                message_ids.append(message.id)
            
            # Commit the changes
            await session.commit()
            
            linked_count = len(message_ids)
            
            logger.info(
                f"Successfully linked {linked_count} messages from {email} "
                f"to pet seeker account {user_id}"
            )
            
            # Return dict with count and list of linked message IDs
            return {
                "linked_count": linked_count,
                "message_ids": message_ids
            }
            
        except Exception as e:
            # Rollback on error
            await session.rollback()
            logger.error(
                f"Failed to link messages from {email} to account {user_id}: {str(e)}"
            )
            raise
