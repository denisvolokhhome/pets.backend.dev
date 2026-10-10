"""
Breeding planner router: matings, progesterone tests, milestones and stage.

Thin layer over `BreedingPlannerService`; every write returns the full planner
view so the UI can re-render due dates and milestones in one round trip.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_breeder
from app.models.user import User
from app.schemas.breeding_planner import (
    MatingCreate,
    MatingUpdate,
    MilestoneCreate,
    MilestoneLocation,
    MilestoneUpdate,
    PlannerRead,
    PlannerUpdate,
    ProgesteroneTestCreate,
    UpcomingMilestoneRead,
)
from app.services.breeding_planner_service import breeding_planner_service as planner

router = APIRouter(
    prefix="/api/breedings",
    tags=["breeding-planner"],
    responses={404: {"description": "Breeding not found"}},
)


# Declared before /milestones/{milestone_id} so "upcoming" isn't parsed as an id
@router.get("/milestones/upcoming", response_model=list[UpcomingMilestoneRead])
async def upcoming_milestones(
    days: int = Query(14, ge=1, le=90),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> list[UpcomingMilestoneRead]:
    """Open milestones due within `days` (plus overdue ones) across the breeder's pregnancies."""
    return await planner.upcoming(session, current_user, days, date.today())


@router.get("/milestones/{milestone_id}", response_model=MilestoneLocation)
async def locate_milestone(
    milestone_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> MilestoneLocation:
    """Resolve a milestone to its breeding (notification links carry the milestone id)."""
    return await planner.locate_milestone(session, current_user, milestone_id)


@router.get("/{breeding_id}/planner", response_model=PlannerRead)
async def get_planner(
    breeding_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> PlannerRead:
    return await planner.get_planner(session, breeding_id, current_user, date.today())


@router.patch("/{breeding_id}/planner", response_model=PlannerRead)
async def update_planner(
    breeding_id: int,
    data: PlannerUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> PlannerRead:
    """Set/clear the ovulation date or move the stage (Mated/Confirmed/Missed)."""
    return await planner.update_planner(session, breeding_id, current_user, data, date.today())


@router.post("/{breeding_id}/matings", response_model=PlannerRead, status_code=status.HTTP_201_CREATED)
async def add_mating(
    breeding_id: int,
    data: MatingCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> PlannerRead:
    return await planner.add_mating(session, breeding_id, current_user, data, date.today())


@router.put("/{breeding_id}/matings/{mating_id}", response_model=PlannerRead)
async def update_mating(
    breeding_id: int,
    mating_id: uuid.UUID,
    data: MatingUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> PlannerRead:
    return await planner.update_mating(session, breeding_id, current_user, mating_id, data, date.today())


@router.delete("/{breeding_id}/matings/{mating_id}", response_model=PlannerRead)
async def delete_mating(
    breeding_id: int,
    mating_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> PlannerRead:
    return await planner.delete_mating(session, breeding_id, current_user, mating_id, date.today())


@router.post(
    "/{breeding_id}/progesterone-tests", response_model=PlannerRead, status_code=status.HTTP_201_CREATED
)
async def add_progesterone_test(
    breeding_id: int,
    data: ProgesteroneTestCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> PlannerRead:
    return await planner.add_progesterone_test(session, breeding_id, current_user, data, date.today())


@router.delete("/{breeding_id}/progesterone-tests/{test_id}", response_model=PlannerRead)
async def delete_progesterone_test(
    breeding_id: int,
    test_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> PlannerRead:
    return await planner.delete_progesterone_test(session, breeding_id, current_user, test_id, date.today())


@router.post("/{breeding_id}/milestones", response_model=PlannerRead, status_code=status.HTTP_201_CREATED)
async def add_milestone(
    breeding_id: int,
    data: MilestoneCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> PlannerRead:
    return await planner.add_milestone(session, breeding_id, current_user, data, date.today())


@router.patch("/{breeding_id}/milestones/{milestone_id}", response_model=PlannerRead)
async def update_milestone(
    breeding_id: int,
    milestone_id: uuid.UUID,
    data: MilestoneUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> PlannerRead:
    """Complete/uncomplete any milestone; edit title/dates of custom ones."""
    return await planner.update_milestone(session, breeding_id, current_user, milestone_id, data, date.today())


@router.delete("/{breeding_id}/milestones/{milestone_id}", response_model=PlannerRead)
async def delete_milestone(
    breeding_id: int,
    milestone_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> PlannerRead:
    return await planner.delete_milestone(session, breeding_id, current_user, milestone_id, date.today())
