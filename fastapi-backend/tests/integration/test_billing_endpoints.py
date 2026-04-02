"""Integration tests for billing endpoints.

Property-based tests validating billing endpoint access control and behavior.
"""
import os
import uuid
from unittest.mock import patch

# Ensure encryption key is available for EncryptedString columns
os.environ.setdefault("BILLING_ENCRYPTION_KEY", "test-encryption-key-for-billing")

import pytest
import stripe
from hypothesis import given, settings, strategies as st, HealthCheck
from httpx import AsyncClient, ASGITransport
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice
from app.models.subscription import Subscription
from app.models.user import User


# --- Hypothesis strategies ---

def non_breeder_user_strategy():
    """Generate random non-breeder user data."""
    return st.fixed_dictionaries({
        "email": st.from_regex(r"[a-z]{5,10}@[a-z]{3,8}\.(com|org|net)", fullmatch=True),
        "name": st.text(
            alphabet=st.characters(whitelist_categories=("L", "Zs")),
            min_size=1,
            max_size=50,
        ).filter(lambda s: s.strip()),
    })


# Feature: billing-service, Property 5: Breeder-only access restriction
class TestBreederOnlyAccessRestriction:
    """Property 5: For any non-breeder user, calling subscription management
    endpoints returns 403.

    **Validates: Requirements 2.5**
    """

    PROTECTED_ENDPOINTS = [
        ("GET", "/api/billing/subscription"),
        ("POST", "/api/billing/subscribe"),
        ("GET", "/api/billing/invoices"),
        ("POST", "/api/billing/create-checkout-session"),
    ]

    @pytest.mark.asyncio
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(user_data=non_breeder_user_strategy())
    async def test_non_breeder_gets_403_on_protected_endpoints(
        self, user_data: dict, async_session: AsyncSession
    ):
        """For any non-breeder user, all subscription management endpoints return 403."""
        from app.main import app
        from app.database import get_async_session
        from app.dependencies import current_active_user

        # Create a non-breeder user with generated data
        non_breeder = User(
            email=user_data["email"],
            hashed_password="hashed_placeholder",
            name=user_data["name"],
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=False,
        )
        async_session.add(non_breeder)
        await async_session.commit()
        await async_session.refresh(non_breeder)

        # Override dependencies to inject non-breeder user and test session
        async def override_session():
            yield async_session

        async def override_user():
            return non_breeder

        app.dependency_overrides[get_async_session] = override_session
        app.dependency_overrides[current_active_user] = override_user

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                for method, path in self.PROTECTED_ENDPOINTS:
                    if method == "GET":
                        response = await client.get(path)
                    else:
                        # POST endpoints need a JSON body with plan_id
                        response = await client.post(
                            path, json={"plan_id": str(uuid.uuid4())}
                        )
                    assert response.status_code == 403, (
                        f"Expected 403 for non-breeder on {method} {path}, "
                        f"got {response.status_code}"
                    )
        finally:
            app.dependency_overrides.clear()

        # Clean up the user for the next Hypothesis example
        await async_session.delete(non_breeder)
        await async_session.commit()

    @pytest.mark.asyncio
    async def test_plans_endpoint_accessible_without_breeder_auth(
        self, async_client: AsyncClient
    ):
        """GET /api/billing/plans is public and should return 200 even for non-breeders."""
        response = await async_client.get("/api/billing/plans")
        assert response.status_code == 200


