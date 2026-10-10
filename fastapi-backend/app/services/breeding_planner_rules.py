"""
Pure date and stage rules for the breeding cycle planner.

No database access here — everything is a function of an anchor date (ovulation
date if known, otherwise the first mating) and the species (`Breed.kind`).
"""
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class Stage(str, Enum):
    """Biological stage of a breeding (separate from the record `status`)."""
    PLANNED = "Planned"
    MATED = "Mated"
    CONFIRMED = "Confirmed"
    MISSED = "Missed"
    WHELPED = "Whelped"


# Stages during which milestone reminders are sent
REMINDER_STAGES = frozenset({Stage.MATED.value, Stage.CONFIRMED.value})

GESTATION_DAYS = {"dog": 63, "cat": 65, "cow": 283, "horse": 340}
DEFAULT_KIND = "dog"

# Stage changes a breeder may make by hand (Planned and Whelped are system-set)
_BREEDER_TRANSITIONS: dict[str, list[str]] = {
    Stage.MATED.value: [Stage.CONFIRMED.value, Stage.MISSED.value],
    Stage.CONFIRMED.value: [Stage.MATED.value, Stage.MISSED.value],
    Stage.MISSED.value: [Stage.MATED.value],
}


@dataclass(frozen=True)
class _Template:
    key: str
    title: str
    offset: int
    remind_before: int


@dataclass(frozen=True)
class PlannedMilestone:
    key: str
    title: str
    due_on: date
    remind_on: date


_TITLES = {
    "ultrasound": "Ultrasound — confirm pregnancy",
    "xray": "X-ray — count the litter",
    "whelping_box": "Set up the whelping/nesting box",
    "temperature": "Start twice-daily temperature checks",
    "due": "Due date",
}


def _templates(offsets: dict[str, int], remind: dict[str, int]) -> list[_Template]:
    return [_Template(k, _TITLES[k], offsets[k], remind[k]) for k in offsets]


_SMALL_ANIMAL_REMIND = {"ultrasound": 2, "xray": 2, "whelping_box": 3, "temperature": 0, "due": 7}

TEMPLATES: dict[str, list[_Template]] = {
    "dog": _templates(
        {"ultrasound": 28, "xray": 55, "whelping_box": 56, "temperature": 58, "due": 63},
        _SMALL_ANIMAL_REMIND,
    ),
    "cat": _templates(
        {"ultrasound": 21, "xray": 45, "whelping_box": 58, "temperature": 60, "due": 65},
        _SMALL_ANIMAL_REMIND,
    ),
    "cow": _templates({"due": GESTATION_DAYS["cow"]}, {"due": 14}),
    "horse": _templates({"due": GESTATION_DAYS["horse"]}, {"due": 14}),
}


def normalize_kind(kind: str | None) -> str:
    kind = (kind or "").lower()
    return kind if kind in GESTATION_DAYS else DEFAULT_KIND


def gestation_days(kind: str | None) -> int:
    return GESTATION_DAYS[normalize_kind(kind)]


def due_window(anchor: date, kind: str | None, on_ovulation: bool) -> tuple[date, date, date]:
    """Return (due_date, window_start, window_end)."""
    kind = normalize_kind(kind)
    due = anchor + timedelta(days=gestation_days(kind))
    if kind in ("cow", "horse"):
        spread = 10
    else:
        spread = 1 if on_ovulation else 5
    return due, due - timedelta(days=spread), due + timedelta(days=spread)


def milestone_plan(anchor: date, kind: str | None) -> list[PlannedMilestone]:
    """Template milestones for a pregnancy anchored on `anchor`, sorted by date."""
    plan = [
        PlannedMilestone(
            key=t.key,
            title=t.title,
            due_on=anchor + timedelta(days=t.offset),
            remind_on=anchor + timedelta(days=t.offset - t.remind_before),
        )
        for t in TEMPLATES[normalize_kind(kind)]
    ]
    return sorted(plan, key=lambda m: m.due_on)


def allowed_targets(current: str, has_matings: bool) -> list[str]:
    """Stages a breeder may move to from `current`."""
    if not has_matings:
        return []
    return list(_BREEDER_TRANSITIONS.get(current, []))


def can_set_stage(current: str, target: str, has_matings: bool) -> bool:
    return target in allowed_targets(current, has_matings)
