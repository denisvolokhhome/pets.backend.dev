"""Property-based tests for billing dashboard metrics correctness.

Feature: billing-service
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from hypothesis import given, settings as hypothesis_settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import text

from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.invoice import Invoice
from app.models.user import User


# --- Strategies ---

subscription_status_st = st.sampled_from(["active", "canceled", "past_due"])
invoice_status_st = st.sampled_from(["pending", "paid", "failed", "void"])

invoice_amount_st = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("9999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


def subscription_data_st():
    """Strategy that generates a single subscription's data dict."""
    return st.fixed_dictionaries({
        "status": subscription_status_st,
    })


def invoice_data_st():
    """Strategy that generates a single invoice's data dict."""
    return st.fixed_dictionaries({
        "status": invoice_status_st,
        "amount": invoice_amount_st,
        "overdue": st.booleans(),  # whether period_end is in the past
    })


# Composite strategy: a list of plans, each with subscriptions, each with invoices
plan_count_st = st.integers(min_value=1, max_value=3)
subs_per_plan_st = st.integers(min_value=0, max_value=3)
invoices_per_sub_st = st.integers(min_value=0, max_value=3)


@st.composite
def billing_dataset_st(draw):
    """Generate a complete billing dataset: plans with subscriptions and invoices."""
    num_plans = draw(plan_count_st)
    dataset = []
    for _ in range(num_plans):
        plan_name = f"Plan-{uuid.uuid4().hex[:8]}"
        num_subs = draw(subs_per_plan_st)
        subs = []
        for _ in range(num_subs):
            sub_status = draw(subscription_status_st)
            num_invoices = draw(invoices_per_sub_st)
            invoices = []
            for _ in range(num_invoices):
                invoices.append({
                    "status": draw(invoice_status_st),
                    "amount": draw(invoice_amount_st),
                    "overdue": draw(st.booleans()),
                })
            subs.append({"status": sub_status, "invoices": invoices})
        dataset.append({"plan_name": plan_name, "subscriptions": subs})
    return dataset


# --- Property 16: Dashboard metrics correctness ---
# Feature: billing-service, Property 16: Dashboard metrics correctness
# **Validates: Requirements 9.7**


@given(dataset=billing_dataset_st())
@hypothesis_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
async def test_dashboard_metrics_correctness(async_session, dataset):
    """For any set of subscriptions and invoices, the computed summary metrics
    should satisfy:
    - total_active_subscriptions == count of subscriptions with status 'active'
    - subscriptions_by_plan == group-by count of active subscriptions by plan name
    - total_revenue == sum of amounts on invoices with status 'paid'
    - overdue_invoices_count == count of invoices with status 'failed' or 'pending'
      past their period_end

    **Validates: Requirements 9.7**
    """
    now = datetime.now(timezone.utc)
    created_objects = []

    # --- Expected metrics computed manually ---
    expected_total_active = 0
    expected_by_plan = defaultdict(int)
    expected_total_revenue = Decimal("0.00")
    expected_overdue_count = 0

    # --- Seed data into DB ---
    for plan_data in dataset:
        plan = Plan(
            name=plan_data["plan_name"],
            price=Decimal("10.00"),
            currency="usd",
            billing_interval="month",
            max_pets=10,
            max_published_locations=5,
            max_simultaneous_offsprings=50,
            is_default=False,
        )
        async_session.add(plan)
        await async_session.flush()
        created_objects.append(plan)

        for sub_data in plan_data["subscriptions"]:
            user_id = uuid.uuid4()
            user = User(
                id=user_id,
                email=f"user-{user_id}@test.com",
                hashed_password="hashed_placeholder",
                is_active=True,
                is_superuser=False,
                is_verified=True,
                is_breeder=True,
            )
            async_session.add(user)
            await async_session.flush()
            created_objects.append(user)

            sub = Subscription(
                user_id=user_id,
                plan_id=plan.id,
                status=sub_data["status"],
                current_period_start=now - timedelta(days=30),
                current_period_end=now + timedelta(days=30),
            )
            async_session.add(sub)
            await async_session.flush()
            created_objects.append(sub)

            # Track expected active subscription counts
            if sub_data["status"] == "active":
                expected_total_active += 1
                expected_by_plan[plan_data["plan_name"]] += 1

            # Create invoices for this subscription
            for inv_data in sub_data["invoices"]:
                if inv_data["overdue"]:
                    period_end = now - timedelta(days=1)
                else:
                    period_end = now + timedelta(days=10)

                invoice = Invoice(
                    subscription_id=sub.id,
                    amount=inv_data["amount"],
                    currency="usd",
                    status=inv_data["status"],
                    period_start=period_end - timedelta(days=30),
                    period_end=period_end,
                )
                async_session.add(invoice)
                created_objects.append(invoice)

                # Track expected revenue
                if inv_data["status"] == "paid":
                    expected_total_revenue += inv_data["amount"]

                # Track expected overdue count
                if inv_data["status"] in ("failed", "pending") and inv_data["overdue"]:
                    expected_overdue_count += 1

        await async_session.flush()

    # --- Query DB using raw SQL (same logic as billing-admin db.py) ---

    # Total active subscriptions
    actual_total_active = (await async_session.execute(
        text("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'")
    )).scalar() or 0

    # Subscriptions by plan
    rows = (await async_session.execute(
        text("""
            SELECT p.name, COUNT(*) AS cnt
            FROM subscriptions s
            INNER JOIN plans p ON p.id = s.plan_id
            WHERE s.status = 'active'
            GROUP BY p.name
            ORDER BY p.name
        """)
    )).fetchall()
    actual_by_plan = {row[0]: row[1] for row in rows}

    # Total revenue (sum of paid invoices)
    actual_total_revenue = (await async_session.execute(
        text("SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE status = 'paid'")
    )).scalar()
    actual_total_revenue = Decimal(str(actual_total_revenue))

    # Overdue invoices: pending or failed invoices past their period end
    actual_overdue_count = (await async_session.execute(
        text("""
            SELECT COUNT(*)
            FROM invoices
            WHERE status IN ('failed', 'pending')
              AND period_end <= :now
        """),
        {"now": now},
    )).scalar() or 0

    # --- Assert metrics match ---
    assert actual_total_active == expected_total_active, (
        f"total_active: expected {expected_total_active}, got {actual_total_active}"
    )

    # Compare subscriptions_by_plan (filter out zero-count plans from expected)
    expected_by_plan_filtered = {k: v for k, v in expected_by_plan.items() if v > 0}
    assert actual_by_plan == expected_by_plan_filtered, (
        f"by_plan: expected {expected_by_plan_filtered}, got {actual_by_plan}"
    )

    assert actual_total_revenue == expected_total_revenue, (
        f"total_revenue: expected {expected_total_revenue}, got {actual_total_revenue}"
    )

    assert actual_overdue_count == expected_overdue_count, (
        f"overdue_count: expected {expected_overdue_count}, got {actual_overdue_count}"
    )

    # --- Clean up ---
    for obj in reversed(created_objects):
        await async_session.delete(obj)
    await async_session.flush()
