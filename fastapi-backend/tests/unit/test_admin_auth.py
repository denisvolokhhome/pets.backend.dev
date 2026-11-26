"""The admin API guard: key check, and invisible to traffic from the Cloudflare tunnel."""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import admin_auth


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(admin_auth.settings, "admin_api_key", "s3cret")
    app = FastAPI()

    @app.get("/api/admin/ping")
    async def ping(_: bool = Depends(admin_auth.verify_admin_key)):
        return {"ok": True}

    return TestClient(app)


def test_valid_key_from_internal_network_is_allowed(client):
    assert client.get("/api/admin/ping", headers={"X-Admin-Key": "s3cret"}).status_code == 200


def test_wrong_or_missing_key_is_forbidden(client):
    assert client.get("/api/admin/ping", headers={"X-Admin-Key": "nope"}).status_code == 403
    assert client.get("/api/admin/ping").status_code == 403


def test_request_through_cloudflare_is_not_found_even_with_valid_key(client):
    resp = client.get("/api/admin/ping", headers={"X-Admin-Key": "s3cret", "CF-Connecting-IP": "203.0.113.7"})
    assert resp.status_code == 404


def test_unset_key_disables_admin_api(client, monkeypatch):
    monkeypatch.setattr(admin_auth.settings, "admin_api_key", "")
    assert client.get("/api/admin/ping", headers={"X-Admin-Key": ""}).status_code == 403
