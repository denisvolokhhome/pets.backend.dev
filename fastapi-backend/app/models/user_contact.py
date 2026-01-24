"""UserContact model for managing user contact information."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserContact(Base):
    """
    UserContact model representing contact information for a user.
    
    Stores phone numbers, email, social media links, and other contact details.
    Uses integer primary key to match Laravel schema.
    """
    __tablename__ = "user_contacts"
    
    # Primary key (integer to match Laravel)
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    
    # Foreign keys
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    location_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Contact information
    phone_number1: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    phone_number2: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    
    # Social media links
    facebook: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    youtube: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    twitter: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    linkedin: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    website: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    
    # Additional information
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True
    )
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="contacts",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<UserContact(id={self.id}, user_id={self.user_id})>"
