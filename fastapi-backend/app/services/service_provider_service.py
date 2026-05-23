"""Service provider business logic for service listing management and discovery."""
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.location import Location
from app.models.service import Service, ServiceImage, service_locations
from app.models.service_category import ServiceCategory
from app.models.user import User
from app.schemas.service import (
    PublicProviderProfile,
    ServiceCreate,
    ServiceImageRead,
    ServiceListResponse,
    ServiceRead,
    ServiceSearchResult,
    ServiceUpdate,
)
from app.schemas.service_category import ServiceCategoryRead
from app.services.file_service import FileService


async def _fetch_service_with_ownership(
    service_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Service:
    """
    Fetch a service by ID, raising 404 if not found and 403 if not owned by user_id.

    Args:
        service_id: UUID of the service to fetch.
        user_id: UUID of the requesting user.
        db: Async database session.

    Returns:
        The Service ORM object.

    Raises:
        HTTPException 404: Service not found or soft-deleted.
        HTTPException 403: Service exists but belongs to a different user.
    """
    result = await db.execute(
        select(Service).where(
            Service.id == service_id,
            Service.is_deleted == False,  # noqa: E712
        )
    )
    service = result.scalar_one_or_none()

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )

    if service.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this service",
        )

    return service


async def list_services(user_id: UUID, db: AsyncSession) -> ServiceListResponse:
    """
    List all non-deleted services owned by the given user.

    Args:
        user_id: UUID of the service provider.
        db: Async database session.

    Returns:
        ServiceListResponse with items, total, page=1, page_size=len(items).
    """
    result = await db.execute(
        select(Service)
        .where(
            Service.user_id == user_id,
            Service.is_deleted == False,  # noqa: E712
        )
        .order_by(Service.created_at.desc())
    )
    services = list(result.scalars().all())

    items = [ServiceRead.model_validate(svc, from_attributes=True) for svc in services]

    return ServiceListResponse(
        items=items,
        total=len(items),
        page=1,
        page_size=len(items),
    )


async def create_service(
    user_id: UUID,
    payload: ServiceCreate,
    db: AsyncSession,
) -> ServiceRead:
    """
    Create a new service listing for the given user.

    Validates that the category exists and that all provided location IDs are
    owned by the user before persisting.

    Args:
        user_id: UUID of the service provider creating the service.
        payload: Validated ServiceCreate payload.
        db: Async database session.

    Returns:
        ServiceRead representation of the newly created service.

    Raises:
        HTTPException 422: category_id does not exist.
        HTTPException 403: One or more location_ids are not owned by user_id.
    """
    # Validate category exists
    cat_result = await db.execute(
        select(ServiceCategory).where(ServiceCategory.id == payload.category_id)
    )
    if cat_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Service category {payload.category_id} does not exist",
        )

    # Validate all location_ids are owned by this user
    loc_result = await db.execute(
        select(Location.id).where(
            Location.id.in_(payload.location_ids),
            Location.user_id == user_id,
        )
    )
    owned_location_ids = {row[0] for row in loc_result.all()}
    for loc_id in payload.location_ids:
        if loc_id not in owned_location_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Location {loc_id} does not belong to the current user",
            )

    # Create the Service ORM object
    service = Service(
        user_id=user_id,
        category_id=payload.category_id,
        title=payload.title,
        description=payload.description,
        price_from=payload.price_from,
        price_to=payload.price_to,
        price_unit=payload.price_unit,
    )
    db.add(service)
    await db.flush()  # Flush to get the generated service.id

    # Insert service_locations join rows
    if payload.location_ids:
        await db.execute(
            insert(service_locations).values(
                [{"service_id": service.id, "location_id": loc_id} for loc_id in payload.location_ids]
            )
        )

    await db.commit()
    await db.refresh(service)

    return ServiceRead.model_validate(service, from_attributes=True)


