"""BreedingApplicationForm model — custom application form attached to a breeding."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
import uuid

from sqlalchemy import Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.breeding import Breeding
    from app.models.user import User


class BreedingApplicationForm(Base):
    """
    Optional application form attached to a breeding.

    The form_fields column stores a JSON array of field definitions:
    [
      {"id": "uuid", "type": "text"|"textarea", "label": "...", "required": true|false},
      ...
    ]
    """
    __tablename__ = "breeding_application_forms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    breeding_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("breedings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one form per breeding
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # JSON array of field definitions
    form_fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    breeding: Mapped["Breeding"] = relationship("Breeding", back_populates="application_form")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<BreedingApplicationForm(id={self.id}, breeding_id={self.breeding_id})>"
