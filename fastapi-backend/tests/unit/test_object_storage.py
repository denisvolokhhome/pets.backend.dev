"""Object storage layer: in-memory stand-in behaves like the S3 one, and /health reports storage."""
import pytest

from app.services import object_storage as os_mod
from app.services.object_storage import MemoryObjectStorage, ObjectNotFound, get_object_storage


def test_memory_round_trip():
    s = MemoryObjectStorage()
    s.ensure_buckets()
    s.put("photos", "storage/a.jpg", b"img", "image/jpeg")
    assert s.exists("photos", "storage/a.jpg")
    obj = s.get("photos", "storage/a.jpg")
    assert (obj.data, obj.content_type) == (b"img", "image/jpeg")
    s.delete("photos", "storage/a.jpg")
    assert not s.exists("photos", "storage/a.jpg")
    s.delete("photos", "storage/a.jpg")  # deleting a missing object is fine


def test_get_missing_raises():
    with pytest.raises(ObjectNotFound):
        MemoryObjectStorage().get("documents", "nope.pdf")


def test_buckets_are_separate():
    s = MemoryObjectStorage()
    s.put("photos", "k", b"1", "image/png")
    assert not s.exists("documents", "k")


def test_tests_use_memory_storage():
    assert isinstance(get_object_storage(), MemoryObjectStorage)


@pytest.mark.asyncio
async def test_health_ok(unauthenticated_client):
    r = await unauthenticated_client.get("/health")
    assert r.status_code == 200
    assert r.json()["storage"] == "ok"


@pytest.mark.asyncio
async def test_health_503_when_storage_unreachable(unauthenticated_client, monkeypatch):
    def boom():
        raise ConnectionError("rustfs down")

    monkeypatch.setattr(os_mod.get_object_storage(), "ping", boom)
    r = await unauthenticated_client.get("/health")
    assert r.status_code == 503
    assert r.json() == {"status": "unhealthy", "storage": "unreachable"}
