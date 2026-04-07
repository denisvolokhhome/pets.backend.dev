"""Breeder review schemas for API request/response validation."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


VALID_REVIEW_TAGS = [
    "Communication",
    "Animal Care",
    "Accuracy of Description",
    "Responsiveness",
    "Professionalism",
    "Punctuality",
    "Transparency",
    "Facility Cleanliness",
]


class ReviewCreate(BaseModel):
    """Schema for creating a new breeder review."""
    breeder_id: uuid.UUID
    thread_id: uuid.UUID
    rating: int = Field(..., ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    comment: Optional[str] = Field(None, max_length=2000)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Ensure all tags are from the predefined list."""
        invalid = set(v) - set(VALID_REVIEW_TAGS)
        if invalid:
            raise ValueError(f"Invalid tags: {invalid}")
        return v

    @field_validator("comment")
    @classmethod
    def validate_not_whitespace(cls, v: Optional[str]) -> Optional[str]:
        """Ensure comment is not empty or whitespace-only."""
        if v is not None and (not v or not v.strip()):
            raise ValueError("Comment cannot be empty or whitespace-only")
        return v


class ReviewRead(BaseModel):
    """Schema for reading a single breeder review."""
    id: uuid.UUID
    reviewer_id: uuid.UUID
    breeder_id: uuid.UUID
    thread_id: uuid.UUID
    rating: int
    tags: list[str]
    comment: Optional[str]
    created_at: datetime
    reviewer_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReviewSummary(BaseModel):
    """Aggregated rating summary for a breeder."""
    breeder_id: uuid.UUID
    average_rating: float = Field(..., ge=0, le=5)
    review_count: int = Field(..., ge=0)
    tag_counts: dict[str, int] = Field(default_factory=dict)


class ReviewEligibility(BaseModel):
    """Eligibility check response for review submission."""
    eligible: bool
    reason: Optional[str] = None
