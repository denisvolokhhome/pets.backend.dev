"""Pet Image model for managing multiple pet images."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PetImage(Base):
    """
    Pet Image model for storing multiple images per pet.
    
    Supports multiple images with ordering and primary image designation.
    """
    __tablename__ = "pet_images"
    
    # Primary key
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    
    # Foreign key
    pet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Image metadata
    image_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )
    image_file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    
    # Display settings
    display_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
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
    pet: Mapped["Pet"] = relationship(
        "Pet",
        back_populates="images",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<PetImage(id={self.id}, pet_id={self.pet_id}, is_primary={self.is_primary})>"
