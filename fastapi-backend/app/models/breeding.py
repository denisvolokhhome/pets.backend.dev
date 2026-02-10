"""Breeding model for managing groups of puppies."""
from datetime import datetime, date
from typing import Optional, TYPE_CHECKING
import uuid

from sqlalchemy import String, Text, Boolean, Integer, Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.pet import Pet
    from app.models.litter_pet import BreedingPet
    from app.models.user import User


class Breeding(Base):
    """
    Breeding model representing a group of puppies born together.
    
    One-to-many relationship with Pet (multiple pets can belong to one breeding).
    Many-to-one relationship with User (each breeding belongs to one breeder).
    Uses integer primary key to match existing schema.
    """
    __tablename__ = "breedings"
    
    # Primary key (integer to match existing schema)
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    
    # Foreign key to user (breeder who owns this breeding)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Breeding information
    date_of_litter: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Started"
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
        back_populates="breedings",
        lazy="selectin"
    )
    pets: Mapped[list["Pet"]] = relationship(
        "Pet",
        back_populates="breeding",
        lazy="selectin"
    )
    breeding_pets: Mapped[list["BreedingPet"]] = relationship(
        "BreedingPet",
        back_populates="breeding",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Breeding(id={self.id}, user_id={self.user_id}, date_of_litter={self.date_of_litter})>"
