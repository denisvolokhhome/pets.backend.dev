"""A dated pregnancy milestone for a breeding; template-generated or breeder-added."""
from datetime import date, datetime
from typing import Optional, TYPE_CHECKING
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.breeding import Breeding


class BreedingMilestone(Base):
    __tablename__ = "breeding_milestones"
    __table_args__ = (
        Index(
            "ix_breeding_milestones_pending_reminder", "remind_on",
            postgresql_where=text("reminded_at IS NULL AND completed_at IS NULL"),
        ),
        Index(
            "uq_breeding_milestones_template_key", "breeding_id", "key", unique=True,
            postgresql_where=text("key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    breeding_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("breedings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Template key (e.g. "xray"); NULL for a breeder-added custom milestone
    key: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    remind_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set atomically when the reminder is claimed, so it is sent exactly once
    reminded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    breeding: Mapped["Breeding"] = relationship("Breeding", back_populates="milestones")
