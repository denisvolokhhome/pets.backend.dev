"""Breeding milestone reminder sweep."""
import asyncio
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.breeding_milestone import BreedingMilestone
from app.models.notification import Notification
from app.models.notification_preference import NotificationPreference
from app.schemas.breeding_planner import MatingCreate, MilestoneCreate, PlannerUpdate
from app.services.notification_service import notification_service
from app.services import email_service as email_module
from app.services.breeding_planner_service import breeding_planner_service as svc
from app.services.breeding_reminder_service import run_sweep

MATED = date(2026, 9, 1)
ULTRASOUND_REMIND = MATED + timedelta(days=26)


@pytest.fixture
def sent_emails(monkeypatch):
    sent = []

    async def fake_send_email(self, to, subject, html, text=None):
        sent.append({"to": to, "subject": subject, "html": html})
        return True

    monkeypatch.setattr(email_module.EmailService, "send_email", fake_send_email)
    return sent


async def _mated(async_session, breeder, breeding):
    await svc.add_mating(async_session, breeding.id, breeder,
                         MatingCreate(mated_on=MATED, method="Natural"), MATED)


async def _notifications(async_session):
    return (await async_session.execute(select(Notification))).scalars().all()


@pytest.mark.asyncio
async def test_sweep_sends_due_reminder_and_email(async_session, test_breeder, test_breeding, sent_emails):
    await _mated(async_session, test_breeder, test_breeding)
    assert await run_sweep(async_session, ULTRASOUND_REMIND - timedelta(days=1)) == 0
    assert await run_sweep(async_session, ULTRASOUND_REMIND) == 1
    [n] = await _notifications(async_session)
    assert n.type == "breeding_milestone" and n.related_type == "breeding_milestone"
    assert n.title.startswith("Ultrasound")
    await asyncio.sleep(0.1)
    assert len(sent_emails) == 1 and "/milestones/" in sent_emails[0]["html"]


@pytest.mark.asyncio
async def test_sweep_is_idempotent(async_session, test_breeder, test_breeding, sent_emails):
    await _mated(async_session, test_breeder, test_breeding)
    assert await run_sweep(async_session, ULTRASOUND_REMIND) == 1
    assert await run_sweep(async_session, ULTRASOUND_REMIND) == 0
    assert len(await _notifications(async_session)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["voided", "missed", "completed", "whelped"])
async def test_sweep_skips_inactive_breedings(async_session, test_breeder, test_breeding, sent_emails, change):
    await _mated(async_session, test_breeder, test_breeding)
    if change == "voided":
        test_breeding.status = "Voided"
    elif change == "whelped":
        test_breeding.stage = "Whelped"
    elif change == "missed":
        await svc.update_planner(async_session, test_breeding.id, test_breeder, PlannerUpdate(stage="Missed"), MATED)
    else:
        for m in (await async_session.execute(select(BreedingMilestone))).scalars():
            from datetime import datetime, timezone
            m.completed_at = datetime.now(timezone.utc)
    await async_session.commit()
    assert await run_sweep(async_session, ULTRASOUND_REMIND) == 0


@pytest.mark.asyncio
async def test_preference_off_suppresses_but_claims(async_session, test_breeder, test_breeding, sent_emails):
    async_session.add(NotificationPreference(user_id=test_breeder.id, breeding_reminder=False))
    await async_session.commit()
    await _mated(async_session, test_breeder, test_breeding)
    assert await run_sweep(async_session, ULTRASOUND_REMIND) == 0
    assert await _notifications(async_session) == []
    milestone = (await async_session.execute(
        select(BreedingMilestone).where(BreedingMilestone.key == "ultrasound")
        .execution_options(populate_existing=True))).scalar_one()
    assert milestone.reminded_at is not None


@pytest.mark.asyncio
async def test_backdated_pregnancy_does_not_burst_past_reminders(async_session, test_breeder, test_breeding, sent_emails):
    """Onboarding a dam mated 60 days ago reminds only about what's still ahead."""
    today = MATED + timedelta(days=60)  # ultrasound, X-ray, box and temperature are all in the past
    await svc.add_mating(async_session, test_breeding.id, test_breeder,
                         MatingCreate(mated_on=MATED, method="Natural"), today)
    assert await run_sweep(async_session, today) == 1
    [n] = await _notifications(async_session)
    assert n.title.startswith("Due date")
    # the past ones are consumed silently, not left to fire later
    assert await run_sweep(async_session, today) == 0


@pytest.mark.asyncio
async def test_long_titles_are_truncated_not_dropped(async_session, test_breeder, test_breeding, sent_emails):
    await _mated(async_session, test_breeder, test_breeding)
    await svc.add_milestone(async_session, test_breeding.id, test_breeder,
                            MilestoneCreate(title="V" * 255, due_on=ULTRASOUND_REMIND, remind_on=ULTRASOUND_REMIND), MATED)
    await run_sweep(async_session, ULTRASOUND_REMIND)
    titles = [n.title for n in await _notifications(async_session)]
    assert any(t.startswith("VVV") for t in titles)
    assert all(len(t) <= 255 for t in titles)


@pytest.mark.asyncio
async def test_failed_notification_releases_claim_and_others_still_send(
    async_session, test_breeder, test_breeding, sent_emails, monkeypatch
):
    await _mated(async_session, test_breeder, test_breeding)
    await svc.add_milestone(async_session, test_breeding.id, test_breeder,
                            MilestoneCreate(title="Vet check", due_on=ULTRASOUND_REMIND, remind_on=ULTRASOUND_REMIND), MATED)
    original = notification_service.create_notification
    calls = {"n": 0}

    async def flaky(db, data):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("smtp down")
        return await original(db, data)

    monkeypatch.setattr(notification_service, "create_notification", flaky)
    assert await run_sweep(async_session, ULTRASOUND_REMIND) == 1      # second milestone still sent
    monkeypatch.setattr(notification_service, "create_notification", original)
    assert await run_sweep(async_session, ULTRASOUND_REMIND) == 1      # first one retried, not lost
    assert len(await _notifications(async_session)) == 2
