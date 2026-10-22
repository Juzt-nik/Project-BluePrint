from enum import Enum
from typing import TypeVar


class InvalidTransition(ValueError):
    pass


E = TypeVar("E", bound=Enum)


DEPOSIT_TRANSITIONS = {
    "DRAFT": {"SUBMITTED"},
    "SUBMITTED": {"UNDER_SCRUTINY"},
    "UNDER_SCRUTINY": {"CLARIFICATION_REQUIRED", "REVIEW_COMPLETE", "REJECTED"},
    "CLARIFICATION_REQUIRED": {"SUBMITTED", "REJECTED"},
    "REVIEW_COMPLETE": {"ACTIVE", "REJECTED"},
    "ACTIVE": {"RENEWAL_PENDING", "REPLACEMENT_PENDING", "MATURED", "CLOSED"},
    "RENEWAL_PENDING": {"ACTIVE", "MATURED", "CLOSED"},
    "REPLACEMENT_PENDING": {"ACTIVE", "MATURED", "CLOSED"},
    "MATURED": {"CLOSED"},
    "CLOSED": set(),
    "REJECTED": set(),
}

CASE_TRANSITIONS = {
    "OPEN": {"ASSIGNED"},
    "ASSIGNED": {"UNDER_REVIEW"},
    "UNDER_REVIEW": {
        "CLARIFICATION_REQUIRED", "AWAITING_EXTERNAL_VERIFICATION",
        "READY_FOR_DECISION", "REJECTED"
    },
    "CLARIFICATION_REQUIRED": {"ASSIGNED", "REJECTED"},
    "AWAITING_EXTERNAL_VERIFICATION": {"UNDER_REVIEW", "READY_FOR_DECISION"},
    "READY_FOR_DECISION": {"COMPLETED", "REJECTED"},
    "COMPLETED": set(),
    "REJECTED": set(),
}

RELEASE_TRANSITIONS = {
    "DRAFT": {"SUBMITTED"},
    "SUBMITTED": {"DOCUMENT_REVIEW"},
    "DOCUMENT_REVIEW": {"CLARIFICATION_REQUIRED", "AWAITING_CLEARANCES", "REJECTED"},
    "CLARIFICATION_REQUIRED": {"SUBMITTED", "REJECTED"},
    "AWAITING_CLEARANCES": {"READY_FOR_AUTHORITY", "REJECTED"},
    "READY_FOR_AUTHORITY": {"AUTHORITY_ACTION_RECORDED", "REJECTED"},
    "AUTHORITY_ACTION_RECORDED": {"COMPLETED"},
    "COMPLETED": set(),
    "REJECTED": set(),
}


def validate_transition(current: str | Enum, target: str | Enum, transitions: dict[str, set[str]]) -> None:
    current_value = current.value if isinstance(current, Enum) else str(current)
    target_value = target.value if isinstance(target, Enum) else str(target)
    allowed = transitions.get(current_value, set())
    if target_value not in allowed:
        raise InvalidTransition(
            f"Transition from {current_value} to {target_value} is not allowed. "
            f"Allowed next states: {', '.join(sorted(allowed)) or 'none'}."
        )


def transition(current: E, target: E, transitions: dict[str, set[str]]) -> E:
    validate_transition(current, target, transitions)
    return type(current)(target.value if isinstance(target, Enum) else target)
