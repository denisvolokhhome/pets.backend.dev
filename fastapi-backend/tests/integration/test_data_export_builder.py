"""Tests for the breeder data export archive builder."""
import csv
import io
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.models.user import User
from app.services import data_export_service as svc

EXPORT_DATE = date(2026, 11, 20)
ROOT = "breedly-export-2026-11-20/"


def _put(storage_root: Path, rel: str, data: bytes) -> str:
    p = storage_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return rel


def _read_csv(zf: zipfile.ZipFile, name: str) -> list[dict]:
    raw = zf.read(ROOT + name).decode("utf-8")
    assert raw.startswith("﻿"), f"{name} must start with a UTF-8 BOM"
    return list(csv.DictReader(io.StringIO(raw.lstrip("﻿"))))


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    root = tmp_path / "storage"
    root.mkdir()
    return root


@pytest.fixture
async def breedery(async_session: AsyncSession, test_breeder: User, test_breed, test_breeding, storage_root: Path):
    """A breeder with a location, pets (one deleted), a breeding with records, a sold puppy and files."""
    loc = Location(user_id=test_breeder.id, name="Home Kennel", address1="1 Main St", city="Austin", state="TX",
                   country="US", zipcode="78701", location_type="user")
    async_session.add(loc)
    await async_session.flush()

    dam = Pet(user_id=test_breeder.id, breed_id=test_breed.id, location_id=loc.id, name="Daisy",
              gender="Female", image_path=_put(storage_root, "app/legacy_daisy.jpg", b"legacy"))
    sire = Pet(user_id=test_breeder.id, breed_id=test_breed.id, location_id=loc.id, name="Duke", gender="Male")
    gone = Pet(user_id=test_breeder.id, name="Old Rex", gender="Male", is_deleted=True)
    async_session.add_all([dam, sire, gone])
    await async_session.flush()

    async_session.add_all([
        PetImage(pet_id=dam.id, image_path=_put(storage_root, "app/daisy1.jpg", b"img1"),
                 image_file_name="daisy.jpg", display_order=0, is_primary=True),
        Document(entity_type="pet", entity_id=dam.id, file_path=_put(storage_root, "app/doc_daisy.pdf", b"%PDF"),
                 file_name="Daisy health.pdf", file_type="application/pdf", file_size=4),
        Document(entity_type="pet", entity_id=gone.id, file_path=_put(storage_root, "app/doc_rex.pdf", b"%PDF"),
                 file_name="Rex papers.pdf", file_type="application/pdf", file_size=4),
        BreedingPet(breeding_id=test_breeding.id, pet_id=dam.id),
        BreedingPet(breeding_id=test_breeding.id, pet_id=sire.id),
        BreedingMating(breeding_id=test_breeding.id, mated_on=date(2024, 1, 1), method="natural", sire_id=sire.id),
        BreedingProgesteroneTest(breeding_id=test_breeding.id, tested_on=date(2023, 12, 30),
                                 value_ng_ml=Decimal("5.2")),
        BreedingMilestone(breeding_id=test_breeding.id, title="X-ray", due_on=date(2024, 2, 15)),
    ])
    pup = Offspring(breeding_id=test_breeding.id, user_id=test_breeder.id, breed_id=test_breed.id,
                    mother_id=dam.id, father_id=sire.id, name="Biscuit", gender="Male",
                    date_of_birth=date(2024, 3, 1), status="Sold", price=Decimal("1500"))
    async_session.add(pup)
    await async_session.flush()
    async_session.add(OffspringImage(offspring_id=pup.id, image_path=_put(storage_root, "app/biscuit.jpg", b"pup"),
                                     is_primary=True, display_order=0))
    await async_session.commit()
    return {"dam": dam, "sire": sire, "gone": gone, "pup": pup, "loc": loc}


async def _build(async_session, user, storage_root, tmp_path) -> tuple[zipfile.ZipFile, list[str]]:
    data = await svc.collect_export_data(async_session, user.id)
    dest = tmp_path / "out.zip"
    missing = svc.write_export_zip(data, storage_root, dest, EXPORT_DATE)
    return zipfile.ZipFile(dest), missing


