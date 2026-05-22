"""
Service Categories router.

Provides a public read-only endpoint for listing active service categories.
These are used during Service Provider registration and service listing creation.
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.service_category import ServiceCategory
from app.schemas.service_category import ServiceCategoryRead


router = APIRouter(
    prefix="/api/service-categories",
    tags=["service-categories"],
    responses={},
)


@router.get("/", response_model=List[ServiceCategoryRead])
async def list_service_categories(
    session: AsyncSession = Depends(get_async_session),
) -> List[ServiceCategory]:
    """
    List all active service categories.

    This endpoint is public and does not require authentication.
    Returns all service categories where `is_active=True`, ordered alphabetically by name.

    **Returns:** List of active service categories with id, name, slug, description, icon, and is_active fields.
    """
    query = (
        select(ServiceCategory)
        .where(ServiceCategory.is_active == True)  # noqa: E712
        .order_by(ServiceCategory.name)
    )
    result = await session.execute(query)
    categories = result.scalars().all()
    return list(categories)
