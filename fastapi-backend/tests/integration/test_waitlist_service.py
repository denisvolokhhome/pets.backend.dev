"""WaitlistService: requests, manual entries, approval, deposits, ordering."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.breeding_application_form import BreedingApplicationForm
from app.models.user import User
from app.schemas.waitlist import (
    DepositUpdate,
    ManualEntryCreate,
    WaitlistRequestCreate,
    WaitlistSettingsUpdate,
)
from app.services.waitlist_service import waitlist_service as svc

TODAY = date(2026, 10, 11)


@pytest.fixture
async def seeker(async_session, test_pet_seeker):
    test_pet_seeker.account_type = "pet_seeker"
    await async_session.commit()
    return test_pet_seeker


async def _other_seeker(db, email="second@example.com"):
    u = User(email=email, hashed_password="x", name="Second Seeker", is_active=True, account_type="pet_seeker")
    db.add(u)
    await db.commit()
    return u


@pytest.mark.asyncio
async def test_request_creates_pending_entry_with_breeder_deposit(async_session, test_breeder, seeker):
    await svc.update_settings(async_session, test_breeder,
                              WaitlistSettingsUpdate(deposit_amount=Decimal("300"), deposit_policy="Non-refundable"))
    mine = await svc.request_spot(async_session, test_breeder.id, seeker,
                                  WaitlistRequestCreate(sex_preference="Female"), TODAY)
    assert mine.status == "pending" and mine.deposit_status == "requested"
    assert mine.deposit_amount == Decimal("300.00")
    lists = await svc.list_breeder(async_session, test_breeder)
    assert [e.display_name for e in lists.pending] == ["Test Seeker"]


@pytest.mark.asyncio
async def test_duplicate_request_is_409(async_session, test_breeder, seeker):
    await svc.request_spot(async_session, test_breeder.id, seeker, WaitlistRequestCreate(), TODAY)
    with pytest.raises(HTTPException) as exc:
        await svc.request_spot(async_session, test_breeder.id, seeker, WaitlistRequestCreate(), TODAY)
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "WAITLIST_DUPLICATE"


@pytest.mark.asyncio
async def test_required_application_answers_enforced(async_session, test_breeder, seeker, test_breeding):
    async_session.add(BreedingApplicationForm(breeding_id=test_breeding.id, user_id=test_breeder.id, form_fields=[
        {"id": "f1", "type": "text", "label": "Fenced yard?", "required": True}]))
    await async_session.commit()
    with pytest.raises(HTTPException) as exc:
        await svc.request_spot(async_session, test_breeder.id, seeker,
                               WaitlistRequestCreate(request_breeding_id=test_breeding.id), TODAY)
    assert exc.value.status_code == 422
    ok = await svc.request_spot(async_session, test_breeder.id, seeker, WaitlistRequestCreate(
        request_breeding_id=test_breeding.id, application_answers={"f1": "Yes", "junk": "x"}), TODAY)
    assert ok.status == "pending"


@pytest.mark.asyncio
async def test_approve_then_deposit_sets_queue_date_and_order(async_session, test_breeder, seeker):
    second = await _other_seeker(async_session)
    a = await svc.request_spot(async_session, test_breeder.id, seeker, WaitlistRequestCreate(), TODAY)
    b = await svc.request_spot(async_session, test_breeder.id, second, WaitlistRequestCreate(), TODAY)
    await svc.approve(async_session, test_breeder, a.id, date(2026, 10, 5))
    await svc.approve(async_session, test_breeder, b.id, date(2026, 10, 6))
    # b pays a deposit dated before a's approval -> b moves ahead
    await svc.update_deposit(async_session, test_breeder, b.id, DepositUpdate(
        deposit_status="received", deposit_amount=Decimal("300"), deposit_received_on=date(2026, 10, 1),
        deposit_method="Zelle"))
    general = (await svc.list_breeder(async_session, test_breeder)).general
    assert [(e.display_name, e.position) for e in general] == [("Second Seeker", 1), ("Test Seeker", 2)]


@pytest.mark.asyncio
async def test_manual_entry_is_active_and_duplicate_email_rejected(async_session, test_breeder):
    e = await svc.add_manual(async_session, test_breeder, ManualEntryCreate(
        contact_name="Jane Phone", contact_email=" Jane@Example.com "), TODAY)
    assert e.status == "active" and e.contact_email == "jane@example.com" and e.queue_date == TODAY
    with pytest.raises(HTTPException) as exc:
        await svc.add_manual(async_session, test_breeder, ManualEntryCreate(
            contact_name="Jane again", contact_email="jane@example.com"), TODAY)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_approving_twice_is_409(async_session, test_breeder, seeker):
    a = await svc.request_spot(async_session, test_breeder.id, seeker, WaitlistRequestCreate(), TODAY)
    await svc.approve(async_session, test_breeder, a.id, TODAY)
    with pytest.raises(HTTPException) as exc:
        await svc.approve(async_session, test_breeder, a.id, TODAY)
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "INVALID_WAITLIST_TRANSITION"


@pytest.mark.asyncio
async def test_other_breeder_cannot_touch_entry(async_session, test_breeder, seeker):
    a = await svc.request_spot(async_session, test_breeder.id, seeker, WaitlistRequestCreate(), TODAY)
    intruder = User(email="intruder@example.com", hashed_password="x", name="I", is_active=True, is_breeder=True)
    async_session.add(intruder)
    await async_session.commit()
    with pytest.raises(HTTPException) as exc:
        await svc.approve(async_session, intruder, a.id, TODAY)
    assert exc.value.status_code == 404