# Feature: billing-service, Property 11: Webhook signature verification
class TestWebhookSignatureVerification:
    """Property 11: For any payload with an invalid signature, the webhook
    endpoint returns 400 and no DB state changes.

    **Validates: Requirements 5.6**
    """

    @pytest.mark.asyncio
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        payload=st.binary(min_size=1, max_size=512),
        invalid_signature=st.text(
            alphabet=st.characters(min_codepoint=33, max_codepoint=126),
            min_size=1,
            max_size=100,
        ),
    )
    async def test_invalid_signature_returns_400_no_db_changes(
        self, payload: bytes, invalid_signature: str, async_session: AsyncSession
    ):
        """For any payload with an invalid signature, webhook returns 400 and DB is unchanged."""
        from app.main import app
        from app.database import get_async_session

        # Count subscriptions and invoices before the request
        sub_count_before = (
            await async_session.execute(select(func.count()).select_from(Subscription))
        ).scalar_one()
        inv_count_before = (
            await async_session.execute(select(func.count()).select_from(Invoice))
        ).scalar_one()

        # Override DB session
        async def override_session():
            yield async_session

        app.dependency_overrides[get_async_session] = override_session

        try:
            # Mock verify_webhook_signature to raise SignatureVerificationError
            with patch.object(
                stripe.Webhook,
                "construct_event",
                side_effect=stripe.error.SignatureVerificationError(
                    "Invalid signature", invalid_signature
                ),
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        "/api/billing/webhook",
                        content=payload,
                        headers={"Stripe-Signature": invalid_signature},
                    )

            # Assert 400 response
            assert response.status_code == 400, (
                f"Expected 400 for invalid signature, got {response.status_code}"
            )

            # Assert no DB state changes
            sub_count_after = (
                await async_session.execute(select(func.count()).select_from(Subscription))
            ).scalar_one()
            inv_count_after = (
                await async_session.execute(select(func.count()).select_from(Invoice))
            ).scalar_one()

            assert sub_count_before == sub_count_after, (
                f"Subscription count changed: {sub_count_before} -> {sub_count_after}"
            )
            assert inv_count_before == inv_count_after, (
                f"Invoice count changed: {inv_count_before} -> {inv_count_after}"
            )
        finally:
            app.dependency_overrides.clear()


# --- Strategies for Property 12 ---

def stripe_customer_id_strategy():
    """Generate random Stripe customer IDs (cus_xxx)."""
    return st.from_regex(r"cus_[A-Za-z0-9]{14,24}", fullmatch=True)


def stripe_subscription_id_strategy():
    """Generate random Stripe subscription IDs (sub_xxx)."""
    return st.from_regex(r"sub_[A-Za-z0-9]{14,24}", fullmatch=True)


# Feature: billing-service, Property 12: Webhook checkout.session.completed activates subscription
class TestWebhookCheckoutSessionCompleted:
    """Property 12: For any valid checkout.session.completed webhook event
    referencing an existing Subscription, after processing, the Subscription
    status should be "active" and the Stripe customer and subscription
    identifiers should be stored.

    **Validates: Requirements 5.3**
    """

    @pytest.mark.asyncio
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        stripe_customer_id=stripe_customer_id_strategy(),
        stripe_subscription_id=stripe_subscription_id_strategy(),
    )
    async def test_checkout_completed_activates_subscription_and_stores_stripe_ids(
        self,
        stripe_customer_id: str,
        stripe_subscription_id: str,
        async_session: AsyncSession,
    ):
        """For any valid checkout.session.completed event, subscription becomes active with Stripe IDs stored."""
        from datetime import datetime, timezone
        from app.main import app
        from app.database import get_async_session
        from app.models.plan import Plan

        # Create a plan
        plan = Plan(
            name=f"test_plan_{uuid.uuid4().hex[:8]}",
            price=29.99,
            currency="usd",
            billing_interval="month",
            max_pets=50,
            max_published_locations=5,
            max_simultaneous_offsprings=100,
            is_default=False,
        )
        async_session.add(plan)
        await async_session.flush()

        # Create a breeder user
        breeder = User(
            email=f"breeder_{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="hashed_placeholder",
            name="Test Breeder",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
        )
        async_session.add(breeder)
        await async_session.flush()

        # Create a subscription with status "pending" (not yet active via checkout)
        now = datetime.now(timezone.utc)
        subscription = Subscription(
            user_id=breeder.id,
            plan_id=plan.id,
            status="pending",
            current_period_start=now,
            current_period_end=now,
            stripe_customer_id=None,
            stripe_subscription_id=None,
        )
        async_session.add(subscription)
        await async_session.commit()
        await async_session.refresh(subscription)

        subscription_id = subscription.id

        # Build the mock checkout.session.completed event
        mock_event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": f"cs_test_{uuid.uuid4().hex[:16]}",
                    "customer": stripe_customer_id,
                    "subscription": stripe_subscription_id,
                    "metadata": {
                        "user_id": str(breeder.id),
                        "plan_id": str(plan.id),
                        "subscription_id": str(subscription_id),
                    },
                }
            },
        }

        # Override DB session
        async def override_session():
            yield async_session

        app.dependency_overrides[get_async_session] = override_session

        try:
            with patch.object(
                stripe.Webhook,
                "construct_event",
                return_value=mock_event,
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        "/api/billing/webhook",
                        content=b'{"mock": "payload"}',
                        headers={"Stripe-Signature": "t=123,v1=fakesig"},
                    )

            # Assert 200 response
            assert response.status_code == 200, (
                f"Expected 200 for valid checkout.session.completed, got {response.status_code}"
            )

            # Reload subscription from DB
            result = await async_session.execute(
                select(Subscription).where(Subscription.id == subscription_id)
            )
            updated_sub = result.scalar_one()

            # Assert subscription is now active
            assert updated_sub.status == "active", (
                f"Expected subscription status 'active', got '{updated_sub.status}'"
            )

            # Assert Stripe IDs are stored
            assert updated_sub.stripe_customer_id == stripe_customer_id, (
                f"Expected stripe_customer_id '{stripe_customer_id}', "
                f"got '{updated_sub.stripe_customer_id}'"
            )
            assert updated_sub.stripe_subscription_id == stripe_subscription_id, (
                f"Expected stripe_subscription_id '{stripe_subscription_id}', "
                f"got '{updated_sub.stripe_subscription_id}'"
            )
        finally:
            app.dependency_overrides.clear()

        # Clean up
        await async_session.delete(subscription)
        await async_session.delete(breeder)
        await async_session.delete(plan)
        await async_session.commit()


