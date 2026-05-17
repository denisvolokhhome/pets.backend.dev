"""Billing service for subscription management, invoice generation, and usage limit enforcement."""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.invoice import Invoice
from app.models.location import Location
from app.models.offspring import Offspring
from app.models.pet import Pet
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_audit_logger import log_billing_event

logger = logging.getLogger(__name__)


class BillingService:
    """Service for billing operations: plans, subscriptions, invoices, and usage limits."""

    async def get_plans(self, session: AsyncSession) -> List[Plan]:
        """
        Retrieve all available subscription plans.

        Args:
            session: Async database session

        Returns:
            List of all Plan records
        """
        result = await session.execute(select(Plan))
        return list(result.scalars().all())

    async def get_subscription(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> Subscription:
        """
        Retrieve the current subscription for a user, with the associated plan eagerly loaded.

        Args:
            session: Async database session
            user_id: UUID of the breeder

        Returns:
            The user's Subscription with nested Plan

        Raises:
            HTTPException: 404 if no subscription found
        """
        result = await session.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active subscription found",
            )

        # Apply pending plan if its effective date has passed
        now = datetime.now(timezone.utc)
        if (
            subscription.pending_plan_id is not None
            and subscription.pending_plan_effective_date is not None
            and subscription.pending_plan_effective_date <= now
        ):
            subscription.plan_id = subscription.pending_plan_id
            subscription.pending_plan_id = None
            subscription.pending_plan_effective_date = None
            subscription.updated_at = now
            await session.flush()
            await session.refresh(subscription)
            logger.info(
                "Applied pending plan for subscription %s at %s",
                subscription.id, now.isoformat(),
            )

        return subscription

    async def subscribe(
        self, session: AsyncSession, user_id: uuid.UUID, plan_id: uuid.UUID
    ) -> Subscription:
        """
        Change a breeder's subscription to a different plan.

        For downgrades (moving to a cheaper/lower plan), validates that the
        breeder's current usage fits within the target plan's limits before
        allowing the change.

        Args:
            session: Async database session
            user_id: UUID of the breeder
            plan_id: UUID of the target plan

        Returns:
            Updated Subscription

        Raises:
            HTTPException: 404 if plan not found, 404 if no subscription,
                           400 if already on the requested plan,
                           422 if current usage exceeds target plan limits
        """
        # Verify the target plan exists
        plan_result = await session.execute(
            select(Plan).where(Plan.id == plan_id)
        )
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found",
            )

        # Get the user's current subscription
        subscription = await self.get_subscription(session, user_id)

        if subscription.plan_id == plan_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already subscribed to this plan",
            )

        # Downgrade validation: check current usage fits within target plan limits
        is_downgrade = plan.price < subscription.plan.price if subscription.plan else False
        if is_downgrade:
            violations = []

            # Check pet count
            pet_count_result = await session.execute(
                select(func.count(Pet.id)).where(
                    Pet.user_id == user_id,
                    Pet.is_deleted == False,  # noqa: E712
                )
            )
            pet_count = pet_count_result.scalar_one()
            if pet_count > plan.max_pets:
                violations.append(
                    f"You have {pet_count} pets but the {plan.name} plan allows {plan.max_pets}. "
                    f"Please remove {pet_count - plan.max_pets} pet(s) before downgrading."
                )

            # Check published locations
            loc_count_result = await session.execute(
                select(func.count(Location.id)).where(
                    Location.user_id == user_id,
                    Location.is_published == True,  # noqa: E712
                )
            )
            loc_count = loc_count_result.scalar_one()
            if loc_count > plan.max_published_locations:
                violations.append(
                    f"You have {loc_count} published location(s) but the {plan.name} plan allows "
                    f"{plan.max_published_locations}. Please unpublish "
                    f"{loc_count - plan.max_published_locations} location(s) before downgrading."
                )

            # Check simultaneous offsprings (Available + Reserved)
            offspring_count_result = await session.execute(
                select(func.count(Offspring.id)).where(
                    Offspring.user_id == user_id,
                    Offspring.status.in_(["Available", "Reserved"]),
                )
            )
            offspring_count = offspring_count_result.scalar_one()
            if offspring_count > plan.max_simultaneous_offsprings:
                violations.append(
                    f"You have {offspring_count} active offspring(s) but the {plan.name} plan allows "
                    f"{plan.max_simultaneous_offsprings}. Please archive or sell "
                    f"{offspring_count - plan.max_simultaneous_offsprings} offspring(s) before downgrading."
                )

            if violations:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"message": "Cannot downgrade: usage exceeds target plan limits.", "violations": violations},
                )

            # Schedule the downgrade for end of current billing period (grace period)
            subscription.pending_plan_id = plan_id
            subscription.pending_plan_effective_date = subscription.current_period_end
            subscription.updated_at = datetime.now(timezone.utc)

            await session.flush()
            await session.refresh(subscription)

            await log_billing_event(
                session,
                user_id=user_id,
                operation="plan_downgrade_scheduled",
                outcome="success",
                details=f"Downgrade to plan '{plan.name}' scheduled for {subscription.current_period_end.isoformat()}",
            )

            return subscription

        # Upgrade (or same-tier switch): apply immediately
        # Also clear any pending downgrade if upgrading
        now = datetime.now(timezone.utc)
        subscription.plan_id = plan_id
        subscription.pending_plan_id = None
        subscription.pending_plan_effective_date = None
        subscription.current_period_start = now
        subscription.current_period_end = now + timedelta(days=30)
        subscription.updated_at = now

        await session.flush()
        await session.refresh(subscription)

        await log_billing_event(
            session,
            user_id=user_id,
            operation="plan_changed",
            outcome="success",
            details=f"Upgraded to plan '{plan.name}', plan_id={plan_id}",
        )

        return subscription

    async def create_default_subscription(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> Subscription:
        """
        Create a default FREE plan subscription for a new breeder.

        Args:
            session: Async database session
            user_id: UUID of the new breeder

        Returns:
            Newly created Subscription with the FREE plan

        Raises:
            HTTPException: 500 if no default FREE plan exists
        """
        # Find the default FREE plan
        result = await session.execute(
            select(Plan).where(Plan.is_default == True)  # noqa: E712
        )
        free_plan = result.scalar_one_or_none()

        if not free_plan:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Default plan not configured",
            )

        now = datetime.now(timezone.utc)
        subscription = Subscription(
            user_id=user_id,
            plan_id=free_plan.id,
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        session.add(subscription)
        await session.flush()
        await session.refresh(subscription)

        await log_billing_event(
            session,
            user_id=user_id,
            operation="subscription_created",
            outcome="success",
            details=f"Default FREE plan assigned, plan_id={free_plan.id}",
        )

        return subscription

    async def get_invoices(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> List[Invoice]:
        """
        Retrieve invoice history for a breeder, ordered by created_at descending.

        Finds the user's subscription first, then fetches all invoices for it.

        Args:
            session: Async database session
            user_id: UUID of the breeder

        Returns:
            List of Invoice records ordered by created_at desc
        """
        # Get subscription ids for this user
        sub_result = await session.execute(
            select(Subscription.id).where(Subscription.user_id == user_id)
        )
        subscription_ids = list(sub_result.scalars().all())

        if not subscription_ids:
            return []

        result = await session.execute(
            select(Invoice)
            .where(Invoice.subscription_id.in_(subscription_ids))
            .order_by(Invoice.created_at.desc())
        )
        return list(result.scalars().all())

    async def generate_invoices(self, session: AsyncSession) -> dict:
        """
        Generate invoices for all active subscriptions whose billing period has ended.

        For FREE plan invoices (price == 0): marks as "paid" immediately and advances
        the billing period by 30 days.
        For paid plan invoices (price > 0): marks as "pending".

        Errors on individual subscriptions are logged and processing continues.

        Args:
            session: Async database session

        Returns:
            Summary dict with total_processed, successful, and failed counts
        """
        now = datetime.now(timezone.utc)

        # Find all active subscriptions due for invoicing
        result = await session.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(
                Subscription.status == "active",
                Subscription.current_period_end <= now,
            )
        )
        due_subscriptions = list(result.scalars().all())

        total = len(due_subscriptions)
        successful = 0
        failed = 0

        for sub in due_subscriptions:
            try:
                plan = sub.plan
                invoice = Invoice(
                    subscription_id=sub.id,
                    amount=plan.price,
                    currency=plan.currency,
                    period_start=sub.current_period_start,
                    period_end=sub.current_period_end,
                )

                if plan.price == 0:
                    # FREE plan: mark paid immediately and advance period
                    invoice.status = "paid"
                    sub.current_period_start = sub.current_period_end
                    sub.current_period_end = sub.current_period_end + timedelta(days=30)
                else:
                    # Paid plan: mark as pending
                    invoice.status = "pending"

                session.add(invoice)
                await session.flush()
                successful += 1

            except Exception:
                failed += 1
                logger.exception(
                    "Error generating invoice for subscription %s", sub.id
                )
                await log_billing_event(
                    session,
                    user_id=sub.user_id,
                    operation="payment_failed",
                    outcome="failure",
                    details=f"Invoice generation error for subscription_id={sub.id}",
                )
                continue

        summary = {
            "total_processed": total,
            "successful": successful,
            "failed": failed,
        }
        logger.info("Invoice generation complete: %s", summary)
        return summary

    async def check_usage(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        resource_type: str,
    ) -> None:
        """
        Check whether a breeder is within their plan's usage limits for a resource type.

        For non-active subscriptions (canceled, past_due), falls back to the FREE
        plan limits regardless of the plan referenced by the subscription.

        Args:
            session: Async database session
            user_id: UUID of the breeder
            resource_type: One of "pets", "locations", "offsprings"

        Raises:
            HTTPException: 403 with USAGE_LIMIT_EXCEEDED if at or above limit
        """
        # Get the user's subscription
        sub_result = await session.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        subscription = sub_result.scalar_one_or_none()

        # Determine effective plan limits
        if subscription and subscription.status == "active":
            plan = subscription.plan
        else:
            # Fall back to FREE plan for non-active or missing subscriptions
            free_result = await session.execute(
                select(Plan).where(Plan.is_default == True)  # noqa: E712
            )
            plan = free_result.scalar_one_or_none()
            if not plan:
                # No default plan configured — allow the operation
                return

        # Count current usage and compare against limit
        if resource_type == "pets":
            count_result = await session.execute(
                select(func.count(Pet.id)).where(
                    Pet.user_id == user_id,
                    Pet.is_deleted == False,  # noqa: E712
                )
            )
            current_count = count_result.scalar_one()
            limit = plan.max_pets
            message = f"Pet limit reached. Your plan allows {limit} pets."

        elif resource_type == "locations":
            count_result = await session.execute(
                select(func.count(Location.id)).where(
                    Location.user_id == user_id,
                    Location.is_published == True,  # noqa: E712
                )
            )
            current_count = count_result.scalar_one()
            limit = plan.max_published_locations
            message = f"Published location limit reached. Your plan allows {limit} locations."

        elif resource_type == "offsprings":
            count_result = await session.execute(
                select(func.count(Offspring.id)).where(
                    Offspring.user_id == user_id,
                    Offspring.status.in_(["Available", "Reserved"]),
                )
            )
            current_count = count_result.scalar_one()
            limit = plan.max_simultaneous_offsprings
            message = f"Offspring limit reached. Your plan allows {limit} simultaneous offsprings."

        else:
            raise ValueError(f"Unknown resource type: {resource_type}")

        if current_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message,
                headers={"X-Error-Code": "USAGE_LIMIT_EXCEEDED"},
            )


# Singleton instance
billing_service = BillingService()
