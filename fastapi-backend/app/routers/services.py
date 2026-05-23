"""
Services router for service provider listing management and discovery.

Provides CRUD operations for service listings, image management,
public search, and public provider profiles.
"""
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_async_session
from app.dependencies import current_active_user, require_service_provider
from app.models.user import User
from app.schemas.service import (
    PublicProviderProfile,
    ServiceCreate,
    ServiceImageRead,
    ServiceListResponse,
    ServiceRead,
    ServiceUpdate,
)
from app.services import service_provider_service
from app.services.file_service import FileService


router = APIRouter(
    prefix="/api/services",
    tags=["services"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized to access this resource"},
        404: {"description": "Service not found"},
    },
)


def get_file_service() -> FileService:
    """Dependency to get FileService instance."""
    settings = Settings()
    return FileService(settings)


# ─── Static routes MUST come before parameterised routes ─────────────────────


@router.get("/search")
async def search_services(
    session: AsyncSession = Depends(get_async_session),
    category_slug: Optional[str] = Query(None, description="Filter by service category slug"),
    latitude: Optional[float] = Query(None, description="Latitude of the search centre"),
    longitude: Optional[float] = Query(None, description="Longitude of the search centre"),
    radius_km: float = Query(50.0, description="Search radius in kilometres"),
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page (max 100)"),
) -> dict:
    """
    Search for service providers.

    Public endpoint — no authentication required.

    Results are grouped by provider (one result per user). When latitude,
    longitude, and radius_km are provided, results are ordered by distance
    ascending; otherwise by created_at descending. Providers whose every
    service is inactive are excluded.

    **Query Parameters:**
    - category_slug: Filter by service category slug (e.g. "grooming")
    - latitude / longitude: Centre of the geo search
    - radius_km: Search radius in km (default 50)
    - page: Page number (default 1)
    - page_size: Results per page, max 100 (default 20)
    """
    return await service_provider_service.search_services(
        db=session,
        category_slug=category_slug,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        page=page,
        page_size=page_size,
    )


@router.get("/provider/{user_id}/public", response_model=PublicProviderProfile)
async def get_public_provider_profile(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> PublicProviderProfile:
    """
    Get the public profile for a service provider.

    Public endpoint — no authentication required.

    Returns provider details, active services, and locations.

    **Path Parameters:**
    - user_id: UUID of the service provider
    """
    return await service_provider_service.get_public_provider_profile(
        user_id=user_id,
        db=session,
    )


# ─── Authenticated CRUD routes ────────────────────────────────────────────────


@router.get("", response_model=ServiceListResponse)
async def list_services(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> ServiceListResponse:
    """
    List all non-deleted services owned by the authenticated user.

    **Returns:** Paginated list of services with category and image data.
    """
    return await service_provider_service.list_services(
        user_id=user.id,
        db=session,
    )


@router.post("", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: ServiceCreate,
    user: User = Depends(require_service_provider),
    session: AsyncSession = Depends(get_async_session),
) -> ServiceRead:
    """
    Create a new service listing.

    Requires a service provider account. Validates that the category exists
    and that all provided location IDs are owned by the authenticated user.

    **Returns:** The created service record.
    """
    return await service_provider_service.create_service(
        user_id=user.id,
        payload=payload,
        db=session,
    )


@router.get("/{service_id}", response_model=ServiceRead)
async def get_service(
    service_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> ServiceRead:
    """
    Get a single service by ID.

    The service must be owned by the authenticated user.

    **Returns:** Service details with category and image data.
    """
    return await service_provider_service.get_service(
        service_id=service_id,
        user_id=user.id,
        db=session,
    )


@router.put("/{service_id}", response_model=ServiceRead)
async def update_service(
    service_id: uuid.UUID,
    payload: ServiceUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> ServiceRead:
    """
    Partially update a service listing.

    The service must be owned by the authenticated user. Only fields
    provided in the request body are applied.

    **Returns:** Updated service record.
    """
    return await service_provider_service.update_service(
        service_id=service_id,
        user_id=user.id,
        payload=payload,
        db=session,
    )


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Soft-delete a service by setting is_deleted=True.

    The service must be owned by the authenticated user.
    """
    await service_provider_service.delete_service(
        service_id=service_id,
        user_id=user.id,
        db=session,
    )


@router.post(
    "/{service_id}/images",
    response_model=ServiceImageRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_service_image(
    service_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    file_service: FileService = Depends(get_file_service),
) -> ServiceImageRead:
    """
    Upload an image for a service.

    The service must be owned by the authenticated user. The first image
    uploaded is automatically set as the primary image.

    **Returns:** Created ServiceImage record.
    """
    return await service_provider_service.upload_service_image(
        service_id=service_id,
        user_id=user.id,
        file=file,
        db=session,
        file_service=file_service,
    )


@router.delete(
    "/{service_id}/images/{img_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_service_image(
    service_id: uuid.UUID,
    img_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    file_service: FileService = Depends(get_file_service),
) -> None:
    """
    Delete a service image.

    The service must be owned by the authenticated user. If the deleted
    image was the primary image, the next image is promoted to primary.
    """
    await service_provider_service.delete_service_image(
        service_id=service_id,
        img_id=img_id,
        user_id=user.id,
        db=session,
        file_service=file_service,
    )


# ── Service Provider Categories Management ────────────────────────────────────

from pydantic import BaseModel, Field
from typing import List


class UpdateCategoriesRequest(BaseModel):
    category_ids: List[int] = Field(..., min_length=1)


@router.put("/me/categories", status_code=status.HTTP_200_OK)
async def update_my_categories(
    payload: UpdateCategoriesRequest,
    user: User = Depends(require_service_provider),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    Replace the authenticated service provider's category associations.

    Requires a service provider account. Validates that all provided
    category_ids exist and are active. Replaces existing associations.
    """
    from sqlalchemy import select, delete, insert
    from app.models.service_category import ServiceCategory, user_service_categories

    # Validate all category_ids exist and are active
    cat_result = await session.execute(
        select(ServiceCategory).where(
            ServiceCategory.id.in_(payload.category_ids),
            ServiceCategory.is_active == True,
        )
    )
    valid_categories = cat_result.scalars().all()
    valid_ids = {cat.id for cat in valid_categories}
    invalid_ids = [cid for cid in payload.category_ids if cid not in valid_ids]

    if invalid_ids:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid or inactive category_id(s): {invalid_ids}",
        )

    # Delete existing associations for this user
    await session.execute(
        delete(user_service_categories).where(
            user_service_categories.c.user_id == user.id
        )
    )

    # Insert new associations
    for category_id in payload.category_ids:
        await session.execute(
            insert(user_service_categories).values(
                user_id=user.id,
                category_id=category_id,
            )
        )

    await session.commit()

    return {
        "message": "Categories updated successfully",
        "category_ids": list(valid_ids),
    }
