"""Billing audit logger service for recording security-relevant billing operations.

Writes BillingAuditLog entries for compliance and incident investigation.
Sensitive payment data (card numbers, full Stripe keys) must never be
included in log details.
"""

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing_audit_log import BillingAuditLog

# Supported billing operations
VALID_OPERATIONS = frozenset({
    "subscription_created",
    "plan_changed",
    "payment_received",
    "payment_failed",
    "webhook_processed",
    "checkout_session_created",
    "validation_failed",
})


async def log_billing_event(
    session: AsyncSession,
    user_id: Optional[uuid.UUID],
    operation: str,
    outcome: str,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> BillingAuditLog:
    """Write a BillingAuditLog entry for a billing operation.

    Args:
        session: Async database session.
        user_id: UUID of the user who triggered the operation, or ``None``
            for webhook-originated events.
        operation: One of the supported operation types (e.g.
            ``"subscription_created"``, ``"plan_changed"``).
        outcome: ``"success"`` or ``"failure"``.
        details: Optional non-sensitive context (plan name, error type, etc.).
            Must never contain payment card data or full Stripe secret keys.
        ip_address: Optional client IP address (supports IPv4/IPv6).

    Returns:
        The newly created :class:`BillingAuditLog` instance.

    Raises:
        ValueError: If *operation* is not in the supported set.
    """
    if operation not in VALID_OPERATIONS:
        raise ValueError(
            f"Unsupported billing operation: {operation!r}. "
            f"Must be one of: {', '.join(sorted(VALID_OPERATIONS))}"
        )

    entry = BillingAuditLog(
        user_id=user_id,
        operation=operation,
        outcome=outcome,
        details=details,
        ip_address=ip_address,
    )
    session.add(entry)
    await session.flush()
    return entry
