"""
Pure ordering and transition rules for breeder waitlists.

A list (general or one litter) is ordered by `queue_date` (deposit date, else
approval date) unless the breeder pinned an entry to a slot. Positions are
1-based and computed on read; only the override is stored.
"""
from datetime import date, datetime
from enum import Enum
from typing import Optional, Protocol, Sequence, TypeVar


class Status(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DECLINED = "declined"
    MATCHED = "matched"
    WITHDRAWN = "withdrawn"


class DepositStatus(str, Enum):
    NONE = "none"
    REQUESTED = "requested"
    RECEIVED = "received"
    REFUNDED = "refunded"
    FORFEITED = "forfeited"
    APPLIED = "applied"


ACTIVE_STATUSES = frozenset({Status.PENDING.value, Status.ACTIVE.value})


class Orderable(Protocol):
    queue_date: Optional[date]
    created_at: datetime
    position_override: Optional[int]
    override_set_at: Optional[datetime]


T = TypeVar("T", bound=Orderable)

_FAR_FUTURE = date.max


def clamp_position(position: int, list_size: int) -> int:
    return max(1, min(position, max(list_size, 1)))


def order_entries(entries: Sequence[T]) -> list[T]:
    """Pinned entries take their (clamped) slot — the latest override wins a contested
    slot and earlier ones shift down — and the rest fill the gaps by queue date."""
    size = len(entries)
    pinned = sorted(
        (e for e in entries if e.position_override is not None),
        key=lambda e: e.override_set_at or datetime.min,
        reverse=True,  # latest override placed first
    )
    unpinned = sorted(
        (e for e in entries if e.position_override is None),
        key=lambda e: (e.queue_date or _FAR_FUTURE, e.created_at),
    )
    slots: list[Optional[T]] = [None] * size
    for e in pinned:
        want = clamp_position(e.position_override or 1, size) - 1
        idx = want
        while idx < size and slots[idx] is not None:
            idx += 1
        if idx >= size:  # shifted past the end: take the nearest free slot above
            idx = want
            while slots[idx] is not None:
                idx -= 1
        slots[idx] = e
    rest = iter(unpinned)
    return [s if s is not None else next(rest) for s in slots]


_ALLOWED: dict[str, set[str]] = {
    "approve": {Status.PENDING.value},
    "decline": {Status.PENDING.value},
    "withdraw": {Status.PENDING.value, Status.ACTIVE.value},
    "move": {Status.ACTIVE.value},
    "reorder": {Status.ACTIVE.value},
    "deposit": {Status.PENDING.value, Status.ACTIVE.value},
    "match": {Status.ACTIVE.value},
    "pass": {Status.ACTIVE.value},
}
_LITTER_ONLY = {"match", "pass"}


def can_transition(status: str, action: str, on_litter: bool) -> bool:
    if action in _LITTER_ONLY and not on_litter:
        return False
    return status in _ALLOWED.get(action, set())
