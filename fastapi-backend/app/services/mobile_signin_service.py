"""
Instant mobile switch: a signed-in desktop user shows a QR code; scanning it on a phone
and tapping Continue signs the phone in as the same user.

- Codes are 32 random bytes, stored only as SHA-256, valid for CODE_TTL, single use.
- Creating a code cancels the user's previous unused codes.
- Redemption is one conditional UPDATE (unused + unexpired), so two scans can't both win.
- The session handed to the phone is a normal JWT from the same auth backend as a
  password sign-in, returned in the response body (never in a URL).
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.middleware.rate_limiter import client_ip, hash_ip, rate_limiter
from app.models.mobile_signin_token import MobileSigninToken
from app.models.user import User

settings = Settings()

CODE_TTL = timedelta(minutes=2)
RECORD_RETENTION = timedelta(days=7)
CREATE_LIMIT = (10, 600)            # codes per account per 10 minutes
REDEEM_FAILURE_LIMIT = (20, 900)    # failed redemptions per IP per 15 minutes
DEFAULT_TARGET = "/dashboard"
# Pages that make no sense to land on after signing in
_BLOCKED_PREFIXES = ("/m", "/login", "/logout", "/register", "/auth", "/reset-password", "/verify-email")

INVALID = "This code isn't valid. Generate a new one on your computer."
EXPIRED = "This code has expired or was already used. Generate a new one on your computer."
INACTIVE = "This account is deactivated."
TOO_MANY = "Too many attempts. Please wait 15 minutes and try again."


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def safe_target(path: Optional[str]) -> str:
    """Only same-site app paths; anything odd falls back to the dashboard."""
    path = (path or "").strip()
    if (not path.startswith("/") or path.startswith("//") or "\\" in path or "://" in path
            or len(path) > 500 or any(c in path for c in "\r\n\t")):
        return DEFAULT_TARGET
    bare = path.split("?", 1)[0].split("#", 1)[0]
    if any(bare == p or bare.startswith(p + "/") for p in _BLOCKED_PREFIXES):
        return DEFAULT_TARGET
    return path


def display_name(user: User) -> str:
    if user.is_breeder and user.breedery_name:
        return user.breedery_name
    return user.name or user.breedery_name or "your Breedly account"


def mask_email(email: Optional[str]) -> str:
    if not email or "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    return f"{local[:1]}•••@{domain}"


class MobileSigninService:

    async def create(self, db: AsyncSession, user: User, target_path: Optional[str]) -> tuple[MobileSigninToken, str]:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=INACTIVE)
        await rate_limiter.check_rate_limit(f"mobile_signin_create:{user.id}", *CREATE_LIMIT)
        now = _now()
        # Housekeeping: old rows go after a week; a new code cancels the previous unused ones
        await db.execute(delete(MobileSigninToken).where(MobileSigninToken.created_at < now - RECORD_RETENTION))
        await db.execute(
            update(MobileSigninToken)
            .where(MobileSigninToken.user_id == user.id, MobileSigninToken.used_at.is_(None),
                   MobileSigninToken.expires_at > now)
            .values(expires_at=now)
        )
        code = secrets.token_urlsafe(32)
        row = MobileSigninToken(user_id=user.id, token_hash=_hash(code), target_path=safe_target(target_path),
                                expires_at=now + CODE_TTL)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row, code

    async def _usable(self, db: AsyncSession, code: str) -> tuple[MobileSigninToken, User]:
        row = (await db.execute(
            select(MobileSigninToken).where(MobileSigninToken.token_hash == _hash(code or ""))
        )).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=INVALID)
        if row.used_at is not None or row.expires_at <= _now():
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=EXPIRED)
        user = await db.get(User, row.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=INACTIVE)
        return row, user

    async def _guard(self, request: Request):
        key = f"mobile_signin_fail:{client_ip(request)}"
        await rate_limiter.ensure_below(key, *REDEEM_FAILURE_LIMIT, TOO_MANY)
        return key

    async def preview(self, db: AsyncSession, request: Request, code: str,
                      current: Optional[User]) -> dict:
        """Who the code belongs to (name + masked email only). Same account → acknowledged, code kept."""
        key = await self._guard(request)
        try:
            row, user = await self._usable(db, code)
        except HTTPException as exc:
            if exc.status_code in (404, 410):
                await rate_limiter.record(key)
            raise
        same = current is not None and current.id == user.id
        if same:
            row.acknowledged_at = _now()
            await db.commit()
        return {"display_name": display_name(user), "masked_email": mask_email(user.email),
                "same_account": same, "target_path": row.target_path if same else None}

    async def redeem(self, db: AsyncSession, request: Request, code: str) -> dict:
        key = await self._guard(request)
        now = _now()
        # Single statement = the lock: a second concurrent redeem updates nothing
        result = await db.execute(
            update(MobileSigninToken)
            .where(MobileSigninToken.token_hash == _hash(code or ""),
                   MobileSigninToken.used_at.is_(None), MobileSigninToken.expires_at > now)
            .values(used_at=now, used_ip_hash=hash_ip(client_ip(request)),
                    used_user_agent=(request.headers.get("user-agent") or "")[:255] or None)
            .returning(MobileSigninToken.user_id, MobileSigninToken.target_path)
            .execution_options(synchronize_session=False)
        )
        hit = result.first()
        if hit is None:  # nothing was updated, so there's nothing to roll back
            await rate_limiter.record(key)
            exists = (await db.execute(
                select(MobileSigninToken.id).where(MobileSigninToken.token_hash == _hash(code or ""))
            )).first()
            raise HTTPException(status_code=status.HTTP_410_GONE if exists else status.HTTP_404_NOT_FOUND,
                                detail=EXPIRED if exists else INVALID)
        user = await db.get(User, hit.user_id)
        if user is None or not user.is_active:
            await db.commit()  # the code is spent either way
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=INACTIVE)
        await db.commit()
        from app.dependencies import get_jwt_strategy
        token = await get_jwt_strategy().write_token(user)
        return {"access_token": token, "token_type": "bearer", "target_path": hit.target_path}

    async def status_of(self, db: AsyncSession, user: User, code_id: uuid.UUID) -> str:
        row = await db.get(MobileSigninToken, code_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code not found")
        if row.used_at is not None:
            return "used"
        if row.acknowledged_at is not None:
            return "already_signed_in"
        if row.expires_at <= _now():
            return "expired"
        return "pending"


mobile_signin_service = MobileSigninService()
