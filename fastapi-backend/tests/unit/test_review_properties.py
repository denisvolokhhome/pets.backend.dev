"""Property-based tests for breeder reviews using Hypothesis.

Each test is tagged with the feature and property it validates,
and links back to the requirements it covers.
"""

import json
import uuid

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.breeder_review import BreederReview
from app.models.message import Message
from app.models.user import User
from app.schemas.breeder_review import VALID_REVIEW_TAGS, ReviewCreate
from app.services.review_service import ReviewService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

ratings_strategy = st.integers(min_value=1, max_value=5)

tags_strategy = st.lists(
    st.sampled_from(VALID_REVIEW_TAGS),
    min_size=0,
    max_size=len(VALID_REVIEW_TAGS),
    unique=True,
)

# Comments: either None or a non-empty, non-whitespace string up to 2000 chars.
# We use text() with a printable alphabet and filter out whitespace-only strings.
comment_strategy = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
        min_size=1,
        max_size=2000,
    ).filter(lambda s: s.strip()),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_pet_seeker(db: AsyncSession, suffix: str = "") -> User:
    """Create and persist a pet seeker user."""
    user = User(
        email=f"seeker{suffix}_{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="hashed_pw",
        name=f"Seeker {suffix}",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=False,
    )
    db.add(user)
    await db.flush()
    return user


