"""Property-based tests for billing service.

Feature: billing-service
"""

import uuid
from decimal import Decimal

import pytest
from hypothesis import given, settings as hypothesis_settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import select

from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.billing_service import billing_service


# --- Strategies ---

user_uuid_st = st.uuids(version=4)

plan_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_ "),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())

plan_price_st = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("9999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

usage_limit_st = st.integers(min_value=1, max_value=1000)


# --- Property 3: Default subscription assignment on breeder creation ---
# Feature: billing-service, Property 3: Default subscription assignment
# **Validates: Requirements 2.1**


@given(user_id=user_uuid_st)
@hypothesis_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_default_subscription_assignment(async_session, user_id):
    """For any new breeder, calling create_default_subscription should yield a
    subscription with FREE plan, status 'active', and correct usage limits.

    **Validates: Requirements 2.1**
    """
    # Seed the FREE plan if it doesn't already exist
    existing = await async_session.execute(
        select(Plan).where(Plan.is_default == True)  # noqa: E712
    )
    free_plan = existing.scalar_one_or_none()

    if free_plan is None:
        free_plan = Plan(
            name="Free",
            price=0,
            currency="usd",
            billing_interval="month",
            max_pets=5,
            max_published_locations=1,
            max_simultaneous_offsprings=20,
            is_default=True,
        )
        async_session.add(free_plan)
        await async_session.flush()

    # Create a real user in the DB to satisfy the FK constraint
    breeder = User(
        id=user_id,
        email=f"breeder-{user_id}@test.com",
        hashed_password="hashed_placeholder",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=True,
    )
    async_session.add(breeder)
    await async_session.flush()

    # Call the service under test
    subscription = await billing_service.create_default_subscription(
        async_session, user_id
    )

    # Assert subscription properties
    assert subscription.status == "active"
    assert subscription.plan_id == free_plan.id
    assert subscription.user_id == user_id
    assert subscription.current_period_start is not None
    assert subscription.current_period_end is not None
    assert subscription.current_period_end > subscription.current_period_start

    # Reload the plan to verify usage limits
    plan_result = await async_session.execute(
        select(Plan).where(Plan.id == subscription.plan_id)
    )
    plan = plan_result.scalar_one()

    assert plan.max_pets == 5
    assert plan.max_published_locations == 1
    assert plan.max_simultaneous_offsprings == 20
    assert plan.price == 0

    # Clean up for next hypothesis example
    await async_session.delete(subscription)
    await async_session.delete(breeder)
    await async_session.flush()


# --- Property 4: Subscription plan change ---
# Feature: billing-service, Property 4: Subscription plan change
# **Validates: Requirements 2.4**


@given(
    user_id=user_uuid_st,
    new_plan_name=plan_name_st,
    new_plan_price=plan_price_st,
    new_max_pets=usage_limit_st,
    new_max_locations=usage_limit_st,
    new_max_offsprings=usage_limit_st,
)
@hypothesis_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_subscription_plan_change(
    async_session,
    user_id,
    new_plan_name,
    new_plan_price,
    new_max_pets,
    new_max_locations,
    new_max_offsprings,
):
    """For any breeder with a subscription and any valid plan, subscribing to
    that plan updates the subscription's plan_id and billing period.

    **Validates: Requirements 2.4**
    """
    # Seed the FREE plan if it doesn't already exist
    existing = await async_session.execute(
        select(Plan).where(Plan.is_default == True)  # noqa: E712
    )
    free_plan = existing.scalar_one_or_none()

    if free_plan is None:
        free_plan = Plan(
            name="Free",
            price=0,
            currency="usd",
            billing_interval="month",
            max_pets=5,
            max_published_locations=1,
            max_simultaneous_offsprings=20,
            is_default=True,
        )
        async_session.add(free_plan)
        await async_session.flush()

    # Create a user
    breeder = User(
        id=user_id,
        email=f"breeder-{user_id}@test.com",
        hashed_password="hashed_placeholder",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=True,
    )
    async_session.add(breeder)
    await async_session.flush()

    # Create a default subscription on the FREE plan
    subscription = await billing_service.create_default_subscription(
        async_session, user_id
    )
    original_period_start = subscription.current_period_start
    original_period_end = subscription.current_period_end

    # Ensure the new plan name doesn't collide with "Free"
    unique_plan_name = f"test-{new_plan_name}-{uuid.uuid4().hex[:8]}"

    # Create a second plan with random properties
    new_plan = Plan(
        name=unique_plan_name,
        price=new_plan_price,
        currency="usd",
        billing_interval="month",
        max_pets=new_max_pets,
        max_published_locations=new_max_locations,
        max_simultaneous_offsprings=new_max_offsprings,
        is_default=False,
    )
    async_session.add(new_plan)
    await async_session.flush()

    # Subscribe to the new plan
    updated_sub = await billing_service.subscribe(
        async_session, user_id, new_plan.id
    )

    # Assert: plan_id updated to the new plan
    assert updated_sub.plan_id == new_plan.id

    # Assert: billing period was updated (reset to now + 30 days)
    assert updated_sub.current_period_start >= original_period_start
    assert updated_sub.current_period_end > updated_sub.current_period_start
    # The period changed from the original
    assert (
        updated_sub.current_period_start != original_period_start
        or updated_sub.current_period_end != original_period_end
    )

    # Clean up test data
    await async_session.delete(updated_sub)
    await async_session.delete(breeder)
    await async_session.delete(new_plan)
    await async_session.flush()


# --- Property 6: Usage limit enforcement ---
# Feature: billing-service, Property 6: Usage limit enforcement
# **Validates: Requirements 3.1, 3.2, 3.3**

resource_type_st = st.sampled_from(["pets", "locations", "offsprings"])
small_limit_st = st.integers(min_value=1, max_value=10)


@given(
    user_id=user_uuid_st,
    resource_type=resource_type_st,
    limit=small_limit_st,
)
@hypothesis_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
async def test_usage_limit_enforcement(async_session, user_id, resource_type, limit):
    """For any breeder at or above their plan's limit for a resource type,
    check_usage should raise an HTTPException with 403.

    **Validates: Requirements 3.1, 3.2, 3.3**
    """
    from datetime import datetime, timedelta, timezone, date
    from fastapi import HTTPException
    from app.models.pet import Pet
    from app.models.location import Location
    from app.models.offspring import Offspring
    from app.models.breed import Breed
    from app.models.breeding import Breeding

    # Track objects for cleanup
    created_objects = []

    # Create a user
    breeder = User(
        id=user_id,
        email=f"breeder-{user_id}@test.com",
        hashed_password="hashed_placeholder",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=True,
    )
    async_session.add(breeder)
    await async_session.flush()
    created_objects.append(breeder)

    # Create a plan with the generated limit for the target resource type
    plan_name = f"test-plan-{uuid.uuid4().hex[:8]}"
    plan = Plan(
        name=plan_name,
        price=0,
        currency="usd",
        billing_interval="month",
        max_pets=limit if resource_type == "pets" else 1000,
        max_published_locations=limit if resource_type == "locations" else 1000,
        max_simultaneous_offsprings=limit if resource_type == "offsprings" else 1000,
        is_default=False,
    )
    async_session.add(plan)
    await async_session.flush()
    created_objects.append(plan)

    # Create an active subscription on this plan
    now = datetime.now(timezone.utc)
    subscription = Subscription(
        user_id=user_id,
        plan_id=plan.id,
        status="active",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    async_session.add(subscription)
    await async_session.flush()
    created_objects.append(subscription)

    # Create exactly `limit` resources of the given type
    if resource_type == "pets":
        for i in range(limit):
            pet = Pet(
                user_id=user_id,
                name=f"Pet-{i}-{uuid.uuid4().hex[:6]}",
                is_deleted=False,
            )
            async_session.add(pet)
            created_objects.append(pet)
        await async_session.flush()

    elif resource_type == "locations":
        for i in range(limit):
            loc = Location(
                user_id=user_id,
                name=f"Loc-{i}-{uuid.uuid4().hex[:6]}",
                address1="123 Test St",
                city="Testville",
                state="TS",
                country="US",
                zipcode="12345",
                location_type="user",
                is_published=True,
            )
            async_session.add(loc)
            created_objects.append(loc)
        await async_session.flush()

    elif resource_type == "offsprings":
        # Offspring requires a Breeding, which requires a user_id
        breeding = Breeding(
            user_id=user_id,
            date_of_litter=date(2024, 1, 1),
            description="Test breeding",
            is_active=True,
            status="Started",
        )
        async_session.add(breeding)
        await async_session.flush()
        created_objects.append(breeding)

        for i in range(limit):
            offspring = Offspring(
                breeding_id=breeding.id,
                user_id=user_id,
                name=f"Offspring-{i}-{uuid.uuid4().hex[:6]}",
                gender="Male",
                date_of_birth=date(2024, 3, 1),
                status="Available",
            )
            async_session.add(offspring)
            created_objects.append(offspring)
        await async_session.flush()

    # Now check_usage should raise HTTPException with 403
    with pytest.raises(HTTPException) as exc_info:
        await billing_service.check_usage(async_session, user_id, resource_type)

    assert exc_info.value.status_code == 403

    # Clean up in reverse order to respect FK constraints
    for obj in reversed(created_objects):
        await async_session.delete(obj)
    await async_session.flush()


# --- Property 7: Non-active subscription falls back to FREE plan limits ---
# Feature: billing-service, Property 7: Non-active subscription falls back to FREE plan limits
# **Validates: Requirements 3.4**

non_active_status_st = st.sampled_from(["canceled", "past_due"])


@given(
    user_id=user_uuid_st,
    non_active_status=non_active_status_st,
)
@hypothesis_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
async def test_non_active_subscription_falls_back_to_free_limits(
    async_session, user_id, non_active_status
):
    """For any breeder with canceled/past_due status, effective limits should
    match the FREE plan, not the paid plan referenced by the subscription.

    **Validates: Requirements 3.4**
    """
    from datetime import datetime, timedelta, timezone
    from fastapi import HTTPException
    from app.models.pet import Pet

    created_objects = []

    # Create the FREE plan (is_default=True) with max_pets=5
    free_plan = Plan(
        name=f"Free-{uuid.uuid4().hex[:8]}",
        price=0,
        currency="usd",
        billing_interval="month",
        max_pets=5,
        max_published_locations=1,
        max_simultaneous_offsprings=20,
        is_default=True,
    )
    async_session.add(free_plan)
    await async_session.flush()
    created_objects.append(free_plan)

    # Create a paid plan with much higher limits
    paid_plan = Plan(
        name=f"Pro-{uuid.uuid4().hex[:8]}",
        price=29.99,
        currency="usd",
        billing_interval="month",
        max_pets=100,
        max_published_locations=50,
        max_simultaneous_offsprings=500,
        is_default=False,
    )
    async_session.add(paid_plan)
    await async_session.flush()
    created_objects.append(paid_plan)

    # Create a breeder user
    breeder = User(
        id=user_id,
        email=f"breeder-{user_id}@test.com",
        hashed_password="hashed_placeholder",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=True,
    )
    async_session.add(breeder)
    await async_session.flush()
    created_objects.append(breeder)

    # Create a subscription on the PAID plan but with non-active status
    now = datetime.now(timezone.utc)
    subscription = Subscription(
        user_id=user_id,
        plan_id=paid_plan.id,
        status=non_active_status,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    async_session.add(subscription)
    await async_session.flush()
    created_objects.append(subscription)

    # Create exactly 5 pets (the FREE plan limit)
    for i in range(5):
        pet = Pet(
            user_id=user_id,
            name=f"Pet-{i}-{uuid.uuid4().hex[:6]}",
            is_deleted=False,
        )
        async_session.add(pet)
        created_objects.append(pet)
    await async_session.flush()

    # check_usage should raise 403 because FREE plan limit (5) is enforced,
    # not the paid plan's limit (100)
    with pytest.raises(HTTPException) as exc_info:
        await billing_service.check_usage(async_session, user_id, "pets")

    assert exc_info.value.status_code == 403

    # Clean up in reverse order
    for obj in reversed(created_objects):
        await async_session.delete(obj)
    await async_session.flush()


# --- Property 8: Invoice generation targets only due subscriptions ---
# Feature: billing-service, Property 8: Invoice generation targets only due subscriptions
# **Validates: Requirements 4.2**

due_count_st = st.integers(min_value=1, max_value=5)
not_due_count_st = st.integers(min_value=1, max_value=5)


@given(
    num_due=due_count_st,
    num_not_due=not_due_count_st,
)
@hypothesis_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
async def test_invoice_generation_targets_only_due_subscriptions(
    async_session, num_due, num_not_due
):
    """Given subscriptions with varying period_end dates, generate_invoices
    creates invoices only for those whose period has ended (due).

    **Validates: Requirements 4.2**
    """
    from datetime import datetime, timedelta, timezone

    created_objects = []
    now = datetime.now(timezone.utc)

    # Create a FREE plan (price=0) so invoices are marked "paid" immediately
    free_plan = Plan(
        name=f"Free-{uuid.uuid4().hex[:8]}",
        price=0,
        currency="usd",
        billing_interval="month",
        max_pets=5,
        max_published_locations=1,
        max_simultaneous_offsprings=20,
        is_default=True,
    )
    async_session.add(free_plan)
    await async_session.flush()
    created_objects.append(free_plan)

    due_sub_ids = []

    # Create "due" subscriptions: period_end in the past
    for i in range(num_due):
        user_id = uuid.uuid4()
        breeder = User(
            id=user_id,
            email=f"due-{user_id}@test.com",
            hashed_password="hashed_placeholder",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
        )
        async_session.add(breeder)
        await async_session.flush()
        created_objects.append(breeder)

        sub = Subscription(
            user_id=user_id,
            plan_id=free_plan.id,
            status="active",
            current_period_start=now - timedelta(days=60),
            current_period_end=now - timedelta(days=1),  # in the past → due
        )
        async_session.add(sub)
        await async_session.flush()
        created_objects.append(sub)
        due_sub_ids.append(sub.id)

    # Create "not due" subscriptions: period_end in the future
    for i in range(num_not_due):
        user_id = uuid.uuid4()
        breeder = User(
            id=user_id,
            email=f"notdue-{user_id}@test.com",
            hashed_password="hashed_placeholder",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
        )
        async_session.add(breeder)
        await async_session.flush()
        created_objects.append(breeder)

        sub = Subscription(
            user_id=user_id,
            plan_id=free_plan.id,
            status="active",
            current_period_start=now - timedelta(days=10),
            current_period_end=now + timedelta(days=20),  # in the future → not due
        )
        async_session.add(sub)
        await async_session.flush()
        created_objects.append(sub)

    # Run invoice generation
    summary = await billing_service.generate_invoices(async_session)

    # Assert: only due subscriptions got invoices
    assert summary["successful"] == num_due
    assert summary["total_processed"] == num_due

    # Verify invoices exist only for due subscriptions
    from app.models.invoice import Invoice
    inv_result = await async_session.execute(select(Invoice))
    invoices = list(inv_result.scalars().all())

    assert len(invoices) == num_due
    invoice_sub_ids = {inv.subscription_id for inv in invoices}
    assert invoice_sub_ids == set(due_sub_ids)

    # All invoices should be "paid" (FREE plan)
    for inv in invoices:
        assert inv.status == "paid"
        created_objects.append(inv)

    # Clean up in reverse order
    for obj in reversed(created_objects):
        await async_session.delete(obj)
    await async_session.flush()


# --- Property 9: Invoice status determined by plan price ---
# Feature: billing-service, Property 9: Invoice status determined by plan price
# **Validates: Requirements 4.4, 4.5**

free_or_paid_price_st = st.one_of(
    st.just(Decimal("0.00")),
    st.decimals(
        min_value=Decimal("0.01"),
        max_value=Decimal("9999.99"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    ),
)


@given(
    user_id=user_uuid_st,
    price=free_or_paid_price_st,
)
@hypothesis_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
async def test_invoice_status_determined_by_plan_price(async_session, user_id, price):
    """For any subscription due for invoicing, if the plan price is 0 the invoice
    status should be 'paid' and the billing period should advance; if the plan
    price is > 0 the invoice status should be 'pending'.

    **Validates: Requirements 4.4, 4.5**
    """
    from datetime import datetime, timedelta, timezone
    from app.models.invoice import Invoice

    created_objects = []
    now = datetime.now(timezone.utc)

    # Create a plan with the generated price
    plan = Plan(
        name=f"TestPlan-{uuid.uuid4().hex[:8]}",
        price=price,
        currency="usd",
        billing_interval="month",
        max_pets=5,
        max_published_locations=1,
        max_simultaneous_offsprings=20,
        is_default=True,
    )
    async_session.add(plan)
    await async_session.flush()
    created_objects.append(plan)

    # Create a breeder user
    breeder = User(
        id=user_id,
        email=f"breeder-{user_id}@test.com",
        hashed_password="hashed_placeholder",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=True,
    )
    async_session.add(breeder)
    await async_session.flush()
    created_objects.append(breeder)

    # Create a due subscription (period_end in the past)
    period_start = now - timedelta(days=60)
    period_end = now - timedelta(days=1)
    subscription = Subscription(
        user_id=user_id,
        plan_id=plan.id,
        status="active",
        current_period_start=period_start,
        current_period_end=period_end,
    )
    async_session.add(subscription)
    await async_session.flush()
    created_objects.append(subscription)

    # Run invoice generation
    summary = await billing_service.generate_invoices(async_session)

    assert summary["successful"] == 1
    assert summary["total_processed"] == 1

    # Fetch the generated invoice
    inv_result = await async_session.execute(select(Invoice))
    invoices = list(inv_result.scalars().all())
    assert len(invoices) == 1
    invoice = invoices[0]

    if price == 0:
        # FREE plan: invoice marked "paid", billing period advanced
        assert invoice.status == "paid"
        await async_session.refresh(subscription)
        assert subscription.current_period_start == period_end
        assert subscription.current_period_end == period_end + timedelta(days=30)
    else:
        # Paid plan: invoice marked "pending"
        assert invoice.status == "pending"

    created_objects.append(invoice)

    # Clean up in reverse order
    for obj in reversed(created_objects):
        await async_session.delete(obj)
    await async_session.flush()


# --- Property 10: Invoice job error isolation ---
# Feature: billing-service, Property 10: Invoice job error isolation
# **Validates: Requirements 4.6**

valid_sub_count_st = st.integers(min_value=1, max_value=5)


@given(
    num_valid=valid_sub_count_st,
)
@hypothesis_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
async def test_invoice_job_error_isolation(async_session, num_valid):
    """If one subscription errors during invoice generation, remaining valid
    subscriptions still get invoices. The summary should show failed >= 1
    and successful == number of valid subscriptions.

    **Validates: Requirements 4.6**
    """
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch
    from app.models.invoice import Invoice
    from sqlalchemy.engine import Result

    created_objects = []
    now = datetime.now(timezone.utc)

    # Create a FREE plan for valid subscriptions
    free_plan = Plan(
        name=f"Free-{uuid.uuid4().hex[:8]}",
        price=0,
        currency="usd",
        billing_interval="month",
        max_pets=5,
        max_published_locations=1,
        max_simultaneous_offsprings=20,
        is_default=True,
    )
    async_session.add(free_plan)
    await async_session.flush()
    created_objects.append(free_plan)

    valid_sub_ids = []

    # Create num_valid "valid" due subscriptions on the FREE plan
    for i in range(num_valid):
        user_id = uuid.uuid4()
        breeder = User(
            id=user_id,
            email=f"valid-{user_id}@test.com",
            hashed_password="hashed_placeholder",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
        )
        async_session.add(breeder)
        await async_session.flush()
        created_objects.append(breeder)

        sub = Subscription(
            user_id=user_id,
            plan_id=free_plan.id,
            status="active",
            current_period_start=now - timedelta(days=60),
            current_period_end=now - timedelta(days=1),  # due
        )
        async_session.add(sub)
        await async_session.flush()
        created_objects.append(sub)
        valid_sub_ids.append(sub.id)

    # Create one "broken" subscription on the same FREE plan.
    broken_user_id = uuid.uuid4()
    broken_breeder = User(
        id=broken_user_id,
        email=f"broken-{broken_user_id}@test.com",
        hashed_password="hashed_placeholder",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=True,
    )
    async_session.add(broken_breeder)
    await async_session.flush()
    created_objects.append(broken_breeder)

    broken_sub = Subscription(
        user_id=broken_user_id,
        plan_id=free_plan.id,
        status="active",
        current_period_start=now - timedelta(days=60),
        current_period_end=now - timedelta(days=1),  # due
    )
    async_session.add(broken_sub)
    await async_session.flush()
    created_objects.append(broken_sub)
    broken_sub_id = broken_sub.id

    # Wrap session.execute so that after the subscription query inside
    # generate_invoices, the broken subscription's plan is replaced with
    # a mock that raises on .price access. This lets us test the real
    # generate_invoices error-handling code path.
    original_execute = async_session.execute

    async def poisoning_execute(stmt, *args, **kwargs):
        result = await original_execute(stmt, *args, **kwargs)
        # Check if this is the subscription query by inspecting the result.
        # We wrap scalars().all() to poison the broken sub after fetching.
        original_scalars = result.scalars

        def patched_scalars():
            scalar_result = original_scalars()
            original_all = scalar_result.all

            def patched_all():
                items = original_all()
                for item in items:
                    if isinstance(item, Subscription) and item.id == broken_sub_id:
                        # Set plan to None directly in the SQLAlchemy instance
                        # state dict, bypassing instrumentation entirely.
                        # This makes sub.plan return None, so accessing
                        # plan.price raises AttributeError in generate_invoices.
                        from sqlalchemy import inspect as sa_inspect
                        state = sa_inspect(item)
                        state.dict['plan'] = None
                return items

            scalar_result.all = patched_all
            return scalar_result

        result.scalars = patched_scalars
        return result

    async_session.execute = poisoning_execute
    try:
        summary = await billing_service.generate_invoices(async_session)
    finally:
        async_session.execute = original_execute

    # Assert: valid subscriptions succeeded, broken one failed
    assert summary["failed"] >= 1
    assert summary["successful"] == num_valid

    # Verify invoices exist only for valid subscriptions
    inv_result = await async_session.execute(select(Invoice))
    invoices = list(inv_result.scalars().all())

    assert len(invoices) == num_valid
    invoice_sub_ids = {inv.subscription_id for inv in invoices}
    assert invoice_sub_ids == set(valid_sub_ids)

    for inv in invoices:
        created_objects.append(inv)

    # Clean up in reverse order
    for obj in reversed(created_objects):
        await async_session.delete(obj)
    await async_session.flush()
