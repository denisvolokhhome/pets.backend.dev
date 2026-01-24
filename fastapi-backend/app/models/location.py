"""Location model for managing breeder locations."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Location(Base):
    """
    Location model representing a physical location for a breeder.
    
    Associated with a user and can be linked to pets.
    Uses integer primary key to match Laravel schema.
    """
    __tablename__ = "locations"
    
    # Primary key (integer to match Laravel)
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    
    # Foreign key to user
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # Location information
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    address1: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    address2: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    city: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    country: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    zipcode: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )
    location_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type: user or pet"
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
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="locations",
        lazy="selectin"
    )
    pets: Mapped[list["Pet"]] = relationship(
        "Pet",
        back_populates="location",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<Location(id={self.id}, name={self.name}, user_id={self.user_id})>"