async def _create_breeder(db: AsyncSession, suffix: str = "") -> User:
    """Create and persist a breeder user."""
    user = User(
        email=f"breeder{suffix}_{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="hashed_pw",
        name=f"Breeder {suffix}",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _create_location_share_message(
    db: AsyncSession,
    breeder: User,
    seeker: User,
    thread_id: uuid.UUID,
) -> Message:
    """Create a location-share message from the breeder in the thread."""
    msg = Message(
        sender_id=breeder.id,
        receiver_id=seeker.id,
        thread_id=thread_id,
        content=json.dumps({"__type": "location", "name": "Test Location"}),
    )
    db.add(msg)
    await db.flush()
    return msg


# ---------------------------------------------------------------------------
# Property 1: Review creation round-trip
# ---------------------------------------------------------------------------
# Feature: breeder-reviews, Property 1: Review creation round-trip


@given(
    rating=ratings_strategy,
    tags=tags_strategy,
    comment=comment_strategy,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_review_creation_round_trip(
    async_session: AsyncSession,
    rating: int,
    tags: list[str],
    comment: str | None,
):
    """**Validates: Requirements 1.1, 3.1, 3.2, 4.3**

    For any valid review input (rating 1-5, tags from the predefined list,
    comment <= 2000 chars or None), creating a review via
    ReviewService.create_review and reading it back should produce a record
    with identical reviewer_id, breeder_id, thread_id, rating, tags, and
    comment values.
    """
    # -- Arrange: create prerequisite data inside the session --
    seeker = await _create_pet_seeker(async_session)
    breeder = await _create_breeder(async_session)
    thread_id = uuid.uuid4()

    await _create_location_share_message(
        async_session, breeder, seeker, thread_id
    )

    data = ReviewCreate(
        breeder_id=breeder.id,
        thread_id=thread_id,
        rating=rating,
        tags=tags,
        comment=comment,
    )

    service = ReviewService()

    # -- Act --
    created = await service.create_review(async_session, seeker.id, data)

    # -- Assert: read-back matches all input fields --
    assert created.reviewer_id == seeker.id
    assert created.breeder_id == breeder.id
    assert created.thread_id == thread_id
    assert created.rating == rating
    assert created.tags == tags
    assert created.comment == comment
    assert created.id is not None
    assert created.created_at is not None

    # -- Cleanup: remove the review so the next example starts fresh --
    await async_session.delete(created)
    await async_session.flush()


# ---------------------------------------------------------------------------
# Property 2: Duplicate review rejection
# ---------------------------------------------------------------------------
# Feature: breeder-reviews, Property 2: Duplicate review rejection


@given(
    rating=ratings_strategy,
    tags=tags_strategy,
    comment=comment_strategy,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_duplicate_review_rejection(
    async_session: AsyncSession,
    rating: int,
    tags: list[str],
    comment: str | None,
):
    """**Validates: Requirements 1.2, 2.3**

    For any existing review with a given (reviewer_id, breeder_id, thread_id),
    attempting to create a second review with the same triple should be rejected
    with a 409 status, and the total review count for that breeder should remain
    unchanged at 1.
    """
    from fastapi import HTTPException

    # -- Arrange: create prerequisite data --
    seeker = await _create_pet_seeker(async_session)
    breeder = await _create_breeder(async_session)
    thread_id = uuid.uuid4()

    await _create_location_share_message(
        async_session, breeder, seeker, thread_id
    )

    data = ReviewCreate(
        breeder_id=breeder.id,
        thread_id=thread_id,
        rating=rating,
        tags=tags,
        comment=comment,
    )

    service = ReviewService()

    # -- Act: create the first review (should succeed) --
    created = await service.create_review(async_session, seeker.id, data)
    assert created.id is not None

    # Capture IDs before the duplicate attempt causes a rollback that
    # expires the ORM object (accessing attributes after rollback would
    # trigger a synchronous lazy-load and raise MissingGreenlet).
    created_id = created.id
    breeder_id = breeder.id

    # Verify review count is 1 before the duplicate attempt
    count_query = select(func.count(BreederReview.id)).where(
        BreederReview.breeder_id == breeder_id
    )
    result = await async_session.execute(count_query)
    assert result.scalar() == 1

    # -- Act: attempt duplicate with same (reviewer, breeder, thread) --
    with pytest.raises(HTTPException) as exc_info:
        await service.create_review(async_session, seeker.id, data)

    # -- Assert: 409 rejection --
    assert exc_info.value.status_code == 409

    # -- Assert: review count unchanged (re-query after rollback) --
    result = await async_session.execute(count_query)
    assert result.scalar() == 1

    # -- Cleanup: re-fetch and remove the review so the next example starts fresh --
    review_query = select(BreederReview).where(BreederReview.id == created_id)
    review_result = await async_session.execute(review_query)
    review = review_result.scalar_one()
    await async_session.delete(review)
    await async_session.flush()


# ---------------------------------------------------------------------------
# Property 6: Rating aggregation correctness
# ---------------------------------------------------------------------------
# Feature: breeder-reviews, Property 6: Rating aggregation correctness


# Strategy: a list of 0–50 reviews, each with a random rating and tag subset
_review_data_strategy = st.lists(
    st.tuples(ratings_strategy, tags_strategy),
    min_size=0,
    max_size=50,
)


@given(review_data=_review_data_strategy)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_rating_aggregation_correctness(
    async_session: AsyncSession,
    review_data: list[tuple[int, list[str]]],
):
    """**Validates: Requirements 5.1, 5.2, 5.3**

    For any list of 0–50 reviews with random ratings and tag subsets,
    the ReviewSummary returned by get_breeder_summary should have:
    - average_rating == round(sum(ratings) / count, 1)  (or 0 when empty)
    - review_count == len(reviews)
    - tag_counts matching the actual frequency of each tag across reviews
    For an empty set, average should be 0, count should be 0, and
    tag_counts should be empty.
    """
    # -- Arrange: create a breeder --
    breeder = await _create_breeder(async_session)
    breeder_id = breeder.id

    # Insert review objects directly (each from a unique reviewer + thread)
    inserted_reviews: list[BreederReview] = []
    for i, (rating, tags) in enumerate(review_data):
        seeker = await _create_pet_seeker(async_session, suffix=f"agg_{i}")
        thread_id = uuid.uuid4()

        review = BreederReview(
            reviewer_id=seeker.id,
            breeder_id=breeder_id,
            thread_id=thread_id,
            rating=rating,
            tags=tags,
        )
        async_session.add(review)
        inserted_reviews.append(review)

    await async_session.flush()

    # -- Act --
    service = ReviewService()
    summary = await service.get_breeder_summary(async_session, breeder_id)

    # -- Assert --
    n = len(review_data)

    if n == 0:
        # Empty set: avg=0, count=0, empty tag_counts
        assert summary.average_rating == 0
        assert summary.review_count == 0
        assert summary.tag_counts == {}
    else:
        ratings = [r for r, _ in review_data]
        expected_avg = round(sum(ratings) / len(ratings), 1)
        assert summary.average_rating == expected_avg
        assert summary.review_count == n

        # Compute expected tag counts
        expected_tag_counts: dict[str, int] = {}
        for _, tags in review_data:
            for tag in tags:
                expected_tag_counts[tag] = expected_tag_counts.get(tag, 0) + 1

        assert summary.tag_counts == expected_tag_counts

    # -- Cleanup: remove inserted reviews and users so next example starts fresh --
    for review in inserted_reviews:
        await async_session.delete(review)
    await async_session.flush()


# ---------------------------------------------------------------------------
# Property 7: Review list ordering
# ---------------------------------------------------------------------------
# Feature: breeder-reviews, Property 7: Review list ordering


@given(
    num_reviews=st.integers(min_value=2, max_value=20),
    page_limit=st.integers(min_value=1, max_value=20),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_review_list_ordering(
    async_session: AsyncSession,
    num_reviews: int,
    page_limit: int,
):
    """**Validates: Requirements 5.4**

    For any breeder with multiple reviews (2–20), each with a random
    created_at timestamp, list_breeder_reviews should return reviews in
    strictly descending created_at order, and the number of results should
    not exceed the requested page size (limit).
    """
    from datetime import datetime, timezone, timedelta
    import random

    # -- Arrange: create a breeder --
    breeder = await _create_breeder(async_session)
    breeder_id = breeder.id

    # Generate random timestamps spread over a 365-day window
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    timestamps = [
        base_time + timedelta(seconds=random.randint(0, 365 * 24 * 3600))
        for _ in range(num_reviews)
    ]

    # Insert review objects directly, each from a unique reviewer + thread
    inserted_reviews: list[BreederReview] = []
    for i in range(num_reviews):
        seeker = await _create_pet_seeker(async_session, suffix=f"ord_{i}")
        thread_id = uuid.uuid4()

        review = BreederReview(
            reviewer_id=seeker.id,
            breeder_id=breeder_id,
            thread_id=thread_id,
            rating=random.randint(1, 5),
            tags=[],
            created_at=timestamps[i],
        )
        async_session.add(review)
        inserted_reviews.append(review)

    await async_session.flush()

    # -- Act --
    service = ReviewService()
    results = await service.list_breeder_reviews(
        async_session, breeder_id, limit=page_limit, offset=0
    )

    # -- Assert: number of results does not exceed the requested page size --
    assert len(results) <= page_limit

    # -- Assert: results are in strictly descending created_at order --
    for i in range(len(results) - 1):
        assert results[i].created_at >= results[i + 1].created_at, (
            f"Review at index {i} (created_at={results[i].created_at}) "
            f"should be >= review at index {i + 1} "
            f"(created_at={results[i + 1].created_at})"
        )

    # -- Cleanup: remove inserted reviews so next example starts fresh --
    for review in inserted_reviews:
        await async_session.delete(review)
    await async_session.flush()


# ---------------------------------------------------------------------------
# Property 8: HTML sanitization strips all tags
# ---------------------------------------------------------------------------
# Feature: breeder-reviews, Property 8: HTML sanitization strips all tags

from app.services.review_service import _sanitize_html

# Strategy: generate plain text segments and interleave random HTML tags
_html_tags = [
    "<script>alert('xss')</script>",
    "<b>",
    "</b>",
    "<img src='x' onerror='alert(1)'>",
    "<div>",
    "</div>",
    '<a href="http://evil.com">',
    "</a>",
    "<span style='color:red'>",
    "</span>",
    "<iframe src='evil'></iframe>",
    "<br/>",
    "<br>",
    "<p>",
    "</p>",
    "<h1>",
    "</h1>",
    "<style>body{display:none}</style>",
]

# Build a strategy that creates a string by interleaving plain text with HTML tags
_plain_text_segment = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters="<>",
    ),
    min_size=0,
    max_size=50,
)

_html_tag_strategy = st.sampled_from(_html_tags)

_html_string_strategy = st.lists(
    st.one_of(_plain_text_segment, _html_tag_strategy),
    min_size=1,
    max_size=10,
).map("".join)


@given(text_with_html=_html_string_strategy)
@settings(max_examples=100)
def test_html_sanitization_strips_all_tags(text_with_html: str):
    """**Validates: Requirements 11.2**

    For any string containing embedded HTML tags (e.g., <script>, <b>, <img>,
    <div>, <a href="...">, etc.), after sanitization by _sanitize_html, the
    resulting string should contain no HTML tags (no <...> patterns) while
    preserving all non-HTML text content.
    """
    import re

    result = _sanitize_html(text_with_html)

    # -- Assert: no HTML tags remain in the output --
    assert not re.search(r"<[^>]+>", result), (
        f"Sanitized output still contains HTML tags: {result!r}"
    )

    # -- Assert: all plain text segments are preserved --
    # Extract the non-HTML text from the original by stripping tags the same
    # way, then verify the sanitised result matches.  A simpler (and
    # independent) way: every character in the result must have appeared in
    # the original, and the result should equal the original with tags removed.
    expected = re.sub(r"<[^>]+>", "", text_with_html)
    assert result == expected, (
        f"Non-HTML text not preserved.\n"
        f"  Input:    {text_with_html!r}\n"
        f"  Expected: {expected!r}\n"
        f"  Got:      {result!r}"
    )


# ---------------------------------------------------------------------------
# Property 3: Only pet seekers can submit reviews
# ---------------------------------------------------------------------------
# Feature: breeder-reviews, Property 3: Only pet seekers can submit reviews

from app.routers.reviews import _require_pet_seeker
from fastapi import HTTPException as _HTTPException
from types import SimpleNamespace


@given(is_breeder=st.booleans())
@settings(max_examples=100)
def test_only_pet_seekers_can_submit(is_breeder: bool):
    """**Validates: Requirements 2.4, 2.5, 6.5**

    For any authenticated user, the user can submit a review if and only if
    is_breeder=False. Users with is_breeder=True should receive a 403
    rejection with the message "Only pet seekers can submit reviews".
    """
    user = SimpleNamespace(is_breeder=is_breeder)

    if is_breeder:
        # Breeders must be rejected with 403
        with pytest.raises(_HTTPException) as exc_info:
            _require_pet_seeker(user)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Only pet seekers can submit reviews"
    else:
        # Pet seekers pass through without exception
        result = _require_pet_seeker(user)
        assert result is None


# ---------------------------------------------------------------------------
# Property 4: Invalid review input rejection
# ---------------------------------------------------------------------------
# Feature: breeder-reviews, Property 4: Invalid review input rejection

from pydantic import ValidationError


# Strategies for invalid inputs
_invalid_rating_strategy = st.integers().filter(lambda x: x < 1 or x > 5)

_long_comment_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=2001,
    max_size=2500,
).filter(lambda s: s.strip())

_invalid_tag_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L",)),
    min_size=1,
    max_size=30,
).filter(lambda s: s not in VALID_REVIEW_TAGS)

