"""
Waitlist router: seeker requests, breeder queue management, deposits, settings.

Thin layer over `WaitlistService`. The whole router 404s while ENABLE_WAITLIST is off.
"""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import (
    current_active_user,
    optional_current_user,
    require_breeder,
    require_waitlist_enabled,
)
from app.models.user import User
from app.schemas.waitlist import (
    BreederWaitlistInfo,
    BreederWaitlistRead,
    DepositUpdate,
    EntryRead,
    EventRead,
    LitterWaitlistRead,
    ManualEntryCreate,
    MatchRequest,
    MoveRequest,
    ReorderRequest,
    SeekerEntryRead,
    WaitlistRequestCreate,
    WaitlistSettingsRead,
    WaitlistSettingsUpdate,
    WithdrawRequest,
)
from app.services.waitlist_service import waitlist_service as svc

router = APIRouter(
    prefix="/api/waitlist",
    tags=["waitlist"],
    dependencies=[Depends(require_waitlist_enabled)],
)


def require_pet_seeker_account(user: User = Depends(current_active_user)) -> User:
    """403 unless the account is a pet seeker."""
    if user.account_type != "pet_seeker":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pet seeker access required")
    return user


# ── public / seeker ──────────────────────────────────────────────────────

@router.get("/breeders/{breeder_id}/info", response_model=BreederWaitlistInfo)
async def breeder_info(
    breeder_id: uuid.UUID,
    breeding_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_async_session),
    current_user: Optional[User] = Depends(optional_current_user),
) -> BreederWaitlistInfo:
    """Public deposit info and application form for a breeder's waitlist."""
    return await svc.get_info(session, breeder_id, breeding_id, current_user)


@router.post("/breeders/{breeder_id}/requests", response_model=SeekerEntryRead,
             status_code=status.HTTP_201_CREATED)
async def request_spot(
    breeder_id: uuid.UUID,
    data: WaitlistRequestCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_pet_seeker_account),
) -> SeekerEntryRead:
    """Ask to join a breeder's waitlist (creates a pending request)."""
    return await svc.request_spot(session, breeder_id, current_user, data, date.today())


@router.get("/mine", response_model=list[SeekerEntryRead])
async def list_mine(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_pet_seeker_account),
) -> list[SeekerEntryRead]:
    """The seeker's own entries with their own position only."""
    return await svc.list_mine(session, current_user)


@router.post("/mine/{entry_id}/withdraw", response_model=SeekerEntryRead)
async def withdraw_mine(
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_pet_seeker_account),
) -> SeekerEntryRead:
    return await svc.withdraw_by_seeker(session, current_user, entry_id)


# ── breeder: lists and settings (static paths before /entries/{id}) ──────

@router.get("", response_model=BreederWaitlistRead)
async def list_waitlist(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> BreederWaitlistRead:
    return await svc.list_breeder(session, current_user)


@router.get("/settings", response_model=WaitlistSettingsRead)
async def get_settings(current_user: User = Depends(require_breeder)) -> WaitlistSettingsRead:
    return svc.get_settings(current_user)


@router.put("/settings", response_model=WaitlistSettingsRead)
async def update_settings(
    data: WaitlistSettingsUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> WaitlistSettingsRead:
    return await svc.update_settings(session, current_user, data)


@router.post("/general/reset-order", status_code=status.HTTP_200_OK)
async def reset_general_order(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> dict[str, bool]:
    await svc.reset_order(session, current_user, None)
    return {"ok": True}


@router.get("/breedings/{breeding_id}", response_model=LitterWaitlistRead)
async def list_litter(
    breeding_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> LitterWaitlistRead:
    return await svc.list_litter(session, current_user, breeding_id)


@router.post("/breedings/{breeding_id}/reset-order", status_code=status.HTTP_200_OK)
async def reset_litter_order(
    breeding_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> dict[str, bool]:
    await svc.reset_order(session, current_user, breeding_id)
    return {"ok": True}


# ── breeder: entries ─────────────────────────────────────────────────────

@router.post("/entries", response_model=EntryRead, status_code=status.HTTP_201_CREATED)
async def add_manual(
    data: ManualEntryCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> EntryRead:
    return await svc.add_manual(session, current_user, data, date.today())


@router.post("/entries/{entry_id}/approve", response_model=EntryRead)
async def approve(
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> EntryRead:
    return await svc.approve(session, current_user, entry_id, date.today())


@router.post("/entries/{entry_id}/decline", response_model=EntryRead)
async def decline(
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> EntryRead:
    return await svc.decline(session, current_user, entry_id)


@router.put("/entries/{entry_id}/deposit", response_model=EntryRead)
async def update_deposit(
    entry_id: uuid.UUID,
    data: DepositUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> EntryRead:
    return await svc.update_deposit(session, current_user, entry_id, data)


@router.post("/entries/{entry_id}/move", response_model=EntryRead)
async def move(
    entry_id: uuid.UUID,
    data: MoveRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> EntryRead:
    return await svc.move(session, current_user, entry_id, data.breeding_id)


@router.post("/entries/{entry_id}/reorder", response_model=EntryRead)
async def reorder(
    entry_id: uuid.UUID,
    data: ReorderRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> EntryRead:
    return await svc.reorder(session, current_user, entry_id, data.position, data.note)


@router.post("/entries/{entry_id}/match", response_model=EntryRead)
async def match(
    entry_id: uuid.UUID,
    data: MatchRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> EntryRead:
    return await svc.match(session, current_user, entry_id, data.offspring_id)


@router.post("/entries/{entry_id}/pass", response_model=EntryRead)
async def pass_entry(
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> EntryRead:
    return await svc.pass_entry(session, current_user, entry_id)


@router.post("/entries/{entry_id}/withdraw", response_model=EntryRead)
async def withdraw(
    entry_id: uuid.UUID,
    data: Optional[WithdrawRequest] = None,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> EntryRead:
    outcome = data.deposit_outcome if data else None
    return await svc.withdraw_by_breeder(session, current_user, entry_id, outcome)


@router.get("/entries/{entry_id}/events", response_model=list[EventRead])
async def list_events(
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_breeder),
) -> list[EventRead]:
    return await svc.list_events(session, current_user, entry_id)
