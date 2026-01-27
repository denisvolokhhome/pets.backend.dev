"""LitterPet junction model for parent pet assignments."""
from datetime import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Integer, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.litter import Litter
    from app.models.pet import Pet


class LitterPet(Base):
    """
    Junction table for many-to-many relationship between litters and parent pets.
    
    Allows tracking which pets are assigned as parents to which litters.
    A pet can be assigned to multiple litters (multi-litter assignment).
    """
    __tablename__ = "litter_pets"
    
    # Primary key
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    
    # Foreign keys
    litter_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("litters.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    pet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    # Relationships
    litter: Mapped["Litter"] = relationship(
        "Litter",
        back_populates="litter_pets",
        lazy="selectin"
    )
    pet: Mapped["Pet"] = relationship(
        "Pet",
        back_populates="litter_assignments",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<LitterPet(litter_id={self.litter_id}, pet_id={self.pet_id})>"
