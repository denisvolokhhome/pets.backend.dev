"""Stripe gateway service for payment processing integration."""
import logging
import uuid
from typing import Any

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.invoice import Invoice
from app.models.subscription import Subscription
from app.services.billing_audit_logger import log_billing_event

logger = logging.getLogger(__name__)


class StripeGateway:
    """Service for Stripe API interactions: customers, checkout sessions, and webhook handling."""

    def __init__(self) -> None:
        self._settings: Settings | None = None

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = Settings()
        return self._settings

    def _configure_stripe(self) -> None:
        """Set the Stripe API key from application settings."""
        stripe.api_key = self.settings.stripe_api_key

    def create_customer(self, email: str, user_id: uuid.UUID) -> stripe.Customer:
        """
        Create a Stripe Customer linked to a breeder.

        Args:
            email: Breeder's email address
            user_id: Breeder's UUID

        Returns:
            The created Stripe Customer object
        """
        self._configure_stripe()
        customer = stripe.Customer.create(
            email=email,
            metadata={"user_id": str(user_id)},
        )
        logger.info("Created Stripe customer %s for user %s", customer.id, user_id)
        return customer

    def create_checkout_session(
        self,
        user_id: uuid.UUID,
        plan: Any,
        subscription: Any,
    ) -> str:
        """
        Create a Stripe Checkout Session for a plan subscription.

        Args:
            user_id: Breeder's UUID
            plan: Plan model instance with name, price, currency, billing_interval
            subscription: Subscription model instance

        Returns:
            The checkout session URL for frontend redirect
        """
        self._configure_stripe()
        frontend_url = self.settings.frontend_url

        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": plan.currency,
                        "unit_amount": int(plan.price * 100),
                        "product_data": {"name": plan.name},
                        "recurring": {"interval": plan.billing_interval},
                    },
                    "quantity": 1,
                },
            ],
            success_url=f"{frontend_url}/settings/subscription?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{frontend_url}/settings/subscription?canceled=true",
            metadata={
                "user_id": str(user_id),
                "plan_id": str(plan.id),
                "subscription_id": str(subscription.id),
            },
            customer=subscription.stripe_customer_id if subscription.stripe_customer_id else None,
        )
        logger.info(
            "Created checkout session %s for user %s, plan %s",
            session.id, user_id, plan.name,
        )
        return session.url

    async def handle_checkout_completed(
        self, event: dict, session: AsyncSession
    ) -> None:
        """
        Handle a checkout.session.completed webhook event.

        Updates the subscription status to "active" and stores the Stripe
        customer and subscription identifiers.

        Args:
            event: The Stripe webhook event payload
            session: Async database session
        """
        checkout_session = event["data"]["object"]
        subscription_id = checkout_session["metadata"].get("subscription_id")

        if not subscription_id:
            logger.error("checkout.session.completed missing subscription_id in metadata")
            return

        result = await session.execute(
            select(Subscription).where(Subscription.id == uuid.UUID(subscription_id))
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            logger.error("Subscription %s not found for checkout completed", subscription_id)
            return

        # Update plan_id from metadata — this is the authoritative moment to apply the plan change
        plan_id_str = checkout_session["metadata"].get("plan_id")
        if plan_id_str:
            subscription.plan_id = uuid.UUID(plan_id_str)
        else:
            logger.warning("checkout.session.completed missing plan_id in metadata for subscription %s", subscription_id)

        subscription.status = "active"
        subscription.stripe_customer_id = checkout_session.get("customer")
        subscription.stripe_subscription_id = checkout_session.get("subscription")
        await session.flush()

        user_id_str = checkout_session["metadata"].get("user_id")
        await log_billing_event(
            session,
            user_id=uuid.UUID(user_id_str) if user_id_str else None,
            operation="webhook_processed",
            outcome="success",
            details="checkout.session.completed, subscription activated",
        )

        logger.info(
            "Checkout completed: subscription %s activated to plan %s, customer %s",
            subscription_id, plan_id_str, checkout_session.get("customer"),
        )

    async def handle_invoice_paid(self, event: dict, session: AsyncSession) -> None:
        """
        Handle an invoice.paid webhook event.

        Marks the corresponding Invoice as "paid".

        Because stripe_invoice_id is stored with AES-256-GCM encryption using
        a random nonce, we cannot perform equality comparisons at the SQL level.
        Instead, we load candidate invoices (status "pending") and match by
        comparing the decrypted stripe_invoice_id in Python.

        Args:
            event: The Stripe webhook event payload
            session: Async database session
        """
        stripe_invoice = event["data"]["object"]
        stripe_invoice_id = stripe_invoice.get("id")

        if not stripe_invoice_id:
            logger.error("invoice.paid event missing invoice id")
            return

        # Load candidate invoices and match by decrypted stripe_invoice_id
        result = await session.execute(
            select(Invoice).where(Invoice.status.in_(["pending"]))
        )
        candidates = result.scalars().all()
        invoice = next(
            (inv for inv in candidates if inv.stripe_invoice_id == stripe_invoice_id),
            None,
        )

        if not invoice:
            logger.warning("Invoice with stripe_invoice_id %s not found", stripe_invoice_id)
            return

        invoice.status = "paid"
        await session.flush()

        await log_billing_event(
            session,
            user_id=None,
            operation="payment_received",
            outcome="success",
            details=f"invoice.paid, invoice_id={invoice.id}",
        )

        logger.info("Invoice %s marked as paid (stripe: %s)", invoice.id, stripe_invoice_id)

    async def handle_invoice_payment_failed(
        self, event: dict, session: AsyncSession
    ) -> None:
        """
        Handle an invoice.payment_failed webhook event.

        Marks the Invoice as "failed" and sets the associated Subscription
        status to "past_due".

        Because stripe_invoice_id is stored with AES-256-GCM encryption using
        a random nonce, we cannot perform equality comparisons at the SQL level.
        Instead, we load candidate invoices (status "pending" or "failed") and
        match by comparing the decrypted stripe_invoice_id in Python.

        Args:
            event: The Stripe webhook event payload
            session: Async database session
        """
        stripe_invoice = event["data"]["object"]
        stripe_invoice_id = stripe_invoice.get("id")

        if not stripe_invoice_id:
            logger.error("invoice.payment_failed event missing invoice id")
            return

        # Load candidate invoices and match by decrypted stripe_invoice_id
        result = await session.execute(
            select(Invoice).where(Invoice.status.in_(["pending", "failed"]))
        )
        candidates = result.scalars().all()
        invoice = next(
            (inv for inv in candidates if inv.stripe_invoice_id == stripe_invoice_id),
            None,
        )

        if not invoice:
            logger.warning("Invoice with stripe_invoice_id %s not found", stripe_invoice_id)
            return

        invoice.status = "failed"
        await session.flush()

        # Also mark the subscription as past_due
        sub_result = await session.execute(
            select(Subscription).where(Subscription.id == invoice.subscription_id)
        )
        subscription = sub_result.scalar_one_or_none()

        if subscription:
            subscription.status = "past_due"
            await session.flush()
            logger.info(
                "Invoice %s failed, subscription %s set to past_due",
                invoice.id, subscription.id,
            )
        else:
            logger.error(
                "Subscription %s not found for failed invoice %s",
                invoice.subscription_id, invoice.id,
            )

        await log_billing_event(
            session,
            user_id=None,
            operation="payment_failed",
            outcome="failure",
            details=f"invoice.payment_failed, invoice_id={invoice.id}",
        )

    def verify_webhook_signature(self, payload: bytes, sig_header: str) -> dict:
        """
        Verify a Stripe webhook signature and construct the event.

        Security: Uses ``stripe.Webhook.construct_event`` which internally
        performs HMAC-SHA256 signature verification with a timing-safe
        comparison (``hmac.compare_digest``). This prevents timing attacks
        on the webhook signature verification process.

        See: https://github.com/stripe/stripe-python — ``WebhookSignature.verify_header``
        uses ``hmac.compare_digest`` for constant-time signature comparison.

        Requirement 11.9: Webhook signatures are verified using HMAC-SHA256
        with timing-safe comparison to prevent timing attacks.

        Args:
            payload: Raw request body bytes
            sig_header: Stripe-Signature header value

        Returns:
            The verified Stripe event dict

        Raises:
            stripe.error.SignatureVerificationError: If signature is invalid
            ValueError: If payload is invalid
        """
        self._configure_stripe()
        # The Stripe SDK's construct_event → WebhookSignature.verify_header
        # uses hmac.compare_digest for timing-safe signature comparison,
        # satisfying the HMAC-SHA256 timing-safe requirement (Req 11.9).
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            self.settings.stripe_webhook_secret,
        )
        return event


# Singleton instance
stripe_gateway = StripeGateway()
