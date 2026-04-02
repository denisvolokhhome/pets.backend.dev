"""Property-based tests for billing models.

Feature: billing-service
"""

from decimal import Decimal

import pytest
from hypothesis import given, settings as hypothesis_settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.models.plan import Plan


# --- Strategies ---

plan_name_st = st.text(
    min_size=1,
    max_size=100,
    alphabet=st.characters(whitelist_categories=("L", "N")),
).filter(lambda x: x.strip())

plan_price_st = st.decimals(
    min_value=0,
    max_value=Decimal("9999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

plan_currency_st = st.sampled_from(["usd", "eur", "gbp"])
plan_billing_interval_st = st.sampled_from(["month", "year"])
plan_limit_st = st.integers(min_value=1, max_value=1000)
plan_is_default_st = st.booleans()


# --- Property 1: Plan data round-trip ---
# **Validates: Requirements 1.1, 4.3**


@given(
    name=plan_name_st,
    price=plan_price_st,
    currency=plan_currency_st,
    billing_interval=plan_billing_interval_st,
    max_pets=plan_limit_st,
    max_published_locations=plan_limit_st,
    max_simultaneous_offsprings=plan_limit_st,
    is_default=plan_is_default_st,
)
@hypothesis_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_plan_data_round_trip(
    async_session,
    name,
    price,
    currency,
    billing_interval,
    max_pets,
    max_published_locations,
    max_simultaneous_offsprings,
    is_default,
):
    """For any valid Plan, storing it in the DB and reading it back preserves all fields.

    **Validates: Requirements 1.1, 4.3**
    """
    plan = Plan(
        name=name,
        price=price,
        currency=currency,
        billing_interval=billing_interval,
        max_pets=max_pets,
        max_published_locations=max_published_locations,
        max_simultaneous_offsprings=max_simultaneous_offsprings,
        is_default=is_default,
    )
    async_session.add(plan)
    await async_session.flush()

    result = await async_session.execute(select(Plan).where(Plan.id == plan.id))
    fetched = result.scalar_one()

    assert fetched.name == name
    assert fetched.price == price
    assert fetched.currency == currency
    assert fetched.billing_interval == billing_interval
    assert fetched.max_pets == max_pets
    assert fetched.max_published_locations == max_published_locations
    assert fetched.max_simultaneous_offsprings == max_simultaneous_offsprings
    assert fetched.is_default == is_default
    assert fetched.created_at is not None

    # Clean up for next hypothesis example
    await async_session.delete(fetched)
    await async_session.flush()


# --- Property 2: Plan name uniqueness enforcement ---
# **Validates: Requirements 1.3**


@given(
    name=plan_name_st,
    price=plan_price_st,
    currency=plan_currency_st,
    billing_interval=plan_billing_interval_st,
    max_pets=plan_limit_st,
    max_published_locations=plan_limit_st,
    max_simultaneous_offsprings=plan_limit_st,
    is_default=plan_is_default_st,
)
@hypothesis_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_plan_name_uniqueness_enforcement(
    async_session,
    name,
    price,
    currency,
    billing_interval,
    max_pets,
    max_published_locations,
    max_simultaneous_offsprings,
    is_default,
):
    """For any two Plans with the same name, attempting to create the second should raise IntegrityError.

    **Validates: Requirements 1.3**
    """
    plan1 = Plan(
        name=name,
        price=price,
        currency=currency,
        billing_interval=billing_interval,
        max_pets=max_pets,
        max_published_locations=max_published_locations,
        max_simultaneous_offsprings=max_simultaneous_offsprings,
        is_default=is_default,
    )
    async_session.add(plan1)
    await async_session.flush()

    plan2 = Plan(
        name=name,
        price=price,
        currency=currency,
        billing_interval=billing_interval,
        max_pets=max_pets,
        max_published_locations=max_published_locations,
        max_simultaneous_offsprings=max_simultaneous_offsprings,
        is_default=is_default,
    )
    async_session.add(plan2)

    with pytest.raises(IntegrityError):
        await async_session.flush()

    await async_session.rollback()
