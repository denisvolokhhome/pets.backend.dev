"""Pet import router for CSV bulk import of pet records."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_breeder
from app.models.user import User
from app.schemas.pet_import import ImportPayload, ImportResult
from app.services.pet_import_service import pet_import_service

router = APIRouter(prefix="/api/pets", tags=["pets"])


@router.post("/import", response_model=ImportResult)
async def import_pets(
    payload: ImportPayload,
    user: User = Depends(require_breeder),
    session: AsyncSession = Depends(get_async_session),
) -> ImportResult:
    """Bulk-import pets from parsed CSV data.

    Accepts a JSON array of pet rows (max 500), validates each row,
    resolves breed/location names, enforces billing limits, and
    batch-creates pet records.
    """
    return await pet_import_service.import_pets(
        session=session,
        user_id=user.id,
        pets_data=payload.pets,
    )
