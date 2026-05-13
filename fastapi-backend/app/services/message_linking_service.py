"""Service for linking guest messages to pet seeker accounts."""
import logging
import uuid
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


class MessageLinkingService:
    """
    Service for linking guest messages to pet seeker accounts.

    NOTE: The Message model no longer has sender_email or pet_seeker_id columns
    (removed in a prior migration). Guest users are now auto-registered at the
    point of sending a message, so retroactive linking is no longer needed.
    This service is kept as a no-op stub so the registration endpoint continues
    to work without modification.
    """

    async def link_messages_to_account(
        self,
        email: str,
        user_id: uuid.UUID,
        session: AsyncSession
    ) -> Dict[str, object]:
        """
        No-op stub — returns zero linked messages.

        The columns (sender_email, pet_seeker_id) this method previously relied
        on no longer exist on the Message model.  Guest-to-account conversion
        is handled at message-send time instead.
        """
        logger.debug(
            f"MessageLinkingService.link_messages_to_account called for {email} "
            f"(no-op: columns removed from Message model)"
        )
        return {
            "linked_count": 0,
            "message_ids": []
        }
