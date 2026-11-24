"""A family's application for a litter (planned or born), from the litter or a puppy page."""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.breeding import Breeding
    from app.models.offspring import Offspring
    from app.models.user import User


class LitterApplication(Base):
    """
    One submitted application form.

    ``answers`` is a snapshot of the form at submission time, so later edits to the
    breeding's form never change what the family wrote:
    ``[{"field_id": "...", "label": "...", "value": "..."}, ...]``.

    A puppy is assigned by setting ``assigned_offspring_id`` with status ``assigned``;
    the puppy itself moves to ``Reserved`` (the same signal the waitlist uses), so a
    puppy can only be held by one family across both flows.
    """
    __tablename__ = "litter_applications"
    __table_args__ = (
        # Backstop for the conditional reservation: one active assignment per puppy
        Index("uq_litter_applications_assigned_offspring", "assigned_offspring_id", unique=True,
              postgresql_where=text("status = 'assigned'")),
        # One open application per family per litter (and per puppy for the puppy flow)
        Index("uq_litter_applications_open_per_applicant",
              "breeding_id", "applicant_id", "source",
              text("coalesce(requested_offspring_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
              unique=True,
              postgresql_where=text("status <> 'declined' AND applicant_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    breeding_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("breedings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    breeder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    applicant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Snapshot of who applied (kept if the account is later deleted)
    applicant_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    applicant_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # litter = "Apply for this litter"; offspring = the existing puppy-page flow
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    # Puppy page the application came from (context only, not an assignment)
    requested_offspring_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("offsprings.id", ondelete="SET NULL"), nullable=True
    )
    answers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # new, contacted, waitlisted, assigned, declined
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="new")
    assigned_offspring_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("offsprings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    breeding: Mapped["Breeding"] = relationship("Breeding", foreign_keys=[breeding_id])
    applicant: Mapped[Optional["User"]] = relationship("User", foreign_keys=[applicant_id])
    requested_offspring: Mapped[Optional["Offspring"]] = relationship(
        "Offspring", foreign_keys=[requested_offspring_id]
    )
    assigned_offspring: Mapped[Optional["Offspring"]] = relationship(
        "Offspring", foreign_keys=[assigned_offspring_id]
    )

    def __repr__(self) -> str:
        return f"<LitterApplication(id={self.id}, breeding_id={self.breeding_id}, status={self.status})>"
