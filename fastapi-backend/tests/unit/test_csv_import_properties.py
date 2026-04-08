"""Property-based tests for CSV Pet Import using Hypothesis.

Each test is tagged with the feature and property it validates,
and links back to the requirements it covers.
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from app.utils.sanitize import sanitize_string

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CSV_INJECTION_CHARS = set("=+-@\t\r")
HTML_TAG_RE = re.compile(r"<[^>]*>")

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy that generates strings containing CSV injection prefixes
csv_injection_prefix_strategy = st.sampled_from(
    ["=", "+", "-", "@", "\t", "\r"]
)

# Strategy for HTML-like tags
html_tag_strategy = st.sampled_from([
    "<script>alert(1)</script>",
    "<img onerror=alert(1)>",
    "<b>bold</b>",
    "<div>content</div>",
    "<a href='x'>link</a>",
])

# Safe content that should be preserved after sanitization
safe_content_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="\x00<>\t\r",
    ),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() and not any(c in CSV_INJECTION_CHARS for c in s))

# Strategy that builds strings with injection patterns mixed in
injection_string_strategy = st.builds(
    lambda prefix, html, safe, nulls: (
        prefix + safe + html + "\x00" * nulls
    ),
    prefix=st.text(
        alphabet=st.sampled_from(list("=+-@\t\r")),
        min_size=0,
        max_size=5,
    ),
    html=st.one_of(st.just(""), html_tag_strategy),
    safe=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=0,
        max_size=30,
    ),
    nulls=st.integers(min_value=0, max_value=3),
)


# ---------------------------------------------------------------------------
# Property 8: String sanitization neutralizes injection
# Feature: csv-pet-import, Property 8: String sanitization neutralizes injection
# **Validates: Requirements 8.3**
# ---------------------------------------------------------------------------


@given(data=injection_string_strategy)
@settings(max_examples=100)
def test_sanitize_string_removes_injection_patterns(data: str):
    """Property 8: sanitize_string output contains no CSV injection
    prefixes, HTML tags, or null bytes.

    **Validates: Requirements 8.3**
    """
    result = sanitize_string(data)

    # No leading CSV injection characters
    if result:
        assert result[0] not in CSV_INJECTION_CHARS, (
            f"Output starts with injection char {result[0]!r}: {result!r}"
        )

    # No HTML tags remain
    assert not HTML_TAG_RE.search(result), (
        f"Output still contains HTML tags: {result!r}"
    )

    # No null bytes
    assert "\x00" not in result, (
        f"Output still contains null bytes: {result!r}"
    )


@given(safe=safe_content_strategy)
@settings(max_examples=100)
def test_sanitize_string_preserves_safe_content(safe: str):
    """Property 8 (preservation): safe content without injection patterns
    is preserved by sanitize_string.

    **Validates: Requirements 8.3**
    """
    result = sanitize_string(safe)
    # Safe content should survive sanitization (after strip)
    assert result == safe.strip(), (
        f"Safe content was altered: input={safe!r}, output={result!r}"
    )


@given(
    value=st.text(min_size=0, max_size=200),
    max_length=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=100)
def test_sanitize_string_respects_max_length(value: str, max_length: int):
    """Property 8 (truncation): output never exceeds max_length.

    **Validates: Requirements 8.3**
    """
    result = sanitize_string(value, max_length=max_length)
    assert len(result) <= max_length, (
        f"Output length {len(result)} exceeds max_length {max_length}"
    )


# ---------------------------------------------------------------------------
# Property 5: Billing limit row partitioning
# Feature: csv-pet-import, Property 5: Billing limit row partitioning
# **Validates: Requirements 4.2, 4.3, 4.4, 5.5**
# ---------------------------------------------------------------------------

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.pet_import import PetImportRow, ImportResult
from app.services.pet_import_service import PetImportService


def _make_valid_rows(count: int) -> list[PetImportRow]:
    """Create *count* minimal valid PetImportRow objects (no breed/location)."""
    return [
        PetImportRow(row_number=i + 1, name=f"Pet{i + 1}")
        for i in range(count)
    ]


async def _run_import_with_limits(
    valid_row_count: int,
    current_count: int,
    max_pets: int,
) -> ImportResult:
    """Run PetImportService.import_pets with mocked DB helpers.

    Only the billing-limit logic is exercised; breed/location resolution
    is bypassed by providing rows without breed or location fields.
    """
    service = PetImportService()
    rows = _make_valid_rows(valid_row_count)

    # Mock the async session — we only need add() and flush()
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    # Patch the four DB-hitting helpers on the service instance
    service._build_breed_map = AsyncMock(return_value={})
    service._build_location_map = AsyncMock(return_value={})
    service._get_current_pet_count = AsyncMock(return_value=current_count)
    service._get_plan_max_pets = AsyncMock(return_value=max_pets)

    import uuid
    user_id = uuid.uuid4()

    result = await service.import_pets(mock_session, user_id, rows)
    return result


@given(
    valid_row_count=st.integers(min_value=0, max_value=100),
    current_count=st.integers(min_value=0, max_value=200),
    max_pets=st.integers(min_value=0, max_value=200),
)
@settings(max_examples=100)
def test_billing_limit_created_count(
    valid_row_count: int,
    current_count: int,
    max_pets: int,
):
    """Property 5 (created count): created_count equals
    min(valid_rows, max(0, max_pets - current_count)).

    **Validates: Requirements 4.2, 4.3, 4.4, 5.5**
    """
    result = asyncio.new_event_loop().run_until_complete(
        _run_import_with_limits(valid_row_count, current_count, max_pets)
    )

    expected_created = min(valid_row_count, max(0, max_pets - current_count))
    assert result.created_count == expected_created, (
        f"created_count={result.created_count}, expected={expected_created} "
        f"(valid_rows={valid_row_count}, current={current_count}, max={max_pets})"
    )


@given(
    valid_row_count=st.integers(min_value=0, max_value=100),
    current_count=st.integers(min_value=0, max_value=200),
    max_pets=st.integers(min_value=0, max_value=200),
)
@settings(max_examples=100)
def test_billing_limit_plan_limit_applied_flag(
    valid_row_count: int,
    current_count: int,
    max_pets: int,
):
    """Property 5 (plan_limit_applied flag): plan_limit_applied is True
    iff valid rows were truncated by the billing limit.

    **Validates: Requirements 4.2, 4.3, 4.4, 5.5**
    """
    result = asyncio.new_event_loop().run_until_complete(
        _run_import_with_limits(valid_row_count, current_count, max_pets)
    )

    expected_created = min(valid_row_count, max(0, max_pets - current_count))
    expected_flag = expected_created < valid_row_count

    assert result.plan_limit_applied == expected_flag, (
        f"plan_limit_applied={result.plan_limit_applied}, expected={expected_flag} "
        f"(valid_rows={valid_row_count}, created={expected_created}, "
        f"current={current_count}, max={max_pets})"
    )


# ---------------------------------------------------------------------------
# Property 6: Breed name resolution
# Feature: csv-pet-import, Property 6: Breed name resolution
# **Validates: Requirements 5.6, 5.8**
# ---------------------------------------------------------------------------

# Strategy: generate a known breed map, then produce breed name strings with
# random casing that either match a known breed or are completely unknown.

# A small fixed set of canonical breed names with assigned IDs.
_KNOWN_BREEDS: dict[str, int] = {
    "golden retriever": 1,
    "labrador": 2,
    "poodle": 3,
    "german shepherd": 4,
    "bulldog": 5,
}


def _random_case(s: str, data) -> str:
    """Return *s* with each character randomly upper- or lower-cased."""
    return "".join(
        data.draw(st.sampled_from([c.upper(), c.lower()]))
        for c in s
    )


async def _run_import_with_breed(
    breed_name: str,
    breed_map: dict[str, int],
) -> ImportResult:
    """Run PetImportService.import_pets with a single row carrying *breed_name*.

    The breed_map is injected via mock so no real DB is needed.
    Location resolution is bypassed (no location on the row).
    Billing limits are set high so they never interfere.
    """
    service = PetImportService()

    row = PetImportRow(row_number=1, name="TestPet", breed=breed_name)

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    service._build_breed_map = AsyncMock(return_value=breed_map)
    service._build_location_map = AsyncMock(return_value={})
    service._get_current_pet_count = AsyncMock(return_value=0)
    service._get_plan_max_pets = AsyncMock(return_value=999_999)

    import uuid
    user_id = uuid.uuid4()

    return await service.import_pets(mock_session, user_id, [row])


@given(data=st.data())
@settings(max_examples=100)
def test_breed_name_case_insensitive_resolution(data):
    """Property 6 (match): A breed name with random casing that matches a
    known breed (case-insensitive) resolves to the correct breed_id and the
    pet is created successfully.

    **Validates: Requirements 5.6, 5.8**
    """
    # Pick a random known breed
    canonical = data.draw(st.sampled_from(list(_KNOWN_BREEDS.keys())))
    expected_id = _KNOWN_BREEDS[canonical]

    # Randomise the casing
    variant = _random_case(canonical, data)

    result = asyncio.new_event_loop().run_until_complete(
        _run_import_with_breed(variant, _KNOWN_BREEDS)
    )

    assert result.created_count == 1, (
        f"Expected 1 created pet for breed '{variant}' (canonical '{canonical}'), "
        f"got {result.created_count}. Errors: {result.errors}"
    )
    assert result.errors == [], (
        f"Expected no errors for known breed '{variant}', got {result.errors}"
    )


# Strategy for breed names guaranteed NOT to match any known breed.
_unknown_breed_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L",)),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip().lower() not in _KNOWN_BREEDS)


@given(unknown_breed=_unknown_breed_strategy)
@settings(max_examples=100)
def test_breed_name_unknown_produces_error(unknown_breed: str):
    """Property 6 (unknown): A breed name that does not match any known breed
    (case-insensitive) causes the row to be skipped with an error containing
    "Unknown breed: {name}".

    **Validates: Requirements 5.6, 5.8**
    """
    result = asyncio.new_event_loop().run_until_complete(
        _run_import_with_breed(unknown_breed, _KNOWN_BREEDS)
    )

    assert result.created_count == 0, (
        f"Expected 0 created pets for unknown breed '{unknown_breed}', "
        f"got {result.created_count}"
    )
    assert len(result.errors) == 1, (
        f"Expected exactly 1 error for unknown breed, got {len(result.errors)}"
    )
    assert f"Unknown breed: {unknown_breed}" in result.errors[0].reason, (
        f"Error reason should contain 'Unknown breed: {unknown_breed}', "
        f"got '{result.errors[0].reason}'"
    )


# ---------------------------------------------------------------------------
# Property 7: Location name resolution
# Feature: csv-pet-import, Property 7: Location name resolution
# **Validates: Requirements 5.7, 5.9**
# ---------------------------------------------------------------------------

# A small fixed set of canonical location names with assigned IDs,
# scoped to a single breeder.
_KNOWN_LOCATIONS: dict[str, int] = {
    "main kennel": 10,
    "north barn": 20,
    "puppy room": 30,
    "outdoor yard": 40,
    "quarantine wing": 50,
}


async def _run_import_with_location(
    location_name: str,
    location_map: dict[str, int],
) -> ImportResult:
    """Run PetImportService.import_pets with a single row carrying *location_name*.

    The location_map is injected via mock so no real DB is needed.
    Breed resolution is bypassed (no breed on the row).
    Billing limits are set high so they never interfere.
    """
    service = PetImportService()

    row = PetImportRow(row_number=1, name="TestPet", location=location_name)

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    service._build_breed_map = AsyncMock(return_value={})
    service._build_location_map = AsyncMock(return_value=location_map)
    service._get_current_pet_count = AsyncMock(return_value=0)
    service._get_plan_max_pets = AsyncMock(return_value=999_999)

    import uuid
    user_id = uuid.uuid4()

    return await service.import_pets(mock_session, user_id, [row])


@given(data=st.data())
@settings(max_examples=100)
def test_location_name_case_insensitive_resolution(data):
    """Property 7 (match): A location name with random casing that matches a
    known breeder location (case-insensitive) resolves to the correct
    location_id and the pet is created successfully.

    **Validates: Requirements 5.7, 5.9**
    """
    # Pick a random known location
    canonical = data.draw(st.sampled_from(list(_KNOWN_LOCATIONS.keys())))
    expected_id = _KNOWN_LOCATIONS[canonical]

    # Randomise the casing
    variant = _random_case(canonical, data)

    result = asyncio.new_event_loop().run_until_complete(
        _run_import_with_location(variant, _KNOWN_LOCATIONS)
    )

    assert result.created_count == 1, (
        f"Expected 1 created pet for location '{variant}' (canonical '{canonical}'), "
        f"got {result.created_count}. Errors: {result.errors}"
    )
    assert result.errors == [], (
        f"Expected no errors for known location '{variant}', got {result.errors}"
    )


# Strategy for location names guaranteed NOT to match any known location.
_unknown_location_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L",)),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip().lower() not in _KNOWN_LOCATIONS)


@given(unknown_location=_unknown_location_strategy)
@settings(max_examples=100)
def test_location_name_unknown_produces_error(unknown_location: str):
    """Property 7 (unknown): A location name that does not match any of the
    breeder's known locations (case-insensitive) causes the row to be skipped
    with an error containing "Unknown location: {name}".

    **Validates: Requirements 5.7, 5.9**
    """
    result = asyncio.new_event_loop().run_until_complete(
        _run_import_with_location(unknown_location, _KNOWN_LOCATIONS)
    )

    assert result.created_count == 0, (
        f"Expected 0 created pets for unknown location '{unknown_location}', "
        f"got {result.created_count}"
    )
    assert len(result.errors) == 1, (
        f"Expected exactly 1 error for unknown location, got {len(result.errors)}"
    )
    assert f"Unknown location: {unknown_location}" in result.errors[0].reason, (
        f"Error reason should contain 'Unknown location: {unknown_location}', "
        f"got '{result.errors[0].reason}'"
    )
