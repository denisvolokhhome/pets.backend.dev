"""Subscription model for breeder subscription management."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
import uuid

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.encrypted_type import EncryptedString

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.plan import Plan


class Subscription(Base):
    """
    Subscription model representing the association between a Breeder and a Plan.

    Tracks the subscription status, billing cycle dates, and Stripe identifiers
    for payment processing.
    """
    __tablename__ = "subscriptions"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )

    # Foreign key to user (breeder)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Foreign key to plan
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id"),
        nullable=False
    )

    # Subscription status: active, canceled, past_due
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active"
    )

    # Billing period
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # Stripe identifiers (encrypted at rest via AES-256-GCM)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        EncryptedString,
        nullable=True
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        EncryptedString,
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
    user: Mapped["User"] = relationship(
        "User",
        lazy="selectin"
    )
    plan: Mapped["Plan"] = relationship(
        "Plan",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        try:
            id_val = object.__getattribute__(self, 'id')
            status_val = object.__getattribute__(self, 'status')
            return f"<Subscription(id={id_val}, status={status_val})>"
        except AttributeError:
            return f"<Subscription(detached)>"