@pytest.mark.asyncio
async def test_zip_contains_all_csvs_and_files(async_session, test_breeder, breedery, storage_root, tmp_path):
    zf, missing = await _build(async_session, test_breeder, storage_root, tmp_path)
    names = zf.namelist()
    for csv_name in ["locations.csv", "pets.csv", "breedings.csv", "breeding_pets.csv", "matings.csv",
                     "progesterone_tests.csv", "milestones.csv", "offspring.csv"]:
        assert ROOT + csv_name in names, csv_name
    assert ROOT + "README.txt" in names
    assert any(n.startswith(ROOT + "photos/pets/Daisy_") for n in names)
    assert sum(1 for n in names if n.startswith(ROOT + "photos/pets/Daisy_")) == 2  # pet_images + legacy
    assert any(n.startswith(ROOT + "documents/pets/Daisy_") and n.endswith("Daisy health.pdf") for n in names)
    assert any(n.startswith(ROOT + "documents/pets/Old Rex_") for n in names)  # deleted pet's files included
    assert any(n.startswith(ROOT + "photos/offspring/Biscuit_") for n in names)
    assert missing == []

    pets = _read_csv(zf, "pets.csv")
    by_name = {p["name"]: p for p in pets}
    assert by_name["Old Rex"]["deleted"] == "yes"
    assert by_name["Daisy"]["deleted"] == "no"
    assert by_name["Daisy"]["breed"] == "Test Breed"
    assert by_name["Daisy"]["location"] == "Home Kennel"
    assert "user_id" not in pets[0] and "image_path" not in pets[0] and "error" not in pets[0]

    offspring = _read_csv(zf, "offspring.csv")
    assert offspring[0]["status"] == "Sold"
    assert offspring[0]["mother"] == "Daisy" and offspring[0]["father"] == "Duke"

    matings = _read_csv(zf, "matings.csv")
    assert matings[0]["sire"] == "Duke"

    locations = _read_csv(zf, "locations.csv")
    assert "coordinates" not in locations[0]


@pytest.mark.asyncio
async def test_photos_are_stored_uncompressed(async_session, test_breeder, breedery, storage_root, tmp_path):
    zf, _ = await _build(async_session, test_breeder, storage_root, tmp_path)
    for info in zf.infolist():
        if info.filename.endswith((".jpg", ".pdf")):
            assert info.compress_type == zipfile.ZIP_STORED
        if info.filename.endswith(".csv"):
            assert info.compress_type == zipfile.ZIP_DEFLATED


@pytest.mark.asyncio
async def test_other_users_data_excluded(async_session, test_breeder, breedery, storage_root, tmp_path):
    other = User(email="other@example.com", hashed_password="x", name="Other", is_active=True, is_breeder=True)
    async_session.add(other)
    await async_session.flush()
    async_session.add(Pet(user_id=other.id, name="Stranger", gender="Male"))
    await async_session.commit()

    zf, _ = await _build(async_session, test_breeder, storage_root, tmp_path)
    assert "Stranger" not in {p["name"] for p in _read_csv(zf, "pets.csv")}


@pytest.mark.asyncio
async def test_missing_file_listed_in_readme(async_session, test_breeder, breedery, storage_root, tmp_path):
    async_session.add(Document(entity_type="pet", entity_id=breedery["dam"].id, file_path="app/gone.pdf",
                               file_name="Lost contract.pdf", file_type="application/pdf", file_size=1))
    await async_session.commit()

    zf, missing = await _build(async_session, test_breeder, storage_root, tmp_path)
    assert any("Lost contract.pdf" in m for m in missing)
    assert "Lost contract.pdf" in zf.read(ROOT + "README.txt").decode("utf-8")


def test_safe_name():
    assert "/" not in svc.safe_name("../a/b", "x")
    assert ".." not in svc.safe_name("../a/b", "x")
    assert svc.safe_name("", "pet") == "pet"
    assert svc.safe_name(None, "pet") == "pet"
    assert svc.safe_name("..", "pet") == "pet"
    assert svc.safe_name("Bella\x00\n", "pet") == "Bella"


@pytest.mark.asyncio
async def test_duplicate_file_names_are_deduplicated(async_session, test_breeder, breedery, storage_root, tmp_path):
    dam = breedery["dam"]
    for _ in range(2):
        async_session.add(Document(entity_type="pet", entity_id=dam.id,
                                   file_path=_put(storage_root, f"app/{uuid.uuid4()}.pdf", b"%PDF"),
                                   file_name="../../same.pdf", file_type="application/pdf", file_size=4))
    await async_session.commit()

    zf, _ = await _build(async_session, test_breeder, storage_root, tmp_path)
    docs = [n for n in zf.namelist() if n.startswith(ROOT + "documents/pets/Daisy_")]
    assert len(docs) == len(set(docs)) == 3
    assert all(".." not in n for n in zf.namelist())


