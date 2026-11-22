"""Existing local uploads move into object storage at startup (idempotent)."""
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.pet import Pet
from app.services.object_storage import documents_bucket, get_object_storage, photos_bucket
from app.services.storage_migration import migrate_local_files


def _factory(session: AsyncSession):
    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    return lambda: _Ctx()


@pytest.fixture
def upload_dir(tmp_path: Path) -> Path:
    d = tmp_path / "storage"  # prod layout: STORAGE_PATH=/app/storage, stored paths "storage/<file>"
    d.mkdir()
    return d


async def _doc(session, owner, path: str) -> Document:
    pet = Pet(user_id=owner.id, name="Daisy", gender="Female")
    session.add(pet)
    await session.flush()
    doc = Document(entity_type="pet", entity_id=pet.id, file_path=path, file_name="health.pdf",
                   file_type="application/pdf", file_size=4)
    session.add(doc)
    await session.commit()
    return doc


@pytest.mark.asyncio
async def test_documents_move_to_private_bucket_and_local_copy_is_removed(async_session, test_breeder, upload_dir):
    local = upload_dir / f"doc_{uuid.uuid4()}_{uuid.uuid4()}.pdf"
    local.write_bytes(b"%PDF")
    doc = await _doc(async_session, test_breeder, f"storage/{local.name}")

    report = await migrate_local_files(_factory(async_session), get_object_storage(), upload_dir)

    await async_session.refresh(doc)
    assert report.documents_moved == 1
    assert "/" not in doc.file_path and doc.file_path.startswith("doc_")
    assert doc.file_path != local.name  # new private name
    assert get_object_storage().get(documents_bucket(), doc.file_path).data == b"%PDF"
    assert not local.exists()
    assert not get_object_storage().exists(photos_bucket(), f"storage/{local.name}")


@pytest.mark.asyncio
async def test_photos_are_copied_and_local_copies_kept(async_session, upload_dir):
    photo = upload_dir / f"{uuid.uuid4()}_{uuid.uuid4()}.jpg"
    photo.write_bytes(b"\xff\xd8img")

    report = await migrate_local_files(_factory(async_session), get_object_storage(), upload_dir)

    assert report.photos_copied == 1
    stored = get_object_storage().get(photos_bucket(), f"storage/{photo.name}")
    assert (stored.data, stored.content_type) == (b"\xff\xd8img", "image/jpeg")
    assert photo.exists()  # kept for one release (rollback safety)


@pytest.mark.asyncio
async def test_second_run_does_nothing(async_session, test_breeder, upload_dir):
    (upload_dir / "a.jpg").write_bytes(b"1")
    local_doc = upload_dir / "doc_x_y.pdf"
    local_doc.write_bytes(b"%PDF")
    await _doc(async_session, test_breeder, f"storage/{local_doc.name}")

    first = await migrate_local_files(_factory(async_session), get_object_storage(), upload_dir)
    second = await migrate_local_files(_factory(async_session), get_object_storage(), upload_dir)

    assert (first.documents_moved, first.photos_copied) == (1, 1)
    assert (second.documents_moved, second.photos_copied, second.missing) == (0, 0, [])


@pytest.mark.asyncio
async def test_missing_document_file_is_reported_not_fatal(async_session, test_breeder, upload_dir):
    doc = await _doc(async_session, test_breeder, "storage/doc_gone.pdf")

    report = await migrate_local_files(_factory(async_session), get_object_storage(), upload_dir)

    await async_session.refresh(doc)
    assert report.missing == ["storage/doc_gone.pdf"]
    assert doc.file_path == "storage/doc_gone.pdf"


@pytest.mark.asyncio
async def test_orphan_local_documents_never_become_photos(async_session, upload_dir):
    (upload_dir / "doc_orphan.pdf").write_bytes(b"%PDF")
    report = await migrate_local_files(_factory(async_session), get_object_storage(), upload_dir)
    assert report.photos_copied == 0
    assert not get_object_storage().exists(photos_bucket(), "storage/doc_orphan.pdf")


@pytest.mark.asyncio
async def test_document_path_outside_upload_dir_is_not_read(async_session, test_breeder, upload_dir):
    secret = upload_dir.parent / "secret.env"
    secret.write_text("SECRET=1")
    await _doc(async_session, test_breeder, "secret.env")
    await _doc(async_session, test_breeder, "storage/../secret.env")

    report = await migrate_local_files(_factory(async_session), get_object_storage(), upload_dir)

    assert report.documents_moved == 0
    assert secret.exists()
