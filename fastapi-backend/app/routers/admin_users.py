"""Admin user management endpoints — suspend/unsuspend accounts."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_async_session
from app.models.user import User
from app.models.location import Location

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])
settings = Settings()
logger = logging.getLogger(__name__)


async def verify_admin_key(x_admin_key: str = Header(...)):
    """Verify the admin API key from request header."""
    if not settings.admin_api_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin API key")
    return True


@router.post("/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Suspend a user account.

    Sets is_active=False and unpublishes all their locations.
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_active:
        return {"detail": "User is already suspended", "user_id": str(user.id)}

    # Deactivate the account
    user.is_active = False

    # Unpublish all locations owned by this user
    await session.execute(
        update(Location)
        .where(Location.user_id == user.id)
        .values(is_published=False)
    )

    await session.commit()
    logger.info("Admin suspended user %s (%s)", user.id, user.email)

    return {
        "detail": "User suspended successfully",
        "user_id": str(user.id),
        "email": user.email,
    }


@router.post("/{user_id}/unsuspend")
async def unsuspend_user(
    user_id: str,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Unsuspend a user account.

    Sets is_active=True. Locations remain unpublished — the user can
    re-publish them manually after logging back in.
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_active:
        return {"detail": "User is already active", "user_id": str(user.id)}

    user.is_active = True
    await session.commit()
    logger.info("Admin unsuspended user %s (%s)", user.id, user.email)

    return {
        "detail": "User unsuspended successfully",
        "user_id": str(user.id),
        "email": user.email,
    }


@router.get("")
async def list_users(
    role: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    _: bool = Depends(verify_admin_key),
    session: AsyncSession = Depends(get_async_session),
):
    """
    List users with optional filters for the admin user management page.

    Query params:
        role: 'breeder' | 'seeker' | None (all)
        status: 'active' | 'suspended' | None (all)
        limit: max rows (default 50)
    """
    query = select(User).order_by(User.created_at.desc()).limit(limit)

    if role == "breeder":
        query = query.where(User.is_breeder == True)
    elif role == "seeker":
        query = query.where(User.is_breeder == False)

    if status == "active":
        query = query.where(User.is_active == True)
    elif status == "suspended":
        query = query.where(User.is_active == False)

    result = await session.execute(query)
    users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "breedery_name": u.breedery_name,
            "is_breeder": u.is_breeder,
            "is_active": u.is_active,
            "is_verified": u.is_verified,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]