async def get_service(
    service_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> ServiceRead:
    """
    Fetch a single service by ID, enforcing ownership.

    Args:
        service_id: UUID of the service to retrieve.
        user_id: UUID of the requesting user.
        db: Async database session.

    Returns:
        ServiceRead representation of the service.

    Raises:
        HTTPException 404: Service not found or soft-deleted.
        HTTPException 403: Service belongs to a different user.
    """
    service = await _fetch_service_with_ownership(service_id, user_id, db)
    return ServiceRead.model_validate(service, from_attributes=True)


async def update_service(
    service_id: UUID,
    user_id: UUID,
    payload: ServiceUpdate,
    db: AsyncSession,
) -> ServiceRead:
    """
    Partially update a service listing.

    Only fields that are not None in the payload are applied. If location_ids
    is provided, the existing service_locations rows are replaced.

    Args:
        service_id: UUID of the service to update.
        user_id: UUID of the requesting user.
        payload: Validated ServiceUpdate payload (all fields optional).
        db: Async database session.

    Returns:
        ServiceRead representation of the updated service.

    Raises:
        HTTPException 404: Service not found or soft-deleted.
        HTTPException 403: Service belongs to a different user, or a provided
            location_id is not owned by the user.
        HTTPException 422: Provided category_id does not exist.
    """
    service = await _fetch_service_with_ownership(service_id, user_id, db)

    # Apply scalar field updates (skip None values — partial update)
    if payload.category_id is not None:
        # Validate new category exists
        cat_result = await db.execute(
            select(ServiceCategory).where(ServiceCategory.id == payload.category_id)
        )
        if cat_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Service category {payload.category_id} does not exist",
            )
        service.category_id = payload.category_id

    if payload.title is not None:
        service.title = payload.title

    if payload.description is not None:
        service.description = payload.description

    if payload.price_from is not None:
        service.price_from = payload.price_from

    if payload.price_to is not None:
        service.price_to = payload.price_to

    if payload.price_unit is not None:
        service.price_unit = payload.price_unit

    if payload.is_active is not None:
        service.is_active = payload.is_active

    # Replace locations if provided
    if payload.location_ids is not None:
        # Validate ownership of new location IDs
        loc_result = await db.execute(
            select(Location.id).where(
                Location.id.in_(payload.location_ids),
                Location.user_id == user_id,
            )
        )
        owned_location_ids = {row[0] for row in loc_result.all()}
        for loc_id in payload.location_ids:
            if loc_id not in owned_location_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Location {loc_id} does not belong to the current user",
                )

        # Delete existing service_locations rows for this service
        await db.execute(
            delete(service_locations).where(
                service_locations.c.service_id == service.id
            )
        )

        # Insert new service_locations rows
        if payload.location_ids:
            await db.execute(
                insert(service_locations).values(
                    [
                        {"service_id": service.id, "location_id": loc_id}
                        for loc_id in payload.location_ids
                    ]
                )
            )

    await db.commit()
    await db.refresh(service)

    return ServiceRead.model_validate(service, from_attributes=True)


