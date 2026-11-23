"""Documents are private: owner, plus participants of chats where they were shared, via 15-minute signed links."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.user import User
from app.services.document_access import sign_document_url


async def _login(client: AsyncClient, email: str) -> dict:
    r = await client.post("/api/auth/jwt/login", data={"username": email, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _upload(client, headers, offspring_id, name="health.pdf", data=b"%PDF-1.4 cert") -> dict:
    r = await client.post(f"/api/offsprings/{offspring_id}/documents", headers=headers,
                          files={"file": (name, data, "application/pdf")})
    assert r.status_code == 201, r.text
    return r.json()


async def _thread(session: AsyncSession, seeker: User, breeder: User, offspring_id) -> uuid.UUID:
    tid = uuid.uuid4()
    session.add(Message(sender_id=seeker.id, receiver_id=breeder.id, thread_id=tid, content="Hi",
                        context_type="offspring", context_id=offspring_id))
    await session.commit()
    return tid


async def _user(session, email, **kw) -> User:
    u = User(email=email, name=email.split("@")[0], is_active=True, is_verified=True,
             hashed_password=bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode(), **kw)
    session.add(u)
    await session.commit()
    return u


@pytest.fixture
def ids(test_breeder, test_pet_seeker, test_offspring):
    # Capture plain values up front; ORM objects can expire during requests.
    return {"breeder": test_breeder.email, "seeker": test_pet_seeker.email, "offspring": test_offspring.id}


@pytest.mark.asyncio
async def test_owner_gets_signed_link_that_downloads(unauthenticated_client, ids):
    h = await _login(unauthenticated_client, ids["breeder"])
    uploaded = await _upload(unauthenticated_client, h, ids["offspring"])
    url = uploaded["file_url"]
    assert url.startswith(f"/api/documents/download/{uploaded['id']}?")
    assert {"exp", "sig"} <= set(parse_qs(urlparse(url).query))

    listed = (await unauthenticated_client.get(f"/api/offsprings/{ids['offspring']}/documents", headers=h)).json()
    assert listed[0]["file_url"].startswith(f"/api/documents/download/{uploaded['id']}?")

    r = await unauthenticated_client.get(url)  # no auth: the signature is the permission
    assert r.status_code == 200
    assert r.content == b"%PDF-1.4 cert"
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["content-disposition"] == 'inline; filename="health.pdf"'


@pytest.mark.asyncio
async def test_tampered_expired_and_unknown_links(unauthenticated_client, ids):
    h = await _login(unauthenticated_client, ids["breeder"])
    doc = await _upload(unauthenticated_client, h, ids["offspring"])
    url = doc["file_url"]

    assert (await unauthenticated_client.get(url[:-4] + "0000")).status_code == 403
    other_doc = url.replace(f"/download/{doc['id']}?", f"/download/{doc['id'] + 1}?")
    assert (await unauthenticated_client.get(other_doc)).status_code == 403  # signature is per document

    old = sign_document_url(doc["id"], now=datetime.now(timezone.utc) - timedelta(seconds=901))
    assert (await unauthenticated_client.get(old)).status_code == 410

    assert (await unauthenticated_client.get(sign_document_url(999999))).status_code == 404


@pytest.mark.asyncio
async def test_link_lifetime_is_15_minutes():
    now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
    exp = int(parse_qs(urlparse(sign_document_url(7, now=now)).query)["exp"][0])
    assert exp == int(now.timestamp()) + 900


@pytest.mark.asyncio
async def test_seeker_gets_links_for_documents_shared_in_their_thread(
        unauthenticated_client, async_session, test_breeder, test_pet_seeker, ids):
    tid = await _thread(async_session, test_pet_seeker, test_breeder, ids["offspring"])
    hb = await _login(unauthenticated_client, ids["breeder"])
    doc = await _upload(unauthenticated_client, hb, ids["offspring"])
    shared = await unauthenticated_client.post(f"/api/messages/threads/{tid}/share-documents", headers=hb)
    assert shared.status_code == 201, shared.text
    assert "file_url" not in shared.text and "/storage/" not in shared.text

    hs = await _login(unauthenticated_client, ids["seeker"])
    r = await unauthenticated_client.get(f"/api/messages/threads/{tid}/documents", headers=hs)
    assert r.status_code == 200, r.text
    (item,) = r.json()
    assert (item["id"], item["file_name"], item["file_type"]) == (doc["id"], "health.pdf", "application/pdf")
    assert (await unauthenticated_client.get(item["url"])).content == b"%PDF-1.4 cert"


@pytest.mark.asyncio
async def test_deleting_the_share_message_or_the_document_revokes_access(
        unauthenticated_client, async_session, test_breeder, test_pet_seeker, ids):
    tid = await _thread(async_session, test_pet_seeker, test_breeder, ids["offspring"])
    hb = await _login(unauthenticated_client, ids["breeder"])
    d1 = await _upload(unauthenticated_client, hb, ids["offspring"], "a.pdf")
    await _upload(unauthenticated_client, hb, ids["offspring"], "b.pdf")
    share = (await unauthenticated_client.post(f"/api/messages/threads/{tid}/share-documents", headers=hb)).json()
    hs = await _login(unauthenticated_client, ids["seeker"])

    r = await unauthenticated_client.delete(f"/api/offsprings/{ids['offspring']}/documents/{d1['id']}", headers=hb)
    assert r.status_code == 204
    names = [d["file_name"] for d in (await unauthenticated_client.get(
        f"/api/messages/threads/{tid}/documents", headers=hs)).json()]
    assert names == ["b.pdf"]

    msg = await async_session.get(Message, uuid.UUID(share["id"]))
    msg.soft_delete()
    await async_session.commit()
    r = await unauthenticated_client.get(f"/api/messages/threads/{tid}/documents", headers=hs)
    assert r.json() == []


@pytest.mark.asyncio
async def test_stranger_cannot_list_thread_documents(
        unauthenticated_client, async_session, test_breeder, test_pet_seeker, ids):
    tid = await _thread(async_session, test_pet_seeker, test_breeder, ids["offspring"])
    await _user(async_session, "stranger@example.com")
    h = await _login(unauthenticated_client, "stranger@example.com")
    assert (await unauthenticated_client.get(f"/api/messages/threads/{tid}/documents", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_old_share_messages_resolve_by_document_id(
        unauthenticated_client, async_session, test_breeder, test_pet_seeker, ids):
    tid = await _thread(async_session, test_pet_seeker, test_breeder, ids["offspring"])
    hb = await _login(unauthenticated_client, ids["breeder"])
    doc = await _upload(unauthenticated_client, hb, ids["offspring"])
    old_card = {"__type": "documents", "offspring_name": "Pup", "documents": [
        {"id": doc["id"], "file_name": "health.pdf", "file_type": "application/pdf", "file_size": 13,
         "file_url": "/storage/app/doc_old.pdf"}]}
    async_session.add(Message(sender_id=test_breeder.id, receiver_id=test_pet_seeker.id, thread_id=tid,
                              content=json.dumps(old_card), context_type="offspring", context_id=ids["offspring"]))
    await async_session.commit()

    hs = await _login(unauthenticated_client, ids["seeker"])
    (item,) = (await unauthenticated_client.get(f"/api/messages/threads/{tid}/documents", headers=hs)).json()
    assert item["url"].startswith(f"/api/documents/download/{doc['id']}?")


@pytest.mark.asyncio
async def test_card_written_by_someone_other_than_the_owner_grants_nothing(
        unauthenticated_client, async_session, test_breeder, test_pet_seeker, ids):
    tid = await _thread(async_session, test_pet_seeker, test_breeder, ids["offspring"])
    hb = await _login(unauthenticated_client, ids["breeder"])
    doc = await _upload(unauthenticated_client, hb, ids["offspring"])
    forged = {"__type": "documents", "documents": [{"id": doc["id"], "file_name": "x"}]}
    async_session.add(Message(sender_id=test_pet_seeker.id, receiver_id=test_breeder.id, thread_id=tid,
                              content=json.dumps(forged), context_type="offspring", context_id=ids["offspring"]))
    await async_session.commit()

    hs = await _login(unauthenticated_client, ids["seeker"])
    assert (await unauthenticated_client.get(f"/api/messages/threads/{tid}/documents", headers=hs)).json() == []


@pytest.mark.asyncio
async def test_documents_are_not_served_from_storage_urls(unauthenticated_client, ids):
    h = await _login(unauthenticated_client, ids["breeder"])
    doc = await _upload(unauthenticated_client, h, ids["offspring"])
    from app.models.document import Document  # noqa: F401 — key lookup below
    from app.services.object_storage import documents_bucket, get_object_storage
    keys = [k for (b, k) in get_object_storage()._objects if b == documents_bucket()]
    assert keys and all(k.startswith("doc_") for k in keys)
    for key in keys:
        for prefix in ("app", "storage"):
            assert (await unauthenticated_client.get(f"/storage/{prefix}/{key}")).status_code == 404
    assert doc["id"]
