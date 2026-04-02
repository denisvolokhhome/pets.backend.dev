"""Invoice model for billing record management."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
import uuid

from sqlalchemy import String, DateTime, Numeric, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.encrypted_type import EncryptedString

if TYPE_CHECKING:
    from app.models.subscription import Subscription


class Invoice(Base):
    """
    Invoice model representing a billing record for a subscription.

    Tracks the amount due, billing period, payment status, and Stripe
    invoice identifier for payment processing.
    """
    __tablename__ = "invoices"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )

    # Foreign key to subscription
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Invoice amount
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False
    )

    # Currency code (ISO 4217)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="usd"
    )

    # Invoice status: pending, paid, failed, void
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending"
    )

    # Billing period
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # Stripe identifier (encrypted at rest via AES-256-GCM)
    stripe_invoice_id: Mapped[Optional[str]] = mapped_column(
        EncryptedString,
        nullable=True
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    subscription: Mapped["Subscription"] = relationship(
        "Subscription",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        try:
            id_val = object.__getattribute__(self, 'id')
            status_val = object.__getattribute__(self, 'status')
            return f"<Invoice(id={id_val}, status={status_val})>"
        except AttributeError:
            return f"<Invoice(detached)>"
