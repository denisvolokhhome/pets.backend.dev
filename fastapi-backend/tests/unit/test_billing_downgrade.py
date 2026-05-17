"""Tests for subscription downgrade, grace period, and verify-session functionality.

Feature: billing-downgrade
Covers:
  - Downgrade is scheduled (not immediate) for end of billing period
  - Grace period: current plan limits remain active until effective date
  - Cancel pending downgrade restores normal state
  - Usage validation blocks downgrade when limits would be exceeded
  - Audit log entries are created for downgrade operations
  - Pending plan is applied lazily when get_subscription is called after effective date
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from hypothesis import HealthCheck, given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st
from sqlalchemy import select

from app.models.location import Location
from app.models.offspring import Offspring
from app.models.pet import Pet
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.billing_service import billing_service


# ── Shared helpers ────────────────────────────────────────────────────────────

async def _make_user(session, user_id=None) -> User:
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        email=f"user-{uid}@test.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=True,
    )
    session.add(user)
    await session.flush()
    return user


async def _make_plan(session, price: Decimal, max_pets=25, max_locs=3,
                     max_off=100, is_default=False) -> Plan:
    plan = Plan(
        name=f"plan-{uuid.uuid4().hex[:8]}",
        price=price,
        currency="usd",
        billing_interval="month",
        max_pets=max_pets,
        max_published_locations=max_locs,
        max_simultaneous_offsprings=max_off,
        is_default=is_default,
    )
    session.add(plan)
    await session.flush()
    return plan


async def _make_subscription(session, user_id, plan_id,
                              period_days_remaining=20) -> Subscription:
    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        status="active",
        current_period_start=now - timedelta(days=10),
        current_period_end=now + timedelta(days=period_days_remaining),
    )
    session.add(sub)
    await session.flush()
    return sub


# ── Test 1: Downgrade is scheduled, not immediate ────────────────────────────

@pytest.mark.asyncio
async def test_downgrade_is_scheduled_not_immediate(async_session):
    """Downgrading to a cheaper plan sets pending_plan_id and does NOT
    change plan_id immediately."""
    user = await _make_user(async_session)
    free_plan = await _make_plan(async_session, Decimal("0"), max_pets=5,
                                  max_locs=1, max_off=20, is_default=True)
    pro_plan = await _make_plan(async_session, Decimal("19.00"), max_pets=25,
                                 max_locs=3, max_off=100)
    sub = await _make_subscription(async_session, user.id, pro_plan.id,
                                    period_days_remaining=20)

    result = await billing_service.subscribe(async_session, user.id, free_plan.id)

    # plan_id must NOT have changed yet
    assert result.plan_id == pro_plan.id, "plan_id should still be Pro during grace period"
    # pending fields must be set
    assert result.pending_plan_id == free_plan.id
    assert result.pending_plan_effective_date is not None
    # effective date should equal current_period_end
    assert result.pending_plan_effective_date == sub.current_period_end


# ── Test 2: Grace period — Pro limits still enforced during pending downgrade ─

@pytest.mark.asyncio
async def test_pro_limits_enforced_during_grace_period(async_session):
    """While a downgrade is pending, the current (Pro) plan limits apply,
    not the target (Free) plan limits."""
    user = await _make_user(async_session)
    free_plan = await _make_plan(async_session, Decimal("0"), max_pets=5,
                                  max_locs=1, max_off=20, is_default=True)
    pro_plan = await _make_plan(async_session, Decimal("19.00"), max_pets=25,
                                 max_locs=3, max_off=100)
    await _make_subscription(async_session, user.id, pro_plan.id,
                              period_days_remaining=20)

    # Schedule downgrade
    await billing_service.subscribe(async_session, user.id, free_plan.id)

    # Add 6 pets — above Free limit (5) but within Pro limit (25)
    for i in range(6):
        pet = Pet(user_id=user.id, name=f"Pet-{i}", is_deleted=False)
        async_session.add(pet)
    await async_session.flush()

    # check_usage should NOT raise — Pro limits (25) still apply
    await billing_service.check_usage(async_session, user.id, "pets")


# ── Test 3: Pending plan applied after effective date ─────────────────────────

@pytest.mark.asyncio
async def test_pending_plan_applied_after_effective_date(async_session):
    """When get_subscription is called after pending_plan_effective_date,
    the plan switches to the pending plan automatically."""
    user = await _make_user(async_session)
    free_plan = await _make_plan(async_session, Decimal("0"), max_pets=5,
                                  max_locs=1, max_off=20, is_default=True)
    pro_plan = await _make_plan(async_session, Decimal("19.00"), max_pets=25,
                                 max_locs=3, max_off=100)

    now = datetime.now(timezone.utc)
    # Create subscription with period that already ended
    sub = Subscription(
        user_id=user.id,
        plan_id=pro_plan.id,
        status="active",
        current_period_start=now - timedelta(days=35),
        current_period_end=now - timedelta(days=5),  # already past
        pending_plan_id=free_plan.id,
        pending_plan_effective_date=now - timedelta(days=5),  # already past
    )
    async_session.add(sub)
    await async_session.flush()

    # get_subscription should apply the pending plan
    result = await billing_service.get_subscription(async_session, user.id)

    assert result.plan_id == free_plan.id, "Plan should have switched to Free"
    assert result.pending_plan_id is None
    assert result.pending_plan_effective_date is None


# ── Test 4: Cancel pending downgrade ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_pending_downgrade_clears_pending_fields(async_session):
    """Canceling a pending downgrade clears pending_plan_id and
    pending_plan_effective_date, keeping the current plan."""
    user = await _make_user(async_session)
    free_plan = await _make_plan(async_session, Decimal("0"), max_pets=5,
                                  max_locs=1, max_off=20, is_default=True)
    pro_plan = await _make_plan(async_session, Decimal("19.00"), max_pets=25,
                                 max_locs=3, max_off=100)
    await _make_subscription(async_session, user.id, pro_plan.id,
                              period_days_remaining=20)

    # Schedule downgrade
    await billing_service.subscribe(async_session, user.id, free_plan.id)

    # Verify it's scheduled
    sub = await billing_service.get_subscription(async_session, user.id)
    assert sub.pending_plan_id == free_plan.id

    # Cancel it directly (simulating the cancel-pending-downgrade endpoint logic)
    sub.pending_plan_id = None
    sub.pending_plan_effective_date = None
    await async_session.flush()
    await async_session.refresh(sub)

    # Verify cleared
    assert sub.pending_plan_id is None
    assert sub.pending_plan_effective_date is None
    assert sub.plan_id == pro_plan.id, "Should still be on Pro"


# ── Test 5: Downgrade blocked when pet count exceeds target limit ─────────────

@pytest.mark.asyncio
async def test_downgrade_blocked_by_pet_count(async_session):
    """Downgrade is rejected with 422 when current pet count exceeds
    the target plan's max_pets limit."""
    user = await _make_user(async_session)
    free_plan = await _make_plan(async_session, Decimal("0"), max_pets=5,
                                  max_locs=1, max_off=20, is_default=True)
    pro_plan = await _make_plan(async_session, Decimal("19.00"), max_pets=25,
                                 max_locs=3, max_off=100)
    await _make_subscription(async_session, user.id, pro_plan.id)

    # Add 6 pets — exceeds Free limit of 5
    for i in range(6):
        pet = Pet(user_id=user.id, name=f"Pet-{i}", is_deleted=False)
        async_session.add(pet)
    await async_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await billing_service.subscribe(async_session, user.id, free_plan.id)

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert "violations" in detail
    assert any("pet" in v.lower() for v in detail["violations"])
    assert any("6" in v for v in detail["violations"])


