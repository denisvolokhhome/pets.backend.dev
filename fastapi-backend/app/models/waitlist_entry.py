"""A seeker's place on a breeder's waitlist (general list or a specific breeding)."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.breeding import Breeding
    from app.models.offspring import Offspring
    from app.models.user import User
    from app.models.waitlist_event import WaitlistEvent


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (
        Index("uq_waitlist_active_user", "breeder_id", "user_id", unique=True,
              postgresql_where=text("user_id IS NOT NULL AND status IN ('pending','active')")),
        Index("uq_waitlist_active_email", "breeder_id", "contact_email", unique=True,
              postgresql_where=text("contact_email IS NOT NULL AND user_id IS NULL "
                                    "AND status IN ('pending','active')")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    breeder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL for an unlinked manual entry
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # request / manual
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Stored lower-cased by the service; used for linking manual entries on register/login
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Current list; NULL = general list
    breeding_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("breedings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # pending, active, declined, matched, withdrawn
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    sex_preference: Mapped[str] = mapped_column(String(6), nullable=False)  # Male / Female / Any
    preference_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    application_answers: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    # Breeding whose offspring page the request came from (context only)
    request_breeding_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("breedings.id", ondelete="SET NULL"), nullable=True
    )
    # Ordering key: deposit received date, else approval date
    queue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    position_override: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    override_set_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    override_note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # none, requested, received, refunded, forfeited, applied
    deposit_status: Mapped[str] = mapped_column(String(10), nullable=False)
    deposit_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    deposit_received_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    deposit_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Reserved for Stripe Connect; unused in v1
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    offspring_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("offsprings.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    breeder: Mapped["User"] = relationship("User", foreign_keys=[breeder_id])
    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id])
    breeding: Mapped[Optional["Breeding"]] = relationship("Breeding", foreign_keys=[breeding_id])
    request_breeding: Mapped[Optional["Breeding"]] = relationship(
        "Breeding", foreign_keys=[request_breeding_id]
    )
    offspring: Mapped[Optional["Offspring"]] = relationship("Offspring", foreign_keys=[offspring_id])
    events: Mapped[list["WaitlistEvent"]] = relationship(
        "WaitlistEvent", back_populates="entry", order_by="WaitlistEvent.created_at",
        cascade="all, delete-orphan", lazy="selectin",
    )
