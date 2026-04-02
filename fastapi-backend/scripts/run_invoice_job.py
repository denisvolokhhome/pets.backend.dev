"""
Standalone invoice generation job script.

Creates its own async SQLAlchemy engine and session, calls
billing_service.generate_invoices(), and logs a summary of results.

Intended to be run via cron daily at a configurable time (default 00:00 UTC).

Usage:
    python scripts/run_invoice_job.py

Environment variables:
    INVOICE_JOB_RUN_TIME  - Scheduled run time in HH:MM format (default: "00:00")
                            Logged for operational visibility; actual scheduling
                            is handled by the external cron/scheduler.
"""

import asyncio
import logging
import os
import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.services.billing_service import billing_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("invoice_job")


async def run_invoice_generation() -> None:
    """Create an async engine/session and run invoice generation."""
    settings = Settings()

    run_time = os.environ.get("INVOICE_JOB_RUN_TIME", "00:00")
    logger.info("Invoice job started (configured run time: %s UTC)", run_time)

    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with session_factory() as session:
            async with session.begin():
                summary = await billing_service.generate_invoices(session)

            logger.info(
                "Invoice job completed — total_processed: %d, successful: %d, failed: %d",
                summary["total_processed"],
                summary["successful"],
                summary["failed"],
            )
    except Exception:
        logger.exception("Invoice job failed due to a database connection or runtime error")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_invoice_generation())
