"""BillingAuditLog model for tracking security-relevant billing operations."""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BillingAuditLog(Base):
    """
    Audit log model for recording security-relevant billing operations.

    Stores operation type, outcome, and non-sensitive context for compliance
    and incident investigation. Sensitive payment data must never be logged.
    """
    __tablename__ = "billing_audit_logs"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )

    # User who triggered the operation (nullable for webhook-originated events)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True
    )

    # Operation type (e.g. subscription_created, plan_changed, payment_received)
    operation: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    # Outcome: "success" or "failure"
    outcome: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    # Non-sensitive context details
    details: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # Client IP address (supports IPv6, max 45 chars)
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        try:
            id_val = object.__getattribute__(self, 'id')
            op_val = object.__getattribute__(self, 'operation')
            return f"<BillingAuditLog(id={id_val}, operation={op_val})>"
        except AttributeError:
            return f"<BillingAuditLog(detached)>"
