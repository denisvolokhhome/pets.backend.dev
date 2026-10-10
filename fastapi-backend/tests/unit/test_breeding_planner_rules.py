"""Pure date/stage rules for the breeding planner."""
from datetime import date, timedelta

from hypothesis import given, strategies as st

from app.services.breeding_planner_rules import (
    Stage, allowed_targets, can_set_stage, due_window, gestation_days,
    milestone_plan, normalize_kind,
)

ANCHOR = date(2026, 9, 1)


def test_gestation_by_kind():
    assert gestation_days("dog") == 63
    assert gestation_days("cat") == 65
    assert gestation_days("cow") == 283
    assert gestation_days("horse") == 340
    assert gestation_days(None) == 63
    assert normalize_kind("Unknown") == "dog"


def test_due_window_widths():
    due, start, end = due_window(ANCHOR, "dog", on_ovulation=True)
    assert due == ANCHOR + timedelta(days=63)
    assert (start, end) == (due - timedelta(days=1), due + timedelta(days=1))
    due, start, end = due_window(ANCHOR, "cat", on_ovulation=False)
    assert due == ANCHOR + timedelta(days=65)
    assert (start, end) == (due - timedelta(days=5), due + timedelta(days=5))
    due, start, end = due_window(ANCHOR, "horse", on_ovulation=False)
    assert (start, end) == (due - timedelta(days=10), due + timedelta(days=10))


def test_dog_template():
    plan = {m.key: m for m in milestone_plan(ANCHOR, "dog")}
    assert [k for k in plan] == ["ultrasound", "xray", "whelping_box", "temperature", "due"]
    assert plan["ultrasound"].due_on == ANCHOR + timedelta(days=28)
    assert plan["ultrasound"].remind_on == ANCHOR + timedelta(days=26)
    assert plan["temperature"].remind_on == plan["temperature"].due_on
    assert plan["due"].due_on == ANCHOR + timedelta(days=63)
    assert plan["due"].remind_on == ANCHOR + timedelta(days=56)


def test_cat_template_offsets():
    plan = {m.key: m.due_on for m in milestone_plan(ANCHOR, "cat")}
    assert plan == {k: ANCHOR + timedelta(days=d) for k, d in
                    {"ultrasound": 21, "xray": 45, "whelping_box": 58, "temperature": 60, "due": 65}.items()}


def test_large_animals_only_get_due_milestone():
    plan = milestone_plan(ANCHOR, "cow")
    assert [m.key for m in plan] == ["due"]
    assert plan[0].remind_on == plan[0].due_on - timedelta(days=14)


@given(st.dates(min_value=date(2000, 1, 1), max_value=date(2090, 1, 1)),
       st.integers(min_value=-200, max_value=200),
       st.sampled_from(["dog", "cat", "cow", "horse"]))
def test_plan_invariants(anchor, shift, kind):
    plan = milestone_plan(anchor, kind)
    assert [m.due_on for m in plan] == sorted(m.due_on for m in plan)
    assert all(m.remind_on <= m.due_on for m in plan)
    shifted = milestone_plan(anchor + timedelta(days=shift), kind)
    assert [m.due_on - p.due_on for m, p in zip(shifted, plan)] == [timedelta(days=shift)] * len(plan)


def test_stage_transitions():
    assert allowed_targets(Stage.MATED, True) == ["Confirmed", "Missed"]
    assert allowed_targets(Stage.CONFIRMED, True) == ["Mated", "Missed"]
    assert allowed_targets(Stage.MISSED, True) == ["Mated"]
    assert allowed_targets(Stage.PLANNED, True) == []
    assert allowed_targets(Stage.WHELPED, True) == []
    assert allowed_targets(Stage.MATED, False) == []
    assert can_set_stage("Mated", "Confirmed", True)
    assert not can_set_stage("Mated", "Whelped", True)
    assert not can_set_stage("Planned", "Confirmed", True)