async def delete_service(
    service_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> None:
    """
    Soft-delete a service by setting is_deleted=True.

    Args:
        service_id: UUID of the service to delete.
        user_id: UUID of the requesting user.
        db: Async database session.

    Raises:
        HTTPException 404: Service not found or already soft-deleted.
        HTTPException 403: Service belongs to a different user.
    """
    service = await _fetch_service_with_ownership(service_id, user_id, db)
    service.is_deleted = True
    await db.commit()


async def upload_service_image(
    service_id: UUID,
    user_id: UUID,
    file: UploadFile,
    db: AsyncSession,
    file_service: FileService,
) -> ServiceImageRead:
    """
    Upload an image for a service and persist the ServiceImage record.

    The first image uploaded for a service is automatically set as primary.
    Subsequent images are appended with display_order = max(existing) + 1.

    Args:
        service_id: UUID of the service to attach the image to.
        user_id: UUID of the requesting user.
        file: Uploaded image file from the request.
        db: Async database session.
        file_service: FileService instance for image storage.

    Returns:
        ServiceImageRead representation of the created image record.

    Raises:
        HTTPException 404: Service not found or soft-deleted.
        HTTPException 403: Service belongs to a different user.
        HTTPException 400: File is not a valid image or exceeds size limits.
    """
    # Ownership check
    service = await _fetch_service_with_ownership(service_id, user_id, db)

    # Save the image file via FileService (reuse the same save_image pipeline)
    try:
        image_path, _ = await file_service.save_image(file, service.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Determine display_order and is_primary
    max_order_result = await db.execute(
        select(ServiceImage.display_order)
        .where(ServiceImage.service_id == service_id)
        .order_by(ServiceImage.display_order.desc())
        .limit(1)
    )
    max_order = max_order_result.scalar_one_or_none()

    if max_order is None:
        # First image — set as primary, display_order = 0
        display_order = 0
        is_primary = True
    else:
        display_order = max_order + 1
        is_primary = False

    img = ServiceImage(
        service_id=service_id,
        image_path=image_path,
        is_primary=is_primary,
        display_order=display_order,
    )
    db.add(img)
    await db.commit()
    await db.refresh(img)

    return ServiceImageRead.model_validate(img, from_attributes=True)


async def delete_service_image(
    service_id: UUID,
    img_id: UUID,
    user_id: UUID,
    db: AsyncSession,
    file_service: FileService,
) -> None:
    """
    Delete a service image: removes the file from storage and the DB row.

    If the deleted image was the primary image, the next image (lowest
    display_order) is promoted to primary.

    Args:
        service_id: UUID of the owning service.
        img_id: UUID of the image to delete.
        user_id: UUID of the requesting user.
        db: Async database session.
        file_service: FileService instance for file deletion.

    Raises:
        HTTPException 404: Service or image not found.
        HTTPException 403: Service belongs to a different user.
    """
    # Ownership check on the service
    await _fetch_service_with_ownership(service_id, user_id, db)

    # Fetch the image record
    img_result = await db.execute(
        select(ServiceImage).where(
            ServiceImage.id == img_id,
            ServiceImage.service_id == service_id,
        )
    )
    img = img_result.scalar_one_or_none()

    if img is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service image not found",
        )

    was_primary = img.is_primary

    # Delete the file from storage (ignore if already gone)
    try:
        await file_service.delete_image(img.image_path)
    except FileNotFoundError:
        pass

    # Delete the DB row
    await db.delete(img)
    await db.flush()

    # If the deleted image was primary, promote the next image
    if was_primary:
        next_img_result = await db.execute(
            select(ServiceImage)
            .where(ServiceImage.service_id == service_id)
            .order_by(ServiceImage.display_order.asc())
            .limit(1)
        )
        next_img = next_img_result.scalar_one_or_none()
        if next_img is not None:
            next_img.is_primary = True

    await db.commit()


async def search_services(
    db: AsyncSession,
    category_slug: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_km: float = 50.0,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """
    Search for service providers, optionally filtered by category and/or location.

    Results are grouped by provider (one result per user). When location
    parameters are provided, results are ordered by distance ascending;
    otherwise by User.created_at descending. Providers whose every service
    is inactive are excluded.

    Args:
        db: Async database session.
        category_slug: Optional slug to filter by service category.
        latitude: Optional latitude of the search centre.
        longitude: Optional longitude of the search centre.
        radius_km: Search radius in kilometres (default 50).
        page: 1-based page number (default 1).
        page_size: Number of results per page (default 20, max 100).

    Returns:
        Dict with keys: total, page, page_size, items (list of ServiceSearchResult).
    """
    use_geo = latitude is not None and longitude is not None

    # Subquery: count of active services per user (used to exclude all-inactive providers)
    active_svc_subq = (
        select(
            Service.user_id.label("user_id"),
            func.count(Service.id).label("active_count"),
        )
        .where(
            Service.is_deleted == False,  # noqa: E712
            Service.is_active == True,  # noqa: E712
        )
        .group_by(Service.user_id)
        .subquery()
    )

    # Base columns to select
    columns = [
        User.id.label("user_id"),
        User.name.label("provider_name"),
        User.breedery_description.label("service_description"),
        User.profile_image_path.label("profile_image_url"),
        func.coalesce(active_svc_subq.c.active_count, 0).label("active_services_count"),
        func.ST_Y(func.ST_Centroid(func.ST_Collect(Location.coordinates))).label("latitude"),
        func.ST_X(func.ST_Centroid(func.ST_Collect(Location.coordinates))).label("longitude"),
    ]

    if use_geo:
        # Distance in km — mirrors the breeder_service.py pattern:
        # ST_Distance with spheroid=True returns metres; divide by 1000 for km.
        search_point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
        distance_expr = (
            func.ST_Distance(
                Location.coordinates,
                search_point,
                True,  # use_spheroid for accurate distance
            )
            / 1000.0
        ).label("distance_km")
        columns.append(distance_expr)

    # Build the base query — join Service → service_locations → Location to
    # support geo filtering; join active_svc_subq to exclude all-inactive providers.
    query = (
        select(*columns)
        .join(Service, Service.user_id == User.id)
        .join(service_locations, service_locations.c.service_id == Service.id)
        .join(Location, Location.id == service_locations.c.location_id)
        .join(active_svc_subq, active_svc_subq.c.user_id == User.id)
        .where(
            Service.is_deleted == False,  # noqa: E712
            Service.is_active == True,  # noqa: E712
            User.account_type == "service",
        )
    )

    # Category filter
    if category_slug is not None:
        query = query.join(
            ServiceCategory, ServiceCategory.id == Service.category_id
        ).where(ServiceCategory.slug == category_slug)

    # Geo filter — mirrors breeder_service.py: ST_DWithin with spheroid=True,
    # radius converted from km to metres.
    if use_geo:
        radius_meters = radius_km * 1000
        search_point_filter = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
        query = query.where(
            func.ST_DWithin(
                Location.coordinates,
                search_point_filter,
                radius_meters,
                True,  # use_spheroid
            )
        )

    # Group by provider to get one row per user
    group_by_cols = [
        User.id,
        User.name,
        User.breedery_description,
        User.profile_image_path,
        active_svc_subq.c.active_count,
    ]
    if use_geo:
        group_by_cols.append(distance_expr)

    query = query.group_by(*group_by_cols)

    # Ordering
    if use_geo:
        query = query.order_by("distance_km")
    else:
        query = query.order_by(User.created_at.desc())

    # Count total (before pagination)
    count_subq = query.subquery()
    count_result = await db.execute(select(func.count()).select_from(count_subq))
    total = count_result.scalar_one()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    rows = (await db.execute(query)).all()

    # Build ServiceSearchResult items — fetch categories per user
    items = []
    for row in rows:
        # Fetch service categories for this provider
        cat_result = await db.execute(
            select(ServiceCategory)
            .join(Service, Service.category_id == ServiceCategory.id)
            .where(
                Service.user_id == row.user_id,
                Service.is_deleted == False,  # noqa: E712
                Service.is_active == True,  # noqa: E712
            )
            .distinct()
        )
        categories = [
            ServiceCategoryRead.model_validate(c, from_attributes=True)
            for c in cat_result.scalars().all()
        ]

        items.append(
            ServiceSearchResult(
                user_id=row.user_id,
                provider_name=row.provider_name or "",
                service_description=row.service_description,
                profile_image_url=row.profile_image_url,
                categories=categories,
                distance_km=round(row.distance_km, 2) if use_geo else None,
                active_services_count=row.active_services_count,
                latitude=round(float(row.latitude), 6) if row.latitude is not None else None,
                longitude=round(float(row.longitude), 6) if row.longitude is not None else None,
            )
        )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


async def get_public_provider_profile(
    user_id: UUID,
    db: AsyncSession,
) -> PublicProviderProfile:
    """
    Return the public profile for a service provider.

    Args:
        user_id: UUID of the service provider.
        db: Async database session.

    Returns:
        PublicProviderProfile with provider details, active services, and locations.

    Raises:
        HTTPException 404: User not found or not a service account.
    """
    user_result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.account_type == "service",
        )
    )
    user = user_result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service provider not found",
        )

    # Fetch active (non-deleted) services for this provider
    svc_result = await db.execute(
        select(Service).where(
            Service.user_id == user_id,
            Service.is_deleted == False,  # noqa: E712
            Service.is_active == True,  # noqa: E712
        )
    )
    services = [
        ServiceRead.model_validate(svc, from_attributes=True)
        for svc in svc_result.scalars().all()
    ]

    # Fetch user's locations
    loc_result = await db.execute(
        select(Location).where(Location.user_id == user_id)
    )
    locations = [
        {
            "id": loc.id,
            "name": loc.name,
            "city": loc.city,
            "state": loc.state,
            "country": loc.country,
            "latitude": loc.lat,
            "longitude": loc.lon,
            "is_default": loc.is_default,
        }
        for loc in loc_result.scalars().all()
    ]

    # Build categories from the user relationship (already loaded via selectin)
    categories = [
        ServiceCategoryRead.model_validate(cat, from_attributes=True)
        for cat in user.service_categories
    ]

    return PublicProviderProfile(
        user_id=user.id,
        provider_name=user.name or user.breedery_name or "",
        service_description=user.breedery_description,
        profile_image_url=user.profile_image_path,
        categories=categories,
        services=services,
        locations=locations,
    )
