"""A logged mating for a breeding (planner)."""
from datetime import date, datetime
from typing import Optional, TYPE_CHECKING
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.breeding import Breeding
    from app.models.pet import Pet

MATING_METHODS = ("Natural", "AI_Fresh", "AI_Chilled", "AI_Frozen", "Surgical")


class BreedingMating(Base):
    __tablename__ = "breeding_matings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    breeding_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("breedings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mated_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    # Optional: outside studs are common, so a sire may only be named
    sire_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pets.id", ondelete="SET NULL"), nullable=True
    )
    outside_sire_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    breeding: Mapped["Breeding"] = relationship("Breeding", back_populates="matings")
    sire: Mapped[Optional["Pet"]] = relationship("Pet")
