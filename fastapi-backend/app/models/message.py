"""Message model for breeder-user communication."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
import uuid

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Message(Base):
    """
    Message model for anonymous users to contact breeders.
    
    Allows anonymous/unauthorized users to send messages to breeders.
    Breeders can view, mark as read, and respond to messages.
    """
    __tablename__ = "messages"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )
    
    # Foreign key to user (breeder receiving the message)
    breeder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Sender information (anonymous user)
    sender_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    sender_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )
    
    # Message content
    message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Message status
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True
    )
    
    # Response from breeder
    response_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    responded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True
    )
    
    # Relationships
    breeder: Mapped["User"] = relationship(
        "User",
        back_populates="messages",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<Message(id={self.id}, breeder_id={self.breeder_id}, sender_email={self.sender_email}, is_read={self.is_read})>"
