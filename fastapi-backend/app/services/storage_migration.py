"""One-time move of local uploads into object storage. Runs at backend startup; safe to repeat.

- Documents (rows whose file_path is still a local path, i.e. contains "/"):
  uploaded to the private documents bucket under their file name (already an
  unguessable doc_<entity>_<uuid> name), the row is updated, then the local copy
  is deleted. The key is deterministic, so if the pre-deploy DB dump is restored
  after a failed deploy, the next start simply repoints the rows.
- Photos (every other file in the upload dir): copied to the photos bucket
  under "<upload dir name>/<file>" if not there yet. Local copies are kept for
  one release so a rollback to the previous image still shows them.
"""
import asyncio
import logging
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from app.models.document import Document
from app.services.object_storage import ObjectStorage, documents_bucket, photos_bucket

logger = logging.getLogger(__name__)


@dataclass
class MigrationReport:
    documents_moved: int = 0
    photos_copied: int = 0
    missing: list[str] = field(default_factory=list)


def _local_document(upload_dir: Path, stored_path: str) -> Optional[Path]:
    """The local file for a legacy document path, only if it lies inside the upload dir."""
    root = upload_dir.resolve()
    candidate = (upload_dir.parent / stored_path.lstrip("/")).resolve()
    return candidate if root in candidate.parents else None


async def _migrate_documents(session_factory, storage: ObjectStorage, upload_dir: Path, report: MigrationReport):
    async with session_factory() as session:
        docs = (await session.execute(
            select(Document).where(Document.file_path.contains("/")).order_by(Document.id)
        )).scalars().all()
        for doc in docs:
            local = _local_document(upload_dir, doc.file_path)
            if local is None:
                report.missing.append(doc.file_path)
                continue
            key = local.name if local.name.startswith("doc_") else f"doc_{doc.entity_id}_{local.name}"
            if not await asyncio.to_thread(storage.exists, documents_bucket(), key):
                if not local.is_file():
                    report.missing.append(doc.file_path)
                    continue
                data = await asyncio.to_thread(local.read_bytes)
                await asyncio.to_thread(storage.put, documents_bucket(), key, data,
                                        doc.file_type or "application/octet-stream")
            doc.file_path = key
            await session.commit()  # the row points at the bucket before the local copy goes
            local.unlink(missing_ok=True)
            report.documents_moved += 1


async def _copy_photos(storage: ObjectStorage, upload_dir: Path, report: MigrationReport):
    if not upload_dir.is_dir():
        return
    for path in sorted(upload_dir.iterdir()):
        if not path.is_file() or path.name.startswith("doc_"):
            continue  # documents never become photos (orphans stay unserved on disk)
        key = f"{upload_dir.name}/{path.name}"
        if await asyncio.to_thread(storage.exists, photos_bucket(), key):
            continue
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = await asyncio.to_thread(path.read_bytes)
        await asyncio.to_thread(storage.put, photos_bucket(), key, data, content_type)
        report.photos_copied += 1


def _log(report: MigrationReport) -> None:
    if report.documents_moved or report.photos_copied or report.missing:
        logger.info("Storage migration: %d documents moved, %d photos copied, %d document files missing: %s",
                    report.documents_moved, report.photos_copied, len(report.missing), report.missing)


async def migrate_local_files(session_factory, storage: ObjectStorage, upload_dir: Path) -> MigrationReport:
    """Move documents and copy photos, all before returning."""
    report = MigrationReport()
    await _migrate_documents(session_factory, storage, upload_dir, report)
    await _copy_photos(storage, upload_dir, report)
    _log(report)
    return report


async def start_storage_migration(session_factory, storage: ObjectStorage, upload_dir: Path) -> "asyncio.Task[MigrationReport]":
    """Startup entry point: documents move before the app serves (signed downloads need the
    new keys); photos are copied in a background task, since the photo route falls back to
    the local copy until then. Await the returned task for the full report."""
    report = MigrationReport()
    await _migrate_documents(session_factory, storage, upload_dir, report)

    async def copy() -> MigrationReport:
        try:
            await _copy_photos(storage, upload_dir, report)
        except Exception:  # noqa: BLE001 — retried on the next start
            logger.exception("Background photo copy failed")
        _log(report)
        return report

    return asyncio.create_task(copy())
