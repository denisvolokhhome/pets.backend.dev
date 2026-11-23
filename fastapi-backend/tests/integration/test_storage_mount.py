"""The /storage static mount must serve uploads only, never the tree around them.

In production STORAGE_PATH=/app/storage, and the mount used to serve its parent (/app):
the whole source tree (e.g. /storage/app/config.py) was publicly downloadable.
"""
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import settings
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def upload_dir() -> Path:
    d = Path(settings.storage_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.mark.asyncio
async def test_uploaded_file_is_served_at_its_existing_url(client, upload_dir):
    """URLs are /storage/<path relative to the parent of STORAGE_PATH>; they must keep working."""
    name = f"mount_test_{uuid.uuid4().hex}.txt"
    f = upload_dir / name
    f.write_text("hello")
    try:
        rel = f.relative_to(upload_dir.parent).as_posix()  # e.g. "app/<name>" in dev, "storage/<name>" in prod
        r = await client.get(f"/storage/{rel}")
        assert r.status_code == 200
        assert r.text == "hello"
    finally:
        f.unlink()


@pytest.mark.asyncio
async def test_files_next_to_the_upload_dir_are_not_served(client, upload_dir):
    """Anything in the upload dir's parent (in prod: the app source tree) must 404."""
    name = f"secret_{uuid.uuid4().hex}.py"
    secret = upload_dir.parent / name
    secret.write_text("SECRET_KEY = 'x'")
    try:
        r = await client.get(f"/storage/{name}")
        assert r.status_code == 404
    finally:
        secret.unlink()


@pytest.mark.asyncio
async def test_sibling_directory_of_upload_dir_is_not_served(client, upload_dir):
    sibling = upload_dir.parent / f"sibling_{uuid.uuid4().hex}"
    sibling.mkdir()
    (sibling / "config.py").write_text("DB_PASSWORD = 'x'")
    try:
        r = await client.get(f"/storage/{sibling.name}/config.py")
        assert r.status_code == 404
    finally:
        (sibling / "config.py").unlink()
        sibling.rmdir()


@pytest.mark.asyncio
async def test_traversal_out_of_upload_dir_is_not_served(client, upload_dir):
    name = f"secret_{uuid.uuid4().hex}.py"
    secret = upload_dir.parent / name
    secret.write_text("x")
    try:
        r = await client.get(f"/storage/{upload_dir.name}/../{name}")
        assert r.status_code == 404
        r = await client.get(f"/storage/{upload_dir.name}/%2e%2e/{name}")
        assert r.status_code == 404
    finally:
        secret.unlink()


# ── Photos now live in object storage; the same URLs serve them from the bucket ──

def _put_photo(key: str, data: bytes = b"\xff\xd8jpeg", content_type: str = "image/jpeg") -> None:
    from app.services.object_storage import get_object_storage, photos_bucket
    get_object_storage().put(photos_bucket(), key, data, content_type)


@pytest.mark.asyncio
async def test_photo_in_bucket_is_served_with_long_cache(client, upload_dir):
    key = f"{upload_dir.name}/pet_{uuid.uuid4().hex}.jpg"
    _put_photo(key, b"\xff\xd8photo")
    r = await client.get(f"/storage/{key}")
    assert r.status_code == 200
    assert r.content == b"\xff\xd8photo"
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


@pytest.mark.asyncio
async def test_documents_are_never_served_on_the_photo_route(client, upload_dir):
    name = f"doc_{uuid.uuid4()}_{uuid.uuid4()}.pdf"
    _put_photo(f"{upload_dir.name}/{name}", b"%PDF", "application/pdf")
    local = upload_dir / name  # a pre-migration local document copy
    local.write_bytes(b"%PDF")
    try:
        r = await client.get(f"/storage/{upload_dir.name}/{name}")
        assert r.status_code == 404
    finally:
        local.unlink()


@pytest.mark.asyncio
async def test_unknown_photo_is_404(client, upload_dir):
    r = await client.get(f"/storage/{upload_dir.name}/nope_{uuid.uuid4().hex}.jpg")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_photo_answers_head_requests(client, upload_dir):
    """Link-preview scrapers send HEAD; the old static mount answered it."""
    key = f"{upload_dir.name}/pet_{uuid.uuid4().hex}.jpg"
    _put_photo(key, b"\xff\xd8photo")
    r = await client.head(f"/storage/{key}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
