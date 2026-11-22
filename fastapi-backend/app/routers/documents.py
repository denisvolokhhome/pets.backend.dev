"""Signed document downloads (no login: the signed link is the permission)."""
import asyncio
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.document import Document
from app.services.document_access import check_signature
from app.services.object_storage import ObjectNotFoundError, documents_bucket, get_object_storage

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _content_disposition(file_name: str) -> str:
    ascii_name = file_name.encode("ascii", "ignore").decode().replace('"', "").replace("\\", "") or "document"
    header = f'inline; filename="{ascii_name}"'
    if ascii_name != file_name:
        header += f"; filename*=UTF-8''{quote(file_name)}"
    return header


@router.get("/download/{doc_id}")
async def download_document(
    doc_id: int,
    exp: int = Query(...),
    sig: str = Query(...),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    verdict = check_signature(doc_id, exp, sig)
    if verdict == "invalid":
        raise HTTPException(status_code=403, detail="Invalid link")
    if verdict == "expired":
        raise HTTPException(status_code=410, detail="This link has expired. Open the document again from Breedly.")

    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        obj = await asyncio.to_thread(get_object_storage().get, documents_bucket(), doc.file_path)
    except ObjectNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found") from None

    return Response(
        content=obj.data,
        media_type=doc.file_type or obj.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": _content_disposition(doc.file_name),
        },
    )
