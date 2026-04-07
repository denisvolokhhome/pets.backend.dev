"""BreederReview model for breeder ratings and reviews."""
from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class BreederReview(Base):
    """
    BreederReview model for pet seeker ratings and reviews of breeders.

    One review per (reviewer, breeder, thread) combination.
    Rating is an integer 1–5, tags are stored as a JSON array,
    and comment is optional free text (max 2000 chars enforced at schema level).
    """

    __tablename__ = "breeder_reviews"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Foreign key to user (pet seeker / reviewer)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Foreign key to user (breeder / reviewee)
    breeder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Thread where the location share occurred
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Star rating 1–5
    rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Quick-feedback tags stored as JSON array
    tags: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default="'[]'::jsonb",
    )

    # Optional text comment
    comment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    reviewer: Mapped["User"] = relationship(
        "User",
        foreign_keys=[reviewer_id],
        lazy="selectin",
    )

    breeder: Mapped["User"] = relationship(
        "User",
        foreign_keys=[breeder_id],
        lazy="selectin",
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "reviewer_id",
            "breeder_id",
            "thread_id",
            name="uq_review_per_thread",
        ),
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_review_rating_range",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<BreederReview(id={self.id}, reviewer_id={self.reviewer_id}, "
            f"breeder_id={self.breeder_id}, rating={self.rating})>"
        )
