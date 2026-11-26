"""Instant mobile switch: QR code on desktop → phone signed in as the same user."""
import uuid
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_async_session
from app.dependencies import current_active_user, optional_current_user
from app.models.user import User
from app.services.mobile_signin_service import mobile_signin_service as svc

settings = Settings()
router = APIRouter(prefix="/api/auth/mobile-signin", tags=["auth"])


class CodeCreate(BaseModel):
    target_path: Optional[str] = Field(None, max_length=1000)


class CodeCreated(BaseModel):
    id: uuid.UUID
    url: str          # what the QR encodes; the code is in the #fragment, never sent to a server
    expires_at: datetime
    expires_in: int


class CodeBody(BaseModel):
    code: str = Field(..., min_length=1, max_length=200)


class CodePreview(BaseModel):
    display_name: str
    masked_email: str
    same_account: bool
    target_path: Optional[str] = None


class Redeemed(BaseModel):
    access_token: str
    token_type: str
    target_path: str


class CodeStatus(BaseModel):
    status: Literal["pending", "used", "already_signed_in", "expired"]


@router.post("/codes", response_model=CodeCreated, status_code=201)
async def create_code(data: CodeCreate, db: AsyncSession = Depends(get_async_session),
                      user: User = Depends(current_active_user)):
    row, code = await svc.create(db, user, data.target_path)
    from app.services.mobile_signin_service import CODE_TTL
    return CodeCreated(id=row.id, url=f"{settings.frontend_url.rstrip('/')}/m#{code}",
                       expires_at=row.expires_at, expires_in=int(CODE_TTL.total_seconds()))


@router.get("/codes/{code_id}/status", response_model=CodeStatus)
async def code_status(code_id: uuid.UUID, db: AsyncSession = Depends(get_async_session),
                      user: User = Depends(current_active_user)):
    """Polled by the desktop popup (owner only)."""
    return CodeStatus(status=await svc.status_of(db, user, code_id))


@router.post("/preview", response_model=CodePreview)
async def preview_code(data: CodeBody, request: Request, db: AsyncSession = Depends(get_async_session),
                       current: Optional[User] = Depends(optional_current_user)):
    """Phone: whose code is this? Doesn't use it up (unless already signed in as that user)."""
    return await svc.preview(db, request, data.code, current)


@router.post("/redeem", response_model=Redeemed)
async def redeem_code(data: CodeBody, request: Request, db: AsyncSession = Depends(get_async_session)):
    """Phone tapped Continue: spend the code, get a normal session token."""
    return await svc.redeem(db, request, data.code)
