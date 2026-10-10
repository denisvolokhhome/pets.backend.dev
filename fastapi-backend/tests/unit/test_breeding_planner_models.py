"""Planner tables persist and cascade with their breeding."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.breeding import Breeding
from app.models.breeding_mating import BreedingMating
from app.models.breeding_milestone import BreedingMilestone
from app.models.breeding_progesterone_test import BreedingProgesteroneTest
from app.models.notification_preference import NotificationPreference


@pytest.mark.asyncio
async def test_planner_rows_cascade(async_session, test_breeding):
    assert test_breeding.stage == "Planned"
    async_session.add_all([
        BreedingMating(breeding_id=test_breeding.id, mated_on=date(2026, 9, 1), method="Natural"),
        BreedingProgesteroneTest(breeding_id=test_breeding.id, tested_on=date(2026, 8, 30),
                                 value_ng_ml=Decimal("5.20")),
        BreedingMilestone(breeding_id=test_breeding.id, key="due", title="Due date",
                          due_on=date(2026, 11, 3), remind_on=date(2026, 10, 27)),
    ])
    await async_session.commit()

    await async_session.delete(test_breeding)
    await async_session.commit()
    for model in (BreedingMating, BreedingProgesteroneTest, BreedingMilestone):
        assert (await async_session.execute(select(model))).scalars().all() == []


@pytest.mark.asyncio
async def test_breeding_reminder_preference_defaults_on(async_session, test_breeder):
    prefs = NotificationPreference(user_id=test_breeder.id)
    async_session.add(prefs)
    await async_session.commit()
    await async_session.refresh(prefs)
    assert prefs.breeding_reminder is True
