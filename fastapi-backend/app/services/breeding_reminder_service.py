"""
Breeding milestone reminders.

`run_sweep` finds milestones whose reminder date has arrived and sends each
exactly once: the milestone is claimed with a conditional UPDATE on
`reminded_at` before anything is sent, so overlapping sweeps (or several
workers) can't double-send. `start_reminder_loop` runs the sweep periodically
from the FastAPI lifespan.
"""
import asyncio
import logging
import uuid
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_maker
from app.models.breeding import Breeding
from app.models.breeding_milestone import BreedingMilestone
from app.models.breeding_pet import BreedingPet
from app.schemas.notification import NotificationCreate
from app.services.breeding_planner_rules import REMINDER_STAGES
from app.services.breeding_planner_service import breeding_label
from app.services.notification_preference_service import notification_preference_service
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE = "breeding_milestone"


def _when(due_on: date, today: date) -> str:
    days = (due_on - today).days
    if days == 0:
        return "Due today"
    if days == 1:
        return "Due tomorrow"
    if days > 1:
        return f"Due in {days} days ({due_on:%b} {due_on.day})"
    return f"Was due {due_on:%b} {due_on.day}"


async def _notify(db: AsyncSession, milestone_id: uuid.UUID, today: date) -> bool:
    """Create the notification for a claimed milestone. Returns False if the user opted out."""
    milestone = (await db.execute(
        select(BreedingMilestone)
        .where(BreedingMilestone.id == milestone_id)
        .options(
            selectinload(BreedingMilestone.breeding)
            .selectinload(Breeding.breeding_pets)
            .selectinload(BreedingPet.pet)
        )
    )).scalar_one()
    breeding = milestone.breeding
    if not await notification_preference_service.should_send_notification(
        db, breeding.user_id, NOTIFICATION_TYPE
    ):
        return False
    await notification_service.create_notification(db, NotificationCreate(
        user_id=breeding.user_id,
        type=NOTIFICATION_TYPE,
        title=f"{milestone.title} — {breeding_label(breeding)}",
        message=_when(milestone.due_on, today),
        related_id=milestone.id,
        related_type=NOTIFICATION_TYPE,
    ))
    return True


async def run_sweep(db: AsyncSession, today: date) -> int:
    """Send every reminder due on or before `today`. Returns the number of notifications created."""
    candidates = (await db.execute(
        select(BreedingMilestone.id)
        .join(Breeding, Breeding.id == BreedingMilestone.breeding_id)
        .where(
            BreedingMilestone.remind_on <= today,
            BreedingMilestone.reminded_at.is_(None),
            BreedingMilestone.completed_at.is_(None),
            Breeding.stage.in_(REMINDER_STAGES),
            Breeding.status != "Voided",
        )
        .order_by(BreedingMilestone.remind_on)
    )).scalars().all()

    sent = 0
    for milestone_id in candidates:
        try:
            claimed = (await db.execute(
                update(BreedingMilestone)
                .where(BreedingMilestone.id == milestone_id, BreedingMilestone.reminded_at.is_(None))
                .values(reminded_at=func.now())
                .returning(BreedingMilestone.id)
                .execution_options(synchronize_session=False)
            )).scalar_one_or_none()
            await db.commit()
            if claimed is None:
                continue  # another sweep got it first
            if await _notify(db, milestone_id, today):
                sent += 1
        except Exception:
            await db.rollback()
            logger.exception("Breeding reminder failed for milestone %s", milestone_id)
    return sent


async def _loop(interval_seconds: int) -> None:
    while True:
        try:
            async with async_session_maker() as db:
                sent = await run_sweep(db, date.today())
            if sent:
                logger.info("Sent %d breeding milestone reminder(s)", sent)
        except Exception:
            logger.exception("Breeding reminder sweep failed")
        await asyncio.sleep(interval_seconds)


def start_reminder_loop(interval_seconds: int) -> "asyncio.Task[None]":
    return asyncio.create_task(_loop(interval_seconds), name="breeding-reminders")


async def stop_reminder_loop(task: "asyncio.Task[None]") -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
