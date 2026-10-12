"""Pure ordering and transition rules for waitlists."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from hypothesis import given, strategies as st

from app.services.waitlist_rules import can_transition, clamp_position, order_entries

T0 = datetime(2026, 10, 1, 12, 0)


@dataclass
class E:
    id: str
    queue_date: date | None
    created_at: datetime = T0
    position_override: int | None = None
    override_set_at: datetime | None = None


def ids(entries):
    return [e.id for e in order_entries(entries)]


def test_orders_by_queue_date_then_created_at():
    a = E("a", date(2026, 9, 3))
    b = E("b", date(2026, 9, 1), created_at=T0 + timedelta(minutes=5))
    c = E("c", date(2026, 9, 1))
    assert ids([a, b, c]) == ["c", "b", "a"]


def test_missing_queue_date_sorts_last():
    assert ids([E("x", None), E("y", date(2026, 9, 9))]) == ["y", "x"]


def test_override_pins_slot():
    a, b, c = E("a", date(2026, 9, 1)), E("b", date(2026, 9, 2)), E("c", date(2026, 9, 3))
    c.position_override, c.override_set_at = 1, T0
    assert ids([a, b, c]) == ["c", "a", "b"]


def test_override_beyond_end_is_clamped():
    a, b = E("a", date(2026, 9, 1)), E("b", date(2026, 9, 2))
    a.position_override, a.override_set_at = 99, T0
    assert ids([a, b]) == ["b", "a"]
    assert clamp_position(0, 3) == 1
    assert clamp_position(7, 3) == 3


def test_later_override_wins_contested_slot():
    a, b, c = E("a", date(2026, 9, 1)), E("b", date(2026, 9, 2)), E("c", date(2026, 9, 3))
    b.position_override, b.override_set_at = 1, T0
    c.position_override, c.override_set_at = 1, T0 + timedelta(hours=1)
    assert ids([a, b, c]) == ["c", "b", "a"]


@given(st.lists(st.tuples(st.integers(0, 30), st.one_of(st.none(), st.integers(1, 12))), max_size=10))
def test_order_is_permutation_with_pins(spec):
    entries = []
    for i, (day, pin) in enumerate(spec):
        e = E(str(i), date(2026, 9, 1) + timedelta(days=day), created_at=T0 + timedelta(seconds=i))
        if pin is not None:
            e.position_override, e.override_set_at = pin, T0 + timedelta(seconds=i)
        entries.append(e)
    ordered = order_entries(entries)
    assert sorted(e.id for e in ordered) == sorted(e.id for e in entries)
    unpinned = [e for e in ordered if e.position_override is None]
    assert unpinned == sorted(unpinned, key=lambda e: (e.queue_date, e.created_at))


def test_transitions():
    assert can_transition("pending", "approve", on_litter=False)
    assert can_transition("pending", "decline", on_litter=False)
    assert not can_transition("active", "approve", on_litter=False)
    assert can_transition("active", "match", on_litter=True)
    assert not can_transition("active", "match", on_litter=False)
    assert can_transition("active", "pass", on_litter=True)
    assert not can_transition("active", "pass", on_litter=False)
    assert can_transition("pending", "withdraw", on_litter=False)
    assert can_transition("active", "withdraw", on_litter=True)
    assert not can_transition("matched", "withdraw", on_litter=True)
    assert can_transition("active", "move", on_litter=False)
    assert not can_transition("pending", "move", on_litter=False)
    assert can_transition("active", "deposit", on_litter=True)
    assert can_transition("pending", "deposit", on_litter=False)
    assert not can_transition("declined", "deposit", on_litter=False)


def test_settle_deposit_only_after_withdrawal():
    assert can_transition("withdrawn", "settle_deposit", on_litter=False)
    assert not can_transition("active", "settle_deposit", on_litter=False)
    assert not can_transition("withdrawn", "deposit", on_litter=False)
