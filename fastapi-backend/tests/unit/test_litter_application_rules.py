import pytest

from app.services import litter_application_rules as rules

FIELDS = [{"id": "a", "label": "Name", "required": True}, {"id": "b", "label": "Yard", "required": False}]


def test_snapshot_keeps_labels_and_order_and_trims():
    snap = rules.snapshot_answers(FIELDS, {"b": "  big ", "a": "Ann", "zzz": "ignored"})
    assert snap == [{"field_id": "a", "label": "Name", "value": "Ann"},
                    {"field_id": "b", "label": "Yard", "value": "big"}]


def test_snapshot_requires_required_fields():
    with pytest.raises(rules.RuleError) as e:
        rules.snapshot_answers(FIELDS, {"a": "   "})
    assert "Name" in str(e.value) and e.value.code == "invalid"


def test_snapshot_rejects_overlong_answers():
    with pytest.raises(rules.RuleError):
        rules.snapshot_answers(FIELDS, {"a": "x" * (rules.MAX_ANSWER_LENGTH + 1)})


def test_manual_status_cannot_set_assigned_or_leave_assigned():
    with pytest.raises(rules.RuleError):
        rules.check_manual_status_change("new", "assigned")
    with pytest.raises(rules.RuleError) as e:
        rules.check_manual_status_change("assigned", "waitlisted")
    assert e.value.code == "conflict"
    rules.check_manual_status_change("declined", "waitlisted")


@pytest.mark.parametrize("current", ["new", "contacted", "waitlisted"])
def test_assignable_statuses(current):
    rules.check_can_assign(current)


@pytest.mark.parametrize("current", ["assigned", "declined"])
def test_not_assignable_statuses(current):
    with pytest.raises(rules.RuleError):
        rules.check_can_assign(current)


def test_unassign_needs_assignment():
    with pytest.raises(rules.RuleError):
        rules.check_can_unassign("waitlisted")
    rules.check_can_unassign("assigned")
