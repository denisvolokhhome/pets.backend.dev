"""Reviews router for breeder ratings and reviews."""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import current_active_user
from app.middleware.rate_limiter import rate_limiter
from app.models.user import User
from app.schemas.breeder_review import (
    ReviewCreate,
    ReviewEligibility,
    ReviewRead,
    ReviewSummary,
    VALID_REVIEW_TAGS,
)
from app.services.review_service import review_service


router = APIRouter(prefix="/api/reviews", tags=["reviews"])


def _require_pet_seeker(user: User) -> None:
    """Raise 403 if the user is a breeder."""
    if user.is_breeder:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only pet seekers can submit reviews",
        )


@router.post(
    "/",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a breeder review",
    description="Submit a star rating, optional tags, and optional comment for a breeder. "
    "Requires a location share event in the specified thread.",
)
async def create_review(
    data: ReviewCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
) -> ReviewRead:
    _require_pet_seeker(current_user)

    # Rate limit: 10 reviews per hour per user
    await rate_limiter.check_rate_limit(
        key=f"review:{current_user.id}",
        max_requests=10,
        window_seconds=3600,
    )

    review = await review_service.create_review(
        db=db,
        reviewer_id=current_user.id,
        data=data,
    )

    return ReviewRead(
        id=review.id,
        reviewer_id=review.reviewer_id,
        breeder_id=review.breeder_id,
        thread_id=review.thread_id,
        rating=review.rating,
        tags=review.tags,
        comment=review.comment,
        created_at=review.created_at,
        reviewer_name=review.reviewer.name if review.reviewer else None,
    )


@router.get(
    "/tags",
    response_model=List[str],
    summary="List predefined review tags",
    description="Return the list of available quick-feedback tags for reviews.",
)
async def list_tags() -> List[str]:
    return VALID_REVIEW_TAGS


@router.get(
    "/eligibility",
    response_model=ReviewEligibility,
    summary="Check review eligibility",
    description="Check whether the authenticated pet seeker can review a breeder in a given thread.",
)
async def check_eligibility(
    breeder_id: uuid.UUID = Query(..., description="Breeder user ID"),
    thread_id: uuid.UUID = Query(..., description="Message thread ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
) -> ReviewEligibility:
    _require_pet_seeker(current_user)

    return await review_service.check_eligibility(
        db=db,
        reviewer_id=current_user.id,
        breeder_id=breeder_id,
        thread_id=thread_id,
    )


@router.get(
    "/breeder/{breeder_id}/summary",
    response_model=ReviewSummary,
    summary="Get breeder rating summary",
    description="Return the aggregated rating summary for a breeder including average rating, "
    "review count, and tag frequency distribution.",
)
async def get_breeder_summary(
    breeder_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
) -> ReviewSummary:
    return await review_service.get_breeder_summary(db=db, breeder_id=breeder_id)


@router.get(
    "/breeder/{breeder_id}",
    response_model=List[ReviewRead],
    summary="List breeder reviews",
    description="Return a paginated list of reviews for a breeder, ordered by creation date descending.",
)
async def list_breeder_reviews(
    breeder_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_async_session),
) -> List[ReviewRead]:
    return await review_service.list_breeder_reviews(
        db=db,
        breeder_id=breeder_id,
        limit=limit,
        offset=offset,
    )
