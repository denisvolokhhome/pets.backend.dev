"""Billing router for subscription management, plan listing, invoices, and Stripe webhooks."""
import logging
from typing import List

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_breeder
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
