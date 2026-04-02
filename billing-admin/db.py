"""Database connection module for the Billing Admin Dashboard."""

import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/breedly")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def mask_stripe_id(identifier: Optional[str]) -> Optional[str]:
    """Mask a Stripe identifier so the dashboard never displays the full value.

    Keeps the prefix (e.g. ``cus_``, ``sub_``, ``in_``) and the last 3
    characters, replacing everything in between with ``***``.

    Examples:
        >>> mask_stripe_id("cus_abc123xyz")
        'cus_***xyz'
        >>> mask_stripe_id(None)
        >>> mask_stripe_id("")
        ''

    Short identifiers (where the body after the prefix is 3 characters or
    fewer) are returned with the body fully replaced by ``***`` to avoid
    leaking the entire value.
    """
    if identifier is None:
        return None
    if identifier == "":
        return ""

    # Detect prefix (everything up to and including the first underscore)
    underscore_idx = identifier.find("_")
    if underscore_idx == -1:
        # No prefix — mask all but last 3 chars
        if len(identifier) <= 3:
            return "***"
        return "***" + identifier[-3:]

    prefix = identifier[: underscore_idx + 1]  # e.g. "cus_"
    body = identifier[underscore_idx + 1 :]     # e.g. "abc123xyz"

    if len(body) <= 3:
        # Body too short to safely reveal suffix — mask entirely
        return prefix + "***"

    return prefix + "***" + body[-3:]


def get_breeder_billing_table(plan_filter=None, status_filter=None):
    """Return a DataFrame of breeder billing info, optionally filtered by plan and status.

    Columns: email, breedery_name, plan_name, subscription_status,
             stripe_customer_id (masked), last_invoice_date
    """
    query = text("""
        SELECT
            u.email,
            u.breedery_name,
            p.name AS plan_name,
            s.status AS subscription_status,
            s.stripe_customer_id,
            MAX(i.created_at) AS last_invoice_date
        FROM users u
        INNER JOIN subscriptions s ON s.user_id = u.id
        INNER JOIN plans p ON p.id = s.plan_id
        LEFT JOIN invoices i ON i.subscription_id = s.id
        WHERE u.is_breeder = true
            AND (:plan_filter IS NULL OR p.name = :plan_filter)
            AND (:status_filter IS NULL OR s.status = :status_filter)
        GROUP BY u.email, u.breedery_name, p.name, s.status, s.stripe_customer_id
        ORDER BY u.email
    """)

    with engine.connect() as conn:
        result = conn.execute(
            query,
            {"plan_filter": plan_filter, "status_filter": status_filter},
        )
        rows = result.fetchall()
        columns = [
            "email", "breedery_name", "plan_name", "subscription_status",
            "stripe_customer_id", "last_invoice_date",
        ]
        df = pd.DataFrame(rows, columns=columns)

    # Mask Stripe identifiers — never display full decrypted IDs
    if not df.empty and "stripe_customer_id" in df.columns:
        df["stripe_customer_id"] = df["stripe_customer_id"].apply(mask_stripe_id)

    return df


def get_invoices_for_breeder(user_id):
    """Return a DataFrame of invoices for a specific breeder.

    Columns: date, amount, status, period_start, period_end, stripe_invoice_id (masked)
    """
    query = text("""
        SELECT
            i.created_at AS date,
            i.amount,
            i.status,
            i.period_start,
            i.period_end,
            i.stripe_invoice_id
        FROM invoices i
        INNER JOIN subscriptions s ON s.id = i.subscription_id
        WHERE s.user_id = :user_id
        ORDER BY i.created_at DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {"user_id": user_id})
        rows = result.fetchall()
        columns = ["date", "amount", "status", "period_start", "period_end", "stripe_invoice_id"]
        df = pd.DataFrame(rows, columns=columns)

    # Mask Stripe identifiers — never display full decrypted IDs
    if not df.empty and "stripe_invoice_id" in df.columns:
        df["stripe_invoice_id"] = df["stripe_invoice_id"].apply(mask_stripe_id)

    return df


def get_summary_metrics():
    """Return a dict of summary billing metrics.

    Keys:
        total_active_subscriptions: int
        subscriptions_by_plan: dict mapping plan name -> count
        total_revenue: float
        overdue_invoices_count: int
    """
    with engine.connect() as conn:
        # Total active subscriptions
        total_active = conn.execute(
            text("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'")
        ).scalar() or 0

        # Subscriptions by plan
        rows = conn.execute(
            text("""
                SELECT p.name, COUNT(*) AS cnt
                FROM subscriptions s
                INNER JOIN plans p ON p.id = s.plan_id
                WHERE s.status = 'active'
                GROUP BY p.name
                ORDER BY p.name
            """)
        ).fetchall()
        subscriptions_by_plan = {row[0]: row[1] for row in rows}

        # Total revenue (sum of paid invoices)
        total_revenue = conn.execute(
            text("SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE status = 'paid'")
        ).scalar()
        total_revenue = float(total_revenue)

        # Overdue invoices: pending or failed invoices past their period end
        overdue_count = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM invoices
                WHERE status IN ('failed', 'pending')
                  AND period_end <= :now
            """),
            {"now": datetime.now(timezone.utc)},
        ).scalar() or 0

    return {
        "total_active_subscriptions": total_active,
        "subscriptions_by_plan": subscriptions_by_plan,
        "total_revenue": total_revenue,
        "overdue_invoices_count": overdue_count,
    }
