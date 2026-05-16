"""Billing router for subscription management, plan listing, invoices, and Stripe webhooks."""
import logging
import uuid
from typing import List

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_session
from app.dependencies import require_breeder
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.billing import (
    CheckoutSessionResponse,
    InvoiceRead,
    PlanRead,
    PortalSessionResponse,
    SubscribeRequest,
    SubscriptionRead,
)
from app.services.billing_service import billing_service
from app.services.stripe_gateway import stripe_gateway
from app.services.billing_audit_logger import log_billing_event
from app.config import Settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/billing",
    tags=["billing"],
)


@router.get("/plans", response_model=List[PlanRead])
async def get_plans(
    session: AsyncSession = Depends(get_async_session),
) -> List[PlanRead]:
    """Return all available subscription plans. Public endpoint, no auth required."""
    plans = await billing_service.get_plans(session)
    return plans


@router.get("/subscription", response_model=SubscriptionRead)
async def get_subscription(
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> SubscriptionRead:
    """Return the authenticated breeder's current subscription with plan details."""
    subscription = await billing_service.get_subscription(session, user.id)
    return subscription


@router.post("/subscribe", response_model=SubscriptionRead)
async def subscribe(
    body: SubscribeRequest,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> SubscriptionRead:
    """Change the authenticated breeder's subscription to a different plan."""
    subscription = await billing_service.subscribe(session, user.id, body.plan_id)
    return subscription


@router.get("/invoices", response_model=List[InvoiceRead])
async def get_invoices(
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> List[InvoiceRead]:
    """Return the authenticated breeder's invoice history, ordered by created_at descending."""
    invoices = await billing_service.get_invoices(session, user.id)
    return invoices


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    body: SubscribeRequest,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> CheckoutSessionResponse:
    """Create a Stripe Checkout Session and return the redirect URL."""
    subscription = await billing_service.get_subscription(session, user.id)
    # Look up the target plan
    plans = await billing_service.get_plans(session)
    plan = next((p for p in plans if p.id == body.plan_id), None)
    if not plan:
        await log_billing_event(
            session,
            user_id=user.id,
            operation="validation_failed",
            outcome="failure",
            details=f"Plan not found for checkout, plan_id={body.plan_id}",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    checkout_url = stripe_gateway.create_checkout_session(user.id, plan, subscription)

    await log_billing_event(
        session,
        user_id=user.id,
        operation="checkout_session_created",
        outcome="success",
        details=f"Checkout session created for plan '{plan.name}'",
    )

    return CheckoutSessionResponse(checkout_url=checkout_url)


@router.post("/portal-session", response_model=PortalSessionResponse)
async def create_portal_session(
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> PortalSessionResponse:
    """Create a Stripe Customer Portal session for the authenticated breeder."""
    subscription = await billing_service.get_subscription(session, user.id)

    if not subscription.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Stripe customer found. Please complete a payment first.",
        )

    settings = Settings()
    return_url = f"{settings.frontend_url}/settings/subscription"
    portal_url = stripe_gateway.create_portal_session(
        subscription.stripe_customer_id, return_url
    )
    return PortalSessionResponse(portal_url=portal_url)


@router.get("/verify-session/{session_id}", response_model=SubscriptionRead)
async def verify_checkout_session(
    session_id: str,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> SubscriptionRead:
    """
    Verify a completed Stripe Checkout Session and apply the plan upgrade.

    Called by the frontend after Stripe redirects back with ?session_id=...
    This is the reliable fallback for when the webhook hasn't fired yet
    (e.g. dev environments without a public tunnel, or race conditions).
    """
    # Use the gateway to configure stripe (reuses the singleton settings)
    stripe_gateway._configure_stripe()

    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as e:
        logger.error("Failed to retrieve Stripe session %s: %s", session_id, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired checkout session.",
        )

    # Verify payment was successful
    if checkout_session.payment_status != "paid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment not completed for this session.",
        )

    # Verify this session belongs to the authenticated user
    metadata = checkout_session.metadata
    session_user_id = metadata["user_id"] if metadata and "user_id" in metadata else None
    if session_user_id != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to the current user.",
        )

    plan_id_str = metadata["plan_id"] if metadata and "plan_id" in metadata else None
    subscription_id_str = metadata["subscription_id"] if metadata and "subscription_id" in metadata else None

    if not plan_id_str or not subscription_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session metadata incomplete.",
        )

    result = await session.execute(
        select(Subscription)
        .options(selectinload(Subscription.plan))
        .where(Subscription.id == uuid.UUID(subscription_id_str))
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found.",
        )

    # Apply update only if not already on the correct plan (idempotent)
    target_plan_id = uuid.UUID(plan_id_str)
    if subscription.plan_id != target_plan_id or subscription.status != "active":
        subscription.plan_id = target_plan_id
        subscription.status = "active"
        subscription.stripe_customer_id = checkout_session.customer or subscription.stripe_customer_id
        subscription.stripe_subscription_id = checkout_session.subscription or subscription.stripe_subscription_id
        await session.flush()
        await session.refresh(subscription)

        await log_billing_event(
            session,
            user_id=user.id,
            operation="plan_changed",
            outcome="success",
            details=f"Plan applied via session verify, plan_id={plan_id_str}, session_id={session_id}",
        )
        logger.info(
            "Session verify: subscription %s updated to plan %s for user %s",
            subscription_id_str, plan_id_str, user.id,
        )
    else:
        logger.info(
            "Session verify: subscription %s already on correct plan %s (idempotent)",
            subscription_id_str, plan_id_str,
        )

    # Re-fetch with plan loaded to return fresh data
    result = await session.execute(
        select(Subscription)
        .options(selectinload(Subscription.plan))
        .where(Subscription.id == uuid.UUID(subscription_id_str))
    )
    return result.scalar_one()


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def webhook(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
) -> dict:
    """
    Handle Stripe webhook events.

    No auth required — signature verification replaces authentication.
    """
    payload = await request.body()

    try:
        event = stripe_gateway.verify_webhook_signature(payload, stripe_signature)
    except stripe.error.SignatureVerificationError:
        await log_billing_event(
            session,
            user_id=None,
            operation="validation_failed",
            outcome="failure",
            details="Invalid webhook signature",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )
    except ValueError:
        await log_billing_event(
            session,
            user_id=None,
            operation="validation_failed",
            outcome="failure",
            details="Invalid webhook payload",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload",
        )

    event_type = event.get("type", "")

    if event_type == "checkout.session.completed":
        await stripe_gateway.handle_checkout_completed(event, session)
    elif event_type == "invoice.paid":
        await stripe_gateway.handle_invoice_paid(event, session)
    elif event_type == "invoice.payment_failed":
        await stripe_gateway.handle_invoice_payment_failed(event, session)
    else:
        logger.warning("Unhandled webhook event type: %s", event_type)

    return {"status": "ok"}
