from app.models.enums import CaseStatus, DepositStatus, ReleaseStatus
from app.workflow.state_machine import (
    CASE_TRANSITIONS, DEPOSIT_TRANSITIONS, RELEASE_TRANSITIONS,
    InvalidTransition, validate_transition
)


def validate_deposit_transition(current: DepositStatus, target: DepositStatus) -> None:
    validate_transition(current, target, DEPOSIT_TRANSITIONS)


def validate_case_transition(current: CaseStatus, target: CaseStatus) -> None:
    validate_transition(current, target, CASE_TRANSITIONS)


def validate_release_transition(current: ReleaseStatus, target: ReleaseStatus) -> None:
    validate_transition(current, target, RELEASE_TRANSITIONS)