_whitespace_only_strategy = st.text(
    alphabet=st.sampled_from([" ", "\t", "\n", "\r", "\u00a0"]),
    min_size=1,
    max_size=50,
)


@given(rating=_invalid_rating_strategy)
@settings(max_examples=100)
def test_invalid_rating_rejected(rating: int):
    """**Validates: Requirements 3.3**

    For any rating outside the range [1, 5], constructing a ReviewCreate
    should raise a Pydantic ValidationError.
    """
    with pytest.raises(ValidationError):
        ReviewCreate(
            breeder_id=uuid.uuid4(),
            thread_id=uuid.uuid4(),
            rating=rating,
            tags=[],
            comment=None,
        )


@given(comment=_long_comment_strategy)
@settings(max_examples=100)
def test_comment_exceeding_2000_chars_rejected(comment: str):
    """**Validates: Requirements 3.4**

    For any comment longer than 2000 characters, constructing a ReviewCreate
    should raise a Pydantic ValidationError.
    """
    with pytest.raises(ValidationError):
        ReviewCreate(
            breeder_id=uuid.uuid4(),
            thread_id=uuid.uuid4(),
            rating=3,
            tags=[],
            comment=comment,
        )


@given(invalid_tag=_invalid_tag_strategy)
@settings(max_examples=100)
def test_invalid_tags_rejected(invalid_tag: str):
    """**Validates: Requirements 3.5**

    For any tag string not in the predefined VALID_REVIEW_TAGS list,
    constructing a ReviewCreate should raise a Pydantic ValidationError.
    """
    with pytest.raises(ValidationError):
        ReviewCreate(
            breeder_id=uuid.uuid4(),
            thread_id=uuid.uuid4(),
            rating=3,
            tags=[invalid_tag],
            comment=None,
        )


