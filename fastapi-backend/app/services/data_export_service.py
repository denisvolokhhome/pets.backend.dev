"""Breeder data export: collect every record and file of a breedery into one ZIP.

The job runs in the background (FastAPI BackgroundTasks) with its own DB session and
writes into a private directory that is NOT served by StaticFiles.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import settings
from app.models.breed import Breed
from app.models.breeding import Breeding
from app.models.breeding_mating import BreedingMating
from app.models.breeding_milestone import BreedingMilestone
from app.models.breeding_pet import BreedingPet
from app.models.breeding_progesterone_test import BreedingProgesteroneTest
from app.models.data_export import DataExport
from app.models.document import Document
from app.models.location import Location
from app.models.offspring import Offspring
from app.models.offspring_image import OffspringImage
from app.models.pet import Pet
from app.models.pet_image import PetImage

logger = logging.getLogger(__name__)

READY_LIFETIME = timedelta(hours=24)

# Columns never written to the CSVs (internal or raw storage paths)
_EXCLUDED = {"user_id", "coordinates", "error", "image_path", "image_file_name", "is_deleted"}

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _storage_root() -> Path:
    """Stored file paths are relative to the parent of STORAGE_PATH."""
    return Path(settings.storage_path).parent


def _allowed_root() -> Path:
    """Only files inside the upload dir itself may go into an archive."""
    return Path(settings.storage_path)


def _export_dir() -> Path:
    return Path(settings.export_path)


def assert_export_dir_private(export_dir: Path, public_dir: Path) -> None:
    """Refuse an export dir that StaticFiles would serve publicly."""
    exp = export_dir.resolve()
    pub = public_dir.resolve()
    if exp == pub or exp.is_relative_to(pub):
        raise RuntimeError(
            f"EXPORT_PATH ({exp}) is inside the publicly served storage directory ({pub}); "
            "point it somewhere outside, e.g. /var/lib/breedly/exports"
        )


def safe_name(name: Optional[str], fallback: str) -> str:
    """A single, safe path segment: no separators, no '..', no control chars."""
    s = _CONTROL.sub("", name or "")
    s = s.replace("/", "_").replace("\\", "_")
    s = s.replace("..", "")
    s = s.strip(" ._")
    return s[:100] or fallback


@dataclass
class FileEntry:
    source: str  # path relative to the storage root
    folder: str  # folder inside the archive root
    name: str  # desired file name (sanitized and de-duplicated on write)
    label: str  # human description for the README if missing


@dataclass
class ExportData:
    tables: dict[str, tuple[list[str], list[list[Any]]]] = field(default_factory=dict)
    files: list[FileEntry] = field(default_factory=list)


def _columns(model) -> list[str]:
    return [c.name for c in model.__table__.columns if c.name not in _EXCLUDED]


def _row(obj, cols: Iterable[str]) -> list[Any]:
    return [getattr(obj, c) for c in cols]


async def collect_export_data(session: AsyncSession, user_id: uuid.UUID) -> ExportData:
    data = ExportData()

    locations = (await session.execute(
        select(Location).where(Location.user_id == user_id).order_by(Location.id)
    )).scalars().all()
    loc_names = {loc.id: loc.name for loc in locations}
    cols = _columns(Location)
    data.tables["locations.csv"] = (cols, [_row(loc, cols) for loc in locations])

    pets = (await session.execute(
        select(Pet).where(Pet.user_id == user_id).order_by(Pet.created_at, Pet.name)
    )).scalars().all()
    breedings = (await session.execute(
        select(Breeding).where(Breeding.user_id == user_id).order_by(Breeding.id)
    )).scalars().all()
    breeding_ids = [b.id for b in breedings]
    offspring = (await session.execute(
        select(Offspring).where(Offspring.user_id == user_id).order_by(Offspring.created_at, Offspring.name)
    )).scalars().all()

    links: list = []
    matings: list = []
    tests: list = []
    milestones: list = []
    if breeding_ids:
        links = (await session.execute(
            select(BreedingPet).where(BreedingPet.breeding_id.in_(breeding_ids)).order_by(BreedingPet.id)
        )).scalars().all()
        matings = (await session.execute(
            select(BreedingMating).where(BreedingMating.breeding_id.in_(breeding_ids))
            .order_by(BreedingMating.breeding_id, BreedingMating.mated_on)
        )).scalars().all()
        tests = (await session.execute(
            select(BreedingProgesteroneTest).where(BreedingProgesteroneTest.breeding_id.in_(breeding_ids))
            .order_by(BreedingProgesteroneTest.breeding_id, BreedingProgesteroneTest.tested_on)
        )).scalars().all()
        milestones = (await session.execute(
            select(BreedingMilestone).where(BreedingMilestone.breeding_id.in_(breeding_ids))
            .order_by(BreedingMilestone.breeding_id, BreedingMilestone.due_on)
        )).scalars().all()

    # Names for any referenced pet, including parents/sires owned by other breeders
    ref_ids = {p.id for p in pets} | {link.pet_id for link in links}
    ref_ids |= {m.sire_id for m in matings if m.sire_id}
    ref_ids |= {o.father_id for o in offspring if o.father_id} | {o.mother_id for o in offspring if o.mother_id}
    pet_names: dict = {}
    if ref_ids:
        rows = (await session.execute(select(Pet.id, Pet.name).where(Pet.id.in_(ref_ids)))).all()
        pet_names = {r.id: r.name for r in rows}

    breed_ids = {p.breed_id for p in pets if p.breed_id} | {o.breed_id for o in offspring if o.breed_id}
    breed_names: dict = {}
    if breed_ids:
        rows = (await session.execute(select(Breed.id, Breed.name).where(Breed.id.in_(breed_ids)))).all()
        breed_names = {r.id: r.name for r in rows}

    cols = _columns(Pet)
    data.tables["pets.csv"] = (
        cols + ["breed", "location", "deleted"],
        [_row(p, cols) + [breed_names.get(p.breed_id), loc_names.get(p.location_id), bool(p.is_deleted)]
         for p in pets],
    )
    cols = _columns(Breeding)
    data.tables["breedings.csv"] = (cols, [_row(b, cols) for b in breedings])
    cols = _columns(BreedingPet)
    data.tables["breeding_pets.csv"] = (cols + ["pet"], [_row(x, cols) + [pet_names.get(x.pet_id)] for x in links])
    cols = _columns(BreedingMating)
    data.tables["matings.csv"] = (
        cols + ["sire"], [_row(m, cols) + [pet_names.get(m.sire_id) or m.outside_sire_name] for m in matings]
    )
    cols = _columns(BreedingProgesteroneTest)
    data.tables["progesterone_tests.csv"] = (cols, [_row(t, cols) for t in tests])
    cols = _columns(BreedingMilestone)
    data.tables["milestones.csv"] = (cols, [_row(m, cols) for m in milestones])
    cols = _columns(Offspring)
    data.tables["offspring.csv"] = (
        cols + ["breed", "father", "mother"],
        [_row(o, cols) + [breed_names.get(o.breed_id), pet_names.get(o.father_id), pet_names.get(o.mother_id)]
         for o in offspring],
    )

    # Files
    pet_folder = {p.id: f"{safe_name(p.name, 'pet')}_{p.id}" for p in pets}
    pup_folder = {o.id: f"{safe_name(o.name, 'offspring')}_{o.id}" for o in offspring}

    if pets:
        images = (await session.execute(
            select(PetImage).where(PetImage.pet_id.in_(list(pet_folder)))
            .order_by(PetImage.pet_id, PetImage.display_order, PetImage.id)
        )).scalars().all()
        counter: dict = {}
        for img in images:
            n = counter[img.pet_id] = counter.get(img.pet_id, 0) + 1
            fname = img.image_file_name or PurePosixPath(img.image_path).name
            data.files.append(FileEntry(img.image_path, f"photos/pets/{pet_folder[img.pet_id]}",
                                        f"{n}_{safe_name(fname, 'photo')}", f"photo of pet {pet_names.get(img.pet_id)}"))
        gallery_paths = {img.image_path for img in images}
        for p in pets:
            # Uploads write the same file to pet_images and the legacy column; export it once
            if p.image_path and p.image_path not in gallery_paths:
                n = counter[p.id] = counter.get(p.id, 0) + 1
                fname = p.image_file_name or PurePosixPath(p.image_path).name
                data.files.append(FileEntry(p.image_path, f"photos/pets/{pet_folder[p.id]}",
                                            f"{n}_{safe_name(fname, 'photo')}", f"photo of pet {p.name}"))
    if offspring:
        images = (await session.execute(
            select(OffspringImage).where(OffspringImage.offspring_id.in_(list(pup_folder)))
            .order_by(OffspringImage.offspring_id, OffspringImage.display_order, OffspringImage.created_at)
        )).scalars().all()
        counter = {}
        for img in images:
            n = counter[img.offspring_id] = counter.get(img.offspring_id, 0) + 1
            ext = PurePosixPath(img.image_path).suffix or ".jpg"
            data.files.append(FileEntry(img.image_path, f"photos/offspring/{pup_folder[img.offspring_id]}",
                                        f"{n}{ext}", f"photo of offspring {img.offspring_id}"))

    conds = []
    if pets:
        conds.append((Document.entity_type == "pet") & Document.entity_id.in_(list(pet_folder)))
    if offspring:
        conds.append((Document.entity_type == "offspring") & Document.entity_id.in_(list(pup_folder)))
    if conds:
        docs = (await session.execute(
            select(Document).where(or_(*conds)).order_by(Document.entity_type, Document.entity_id, Document.id)
        )).scalars().all()
        for d in docs:
            if d.entity_type == "pet":
                folder = f"documents/pets/{pet_folder[d.entity_id]}"
            else:
                folder = f"documents/offspring/{pup_folder[d.entity_id]}"
            data.files.append(FileEntry(d.file_path, folder, safe_name(d.file_name, "document"),
                                        f"document {d.file_name}"))
    return data


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return format(v, "f")
    return str(v)


def _csv_bytes(header: list[str], rows: list[list[Any]]) -> bytes:
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow([_fmt(v) for v in r])
    return buf.getvalue().encode("utf-8")


def _unique(path: str, used: set[str]) -> str:
    if path not in used:
        used.add(path)
        return path
    p = PurePosixPath(path)
    i = 2
    while True:
        cand = str(p.with_name(f"{p.stem}_{i}{p.suffix}"))
        if cand not in used:
            used.add(cand)
            return cand
        i += 1


def write_export_zip(
    data: ExportData, storage_root: Path, dest: Path, export_date: date, allowed_root: Optional[Path] = None
) -> list[str]:
    """Write the archive to `dest`. Returns descriptions of files that were missing on disk.

    File sources resolve against `storage_root`; only files inside `allowed_root` (default:
    `storage_root`) are read.
    """
    root = f"breedly-export-{export_date.isoformat()}"
    missing: list[str] = []
    used: set[str] = set()
    root_resolved = (allowed_root or storage_root).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", allowZip64=True) as zf:
        for name, (header, rows) in data.tables.items():
            zf.writestr(f"{root}/{name}", _csv_bytes(header, rows), compress_type=zipfile.ZIP_DEFLATED)
        added = 0
        for f in data.files:
            src = (storage_root / f.source).resolve()
            if not src.is_relative_to(root_resolved) or not src.is_file():
                missing.append(f"{f.folder}/{f.name} ({f.label})")
                continue
            arc = _unique(f"{root}/{f.folder}/{f.name}", used)
            try:
                zf.write(src, arc, compress_type=zipfile.ZIP_STORED)
            except OSError:
                # Deleted or unreadable since the check: list it, don't fail the whole export
                used.discard(arc)
                missing.append(f"{f.folder}/{f.name} ({f.label})")
                continue
            added += 1
        zf.writestr(f"{root}/README.txt", _readme(data, export_date, added, missing),
                    compress_type=zipfile.ZIP_DEFLATED)
    return missing


def _readme(data: ExportData, export_date: date, added: int, missing: list[str]) -> str:
    lines = [
        "Breedly data export",
        f"Exported on {export_date.isoformat()}",
        "",
        "Spreadsheets (CSV, UTF-8; open in Excel, Numbers or Google Sheets):",
    ]
    for name, (_, rows) in data.tables.items():
        lines.append(f"  {name:<24} {len(rows)} rows")
    lines += [
        "",
        "Rows keep their IDs so files can be cross-referenced (e.g. offspring.breeding_id -> breedings.id).",
        "pets.csv includes deleted pets (deleted = yes).",
        "",
        f"Files: {added} photos and documents under photos/ and documents/.",
    ]
    if missing:
        lines += ["", "These files were listed in your account but were missing on the server:"]
        lines += [f"  - {m}" for m in missing]
    return "\n".join(lines) + "\n"


def remove_file(path: Optional[str]) -> None:
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete export file %s", path)


SessionFactory = Callable[[], Any]


async def run_export(export_id: uuid.UUID, session_factory: SessionFactory) -> None:
    """Build the archive for an export row; marks it ready or failed."""
    async with session_factory() as session:
        export = await session.get(DataExport, export_id)
        if export is None:
            return
        dest = _export_dir() / f"{export.id}.zip"
        user_id = export.user_id
        # Record the path before writing so a sweep can always find a partial file
        export.status = "running"
        export.file_path = str(dest)
        await session.commit()
        try:
            data = await collect_export_data(session, user_id)
            await session.commit()  # don't hold a transaction open while the ZIP is written
            today = datetime.now(timezone.utc).date()
            await asyncio.to_thread(write_export_zip, data, _storage_root(), dest, today,
                                    allowed_root=_allowed_root())
            now = datetime.now(timezone.utc)
            result = await session.execute(
                update(DataExport)
                .where(DataExport.id == export_id, DataExport.status == "running")
                .values(status="ready", file_path=str(dest), file_size=dest.stat().st_size,
                        completed_at=now, expires_at=now + READY_LIFETIME, error=None)
            )
            await session.commit()
            if result.rowcount == 0:
                # Failed by a sweep (or replaced) while running: don't resurrect it
                remove_file(str(dest))
        except Exception:  # noqa: BLE001 — any failure must end as a failed export
            logger.exception("Data export %s failed", export_id)
            await session.rollback()
            remove_file(str(dest))
            await session.execute(
                update(DataExport).where(DataExport.id == export_id).values(
                    status="failed", file_path=None, completed_at=datetime.now(timezone.utc),
                    error="Something went wrong while building your archive. Please try again.",
                )
            )
            await session.commit()


async def sweep_exports(
    session_factory: SessionFactory, user_id: Optional[uuid.UUID] = None, startup: bool = False
) -> None:
    """Delete files of expired exports.

    With `startup=True` (single process, so nothing can still be running) also fail every
    pending/running job, remove its partial file, and delete orphan ZIPs no ready row points to.
    """
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        cond = (DataExport.file_path.is_not(None)) & (DataExport.expires_at < now)
        if startup:
            cond = or_(cond, DataExport.status.in_(("pending", "running")))
        q = select(DataExport).where(cond)
        if user_id is not None:
            q = q.where(DataExport.user_id == user_id)
        for export in (await session.execute(q)).scalars().all():
            if export.status in ("pending", "running"):
                export.status = "failed"
                export.error = "The export was interrupted. Please try again."
                remove_file(export.file_path)
                export.file_path = None
            elif export.expires_at and export.expires_at < now:
                remove_file(export.file_path)
                export.file_path = None
        await session.commit()

        if startup:
            live = set((await session.execute(
                select(DataExport.file_path).where(DataExport.file_path.is_not(None))
            )).scalars().all())
            export_dir = _export_dir()
            if export_dir.is_dir():
                for f in export_dir.glob("*.zip"):
                    if str(f) not in live:
                        remove_file(str(f))
