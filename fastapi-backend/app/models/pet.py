"""Pet model for managing pet records."""
import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Text, Boolean, Float, Date, DateTime, ForeignKey, func, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Pet(Base):
    """
    Pet model representing a registered pet (puppy or adult dog).
    
    Includes health records, breeding information, and image metadata.
    Uses UUID primary key for compatibility with Laravel system.
    """
    __tablename__ = "pets"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )
    
    # Foreign keys
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    breed_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("breeds.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    litter_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("litters.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    location_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Basic information
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    date_of_birth: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )
    gender: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    weight: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    is_puppy: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True
    )
    
    # Health records (changed from boolean to text to match design doc)
    microchip: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    vaccination: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    health_certificate: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    deworming: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    birth_certificate: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Legacy boolean fields from original schema
    has_microchip: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True
    )
    has_vaccination: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True
    )
    has_healthcertificate: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True
    )
    has_dewormed: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True
    )
    has_birthcertificate: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True
    )
    
    # Image metadata
    image_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )
    image_file_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    
    # Soft deletion and error tracking
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )
    error: Mapped[Optional[str]] = mapped_column(
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
        back_populates="pets",
        lazy="selectin"
    )
    breed: Mapped[Optional["Breed"]] = relationship(
        "Breed",
        back_populates="pets",
        lazy="selectin"
    )
    litter: Mapped[Optional["Litter"]] = relationship(
        "Litter",
        back_populates="pets",
        lazy="selectin"
    )
    location: Mapped[Optional["Location"]] = relationship(
        "Location",
        back_populates="pets",
        lazy="selectin"
    )
    litter_assignments: Mapped[list["LitterPet"]] = relationship(
        "LitterPet",
        back_populates="pet",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<Pet(id={self.id}, name={self.name}, user_id={self.user_id})>"