@pytest.mark.asyncio
async def test_run_export_marks_ready(async_session, test_breeder, breedery, storage_root, tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_storage_root", lambda: storage_root)
    monkeypatch.setattr(svc, "_allowed_root", lambda: storage_root)
    monkeypatch.setattr(svc, "_export_dir", lambda: tmp_path / "exports")
    export = DataExport(user_id=test_breeder.id)
    async_session.add(export)
    await async_session.commit()

    await svc.run_export(export.id, _factory(async_session))

    await async_session.refresh(export)
    assert export.status == "ready"
    assert export.file_size and export.file_size > 0
    assert Path(export.file_path).is_file()
    assert Path(export.file_path).is_relative_to(tmp_path / "exports")
    assert export.expires_at - export.completed_at == timedelta(hours=24)


@pytest.mark.asyncio
async def test_run_export_marks_failed(async_session, test_breeder, storage_root, tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_storage_root", lambda: storage_root)
    monkeypatch.setattr(svc, "_allowed_root", lambda: storage_root)
    monkeypatch.setattr(svc, "_export_dir", lambda: tmp_path / "exports")

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(svc, "write_export_zip", boom)
    export = DataExport(user_id=test_breeder.id)
    async_session.add(export)
    await async_session.commit()

    await svc.run_export(export.id, _factory(async_session))

    await async_session.refresh(export)
    assert export.status == "failed"
    assert export.error
    assert export.file_path is None
    assert not any((tmp_path / "exports").glob("*"))


@pytest.mark.asyncio
async def test_sweep_expires_files_and_fails_stale_jobs(async_session, test_breeder, tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    old_file = tmp_path / "old.zip"
    old_file.write_bytes(b"zip")
    expired = DataExport(user_id=test_breeder.id, status="ready", file_path=str(old_file),
                         file_size=3, completed_at=now - timedelta(hours=30), expires_at=now - timedelta(hours=6))
    stale = DataExport(user_id=test_breeder.id, status="running", created_at=now - timedelta(hours=2))
    async_session.add_all([expired, stale])
    await async_session.commit()

    await svc.sweep_exports(_factory(async_session), startup=True)

    await async_session.refresh(expired)
    await async_session.refresh(stale)
    assert not old_file.exists()
    assert expired.file_path is None
    assert stale.status == "failed"


def _factory(session: AsyncSession):
    """A session factory that hands out the test session (job code uses `async with factory() as s`)."""
    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    return lambda: _Ctx()


@pytest.mark.asyncio
async def test_same_file_in_gallery_and_legacy_photo_exported_once(async_session, test_breeder, storage_root, tmp_path):
    """Uploading a pet photo writes it to pet_images AND pets.image_path; export it once."""
    rel = _put(storage_root, "app/shared.jpg", b"img")
    pet = Pet(user_id=test_breeder.id, name="Solo", gender="Female", image_path=rel)
    async_session.add(pet)
    await async_session.flush()
    async_session.add(PetImage(pet_id=pet.id, image_path=rel, image_file_name="shared.jpg",
                               display_order=0, is_primary=True))
    await async_session.commit()

    zf, _ = await _build(async_session, test_breeder, storage_root, tmp_path)
    photos = [n for n in zf.namelist() if n.startswith(ROOT + "photos/pets/Solo_")]
    assert len(photos) == 1


# ─── Final-review fixes ────────────────────────────────────────────────────────

def test_export_dir_inside_public_static_dir_is_rejected(tmp_path):
    """C1: StaticFiles serves the parent of STORAGE_PATH; the export dir must never be under it."""
    public = tmp_path / "app"
    with pytest.raises(RuntimeError):
        svc.assert_export_dir_private(public / "private" / "exports", public)
    svc.assert_export_dir_private(tmp_path / "var" / "exports", public)  # outside: fine


@pytest.mark.asyncio
async def test_files_outside_upload_dir_are_not_read(async_session, test_breeder, tmp_path):
    """I1: containment is the upload dir itself, not its (publicly broad) parent."""
    parent = tmp_path / "srv"
    uploads = parent / "uploads"
    uploads.mkdir(parents=True)
    (parent / "secret.env").write_text("SECRET=1")
    pet = Pet(user_id=test_breeder.id, name="Sneaky", gender="Male")
    async_session.add(pet)
    await async_session.flush()
    async_session.add(Document(entity_type="pet", entity_id=pet.id, file_path="secret.env",
                               file_name="secret.env", file_type="application/pdf", file_size=8))
    await async_session.commit()

    data = await svc.collect_export_data(async_session, test_breeder.id)
    missing = svc.write_export_zip(data, parent, tmp_path / "o.zip", EXPORT_DATE, allowed_root=uploads)
    names = zipfile.ZipFile(tmp_path / "o.zip").namelist()
    assert not any(n.endswith("secret.env") for n in names)
    assert any("secret.env" in m for m in missing)


@pytest.mark.asyncio
async def test_unreadable_file_is_listed_not_fatal(async_session, test_breeder, breedery, storage_root, tmp_path,
                                                   monkeypatch):
    """I7: a file deleted/unreadable between the check and the write goes to `missing`."""
    real_write = zipfile.ZipFile.write

    def flaky(self, filename, arcname=None, *a, **k):
        if str(filename).endswith("doc_daisy.pdf"):
            raise FileNotFoundError(filename)
        return real_write(self, filename, arcname, *a, **k)

    monkeypatch.setattr(zipfile.ZipFile, "write", flaky)
    zf, missing = await _build(async_session, test_breeder, storage_root, tmp_path)
    assert any("Daisy health.pdf" in m for m in missing)
    assert ROOT + "offspring.csv" in zf.namelist()


@pytest.mark.asyncio
async def test_request_sweep_does_not_fail_long_running_job(async_session, test_breeder):
    """I4a: only the startup sweep fails in-flight jobs; per-request sweeps just expire files."""
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    job = DataExport(user_id=test_breeder.id, status="running", created_at=old)
    async_session.add(job)
    await async_session.commit()

    await svc.sweep_exports(_factory(async_session), test_breeder.id)
    await async_session.refresh(job)
    assert job.status == "running"


@pytest.mark.asyncio
async def test_startup_sweep_fails_all_active_jobs_and_removes_partial_files(async_session, test_breeder, tmp_path,
                                                                             monkeypatch):
    """I4b + I5: after a restart nothing is still running, so fail every active job at once and clean up."""
    monkeypatch.setattr(svc, "_export_dir", lambda: tmp_path)
    partial = tmp_path / "partial.zip"
    partial.write_bytes(b"half")
    orphan = tmp_path / "orphan.zip"
    orphan.write_bytes(b"orphan")
    keep = tmp_path / "keep.zip"
    keep.write_bytes(b"ready")
    fresh = DataExport(user_id=test_breeder.id, status="running", file_path=str(partial))
    ready = DataExport(user_id=test_breeder.id, status="ready", file_path=str(keep),
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=5))
    async_session.add_all([fresh, ready])
    await async_session.commit()

    await svc.sweep_exports(_factory(async_session), startup=True)

    await async_session.refresh(fresh)
    assert fresh.status == "failed"
    assert fresh.file_path is None
    assert not partial.exists()
    assert not orphan.exists()
    assert keep.exists()


@pytest.mark.asyncio
async def test_run_export_records_file_path_before_writing(async_session, test_breeder, storage_root, tmp_path,
                                                           monkeypatch):
    """I5: the row points at the file while it is being written, so a sweep can find a partial file."""
    monkeypatch.setattr(svc, "_storage_root", lambda: storage_root)
    monkeypatch.setattr(svc, "_allowed_root", lambda: storage_root)
    monkeypatch.setattr(svc, "_export_dir", lambda: tmp_path / "exports")
    seen = {}
    real = svc.write_export_zip

    def spy(data, root, dest, d, **k):
        seen["file_path"] = export.file_path
        return real(data, root, dest, d, **k)

    monkeypatch.setattr(svc, "write_export_zip", spy)
    export = DataExport(user_id=test_breeder.id)
    async_session.add(export)
    await async_session.commit()
    await svc.run_export(export.id, _factory(async_session))
    assert seen["file_path"] and seen["file_path"].endswith(f"{export.id}.zip")


@pytest.mark.asyncio
async def test_run_export_discards_result_if_job_was_failed_meanwhile(async_session, test_breeder, storage_root,
                                                                      tmp_path, monkeypatch):
    """I4a: a job swept as failed while running must not flip back to ready."""
    monkeypatch.setattr(svc, "_storage_root", lambda: storage_root)
    monkeypatch.setattr(svc, "_allowed_root", lambda: storage_root)
    monkeypatch.setattr(svc, "_export_dir", lambda: tmp_path / "exports")
    real = svc.write_export_zip
    export = DataExport(user_id=test_breeder.id)
    async_session.add(export)
    await async_session.commit()

    def write_then_get_swept(data, root, dest, d, **k):
        seen["dest"] = dest
        return real(data, root, dest, d, **k)

    seen = {}
    from sqlalchemy import text

    async def fake_to_thread(fn, *a, **k):
        # Simulate another process failing the job (raw SQL, so the job's ORM object is stale)
        res = fn(*a, **k)
        await async_session.execute(text("UPDATE data_exports SET status='failed' WHERE id=:i"), {"i": export.id})
        return res

    monkeypatch.setattr(svc, "write_export_zip", write_then_get_swept)
    monkeypatch.setattr(svc.asyncio, "to_thread", fake_to_thread)
    await svc.run_export(export.id, _factory(async_session))

    await async_session.refresh(export)
    assert export.status == "failed"
    assert not seen["dest"].exists()


@pytest.mark.asyncio
async def test_only_one_active_export_per_user_at_db_level(async_session, test_breeder):
    """I6: a partial unique index makes concurrent starts impossible to double up."""
    from sqlalchemy.exc import IntegrityError

    async_session.add(DataExport(user_id=test_breeder.id, status="pending"))
    await async_session.commit()
    async_session.add(DataExport(user_id=test_breeder.id, status="running"))
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()
