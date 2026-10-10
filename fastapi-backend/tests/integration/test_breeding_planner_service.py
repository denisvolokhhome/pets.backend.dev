"""BreedingPlannerService: regeneration, stages, ownership."""
from datetime import date, timedelta, datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.breed import Breed
from app.models.breeding_pet import BreedingPet
from app.models.pet import Pet
from app.models.user import User
from app.schemas.breeding_planner import (
    MatingCreate, MatingUpdate, MilestoneCreate, MilestoneUpdate, PlannerUpdate,
)
from app.services.breeding_planner_service import breeding_planner_service as svc

TODAY = date(2026, 10, 10)
MATED = date(2026, 9, 1)


def _mating(day=MATED, **kw):
    return MatingCreate(mated_on=day, method="Natural", **kw)


@pytest.fixture
async def dam(async_session, test_breeder, test_breed, test_breeding):
    pet = Pet(user_id=test_breeder.id, name="Honey", gender="Female", breed_id=test_breed.id)
    async_session.add(pet)
    await async_session.flush()
    async_session.add(BreedingPet(breeding_id=test_breeding.id, pet_id=pet.id))
    await async_session.commit()
    return pet


@pytest.mark.asyncio
async def test_empty_planner(async_session, test_breeder, test_breeding):
    p = await svc.get_planner(async_session, test_breeding.id, test_breeder, TODAY)
    assert p.stage == "Planned" and p.due_date is None and p.milestones == []


@pytest.mark.asyncio
async def test_first_mating_sets_mated_and_milestones(async_session, test_breeder, test_breeding, dam):
    p = await svc.add_mating(async_session, test_breeding.id, test_breeder, _mating(), TODAY)
    assert p.stage == "Mated"
    assert p.kind == "dog"
    assert p.due_date == MATED + timedelta(days=63)
    assert (p.due_window_start, p.due_window_end) == (p.due_date - timedelta(days=5), p.due_date + timedelta(days=5))
    assert p.gestation_day == (TODAY - MATED).days
    assert [m.key for m in p.milestones] == ["ultrasound", "xray", "whelping_box", "temperature", "due"]
    assert p.allowed_stage_targets == ["Confirmed", "Missed"]


@pytest.mark.asyncio
async def test_cat_dam_uses_cat_gestation(async_session, test_breeder, test_breeding, dam):
    cat = Breed(name="Test Cat Breed", kind="cat")
    async_session.add(cat)
    await async_session.flush()
    dam.breed_id = cat.id
    await async_session.commit()
    p = await svc.add_mating(async_session, test_breeding.id, test_breeder, _mating(), TODAY)
    assert p.kind == "cat" and p.due_date == MATED + timedelta(days=65)


@pytest.mark.asyncio
async def test_ovulation_date_takes_precedence(async_session, test_breeder, test_breeding, dam):
    await svc.add_mating(async_session, test_breeding.id, test_breeder, _mating(), TODAY)
    p = await svc.update_planner(async_session, test_breeding.id, test_breeder,
                                 PlannerUpdate(ovulation_date=MATED - timedelta(days=2)), TODAY)
    assert p.anchored_on_ovulation is True
    assert p.due_date == MATED + timedelta(days=61)
    assert p.due_window_end - p.due_window_start == timedelta(days=2)
    p = await svc.update_planner(async_session, test_breeding.id, test_breeder,
                                 PlannerUpdate(ovulation_date=None), TODAY)
    assert p.anchored_on_ovulation is False and p.due_date == MATED + timedelta(days=63)


