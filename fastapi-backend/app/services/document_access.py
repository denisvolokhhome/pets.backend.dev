"""Private documents: who may open them, and short-lived signed download links.

Access is decided when a link is handed out:
- the owner (breeder of the pet/offspring) gets links from the documents list;
- a chat participant gets links for documents the owner shared in that chat
  (a non-deleted "documents" card message sent by the owner).
The link itself is the permission: HMAC-signed, valid for 15 minutes.
"""
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.document import Document
from app.models.message import Message
from app.models.offspring import Offspring
from app.models.pet import Pet

LINK_LIFETIME_SECONDS = 900


def _signature(doc_id: int, exp: int) -> str:
    key = Settings().secret_key.encode()
    return hmac.new(key, f"{doc_id}.{exp}".encode(), hashlib.sha256).hexdigest()


def sign_document_url(doc_id: int, now: Optional[datetime] = None) -> str:
    """Host-relative download URL valid for 15 minutes."""
    issued = int(now.timestamp()) if now else int(time.time())
    exp = issued + LINK_LIFETIME_SECONDS
    return f"/api/documents/download/{doc_id}?exp={exp}&sig={_signature(doc_id, exp)}"


def check_signature(doc_id: int, exp: int, sig: str) -> str:
    """'ok', 'invalid' or 'expired'. The signature is checked before the expiry."""
    if not hmac.compare_digest(_signature(doc_id, exp), sig or ""):
        return "invalid"
    if exp < int(time.time()):
        return "expired"
    return "ok"


def document_payload(doc: Document) -> dict:
    """The JSON shape the frontend gets for a document the caller may open."""
    return {
        "id": doc.id,
        "file_name": doc.file_name,
        "file_type": doc.file_type,
        "file_size": doc.file_size,
        "file_url": sign_document_url(doc.id),
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


async def document_owner_ids(session: AsyncSession, docs: list[Document]) -> dict[int, uuid.UUID]:
    """Map document id -> owner user id (the breeder of its pet or offspring)."""
    pet_ids = {d.entity_id for d in docs if d.entity_type == "pet"}
    pup_ids = {d.entity_id for d in docs if d.entity_type == "offspring"}
    owners: dict[tuple[str, uuid.UUID], uuid.UUID] = {}
    if pet_ids:
        for pid, uid in (await session.execute(select(Pet.id, Pet.user_id).where(Pet.id.in_(pet_ids)))).all():
            owners[("pet", pid)] = uid
    if pup_ids:
        rows = (await session.execute(select(Offspring.id, Offspring.user_id).where(Offspring.id.in_(pup_ids)))).all()
        for oid, uid in rows:
            owners[("offspring", oid)] = uid
    return {d.id: owners[(d.entity_type, d.entity_id)] for d in docs if (d.entity_type, d.entity_id) in owners}


def _card_document_ids(content: str) -> list[int]:
    try:
        card = json.loads(content)
    except (ValueError, TypeError):
        return []
    if not isinstance(card, dict) or card.get("__type") != "documents":
        return []
    ids = []
    for item in card.get("documents") or []:
        if isinstance(item, dict) and isinstance(item.get("id"), int):
            ids.append(item["id"])
    return ids


async def shared_documents_in_thread(session: AsyncSession, thread_id: uuid.UUID) -> list[Document]:
    """Documents the owner shared in this thread (non-deleted cards, documents that still exist)."""
    messages = (await session.execute(
        select(Message).where(Message.thread_id == thread_id, Message.deleted_at.is_(None))
        .order_by(Message.created_at.asc())
    )).scalars().all()

    wanted: list[tuple[int, uuid.UUID]] = []  # (document id, card sender)
    for m in messages:
        wanted.extend((doc_id, m.sender_id) for doc_id in _card_document_ids(m.content))
    if not wanted:
        return []

    docs = {d.id: d for d in (await session.execute(
        select(Document).where(Document.id.in_({doc_id for doc_id, _ in wanted}))
    )).scalars().all()}
    owners = await document_owner_ids(session, list(docs.values()))

    result: list[Document] = []
    seen: set[int] = set()
    for doc_id, sender in wanted:
        doc = docs.get(doc_id)
        if doc is None or doc_id in seen or owners.get(doc_id) != sender:
            continue  # deleted, duplicate, or a card written by someone other than the owner
        seen.add(doc_id)
        result.append(doc)
    return result