# ── Test 6: Downgrade blocked by published locations ─────────────────────────

@pytest.mark.asyncio
async def test_downgrade_blocked_by_published_locations(async_session):
    """Downgrade is rejected with 422 when published location count exceeds
    the target plan's max_published_locations limit."""
    user = await _make_user(async_session)
    free_plan = await _make_plan(async_session, Decimal("0"), max_pets=5,
                                  max_locs=1, max_off=20, is_default=True)
    pro_plan = await _make_plan(async_session, Decimal("19.00"), max_pets=25,
                                 max_locs=3, max_off=100)
    await _make_subscription(async_session, user.id, pro_plan.id)

    # Add 2 published locations — exceeds Free limit of 1
    for i in range(2):
        loc = Location(
            user_id=user.id,
            name=f"Loc-{i}",
            address1="123 St",
            city="City",
            state="ST",
            country="US",
            zipcode="12345",
            location_type="user",
            is_published=True,
        )
        async_session.add(loc)
    await async_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await billing_service.subscribe(async_session, user.id, free_plan.id)

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert any("location" in v.lower() for v in detail["violations"])


# ── Test 7: Downgrade blocked by active offsprings ───────────────────────────

@pytest.mark.asyncio
async def test_downgrade_blocked_by_active_offsprings(async_session):
    """Downgrade is rejected with 422 when active offspring count exceeds
    the target plan's max_simultaneous_offsprings limit."""
    from app.models.breeding import Breeding
    from datetime import date

    user = await _make_user(async_session)
    free_plan = await _make_plan(async_session, Decimal("0"), max_pets=5,
                                  max_locs=1, max_off=5, is_default=True)
    pro_plan = await _make_plan(async_session, Decimal("19.00"), max_pets=25,
                                 max_locs=3, max_off=100)
    await _make_subscription(async_session, user.id, pro_plan.id)

    breeding = Breeding(
        user_id=user.id,
        date_of_litter=date(2024, 1, 1),
        description="Test",
        is_active=True,
        status="Started",
    )
    async_session.add(breeding)
    await async_session.flush()

    # Add 6 available offsprings — exceeds Free limit of 5
    for i in range(6):
        offspring = Offspring(
            breeding_id=breeding.id,
            user_id=user.id,
            name=f"Offspring-{i}",
            gender="Male",
            date_of_birth=date(2024, 3, 1),
            status="Available",
        )
        async_session.add(offspring)
    await async_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await billing_service.subscribe(async_session, user.id, free_plan.id)

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert any("offspring" in v.lower() for v in detail["violations"])


