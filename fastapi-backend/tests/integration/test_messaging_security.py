"""Messaging authorization, thread reuse and abuse protections."""
import json

import bcrypt
import pytest

from app.models.message import Message
from app.models.user import User


async def _login(client, email):
    r = await client.post("/api/auth/jwt/login", data={"username": email, "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def stranger(async_session) -> User:
    user = User(
        email="stranger@example.com", name=None, is_active=True, is_verified=True, is_breeder=False,
        hashed_password=bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode(),
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def seeker_thread(unauthenticated_client, test_pet_seeker, test_offspring):
    """A private seeker → breeder conversation about the offspring."""
    h = await _login(unauthenticated_client, test_pet_seeker.email)
    r = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}", json={"message": "private secret"}, headers=h
    )
    assert r.status_code == 201
    return r.json()["thread_id"]


@pytest.mark.asyncio
async def test_stranger_cannot_post_into_or_read_someone_elses_thread(
    unauthenticated_client, stranger, test_offspring, seeker_thread
):
    h = await _login(unauthenticated_client, stranger.email)
    r = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={"message": "hi", "thread_id": seeker_thread}, headers=h,
    )
    assert r.status_code == 404
    r = await unauthenticated_client.get(f"/api/messages/threads/{seeker_thread}", headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_injected_message_does_not_grant_thread_access(
    unauthenticated_client, async_session, stranger, test_breeder, seeker_thread
):
    # Even if a stranger's message already sits in the thread (legacy data), they can't read it.
    async_session.add(Message(sender_id=stranger.id, receiver_id=test_breeder.id,
                              thread_id=seeker_thread, content="injected", is_read=False))
    await async_session.commit()
    h = await _login(unauthenticated_client, stranger.email)
    r = await unauthenticated_client.get(f"/api/messages/threads/{seeker_thread}", headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_offspring_message_receiver_is_always_the_owner(
    unauthenticated_client, stranger, test_pet_seeker, test_breeder, test_offspring
):
    h = await _login(unauthenticated_client, test_pet_seeker.email)
    r = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={"message": "hello", "receiver_id": str(stranger.id)}, headers=h,
    )
    assert r.status_code == 201
    assert r.json()["receiver_id"] == str(test_breeder.id)


@pytest.mark.asyncio
async def test_breeder_cannot_open_thread_with_self(unauthenticated_client, test_breeder, test_offspring):
    h = await _login(unauthenticated_client, test_breeder.email)
    r = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}", json={"message": "me"}, headers=h
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_breeder_reply_goes_to_the_seeker(
    unauthenticated_client, test_pet_seeker, test_breeder, test_offspring, seeker_thread
):
    h = await _login(unauthenticated_client, test_breeder.email)
    r = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}",
        json={"message": "Yes, available", "thread_id": seeker_thread}, headers=h,
    )
    assert r.status_code == 201
    assert r.json()["receiver_id"] == str(test_pet_seeker.id)
    assert r.json()["thread_id"] == seeker_thread


@pytest.mark.asyncio
async def test_new_offspring_message_without_thread_id_reuses_conversation(
    unauthenticated_client, test_pet_seeker, test_offspring, seeker_thread
):
    h = await _login(unauthenticated_client, test_pet_seeker.email)
    r = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}", json={"message": "again"}, headers=h
    )
    assert r.json()["thread_id"] == seeker_thread


@pytest.mark.asyncio
async def test_direct_replies_stay_in_one_thread(unauthenticated_client, test_pet_seeker, test_breeder):
    hs = await _login(unauthenticated_client, test_pet_seeker.email)
    hb = await _login(unauthenticated_client, test_breeder.email)
    r1 = await unauthenticated_client.post(
        "/api/messages/direct", json={"receiver_id": str(test_breeder.id), "message": "hi"}, headers=hs)
    assert r1.status_code == 201
    tid = r1.json()["thread_id"]
    # Breeder replies with the thread id; seeker sends again without one.
    r2 = await unauthenticated_client.post(
        "/api/messages/direct",
        json={"receiver_id": str(test_pet_seeker.id), "message": "hello", "thread_id": tid}, headers=hb)
    r3 = await unauthenticated_client.post(
        "/api/messages/direct", json={"receiver_id": str(test_breeder.id), "message": "again"}, headers=hs)
    assert r2.json()["thread_id"] == tid and r3.json()["thread_id"] == tid
    assert r2.json()["receiver_id"] == str(test_pet_seeker.id)
    thread = await unauthenticated_client.get(f"/api/messages/threads/{tid}", headers=hs)
    assert [m["message"] for m in thread.json()["messages"]] == ["hi", "hello", "again"]


@pytest.mark.asyncio
async def test_direct_cannot_cold_message_non_breeders(unauthenticated_client, stranger, test_pet_seeker):
    h = await _login(unauthenticated_client, stranger.email)
    r = await unauthenticated_client.post(
        "/api/messages/direct", json={"receiver_id": str(test_pet_seeker.id), "message": "spam"}, headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_direct_cannot_post_into_foreign_thread(
    unauthenticated_client, stranger, test_pet_seeker, test_breeder
):
    hs = await _login(unauthenticated_client, test_pet_seeker.email)
    tid = (await unauthenticated_client.post(
        "/api/messages/direct", json={"receiver_id": str(test_breeder.id), "message": "hi"}, headers=hs)
    ).json()["thread_id"]
    h = await _login(unauthenticated_client, stranger.email)
    r = await unauthenticated_client.post(
        "/api/messages/direct",
        json={"receiver_id": str(test_breeder.id), "message": "x", "thread_id": tid}, headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_users_cannot_fake_location_cards(unauthenticated_client, test_pet_seeker, test_offspring):
    h = await _login(unauthenticated_client, test_pet_seeker.email)
    fake = json.dumps({"__type": "location", "address": "Somewhere fake"})
    r = await unauthenticated_client.post(
        f"/api/messages/offspring/{test_offspring.id}", json={"message": fake}, headers=h)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_email_is_never_used_as_display_name(
    unauthenticated_client, stranger, test_breeder
):
    h = await _login(unauthenticated_client, stranger.email)  # stranger has no name
    r = await unauthenticated_client.post(
        "/api/messages/direct", json={"receiver_id": str(test_breeder.id), "message": "hi"}, headers=h)
    tid = r.json()["thread_id"]
    hb = await _login(unauthenticated_client, test_breeder.email)
    thread = await unauthenticated_client.get(f"/api/messages/threads/{tid}", headers=hb)
    assert stranger.email not in json.dumps(thread.json())
    listing = await unauthenticated_client.get("/api/messages/", headers=hb)
    assert stranger.email not in json.dumps(listing.json())


@pytest.mark.asyncio
async def test_unread_filter_excludes_own_sent_messages(
    unauthenticated_client, test_pet_seeker, test_offspring, seeker_thread
):
    h = await _login(unauthenticated_client, test_pet_seeker.email)
    r = await unauthenticated_client.get("/api/messages/?status=unread", headers=h)
    assert r.json()["total"] == 0
