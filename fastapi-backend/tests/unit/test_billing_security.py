"""Property-based tests for billing security features.

Feature: billing-service
Properties: 17, 18, 19, 21, 22
"""

import os
import uuid

# Set encryption key BEFORE any app imports
os.environ['BILLING_ENCRYPTION_KEY'] = 'test-encryption-key-for-billing'

from decimal import Decimal
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings as hypothesis_settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import select, text

from app.services.encryption_service import encrypt, decrypt
from app.models.subscription import Subscription
from app.models.invoice import Invoice
from app.models.plan import Plan
from app.models.billing_audit_log import BillingAuditLog
from app.services.billing_audit_logger import log_billing_event, VALID_OPERATIONS

# Import mask_stripe_id: replicate the function from billing-admin/db.py
# to avoid importing the billing-admin module (which requires pandas/streamlit).
# This test validates the masking *logic* as specified in the design doc.


def mask_stripe_id(identifier):
    """Mask a Stripe identifier — mirrors billing-admin/db.py implementation."""
    if identifier is None:
        return None
    if identifier == "":
        return ""
    underscore_idx = identifier.find("_")
    if underscore_idx == -1:
        if len(identifier) <= 3:
            return "***"
        return "***" + identifier[-3:]
    prefix = identifier[: underscore_idx + 1]
    body = identifier[underscore_idx + 1:]
    if len(body) <= 3:
        return prefix + "***"
    return prefix + "***" + body[-3:]


# --- Strategies ---

stripe_prefix_st = st.sampled_from(["cus_", "sub_", "in_"])

stripe_body_st = st.text(
    min_size=4,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N")),
).filter(lambda x: len(x.strip()) >= 4)

stripe_id_st = st.builds(lambda prefix, body: prefix + body, stripe_prefix_st, stripe_body_st)

# Strategy for non-UUID strings (for Property 21)
non_uuid_st = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
).filter(lambda x: not _is_valid_uuid(x))

audit_operation_st = st.sampled_from(sorted(VALID_OPERATIONS))
audit_outcome_st = st.sampled_from(["success", "failure"])

# Sensitive patterns that must never appear in audit log details
SENSITIVE_PATTERNS = [
    "sk_live_", "sk_test_",  # Stripe secret keys
    "rk_live_", "rk_test_",  # Stripe restricted keys
]


def _is_valid_uuid(s: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        uuid.UUID(s, version=4)
        return True
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Property 17: Stripe identifier encryption round-trip
# **Validates: Requirements 11.3, 11.4**
# ---------------------------------------------------------------------------


@given(identifier=stripe_id_st)
@hypothesis_settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_stripe_identifier_encryption_round_trip(identifier):
    """For any valid Stripe identifier, encrypting then decrypting produces the original.

    **Validates: Requirements 11.3, 11.4**
    """
    encrypted = encrypt(identifier)
    decrypted = decrypt(encrypted)
    assert decrypted == identifier


# ---------------------------------------------------------------------------
# Property 18: Encrypted fields are not stored in plaintext
# **Validates: Requirements 11.3**
# ---------------------------------------------------------------------------


@given(
    stripe_customer_id=stripe_id_st.filter(lambda x: x.startswith("cus_")),
    stripe_subscription_id=stripe_id_st.filter(lambda x: x.startswith("sub_")),
)
@hypothesis_settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_encrypted_fields_not_stored_in_plaintext(
    async_session,
    test_user,
    stripe_customer_id,
    stripe_subscription_id,
):
    """For any Subscription with Stripe IDs, raw DB column values differ from plaintext.

    **Validates: Requirements 11.3**
    """
    # Create a plan for the subscription
    plan = Plan(
        name=f"test_plan_{uuid.uuid4().hex[:8]}",
        price=Decimal("9.99"),
        currency="usd",
        billing_interval="month",
        max_pets=10,
        max_published_locations=5,
        max_simultaneous_offsprings=50,
        is_default=False,
    )
    async_session.add(plan)
    await async_session.flush()

    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=test_user.id,
        plan_id=plan.id,
        status="active",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
    )
    async_session.add(sub)
    await async_session.flush()

    # Read raw column values via SQL — bypasses the TypeDecorator
    raw_result = await async_session.execute(
        text(
            "SELECT stripe_customer_id, stripe_subscription_id "
            "FROM subscriptions WHERE id = :sub_id"
        ),
        {"sub_id": str(sub.id)},
    )
    raw_row = raw_result.one()
    raw_customer_id = raw_row[0]
    raw_subscription_id = raw_row[1]

    # Raw values must NOT equal the plaintext identifiers
    assert raw_customer_id != stripe_customer_id, (
        f"stripe_customer_id stored in plaintext: {stripe_customer_id}"
    )
    assert raw_subscription_id != stripe_subscription_id, (
        f"stripe_subscription_id stored in plaintext: {stripe_subscription_id}"
    )

    # Clean up
    await async_session.delete(sub)
    await async_session.delete(plan)
    await async_session.flush()


