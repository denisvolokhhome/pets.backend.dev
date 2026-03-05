"""Notification model for breeder notifications."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
import uuid

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Notification(Base):
    """
    Notification model for tracking breeder notifications.
    
    Supports various notification types (favorites, messages, etc.)
    with links to related entities.
    """
    __tablename__ = "notifications"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )
    
    # Foreign key to user (recipient)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Notification information
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )  # "favorite_added", "message_received", etc.
    
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    
    message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Related entity information
    related_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True
    )
    
    related_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    
    # Read status
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True
    )
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.type}, is_read={self.is_read})>"
