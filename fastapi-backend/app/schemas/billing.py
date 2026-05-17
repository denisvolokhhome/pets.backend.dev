"""Billing schemas for subscription, plan, and invoice API validation."""
from datetime import datetime
from decimal import Decimal
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict


class PlanRead(BaseModel):
    """Schema for reading plan data with usage limits."""
    id: uuid.UUID
    name: str
    price: Decimal
    currency: str
    billing_interval: str
    max_pets: int
    max_published_locations: int
    max_simultaneous_offsprings: int
    is_default: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SubscriptionRead(BaseModel):
    """Schema for reading subscription data with nested plan."""
    id: uuid.UUID
    user_id: uuid.UUID
    plan_id: uuid.UUID
    status: str
    current_period_start: datetime
    current_period_end: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None
    plan: PlanRead
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    pending_plan_id: Optional[uuid.UUID] = None
    pending_plan_effective_date: Optional[datetime] = None
    pending_plan: Optional[PlanRead] = None

    model_config = ConfigDict(from_attributes=True)


class SubscribeRequest(BaseModel):
    """Schema for subscribing to a plan."""
    plan_id: uuid.UUID


class InvoiceRead(BaseModel):
    """Schema for reading invoice data."""
    id: uuid.UUID
    subscription_id: uuid.UUID
    amount: Decimal
    currency: str
    status: str
    period_start: datetime
    period_end: datetime
    stripe_invoice_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CheckoutSessionResponse(BaseModel):
    """Schema for Stripe checkout session redirect URL."""
    checkout_url: str


class PortalSessionResponse(BaseModel):
    """Schema for Stripe customer portal session redirect URL."""
    portal_url: str