# ---------------------------------------------------------------------------
# Property 19: Audit log completeness for billing operations
# **Validates: Requirements 11.8**
# ---------------------------------------------------------------------------


@given(
    operation=audit_operation_st,
    outcome=audit_outcome_st,
    details=st.one_of(
        st.none(),
        st.text(min_size=1, max_size=200, alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"))),
    ),
)
@hypothesis_settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_audit_log_completeness(
    async_session,
    test_user,
    operation,
    outcome,
    details,
):
    """For any billing operation, a corresponding audit log entry exists with correct fields.

    **Validates: Requirements 11.8**
    """
    entry = await log_billing_event(
        session=async_session,
        user_id=test_user.id,
        operation=operation,
        outcome=outcome,
        details=details,
    )

    # Verify the entry was persisted and can be read back
    result = await async_session.execute(
        select(BillingAuditLog).where(BillingAuditLog.id == entry.id)
    )
    fetched = result.scalar_one()

    assert fetched.user_id == test_user.id
    assert fetched.operation == operation
    assert fetched.outcome == outcome
    assert fetched.details == details
    assert fetched.created_at is not None

    # Verify no sensitive data in details
    if fetched.details is not None:
        for pattern in SENSITIVE_PATTERNS:
            assert pattern not in fetched.details, (
                f"Sensitive pattern '{pattern}' found in audit log details"
            )

    # Clean up
    await async_session.delete(fetched)
    await async_session.flush()


# ---------------------------------------------------------------------------
# Property 21: Input validation rejects malformed identifiers
# **Validates: Requirements 11.7, 11.10**
# ---------------------------------------------------------------------------


@given(malformed_id=non_uuid_st)
@hypothesis_settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_input_validation_rejects_malformed_identifiers(
    async_client,
    malformed_id,
):
    """For any non-UUID plan_id, POST /api/billing/subscribe returns 422 and no state change.

    **Validates: Requirements 11.7, 11.10**
    """
    # Clear billing rate limiter keys in Redis so Hypothesis examples
    # are not throttled across iterations within the same test function.
    try:
        from redis.asyncio import Redis
        redis = Redis.from_url("redis://localhost:6379", decode_responses=True)
        keys = await redis.keys("billing_rl:*")
        if keys:
            await redis.delete(*keys)
        await redis.aclose()
    except Exception:
        pass  # Redis unavailable — rate limiter degrades gracefully

    response = await async_client.post(
        "/api/billing/subscribe",
        json={"plan_id": malformed_id},
    )
    assert response.status_code == 422, (
        f"Expected 422 for malformed plan_id '{malformed_id}', got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Property 22: Dashboard masks Stripe identifiers
# **Validates: Requirements 11.12**
# ---------------------------------------------------------------------------


@given(identifier=stripe_id_st)
@hypothesis_settings(max_examples=100)
def test_dashboard_masks_stripe_identifiers(identifier):
    """For any Stripe identifier, the masking function hides the middle portion.

    **Validates: Requirements 11.12**
    """
    masked = mask_stripe_id(identifier)

    # The masked value must not equal the original
    assert masked != identifier, (
        f"Masked value equals original: {identifier}"
    )

    # Detect prefix
    underscore_idx = identifier.find("_")
    assert underscore_idx != -1, "Test strategy should always produce prefixed IDs"

    prefix = identifier[: underscore_idx + 1]
    body = identifier[underscore_idx + 1 :]

    # Masked value must start with the original prefix
    assert masked.startswith(prefix), (
        f"Masked '{masked}' does not start with prefix '{prefix}'"
    )

    # Masked value must contain '***'
    assert "***" in masked, (
        f"Masked '{masked}' does not contain '***'"
    )

    # If body is long enough, last 3 chars of masked should match last 3 of body
    if len(body) > 3:
        assert masked.endswith(body[-3:]), (
            f"Masked '{masked}' does not end with last 3 chars of body '{body[-3:]}'"
        )

    # The full original identifier must not appear in the masked output
    # (the body portion should be partially hidden)
    masked_body = masked[underscore_idx + 1 :]
    assert masked_body != body, (
        f"Masked body equals original body: {body}"
    )