@pytest.mark.asyncio
async def test_editing_first_mating_moves_milestones_and_rearms(async_session, test_breeder, test_breeding, dam):
    p = await svc.add_mating(async_session, test_breeding.id, test_breeder, _mating(), TODAY)
    ultrasound = next(m for m in p.milestones if m.key == "ultrasound")
    p = await svc.update_milestone(async_session, test_breeding.id, test_breeder, ultrasound.id,
                                   MilestoneUpdate(completed=True), TODAY)
    # simulate an already-sent reminder on the X-ray milestone
    breeding = await svc._load(async_session, test_breeding.id, test_breeder)
    xray = next(m for m in breeding.milestones if m.key == "xray")
    xray.reminded_at = datetime.now(timezone.utc)
    await async_session.commit()

    mating_id = p.matings[0].id
    p = await svc.update_mating(async_session, test_breeding.id, test_breeder, mating_id,
                                MatingUpdate(mated_on=MATED + timedelta(days=3), method="Natural"), TODAY)
    by_key = {m.key: m for m in p.milestones}
    assert by_key["ultrasound"].due_on == MATED + timedelta(days=28)      # completed: kept
    assert by_key["xray"].due_on == MATED + timedelta(days=58)            # moved
    breeding = await svc._load(async_session, test_breeding.id, test_breeder)
    assert next(m for m in breeding.milestones if m.key == "xray").reminded_at is None


@pytest.mark.asyncio
async def test_deleting_last_mating_resets(async_session, test_breeder, test_breeding, dam):
    p = await svc.add_mating(async_session, test_breeding.id, test_breeder, _mating(), TODAY)
    p = await svc.add_milestone(async_session, test_breeding.id, test_breeder,
                                MilestoneCreate(title="Vet visit", due_on=TODAY + timedelta(days=3)), TODAY)
    p = await svc.delete_mating(async_session, test_breeding.id, test_breeder, p.matings[0].id, TODAY)
    assert p.stage == "Planned" and p.due_date is None
    assert [m.title for m in p.milestones] == ["Vet visit"]


@pytest.mark.asyncio
async def test_stage_changes(async_session, test_breeder, test_breeding, dam):
    with pytest.raises(HTTPException) as exc:
        await svc.update_planner(async_session, test_breeding.id, test_breeder, PlannerUpdate(stage="Confirmed"), TODAY)
    assert exc.value.status_code == 409
    await svc.add_mating(async_session, test_breeding.id, test_breeder, _mating(), TODAY)
    p = await svc.update_planner(async_session, test_breeding.id, test_breeder, PlannerUpdate(stage="Confirmed"), TODAY)
    assert p.stage == "Confirmed"
    p = await svc.update_planner(async_session, test_breeding.id, test_breeder, PlannerUpdate(stage="Missed"), TODAY)
    assert p.stage == "Missed" and p.gestation_day is None
    # a second mating doesn't flip Missed back automatically
    p = await svc.add_mating(async_session, test_breeding.id, test_breeder, _mating(MATED + timedelta(days=1)), TODAY)
    assert p.stage == "Missed"


@pytest.mark.asyncio
async def test_voided_breeding_rejects_writes(async_session, test_breeder, test_breeding):
    test_breeding.status = "Voided"
    await async_session.commit()
    with pytest.raises(HTTPException) as exc:
        await svc.add_mating(async_session, test_breeding.id, test_breeder, _mating(), TODAY)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_other_breeder_gets_404(async_session, test_breeding):
    other = User(email="other@example.com", hashed_password="x", name="Other", is_active=True, is_breeder=True)
    async_session.add(other)
    await async_session.commit()
    with pytest.raises(HTTPException) as exc:
        await svc.get_planner(async_session, test_breeding.id, other, TODAY)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_future_mating_rejected(async_session, test_breeder, test_breeding):
    with pytest.raises(HTTPException) as exc:
        await svc.add_mating(async_session, test_breeding.id, test_breeder, _mating(TODAY + timedelta(days=1)), TODAY)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_upcoming_lists_due_and_overdue(async_session, test_breeder, test_breeding, dam):
    await svc.add_mating(async_session, test_breeding.id, test_breeder, _mating(), TODAY)
    items = await svc.upcoming(async_session, test_breeder, 14, TODAY)
    # mated Sep 1: ultrasound Sep 29 (overdue), nothing else within Oct 24
    assert [(i.title, i.is_overdue) for i in items] == [("Ultrasound — confirm pregnancy", True)]
    assert items[0].breeding_label == "Honey"