# --- Strategy for Property 13 ---

def stripe_invoice_id_strategy():
    """Generate random Stripe invoice IDs (in_xxx)."""
    return st.from_regex(r"in_[A-Za-z0-9]{14,24}", fullmatch=True)


# Feature: billing-service, Property 13: Webhook invoice.paid marks invoice paid
class TestWebhookInvoicePaid:
    """Property 13: For any valid invoice.paid webhook event referencing an
    existing Invoice, after processing, the Invoice status should be "paid".

    **Validates: Requirements 5.4**
    """

    @pytest.mark.asyncio
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        stripe_inv_id=stripe_invoice_id_strategy(),
    )
    async def test_invoice_paid_webhook_marks_invoice_paid(
        self,
        stripe_inv_id: str,
        async_session: AsyncSession,
    ):
        """For any valid invoice.paid event, the referenced invoice status becomes 'paid'."""
        from datetime import datetime, timezone
        from app.main import app
        from app.database import get_async_session
        from app.models.plan import Plan

        # Create a plan
        plan = Plan(
            name=f"test_plan_{uuid.uuid4().hex[:8]}",
            price=29.99,
            currency="usd",
            billing_interval="month",
            max_pets=50,
            max_published_locations=5,
            max_simultaneous_offsprings=100,
            is_default=False,
        )
        async_session.add(plan)
        await async_session.flush()

        # Create a breeder user
        breeder = User(
            email=f"breeder_{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="hashed_placeholder",
            name="Test Breeder",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
        )
        async_session.add(breeder)
        await async_session.flush()

        # Create a subscription
        now = datetime.now(timezone.utc)
        subscription = Subscription(
            user_id=breeder.id,
            plan_id=plan.id,
            status="active",
            current_period_start=now,
            current_period_end=now,
        )
        async_session.add(subscription)
        await async_session.flush()

        # Create an invoice with status "pending" and the generated stripe_invoice_id
        invoice = Invoice(
            subscription_id=subscription.id,
            amount=29.99,
            currency="usd",
            status="pending",
            period_start=now,
            period_end=now,
            stripe_invoice_id=stripe_inv_id,
        )
        async_session.add(invoice)
        await async_session.commit()
        await async_session.refresh(invoice)

        invoice_id = invoice.id

        # Build the mock invoice.paid event
        mock_event = {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": stripe_inv_id,
                }
            },
        }

        # Override DB session
        async def override_session():
            yield async_session

        app.dependency_overrides[get_async_session] = override_session

        try:
            with patch.object(
                stripe.Webhook,
                "construct_event",
                return_value=mock_event,
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        "/api/billing/webhook",
                        content=b'{"mock": "payload"}',
                        headers={"Stripe-Signature": "t=123,v1=fakesig"},
                    )

            # Assert 200 response
            assert response.status_code == 200, (
                f"Expected 200 for valid invoice.paid, got {response.status_code}"
            )

            # Reload invoice from DB
            result = await async_session.execute(
                select(Invoice).where(Invoice.id == invoice_id)
            )
            updated_invoice = result.scalar_one()

            # Assert invoice status is now "paid"
            assert updated_invoice.status == "paid", (
                f"Expected invoice status 'paid', got '{updated_invoice.status}'"
            )
        finally:
            app.dependency_overrides.clear()

        # Clean up
        await async_session.delete(invoice)
        await async_session.delete(subscription)
        await async_session.delete(breeder)
        await async_session.delete(plan)
        await async_session.commit()


