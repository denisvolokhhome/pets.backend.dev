"""OffspringFavorite model for tracking pet seeker favorites."""
from datetime import datetime
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.offspring import Offspring
    from app.models.user import User


class OffspringFavorite(Base):
    """
    OffspringFavorite model for tracking which pet seekers have favorited which offsprings.
    
    Junction table with unique constraint to prevent duplicate favorites.
    """
    __tablename__ = "offspring_favorites"
    
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
    
    # Foreign key to user (pet seeker)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
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
    offspring: Mapped["Offspring"] = relationship(
        "Offspring",
        back_populates="favorites",
        lazy="selectin"
    )
    
    user: Mapped["User"] = relationship(
        "User",
        lazy="selectin"
    )
    
    # Unique constraint to prevent duplicate favorites
    __table_args__ = (
        UniqueConstraint('offspring_id', 'user_id', name='uq_offspring_user_favorite'),
    )
    
    def __repr__(self) -> str:
        return f"<OffspringFavorite(id={self.id}, offspring_id={self.offspring_id}, user_id={self.user_id})>"