@given(comment=_whitespace_only_strategy)
@settings(max_examples=100)
def test_whitespace_only_comment_rejected(comment: str):
    """**Validates: Requirements 3.6**

    For any non-null comment composed entirely of whitespace characters,
    constructing a ReviewCreate should raise a Pydantic ValidationError.
    """
    with pytest.raises(ValidationError):
        ReviewCreate(
            breeder_id=uuid.uuid4(),
            thread_id=uuid.uuid4(),
            rating=3,
            tags=[],
            comment=comment,
        )


# ---------------------------------------------------------------------------
# Property 5: Eligibility correctness
# ---------------------------------------------------------------------------
# Feature: breeder-reviews, Property 5: Eligibility correctness


@given(
    has_location_share=st.booleans(),
    has_existing_review=st.booleans(),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_eligibility_correctness(
    async_session: AsyncSession,
    has_location_share: bool,
    has_existing_review: bool,
):
    """**Validates: Requirements 2.1, 2.2, 6.1, 6.2, 6.3, 6.4**

    For any (pet_seeker, breeder, thread) triple, the eligibility check should
    return eligible=True if and only if (a) a location-share message exists in
    the thread sent by the breeder, AND (b) no review exists for that triple.
    Otherwise it should return eligible=False with reason "no_location_shared"
    or "already_reviewed" respectively.
    """
    # -- Arrange --
    seeker = await _create_pet_seeker(async_session, suffix="elig")
    breeder = await _create_breeder(async_session, suffix="elig")
    thread_id = uuid.uuid4()

    # Conditionally create a location-share message
    location_msg = None
    if has_location_share:
        location_msg = await _create_location_share_message(
            async_session, breeder, seeker, thread_id
        )

    # Conditionally create an existing review
    existing_review = None
    if has_existing_review:
        existing_review = BreederReview(
            reviewer_id=seeker.id,
            breeder_id=breeder.id,
            thread_id=thread_id,
            rating=3,
            tags=[],
        )
        async_session.add(existing_review)
        await async_session.flush()

    # -- Act --
    service = ReviewService()
    result = await service.check_eligibility(
        async_session, seeker.id, breeder.id, thread_id
    )

    # -- Assert --
    if not has_location_share:
        # No location share → ineligible, reason = "no_location_shared"
        assert result.eligible is False
        assert result.reason == "no_location_shared"
    elif has_existing_review:
        # Location share exists but already reviewed → ineligible
        assert result.eligible is False
        assert result.reason == "already_reviewed"
    else:
        # Location share exists and no prior review → eligible
        assert result.eligible is True
        assert result.reason is None

    # -- Cleanup --
    if existing_review is not None:
        await async_session.delete(existing_review)
    if location_msg is not None:
        await async_session.delete(location_msg)
    await async_session.flush()


# ---------------------------------------------------------------------------
# Property 9: Rate limiting enforced
# ---------------------------------------------------------------------------
# Feature: breeder-reviews, Property 9: Rate limiting enforced

from app.middleware.rate_limiter import RateLimiter


@given(n=st.integers(min_value=11, max_value=20))
@settings(max_examples=100)
@pytest.mark.asyncio
async def test_rate_limiting_enforced(n: int):
    """**Validates: Requirements 11.1**

    For any authenticated user, after submitting 10 reviews within a 1-hour
    window, the 11th submission attempt should be rejected with a 429 status.

    We test the RateLimiter directly with the same key pattern used in the
    router (review:{user_id}), calling check_rate_limit N times (N in 11..20)
    with max_requests=10 and window_seconds=3600. The first 10 calls must
    succeed and the 11th must raise HTTPException 429.
    """
    from fastapi import HTTPException

    # Use a fresh RateLimiter instance so examples don't interfere
    limiter = RateLimiter()
    user_id = uuid.uuid4()
    key = f"review:{user_id}"

    # First 10 calls should succeed
    for i in range(10):
        result = await limiter.check_rate_limit(
            key=key, max_requests=10, window_seconds=3600
        )
        assert result is True, f"Call {i + 1} should succeed but didn't"

    # Calls 11 through N should all raise 429
    for i in range(10, n):
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check_rate_limit(
                key=key, max_requests=10, window_seconds=3600
            )
        assert exc_info.value.status_code == 429, (
            f"Call {i + 1} should return 429 but got {exc_info.value.status_code}"
        )


# ---------------------------------------------------------------------------
# Property 13: Breeder and thread validation
# ---------------------------------------------------------------------------
# Feature: breeder-reviews, Property 13: Breeder and thread validation


@given(fake_breeder_id=st.uuids())
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_nonexistent_breeder_returns_404(
    async_session: AsyncSession,
    fake_breeder_id: uuid.UUID,
):
    """**Validates: Requirements 11.3**

    For any UUID that does not reference an existing user with is_breeder=True,
    calling ReviewService.create_review should raise HTTPException 404 with
    detail "Breeder not found".
    """
    from fastapi import HTTPException

    seeker = await _create_pet_seeker(async_session, suffix="p13b")
    thread_id = uuid.uuid4()

    data = ReviewCreate(
        breeder_id=fake_breeder_id,
        thread_id=thread_id,
        rating=3,
        tags=[],
        comment=None,
    )

    service = ReviewService()

    with pytest.raises(HTTPException) as exc_info:
        await service.create_review(async_session, seeker.id, data)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Breeder not found"


@given(fake_thread_id=st.uuids())
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_nonexistent_thread_returns_404(
    async_session: AsyncSession,
    fake_thread_id: uuid.UUID,
):
    """**Validates: Requirements 11.4**

    For any thread_id UUID where the authenticated Pet Seeker has no messages
    (i.e. is not a participant), calling ReviewService.create_review should
    raise HTTPException 404 with detail "Thread not found".
    """
    from fastapi import HTTPException

    seeker = await _create_pet_seeker(async_session, suffix="p13t")
    breeder = await _create_breeder(async_session, suffix="p13t")

    data = ReviewCreate(
        breeder_id=breeder.id,
        thread_id=fake_thread_id,
        rating=4,
        tags=["Communication"],
        comment="Great breeder",
    )

    service = ReviewService()

    with pytest.raises(HTTPException) as exc_info:
        await service.create_review(async_session, seeker.id, data)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Thread not found"