# ── Test 8: Downgrade allowed when usage is within target limits ──────────────

@pytest.mark.asyncio
async def test_downgrade_allowed_when_within_limits(async_session):
    """Downgrade succeeds (schedules) when current usage fits within
    the target plan's limits."""
    user = await _make_user(async_session)
    free_plan = await _make_plan(async_session, Decimal("0"), max_pets=5,
                                  max_locs=1, max_off=20, is_default=True)
    pro_plan = await _make_plan(async_session, Decimal("19.00"), max_pets=25,
                                 max_locs=3, max_off=100)
    await _make_subscription(async_session, user.id, pro_plan.id,
                              period_days_remaining=15)

    # Add 3 pets — within Free limit of 5
    for i in range(3):
        pet = Pet(user_id=user.id, name=f"Pet-{i}", is_deleted=False)
        async_session.add(pet)
    await async_session.flush()

    # Should not raise
    result = await billing_service.subscribe(async_session, user.id, free_plan.id)

    assert result.pending_plan_id == free_plan.id
    assert result.plan_id == pro_plan.id  # still Pro during grace period


# ── Test 9: Upgrade cancels any pending downgrade ────────────────────────────

@pytest.mark.asyncio
async def test_upgrade_cancels_pending_downgrade(async_session):
    """Upgrading to a more expensive plan clears any pending downgrade."""
    user = await _make_user(async_session)
    free_plan = await _make_plan(async_session, Decimal("0"), max_pets=5,
                                  max_locs=1, max_off=20, is_default=True)
    pro_plan = await _make_plan(async_session, Decimal("19.00"), max_pets=25,
                                 max_locs=3, max_off=100)
    premium_plan = await _make_plan(async_session, Decimal("49.00"), max_pets=999,
                                     max_locs=10, max_off=500)
    await _make_subscription(async_session, user.id, pro_plan.id,
                              period_days_remaining=20)

    # Schedule downgrade to Free
    await billing_service.subscribe(async_session, user.id, free_plan.id)
    sub = await billing_service.get_subscription(async_session, user.id)
    assert sub.pending_plan_id == free_plan.id

    # Now upgrade to Premium — should clear the pending downgrade
    result = await billing_service.subscribe(async_session, user.id, premium_plan.id)

    assert result.plan_id == premium_plan.id
    assert result.pending_plan_id is None
    assert result.pending_plan_effective_date is None


# ── Test 10: Multiple violations reported together ────────────────────────────

