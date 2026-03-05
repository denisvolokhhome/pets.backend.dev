"""Offspring model for managing individual animals from litters."""
from datetime import datetime, date
from typing import Optional, TYPE_CHECKING
import uuid
from decimal import Decimal

from sqlalchemy import String, Text, Integer, Date, DateTime, Numeric, ForeignKey, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, column_property
from sqlalchemy.ext.hybrid import hybrid_property

from app.database import Base

if TYPE_CHECKING:
    from app.models.breeding import Breeding
    from app.models.user import User
    from app.models.breed import Breed
    from app.models.pet import Pet
    from app.models.offspring_image import OffspringImage
    from app.models.offspring_favorite import OffspringFavorite
    from app.models.message import Message


class Offspring(Base):
    """
    Offspring model representing an individual animal born from a breeding/litter.
    
    Each offspring is linked to a breeding event and tracks detailed information
    including images, availability status, and interactions with pet seekers.
    """
    __tablename__ = "offsprings"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )
    
    # Foreign key to breeding (required, immutable after creation)
    breeding_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("breedings.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Foreign key to user (breeder owner)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Foreign key to breed (auto-populated from breeding)
    breed_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("breeds.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Foreign keys to parent pets (optional, for direct tracking)
    father_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pets.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    mother_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pets.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Offspring information
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    
    gender: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )  # "Male" or "Female"
    
    date_of_birth: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True
    )
    
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Available",
        index=True
    )  # "Available", "Reserved", "Sold", "Archived"
    
    price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    color_markings: Mapped[Optional[str]] = mapped_column(
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
    breeding: Mapped["Breeding"] = relationship(
        "Breeding",
        lazy="selectin"
    )
    
    user: Mapped["User"] = relationship(
        "User",
        lazy="selectin"
    )
    
    breed: Mapped[Optional["Breed"]] = relationship(
        "Breed",
        lazy="selectin"
    )
    
    father: Mapped[Optional["Pet"]] = relationship(
        "Pet",
        foreign_keys=[father_id],
        lazy="selectin"
    )
    
    mother: Mapped[Optional["Pet"]] = relationship(
        "Pet",
        foreign_keys=[mother_id],
        lazy="selectin"
    )
    
    images: Mapped[list["OffspringImage"]] = relationship(
        "OffspringImage",
        back_populates="offspring",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="OffspringImage.display_order"
    )
    
    favorites: Mapped[list["OffspringFavorite"]] = relationship(
        "OffspringFavorite",
        back_populates="offspring",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="offspring",
        lazy="selectin"
    )
    
    @property
    def age(self) -> str:
        """
        Calculate human-readable age from date of birth.
        
        Returns age in weeks (< 12 weeks), months (12-24 months), or years (> 24 months).
        """
        today = date.today()
        delta = today - self.date_of_birth
        
        weeks = delta.days // 7
        months = (today.year - self.date_of_birth.year) * 12 + (today.month - self.date_of_birth.month)
        years = today.year - self.date_of_birth.year
        
        if weeks < 12:
            return f"{weeks} week{'s' if weeks != 1 else ''}"
        elif months < 24:
            return f"{months} month{'s' if months != 1 else ''}"
        else:
            return f"{years} year{'s' if years != 1 else ''}"
    
    @property
    def favorites_count(self) -> int:
        """Count of pet seekers who have favorited this offspring."""
        return len(self.favorites)
    
    @property
    def messages_count(self) -> int:
        """Count of messages associated with this offspring."""
        return len(self.messages)
    
    @property
    def primary_image(self):
        """Get the primary image for this offspring."""
        if self.images:
            for image in self.images:
                if image.is_primary:
                    return image
            # If no primary image is set, return the first image
            return self.images[0] if self.images else None
        return None
    
    def __repr__(self) -> str:
        return f"<Offspring(id={self.id}, name={self.name}, status={self.status})>"
