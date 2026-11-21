"""Breeder data export: start a background export, poll it, and download via a short-lived link."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker, get_async_session
from app.dependencies import require_breeder
from app.models.data_export import DataExport
from app.models.user import User
from app.schemas.data_export import DataExportRead, DownloadLink
from app.services import data_export_service as svc

router = APIRouter(prefix="/api/exports", tags=["exports"])

UNUSED_TOKEN_TTL = timedelta(seconds=60)
USED_TOKEN_TTL = timedelta(hours=1)


def get_export_session_factory():
    """Session factory for the background job (tests override this)."""
    return async_session_maker


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_expired(export: DataExport) -> bool:
    return export.status == "ready" and export.expires_at is not None and export.expires_at <= _now()


def _read(export: DataExport) -> DataExportRead:
    out = DataExportRead.model_validate(export)
    out.is_expired = _is_expired(export)
    return out


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _latest(session: AsyncSession, user_id: uuid.UUID) -> Optional[DataExport]:
    return (await session.execute(
        select(DataExport).where(DataExport.user_id == user_id)
        .order_by(DataExport.created_at.desc()).limit(1)
    )).scalar_one_or_none()


@router.post("", response_model=DataExportRead, status_code=status.HTTP_202_ACCEPTED)
async def start_export(
    background_tasks: BackgroundTasks,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
    session_factory=Depends(get_export_session_factory),
):
    """Start a new export, or return the one already in progress."""
    await svc.sweep_exports(session_factory, user.id)
    previous = (await session.execute(
        select(DataExport).where(DataExport.user_id == user.id)
    )).scalars().all()
    for prev in previous:
        if prev.status in ("pending", "running"):
            return _read(prev)
    # One live export per breeder: starting a new one removes the previous file
    for prev in previous:
        if prev.file_path:
            svc.remove_file(prev.file_path)
            prev.file_path = None
        prev.download_token_hash = None

    export = DataExport(user_id=user.id, status="pending")
    session.add(export)
    await session.commit()
    await session.refresh(export)
    background_tasks.add_task(svc.run_export, export.id, session_factory)
    return _read(export)


@router.get("/latest", response_model=Optional[DataExportRead])
async def latest_export(
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
    session_factory=Depends(get_export_session_factory),
):
    await svc.sweep_exports(session_factory, user.id)
    export = await _latest(session, user.id)
    if export is not None:
        await session.refresh(export)
    return _read(export) if export else None


@router.post("/{export_id}/download-link", response_model=DownloadLink)
async def create_download_link(
    export_id: uuid.UUID,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
):
    export = await session.get(DataExport, export_id)
    if export is None or export.user_id != user.id or export.status != "ready":
        raise HTTPException(status_code=404, detail="Export not found")
    if _is_expired(export) or not export.file_path:
        raise HTTPException(status_code=410, detail="This export has expired. Please create a new one.")

    token = secrets.token_urlsafe(32)
    export.download_token_hash = _hash(token)
    export.download_token_expires_at = _now() + UNUSED_TOKEN_TTL
    export.download_token_used_at = None
    await session.commit()
    return DownloadLink(url=f"/api/exports/download/{token}")


@router.get("/download/{token}")
async def download_export(token: str, session: AsyncSession = Depends(get_async_session)):
    """Serve the archive for a valid link token. No auth header: the token is the credential."""
    export = (await session.execute(
        select(DataExport).where(DataExport.download_token_hash == _hash(token))
    )).scalar_one_or_none()
    now = _now()
    if (
        export is None
        or export.status != "ready"
        or not export.file_path
        or _is_expired(export)
        or export.download_token_expires_at is None
        or export.download_token_expires_at <= now
        or not Path(export.file_path).is_file()
    ):
        raise HTTPException(status_code=404, detail="Download link is invalid or has expired")

    if export.download_token_used_at is None:
        export.download_token_used_at = now
        export.download_token_expires_at = now + USED_TOKEN_TTL
        await session.commit()

    filename = f"breedly-export-{(export.completed_at or now).date().isoformat()}.zip"
    return FileResponse(
        export.file_path,
        media_type="application/zip",
        filename=filename,
        headers={"Cache-Control": "no-store"},
    )
