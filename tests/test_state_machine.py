import pytest

from app.models.enums import CaseStatus, DepositStatus, ReleaseStatus
from app.workflow.service import (
    validate_case_transition, validate_deposit_transition, validate_release_transition
)
from app.workflow.state_machine import InvalidTransition


def test_valid_deposit_transition():
    validate_deposit_transition(DepositStatus.DRAFT, DepositStatus.SUBMITTED)


def test_invalid_deposit_transition_cannot_skip_scrutiny():
    with pytest.raises(InvalidTransition):
        validate_deposit_transition(DepositStatus.DRAFT, DepositStatus.ACTIVE)


def test_terminal_deposit_state_has_no_outgoing_transition():
    with pytest.raises(InvalidTransition):
        validate_deposit_transition(DepositStatus.CLOSED, DepositStatus.ACTIVE)


def test_valid_case_transition():
    validate_case_transition(CaseStatus.OPEN, CaseStatus.ASSIGNED)


def test_case_cannot_complete_without_decision_stage():
    with pytest.raises(InvalidTransition):
        validate_case_transition(CaseStatus.UNDER_REVIEW, CaseStatus.COMPLETED)


def test_valid_release_transition():
    validate_release_transition(ReleaseStatus.DRAFT, ReleaseStatus.SUBMITTED)


def test_release_cannot_skip_clearances():
    with pytest.raises(InvalidTransition):
        validate_release_transition(ReleaseStatus.DOCUMENT_REVIEW, ReleaseStatus.READY_FOR_AUTHORITY)


def test_completed_release_is_terminal():
    with pytest.raises(InvalidTransition):
        validate_release_transition(ReleaseStatus.COMPLETED, ReleaseStatus.SUBMITTED)