# Feature: billing-service, Property 14: Webhook invoice.payment_failed
class TestWebhookInvoicePaymentFailed:
    """Property 14: For any valid invoice.payment_failed webhook event
    referencing an existing Invoice, after processing, the Invoice status
    should be "failed" and the associated Subscription status should be
    "past_due".

    **Validates: Requirements 5.5**
    """

    @pytest.mark.asyncio
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        stripe_inv_id=stripe_invoice_id_strategy(),
    )
    async def test_invoice_payment_failed_webhook_marks_invoice_failed_and_subscription_past_due(
        self,
        stripe_inv_id: str,
        async_session: AsyncSession,
    ):
        """For any valid invoice.payment_failed event, invoice becomes 'failed' and subscription becomes 'past_due'."""
        from datetime import datetime, timezone
        from app.main import app
        from app.database import get_async_session
        from app.models.plan import Plan

        # Create a plan
        plan = Plan(
            name=f"test_plan_{uuid.uuid4().hex[:8]}",
            price=29.99,
            currency="usd",
            billing_interval="month",
            max_pets=50,
            max_published_locations=5,
            max_simultaneous_offsprings=100,
            is_default=False,
        )
        async_session.add(plan)
        await async_session.flush()

        # Create a breeder user
        breeder = User(
            email=f"breeder_{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="hashed_placeholder",
            name="Test Breeder",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
        )
        async_session.add(breeder)
        await async_session.flush()

        # Create a subscription with status "active"
        now = datetime.now(timezone.utc)
        subscription = Subscription(
            user_id=breeder.id,
            plan_id=plan.id,
            status="active",
            current_period_start=now,
            current_period_end=now,
        )
        async_session.add(subscription)
        await async_session.flush()

        # Create an invoice with status "pending" and the generated stripe_invoice_id
        invoice = Invoice(
            subscription_id=subscription.id,
            amount=29.99,
            currency="usd",
            status="pending",
            period_start=now,
            period_end=now,
            stripe_invoice_id=stripe_inv_id,
        )
        async_session.add(invoice)
        await async_session.commit()
        await async_session.refresh(invoice)
        await async_session.refresh(subscription)

        invoice_id = invoice.id
        subscription_id = subscription.id

        # Build the mock invoice.payment_failed event
        mock_event = {
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "id": stripe_inv_id,
                }
            },
        }

        # Override DB session
        async def override_session():
            yield async_session

        app.dependency_overrides[get_async_session] = override_session

        try:
            with patch.object(
                stripe.Webhook,
                "construct_event",
                return_value=mock_event,
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        "/api/billing/webhook",
                        content=b'{"mock": "payload"}',
                        headers={"Stripe-Signature": "t=123,v1=fakesig"},
                    )

            # Assert 200 response
            assert response.status_code == 200, (
                f"Expected 200 for valid invoice.payment_failed, got {response.status_code}"
            )

            # Reload invoice from DB
            result = await async_session.execute(
                select(Invoice).where(Invoice.id == invoice_id)
            )
            updated_invoice = result.scalar_one()

            # Assert invoice status is now "failed"
            assert updated_invoice.status == "failed", (
                f"Expected invoice status 'failed', got '{updated_invoice.status}'"
            )

            # Reload subscription from DB
            sub_result = await async_session.execute(
                select(Subscription).where(Subscription.id == subscription_id)
            )
            updated_sub = sub_result.scalar_one()

            # Assert subscription status is now "past_due"
            assert updated_sub.status == "past_due", (
                f"Expected subscription status 'past_due', got '{updated_sub.status}'"
            )
        finally:
            app.dependency_overrides.clear()

        # Clean up
        await async_session.delete(invoice)
        await async_session.delete(subscription)
        await async_session.delete(breeder)
        await async_session.delete(plan)
        await async_session.commit()