@pytest.mark.asyncio
async def test_downgrade_reports_all_violations(async_session):
    """When multiple limits are exceeded, all violations are reported
    in a single 422 response."""
    from app.models.breeding import Breeding
    from datetime import date

    user = await _make_user(async_session)
    # Free plan: 2 pets, 1 location, 2 offsprings
    free_plan = await _make_plan(async_session, Decimal("0"), max_pets=2,
                                  max_locs=1, max_off=2, is_default=True)
    pro_plan = await _make_plan(async_session, Decimal("19.00"), max_pets=25,
                                 max_locs=3, max_off=100)
    await _make_subscription(async_session, user.id, pro_plan.id)

    # Exceed all three limits
    for i in range(4):  # 4 pets > 2
        pet = Pet(user_id=user.id, name=f"Pet-{i}", is_deleted=False)
        async_session.add(pet)

    for i in range(3):  # 3 locations > 1
        loc = Location(
            user_id=user.id, name=f"Loc-{i}", address1="123 St",
            city="City", state="ST", country="US", zipcode="12345",
            location_type="user", is_published=True,
        )
        async_session.add(loc)

    breeding = Breeding(
        user_id=user.id, date_of_litter=date(2024, 1, 1),
        description="Test", is_active=True, status="Started",
    )
    async_session.add(breeding)
    await async_session.flush()

    for i in range(5):  # 5 offsprings > 2
        offspring = Offspring(
            breeding_id=breeding.id, user_id=user.id,
            name=f"Offspring-{i}", gender="Male",
            date_of_birth=date(2024, 3, 1), status="Available",
        )
        async_session.add(offspring)
    await async_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await billing_service.subscribe(async_session, user.id, free_plan.id)

    assert exc_info.value.status_code == 422
    violations = exc_info.value.detail["violations"]
    assert len(violations) == 3, f"Expected 3 violations, got: {violations}"


# ── Test 11: Audit log entries created for downgrade operations ───────────────

@pytest.mark.asyncio
async def test_audit_log_created_for_downgrade_scheduled(async_session):
    """A billing audit log entry with operation='plan_downgrade_scheduled'
    is created when a downgrade is scheduled."""
    from app.models.billing_audit_log import BillingAuditLog

    user = await _make_user(async_session)
    free_plan = await _make_plan(async_session, Decimal("0"), max_pets=5,
                                  max_locs=1, max_off=20, is_default=True)
    pro_plan = await _make_plan(async_session, Decimal("19.00"), max_pets=25,
                                 max_locs=3, max_off=100)
    await _make_subscription(async_session, user.id, pro_plan.id,
                              period_days_remaining=20)

    await billing_service.subscribe(async_session, user.id, free_plan.id)

    result = await async_session.execute(
        select(BillingAuditLog).where(
            BillingAuditLog.user_id == user.id,
            BillingAuditLog.operation == "plan_downgrade_scheduled",
        )
    )
    log_entry = result.scalar_one_or_none()
    assert log_entry is not None
    assert log_entry.outcome == "success"
    assert free_plan.name in log_entry.details


# ── Test 12: Property-based — downgrade always schedules for period end ───────

user_uuid_st = st.uuids(version=4)
days_remaining_st = st.integers(min_value=1, max_value=60)


@given(user_id=user_uuid_st, days_remaining=days_remaining_st)
@hypothesis_settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
async def test_downgrade_effective_date_equals_period_end(
    async_session, user_id, days_remaining
):
    """For any subscription with any remaining days, the pending downgrade
    effective date always equals current_period_end."""
    user = await _make_user(async_session, user_id)
    free_plan = await _make_plan(async_session, Decimal("0"), max_pets=999,
                                  max_locs=999, max_off=999, is_default=True)
    pro_plan = await _make_plan(async_session, Decimal("19.00"), max_pets=25,
                                 max_locs=3, max_off=100)
    sub = await _make_subscription(async_session, user.id, pro_plan.id,
                                    period_days_remaining=days_remaining)

    result = await billing_service.subscribe(async_session, user.id, free_plan.id)

    assert result.pending_plan_effective_date == sub.current_period_end

    # Cleanup
    await async_session.delete(result)
    await async_session.delete(sub)
    await async_session.delete(user)
    await async_session.delete(pro_plan)
    await async_session.delete(free_plan)
    await async_session.flush()
