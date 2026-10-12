"""Waitlist tables persist, cascade and enforce one active entry per person per breeder."""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.waitlist_entry import WaitlistEntry
from app.models.waitlist_event import WaitlistEvent


@pytest.mark.asyncio
async def test_entry_with_events_round_trips(async_session, test_breeder, test_pet_seeker):
    entry = WaitlistEntry(breeder_id=test_breeder.id, user_id=test_pet_seeker.id, source="request",
                          status="pending", sex_preference="Any", deposit_status="none")
    entry.events.append(WaitlistEvent(type="requested", actor_id=test_pet_seeker.id, payload={}))
    async_session.add(entry)
    await async_session.commit()
    await async_session.refresh(entry)
    assert entry.breeding_id is None and len(entry.events) == 1


@pytest.mark.asyncio
async def test_one_active_entry_per_seeker_per_breeder(async_session, test_breeder, test_pet_seeker):
    for _ in range(2):
        async_session.add(WaitlistEntry(breeder_id=test_breeder.id, user_id=test_pet_seeker.id, source="request",
                                        status="active", sex_preference="Any", deposit_status="none",
                                        queue_date=date(2026, 10, 1)))
    with pytest.raises(IntegrityError):
        await async_session.commit()
