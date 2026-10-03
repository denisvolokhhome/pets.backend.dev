"""Shared Pydantic validators reused across schema modules.

These centralize the ``validate_not_whitespace`` convention noted in the
project docs so the check lives in one place instead of being copy-pasted per
schema. Prefer the ``NonWhitespaceStr`` / ``OptionalNonWhitespaceStr`` annotated
types for new fields; the bare functions are exposed for cases that need to wire
a validator onto an existing field declaration.
"""
from typing import Annotated, Optional

from pydantic import AfterValidator

_EMPTY_MESSAGE = "Field cannot be empty or whitespace-only"


def reject_whitespace(v: str) -> str:
    """Reject empty or whitespace-only strings for required fields."""
    if not v or not v.strip():
        raise ValueError(_EMPTY_MESSAGE)
    return v


def reject_whitespace_optional(v: Optional[str]) -> Optional[str]:
    """Reject whitespace-only strings for optional fields; ``None`` passes through."""
    if v is not None and (not v or not v.strip()):
        raise ValueError(_EMPTY_MESSAGE)
    return v


# Annotated string types carrying the whitespace check, for concise reuse in
# field declarations, e.g. ``name: NonWhitespaceStr = Field(..., max_length=255)``.
NonWhitespaceStr = Annotated[str, AfterValidator(reject_whitespace)]
OptionalNonWhitespaceStr = Annotated[Optional[str], AfterValidator(reject_whitespace_optional)]
