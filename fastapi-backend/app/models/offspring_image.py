"""OffspringImage model for managing multiple images per offspring."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
import uuid

from sqlalchemy import String, Boolean, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.offspring import Offspring


class OffspringImage(Base):
    """
    OffspringImage model for storing multiple images per offspring.
    
    Supports primary image designation and custom display ordering.
    Only one image per offspring can be marked as primary.
    """
    __tablename__ = "offspring_images"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )
    
    # Foreign key to offspring
    offspring_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offsprings.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Image information
    image_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )
    
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )
    
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        index=True
    )
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    # Relationships
    offspring: Mapped["Offspring"] = relationship(
        "Offspring",
        back_populates="images",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<OffspringImage(id={self.id}, offspring_id={self.offspring_id}, is_primary={self.is_primary})>"
