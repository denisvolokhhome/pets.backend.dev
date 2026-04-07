"""Review service for managing breeder reviews and ratings."""
import logging
import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.breeder_review import BreederReview
from app.models.message import Message
from app.models.user import User
from app.schemas.breeder_review import (
    ReviewCreate,
    ReviewEligibility,
    ReviewRead,
    ReviewSummary,
)

logger = logging.getLogger(__name__)

HTML_TAG_RE = re.compile(r"<[^>]+>")


def _sanitize_html(text: str) -> str:
    """Strip all HTML tags from *text*, preserving non-HTML content."""
    return HTML_TAG_RE.sub("", text)


class ReviewService:
    """Service for breeder review creation, eligibility, and aggregation."""

    # ------------------------------------------------------------------
    # Eligibility helpers
    # ------------------------------------------------------------------

    async def _location_shared_in_thread(
        self,
        db: AsyncSession,
        breeder_id: uuid.UUID,
        thread_id: uuid.UUID,
    ) -> bool:
        """Return True if the breeder sent a location-share message in the thread."""
        query = (
            select(Message.id)
            .where(
                Message.thread_id == thread_id,
                Message.sender_id == breeder_id,
                Message.content.ilike('%"__type": "location"%'),
                Message.deleted_at.is_(None),
            )
            .limit(1)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None

    async def _validate_breeder(
        self,
        db: AsyncSession,
        breeder_id: uuid.UUID,
    ) -> User:
        """Return the breeder User or raise 404."""
        query = select(User).where(User.id == breeder_id, User.is_breeder.is_(True))
        result = await db.execute(query)
        breeder = result.scalar_one_or_none()
        if breeder is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Breeder not found",
            )
        return breeder

    async def _validate_thread_participation(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        thread_id: uuid.UUID,
    ) -> None:
        """Raise 404 if the user is not a participant in the thread."""
        query = (
            select(Message.id)
            .where(
                Message.thread_id == thread_id,
                (Message.sender_id == user_id) | (Message.receiver_id == user_id),
            )
            .limit(1)
        )
        result = await db.execute(query)
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thread not found",
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_review(
        self,
        db: AsyncSession,
        reviewer_id: uuid.UUID,
        data: ReviewCreate,
    ) -> BreederReview:
        """Create a breeder review after validating eligibility.

        Raises:
            HTTPException 403 – no location share in thread
            HTTPException 404 – invalid breeder or thread
            HTTPException 409 – duplicate review
        """
        # 1. Validate breeder exists and is a breeder
        await self._validate_breeder(db, data.breeder_id)

        # 2. Validate thread participation
        await self._validate_thread_participation(db, reviewer_id, data.thread_id)

        # 3. Verify location share exists
        has_location = await self._location_shared_in_thread(
            db, data.breeder_id, data.thread_id
        )
        if not has_location:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Review not permitted: breeder has not shared location in this thread",
            )

        # 4. Sanitize comment
        comment = data.comment
        if comment is not None:
            comment = _sanitize_html(comment)

        # 5. Insert review
        review = BreederReview(
            reviewer_id=reviewer_id,
            breeder_id=data.breeder_id,
            thread_id=data.thread_id,
            rating=data.rating,
            tags=data.tags,
            comment=comment,
        )
        db.add(review)

        try:
            await db.commit()
            await db.refresh(review)
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Review already submitted for this interaction",
            )

        # 6. Audit log (rating only – never log comment text)
        logger.info(
            "review_created reviewer_id=%s breeder_id=%s rating=%s",
            reviewer_id,
            data.breeder_id,
            data.rating,
        )

        return review

    async def check_eligibility(
        self,
        db: AsyncSession,
        reviewer_id: uuid.UUID,
        breeder_id: uuid.UUID,
        thread_id: uuid.UUID,
    ) -> ReviewEligibility:
        """Check whether a pet seeker can review a breeder in a thread.

        Returns ReviewEligibility with eligible=True only when a location
        share exists AND no prior review has been submitted.
        """
        # Check location share
        has_location = await self._location_shared_in_thread(db, breeder_id, thread_id)
        if not has_location:
            return ReviewEligibility(eligible=False, reason="no_location_shared")

        # Check for existing review
        existing_query = (
            select(BreederReview.id)
            .where(
                BreederReview.reviewer_id == reviewer_id,
                BreederReview.breeder_id == breeder_id,
                BreederReview.thread_id == thread_id,
            )
            .limit(1)
        )
        result = await db.execute(existing_query)
        if result.scalar_one_or_none() is not None:
            return ReviewEligibility(eligible=False, reason="already_reviewed")

        return ReviewEligibility(eligible=True)

    async def get_breeder_summary(
        self,
        db: AsyncSession,
        breeder_id: uuid.UUID,
    ) -> ReviewSummary:
        """Compute average rating, count, and tag frequency for a breeder.

        Returns zeros / empty dict when the breeder has no reviews.
        """
        # Avg + count in a single query
        agg_query = select(
            func.coalesce(func.avg(BreederReview.rating), 0),
            func.count(BreederReview.id),
        ).where(BreederReview.breeder_id == breeder_id)

        result = await db.execute(agg_query)
        row = result.one()
        avg_rating = round(float(row[0]), 1)
        review_count = int(row[1])

        # Tag frequency
        tag_counts: dict[str, int] = {}
        if review_count > 0:
            tags_query = select(BreederReview.tags).where(
                BreederReview.breeder_id == breeder_id
            )
            tags_result = await db.execute(tags_query)
            for (tags_list,) in tags_result:
                if tags_list:
                    for tag in tags_list:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1

        return ReviewSummary(
            breeder_id=breeder_id,
            average_rating=avg_rating,
            review_count=review_count,
            tag_counts=tag_counts,
        )

    async def list_breeder_reviews(
        self,
        db: AsyncSession,
        breeder_id: uuid.UUID,
        limit: int = 10,
        offset: int = 0,
    ) -> list[ReviewRead]:
        """Return paginated reviews for a breeder, newest first."""
        query = (
            select(BreederReview)
            .where(BreederReview.breeder_id == breeder_id)
            .order_by(BreederReview.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(query)
        reviews = result.scalars().all()

        return [
            ReviewRead(
                id=r.id,
                reviewer_id=r.reviewer_id,
                breeder_id=r.breeder_id,
                thread_id=r.thread_id,
                rating=r.rating,
                tags=r.tags,
                comment=r.comment,
                created_at=r.created_at,
                reviewer_name=r.reviewer.name if r.reviewer else None,
            )
            for r in reviews
        ]

    async def get_breeder_rating(
        self,
        db: AsyncSession,
        breeder_id: uuid.UUID,
    ) -> dict:
        """Lightweight avg + count query for card / map display."""
        query = select(
            func.coalesce(func.avg(BreederReview.rating), 0),
            func.count(BreederReview.id),
        ).where(BreederReview.breeder_id == breeder_id)

        result = await db.execute(query)
        row = result.one()
        return {
            "average_rating": round(float(row[0]), 1),
            "review_count": int(row[1]),
        }


# Singleton instance
review_service = ReviewService()
