"""Pure, DB-free rules for litter applications: statuses, transitions, answer snapshots."""
from typing import Any, Iterable, Mapping, Optional

STATUSES = ("new", "contacted", "waitlisted", "assigned", "declined")
# Statuses a breeder can set by hand; "assigned" only comes from assigning a puppy
MANUAL_STATUSES = frozenset({"new", "contacted", "waitlisted", "declined"})
# Statuses from which a puppy can be assigned
ASSIGNABLE_STATUSES = frozenset({"new", "contacted", "waitlisted"})
# Status an application returns to when its assignment is undone
UNASSIGNED_STATUS = "waitlisted"

MAX_ANSWER_LENGTH = 5000


class RuleError(ValueError):
    """A request that breaks a rule; ``code`` maps to an HTTP status in the service."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


def check_manual_status_change(current: str, new: str) -> None:
    if new not in MANUAL_STATUSES:
        raise RuleError("Use Assign puppy to mark an application as assigned", "invalid")
    if current == "assigned":
        raise RuleError("Undo the puppy assignment before changing the status", "conflict")


def check_can_assign(current: str) -> None:
    if current == "assigned":
        raise RuleError("This application already has a puppy. Undo it first to pick another.", "conflict")
    if current not in ASSIGNABLE_STATUSES:
        raise RuleError("Declined applications can't be assigned a puppy", "conflict")


def check_can_unassign(current: str) -> None:
    if current != "assigned":
        raise RuleError("This application has no puppy assigned", "conflict")


def snapshot_answers(fields: Iterable[Mapping[str, Any]],
                     answers: Optional[Mapping[str, Any]]) -> list[dict[str, str]]:
    """
    Validate answers against the form and freeze them with their labels.

    Unknown keys are ignored; required fields must be non-blank.
    """
    answers = answers or {}
    snapshot: list[dict[str, str]] = []
    missing: list[str] = []
    for field in fields:
        field_id = str(field.get("id", ""))
        label = str(field.get("label", ""))
        raw = answers.get(field_id)
        value = raw.strip() if isinstance(raw, str) else ""
        if len(value) > MAX_ANSWER_LENGTH:
            raise RuleError(f'"{label}" is too long (max {MAX_ANSWER_LENGTH} characters)', "invalid")
        if field.get("required") and not value:
            missing.append(label)
        snapshot.append({"field_id": field_id, "label": label, "value": value})
    if missing:
        raise RuleError("Please answer: " + ", ".join(missing), "invalid")
    return snapshot
