"""Integration tests for the data export API (background job + short-lived download links)."""
import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_export import DataExport
from app.models.user import User
from app.services import data_export_service as svc


async def _token(client: AsyncClient, user: User) -> dict:
    r = await client.post("/api/auth/jwt/login", data={"username": user.email, "password": "testpass123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _factory(session: AsyncSession):
    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    return lambda: _Ctx()


@pytest.fixture
def export_env(async_session: AsyncSession, tmp_path: Path, monkeypatch):
    """Run export jobs against the test session and a temp private dir."""
    from app.main import app
    from app.routers.exports import get_export_session_factory

    (tmp_path / "storage").mkdir()
    monkeypatch.setattr(svc, "_storage_root", lambda: tmp_path / "storage")
    monkeypatch.setattr(svc, "_export_dir", lambda: tmp_path / "exports")
    app.dependency_overrides[get_export_session_factory] = lambda: _factory(async_session)
    yield tmp_path
    app.dependency_overrides.pop(get_export_session_factory, None)


@pytest.mark.asyncio
async def test_non_breeder_forbidden(unauthenticated_client, test_pet_seeker, export_env):
    h = await _token(unauthenticated_client, test_pet_seeker)
    assert (await unauthenticated_client.post("/api/exports", headers=h)).status_code == 403
    assert (await unauthenticated_client.get("/api/exports/latest", headers=h)).status_code == 403


@pytest.mark.asyncio
async def test_requires_auth(unauthenticated_client, export_env):
    assert (await unauthenticated_client.post("/api/exports")).status_code == 401


@pytest.mark.asyncio
async def test_latest_is_null_before_any_export(unauthenticated_client, test_breeder, export_env):
    h = await _token(unauthenticated_client, test_breeder)
    r = await unauthenticated_client.get("/api/exports/latest", headers=h)
    assert r.status_code == 200
    assert r.json() is None


@pytest.mark.asyncio
async def test_post_returns_existing_running_export(unauthenticated_client, async_session, test_breeder, export_env):
    running = DataExport(user_id=test_breeder.id, status="running")
    async_session.add(running)
    await async_session.commit()

    h = await _token(unauthenticated_client, test_breeder)
    r = await unauthenticated_client.post("/api/exports", headers=h)
    assert r.status_code == 202
    assert r.json()["id"] == str(running.id)
    assert r.json()["status"] == "running"


@pytest.mark.asyncio
async def test_full_flow_export_link_download(unauthenticated_client, async_session, test_breeder, test_offspring,
                                              export_env):
    h = await _token(unauthenticated_client, test_breeder)
    r = await unauthenticated_client.post("/api/exports", headers=h)
    assert r.status_code == 202
    export_id = r.json()["id"]

    latest = (await unauthenticated_client.get("/api/exports/latest", headers=h)).json()
    assert latest["id"] == export_id
    assert latest["status"] == "ready"
    assert latest["file_size"] > 0
    assert latest["is_expired"] is False
    assert "file_path" not in latest

    link = await unauthenticated_client.post(f"/api/exports/{export_id}/download-link", headers=h)
    assert link.status_code == 200
    url = link.json()["url"]
    assert url.startswith("/api/exports/download/")

    dl = await unauthenticated_client.get(url)  # no auth header
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/zip"
    assert "attachment" in dl.headers["content-disposition"]
    assert "breedly-export-" in dl.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(dl.content))
    assert any(n.endswith("offspring.csv") for n in zf.namelist())

    # Still usable for resume within the hour after first use
    again = await unauthenticated_client.get(url, headers={"Range": "bytes=0-9"})
    assert again.status_code in (200, 206)


@pytest.mark.asyncio
async def test_new_export_replaces_previous_file(unauthenticated_client, async_session, test_breeder, export_env):
    h = await _token(unauthenticated_client, test_breeder)
    first = (await unauthenticated_client.post("/api/exports", headers=h)).json()
    first_row = await async_session.get(DataExport, first["id"])
    first_file = Path(first_row.file_path)
    assert first_file.exists()

    second = (await unauthenticated_client.post("/api/exports", headers=h)).json()
    assert second["id"] != first["id"]
    assert not first_file.exists()


@pytest.mark.asyncio
async def test_unused_token_expires_after_60s(unauthenticated_client, async_session, test_breeder, export_env):
    h = await _token(unauthenticated_client, test_breeder)
    export_id = (await unauthenticated_client.post("/api/exports", headers=h)).json()["id"]
    url = (await unauthenticated_client.post(f"/api/exports/{export_id}/download-link", headers=h)).json()["url"]

    row = await async_session.get(DataExport, export_id)
    assert row.download_token_expires_at - datetime.now(timezone.utc) <= timedelta(seconds=60)
    row.download_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await async_session.commit()

    assert (await unauthenticated_client.get(url)).status_code == 404


@pytest.mark.asyncio
async def test_used_token_valid_for_one_hour(unauthenticated_client, async_session, test_breeder, export_env):
    h = await _token(unauthenticated_client, test_breeder)
    export_id = (await unauthenticated_client.post("/api/exports", headers=h)).json()["id"]
    url = (await unauthenticated_client.post(f"/api/exports/{export_id}/download-link", headers=h)).json()["url"]
    assert (await unauthenticated_client.get(url)).status_code == 200

    row = await async_session.get(DataExport, export_id)
    await async_session.refresh(row)
    assert row.download_token_used_at is not None
    lifetime = row.download_token_expires_at - row.download_token_used_at
    assert timedelta(minutes=59) < lifetime <= timedelta(hours=1)


@pytest.mark.asyncio
async def test_new_link_invalidates_old_one(unauthenticated_client, test_breeder, export_env):
    h = await _token(unauthenticated_client, test_breeder)
    export_id = (await unauthenticated_client.post("/api/exports", headers=h)).json()["id"]
    old = (await unauthenticated_client.post(f"/api/exports/{export_id}/download-link", headers=h)).json()["url"]
    new = (await unauthenticated_client.post(f"/api/exports/{export_id}/download-link", headers=h)).json()["url"]
    assert old != new
    assert (await unauthenticated_client.get(old)).status_code == 404
    assert (await unauthenticated_client.get(new)).status_code == 200


@pytest.mark.asyncio
async def test_bogus_token_404(unauthenticated_client, export_env):
    assert (await unauthenticated_client.get("/api/exports/download/not-a-real-token")).status_code == 404


@pytest.mark.asyncio
async def test_other_users_export_404(unauthenticated_client, async_session, test_breeder, export_env):
    import bcrypt

    other = User(email="other-breeder@example.com", name="Other",
                 hashed_password=bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode(),
                 is_active=True, is_verified=True, is_breeder=True)
    async_session.add(other)
    await async_session.commit()

    h_owner = await _token(unauthenticated_client, test_breeder)
    export_id = (await unauthenticated_client.post("/api/exports", headers=h_owner)).json()["id"]

    h_other = await _token(unauthenticated_client, other)
    r = await unauthenticated_client.post(f"/api/exports/{export_id}/download-link", headers=h_other)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_expired_export_410(unauthenticated_client, async_session, test_breeder, export_env):
    h = await _token(unauthenticated_client, test_breeder)
    export_id = (await unauthenticated_client.post("/api/exports", headers=h)).json()["id"]
    row = await async_session.get(DataExport, export_id)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await async_session.commit()

    r = await unauthenticated_client.post(f"/api/exports/{export_id}/download-link", headers=h)
    assert r.status_code == 410
    latest = (await unauthenticated_client.get("/api/exports/latest", headers=h)).json()
    assert latest["is_expired"] is True