# Feature: billing-service, Property 15: Invoice history ordering
class TestInvoiceHistoryOrdering:
    """Property 15: For any breeder with multiple invoices, GET /api/billing/invoices
    returns them in descending created_at order — that is, for every consecutive pair
    of invoices in the response, the first invoice's created_at >= the second's.

    **Validates: Requirements 6.4**
    """

    @pytest.mark.asyncio
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        num_invoices=st.integers(min_value=2, max_value=10),
    )
    async def test_invoices_returned_in_descending_created_at_order(
        self,
        num_invoices: int,
        async_session: AsyncSession,
    ):
        """For any breeder with multiple invoices, GET /api/billing/invoices returns them
        ordered by created_at descending."""
        from datetime import datetime, timezone, timedelta
        from app.main import app
        from app.database import get_async_session
        from app.dependencies import current_active_user
        from app.models.plan import Plan

        # Create a plan
        plan = Plan(
            name=f"test_plan_{uuid.uuid4().hex[:8]}",
            price=29.99,
            currency="usd",
            billing_interval="month",
            max_pets=50,
            max_published_locations=5,
            max_simultaneous_offsprings=100,
            is_default=False,
        )
        async_session.add(plan)
        await async_session.flush()

        # Create a breeder user
        breeder = User(
            email=f"breeder_{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="hashed_placeholder",
            name="Test Breeder",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            is_breeder=True,
        )
        async_session.add(breeder)
        await async_session.flush()

        # Create a subscription
        now = datetime.now(timezone.utc)
        subscription = Subscription(
            user_id=breeder.id,
            plan_id=plan.id,
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        async_session.add(subscription)
        await async_session.flush()

        # Create multiple invoices with distinct created_at timestamps
        invoices = []
        for i in range(num_invoices):
            invoice = Invoice(
                subscription_id=subscription.id,
                amount=29.99,
                currency="usd",
                status="paid",
                period_start=now + timedelta(days=30 * i),
                period_end=now + timedelta(days=30 * (i + 1)),
                created_at=now + timedelta(hours=i),
            )
            async_session.add(invoice)
            invoices.append(invoice)

        await async_session.commit()

        # Override dependencies
        async def override_session():
            yield async_session

        async def override_user():
            return breeder

        app.dependency_overrides[get_async_session] = override_session
        app.dependency_overrides[current_active_user] = override_user

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/billing/invoices")

            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}"
            )

            data = response.json()
            assert len(data) >= num_invoices, (
                f"Expected at least {num_invoices} invoices, got {len(data)}"
            )

            # Assert descending created_at order for every consecutive pair
            for i in range(len(data) - 1):
                first_created = data[i]["created_at"]
                second_created = data[i + 1]["created_at"]
                assert first_created >= second_created, (
                    f"Invoice ordering violated at index {i}: "
                    f"{first_created} < {second_created}"
                )
        finally:
            app.dependency_overrides.clear()

        # Clean up
        for inv in invoices:
            await async_session.delete(inv)
        await async_session.delete(subscription)
        await async_session.delete(breeder)
        await async_session.delete(plan)
        await async_session.commit()
