from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_authenticated_user, is_institution_user, normalized_role
from app.db.session import get_db
from app.models.entities import AuditEvent, ClearanceRecord, Deposit, Institution, ReleaseRequest, User
from app.models.enums import ClearanceStatus, ClearanceUnit, DepositStatus, ReleaseMethod, ReleaseStatus
from app.workflow.state_machine import InvalidTransition, validate_transition, RELEASE_TRANSITIONS

router = APIRouter(prefix="/release-requests", tags=["release requests"])
REVIEW_ROLES = {"case_officer"}
ASSIGN_ROLES = {"case_officer", "admin"}
# Platform administration is intentionally separate from regulatory decisions.
CLEARANCE_ROLES = {"clearance_officer"}
AUTHORITY_ROLES = {"approval_authority"}
READ_ROLES = {"admin", "case_officer", "clearance_officer", "approval_authority", "auditor"}


class ReleaseCreate(BaseModel):
    deposit_id: str
    request_reference: str = Field(min_length=3, max_length=80)
    release_method: ReleaseMethod


class ReleaseTransition(BaseModel):
    target_status: ReleaseStatus
    reason: str | None = Field(default=None, max_length=2000)
    final_action_reference: str | None = Field(default=None, min_length=1, max_length=150)
    final_action_date: date | None = None
    final_action_note: str | None = Field(default=None, max_length=2000)


class ClearanceDecision(BaseModel):
    status: ClearanceStatus
    outcome_note: str = Field(min_length=1, max_length=2000)


class ClearanceAssignment(BaseModel):
    assigned_to_user_id: str


def _get_release(db: Session, release_id: str, *, lock: bool = False) -> ReleaseRequest:
    query = db.query(ReleaseRequest).filter(ReleaseRequest.id == release_id)
    # On PostgreSQL this serializes clearance decisions and workflow transitions
    # for a release request. SQLite ignores FOR UPDATE, which is fine for tests.
    if lock:
        query = query.with_for_update()
    item = query.one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Release request not found.")
    return item


def _check_read_access(item: ReleaseRequest, user: User) -> None:
    role = normalized_role(user)
    if is_institution_user(user):
        if user.institution_id != item.deposit.institution_id:
            raise HTTPException(status_code=403, detail="You may only access release requests for your institution.")
    elif role not in READ_ROLES:
        raise HTTPException(status_code=403, detail="You are not permitted to access release requests.")


def _audit(db: Session, item: ReleaseRequest, user: User, action: str, before: dict | None, after: dict | None, reason: str | None = None):
    institution = item.deposit.institution
    db.add(AuditEvent(
        institution_id=item.deposit.institution_id,
        entity_type="release_request",
        entity_id=item.id,
        actor_user_id=user.id,
        action=action,
        before_state=before,
        after_state=after,
        reason=reason,
        is_synthetic=bool(institution and institution.is_synthetic),
    ))


def _required_clearances_met(item: ReleaseRequest) -> tuple[bool, list[str]]:
    required = {ClearanceUnit.PGRC, ClearanceUnit.VIGILANCE, ClearanceUnit.RELEVANT_CELL_OR_BUREAU}
    by_unit = {c.unit: c for c in item.clearances}
    missing = []
    for unit in sorted(required, key=lambda u: u.value):
        record = by_unit.get(unit)
        # Every configured mandatory unit must explicitly clear the request.
        # NOT_APPLICABLE does not satisfy a mandatory gate without a separately
        # approved policy exception mechanism.
        if record is None or record.status != ClearanceStatus.CLEARED:
            missing.append(unit.value)
    return not missing, missing


@router.post("", status_code=status.HTTP_201_CREATED)
def create_release_request(payload: ReleaseCreate, db: Session = Depends(get_db), user: User = Depends(get_authenticated_user)):
    if not is_institution_user(user) and normalized_role(user) not in REVIEW_ROLES:
        raise HTTPException(status_code=403, detail="You are not permitted to create release requests.")
    deposit = db.get(Deposit, payload.deposit_id)
    if deposit is None:
        raise HTTPException(status_code=404, detail="Deposit not found.")
    if is_institution_user(user) and deposit.institution_id != user.institution_id:
        raise HTTPException(status_code=403, detail="You may only request release for your own institution.")
    if deposit.status not in {DepositStatus.ACTIVE, DepositStatus.MATURED}:
        raise HTTPException(status_code=409, detail="Release can only be requested for an active or matured deposit.")
    if db.query(ReleaseRequest).filter_by(request_reference=payload.request_reference).first():
        raise HTTPException(status_code=409, detail="Release request reference already exists.")
    item = ReleaseRequest(
        id=str(uuid4()), deposit_id=deposit.id, request_reference=payload.request_reference,
        release_method=payload.release_method, status=ReleaseStatus.DRAFT, requested_by_user_id=user.id,
    )
    db.add(item)
    db.flush()
    for unit in (ClearanceUnit.PGRC, ClearanceUnit.VIGILANCE, ClearanceUnit.RELEVANT_CELL_OR_BUREAU):
        db.add(ClearanceRecord(release_request_id=item.id, unit=unit, status=ClearanceStatus.NOT_STARTED))
    _audit(db, item, user, "RELEASE_REQUEST_CREATED", None, {"status": item.status.value, "release_method": item.release_method.value})
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.get("")
def list_release_requests(db: Session = Depends(get_db), user: User = Depends(get_authenticated_user)):
    query = db.query(ReleaseRequest)
    if is_institution_user(user):
        if not user.institution_id:
            return []
        query = query.join(Deposit).filter(Deposit.institution_id == user.institution_id)
    elif normalized_role(user) not in READ_ROLES:
        raise HTTPException(status_code=403, detail="You are not permitted to access release requests.")
    return [_serialize(item) for item in query.order_by(ReleaseRequest.created_at.desc()).all()]


@router.get("/{release_id}")
def get_release_request(release_id: str, db: Session = Depends(get_db), user: User = Depends(get_authenticated_user)):
    item = _get_release(db, release_id)
    _check_read_access(item, user)
    return _serialize(item)


@router.post("/{release_id}/clearances/{unit}/assign")
def assign_clearance(
    release_id: str,
    unit: ClearanceUnit,
    payload: ClearanceAssignment,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    if normalized_role(user) not in ASSIGN_ROLES:
        raise HTTPException(status_code=403, detail="Only authorized case reviewers may assign clearances.")
    item = _get_release(db, release_id, lock=True)
    if item.status not in {ReleaseStatus.DOCUMENT_REVIEW, ReleaseStatus.AWAITING_CLEARANCES}:
        raise HTTPException(status_code=409, detail="Clearances can only be assigned during document review or the clearance stage.")
    record = next((c for c in item.clearances if c.unit == unit), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Clearance unit is not configured for this release.")
    assignee = db.get(User, payload.assigned_to_user_id)
    if assignee is None or not assignee.is_active or normalized_role(assignee) != "clearance_officer":
        raise HTTPException(status_code=422, detail="Assignee must be an active clearance officer.")
    if assignee.id == item.requested_by_user_id:
        raise HTTPException(status_code=409, detail="The release requester cannot be assigned to clear their own request.")
    before = {"unit": unit.value, "assigned_to_user_id": record.assigned_to_user_id}
    record.assigned_to_user_id = assignee.id
    if record.status == ClearanceStatus.NOT_STARTED:
        record.status = ClearanceStatus.PENDING
    _audit(db, item, user, "RELEASE_CLEARANCE_ASSIGNED", before, {"unit": unit.value, "assigned_to_user_id": assignee.id})
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.post("/{release_id}/clearances/{unit}")
def decide_clearance(
    release_id: str,
    unit: ClearanceUnit,
    payload: ClearanceDecision,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    if normalized_role(user) not in CLEARANCE_ROLES:
        raise HTTPException(status_code=403, detail="Only clearance officers may record clearance decisions.")
    item = _get_release(db, release_id, lock=True)
    if item.status not in {ReleaseStatus.AWAITING_CLEARANCES, ReleaseStatus.DOCUMENT_REVIEW}:
        raise HTTPException(status_code=409, detail="Clearances can only be recorded during document review or the clearance stage.")
    if payload.status not in {ClearanceStatus.CLEARED, ClearanceStatus.NOT_CLEARED, ClearanceStatus.NOT_APPLICABLE}:
        raise HTTPException(status_code=422, detail="A decision must be CLEARED, NOT_CLEARED, or NOT_APPLICABLE.")
    record = next((c for c in item.clearances if c.unit == unit), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Clearance unit is not configured for this release.")
    if record.assigned_to_user_id is None:
        raise HTTPException(status_code=409, detail="This clearance must be assigned before a decision can be recorded.")
    if record.assigned_to_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the officer assigned to this clearance may decide it.")
    if item.requested_by_user_id == user.id:
        raise HTTPException(status_code=403, detail="The release requester cannot decide their own clearance.")
    before = {"unit": unit.value, "status": record.status.value}
    record.status = payload.status
    record.outcome_note = payload.outcome_note
    record.decided_by_user_id = user.id
    from app.models.entities import utc_now
    record.decided_at = utc_now()
    _audit(db, item, user, "RELEASE_CLEARANCE_DECIDED", before, {"unit": unit.value, "status": record.status.value}, payload.outcome_note)
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.post("/{release_id}/transition")
def transition_release_request(release_id: str, payload: ReleaseTransition, db: Session = Depends(get_db), user: User = Depends(get_authenticated_user)):
    item = _get_release(db, release_id, lock=True)
    _check_read_access(item, user)
    role = normalized_role(user)
    target = payload.target_status

    if target == ReleaseStatus.SUBMITTED:
        if not is_institution_user(user) and role not in REVIEW_ROLES:
            raise HTTPException(status_code=403, detail="You are not permitted to submit this release request.")
    elif target == ReleaseStatus.CLARIFICATION_REQUIRED:
        if role not in REVIEW_ROLES:
            raise HTTPException(status_code=403, detail="Only case officers may request clarification.")
    elif target in {ReleaseStatus.DOCUMENT_REVIEW, ReleaseStatus.AWAITING_CLEARANCES, ReleaseStatus.REJECTED}:
        if role not in REVIEW_ROLES:
            raise HTTPException(status_code=403, detail="Only case officers may perform this workflow transition.")
    elif target == ReleaseStatus.READY_FOR_AUTHORITY:
        if role not in REVIEW_ROLES:
            raise HTTPException(status_code=403, detail="Only case officers may advance a release for authority review.")
        ok, missing = _required_clearances_met(item)
        if not ok:
            raise HTTPException(status_code=409, detail={"message": "Required clearances are incomplete.", "missing_clearances": missing})
        if item.status != ReleaseStatus.AWAITING_CLEARANCES:
            raise HTTPException(status_code=409, detail="Release must be awaiting clearances before authority review.")
    elif target == ReleaseStatus.AUTHORITY_ACTION_RECORDED:
        if role not in AUTHORITY_ROLES:
            raise HTTPException(status_code=403, detail="Only the competent authority may record the final action.")
        if item.status != ReleaseStatus.READY_FOR_AUTHORITY:
            raise HTTPException(status_code=409, detail="Release is not ready for authority action.")
        ok, missing = _required_clearances_met(item)
        if not ok:
            raise HTTPException(status_code=409, detail={"message": "Required clearances are incomplete.", "missing_clearances": missing})
        if not payload.final_action_reference or not payload.final_action_date or not payload.final_action_note:
            raise HTTPException(status_code=422, detail="Final action reference, date, and note are required.")
        if item.requested_by_user_id == user.id:
            raise HTTPException(status_code=403, detail="The release requester cannot approve their own release.")
        if any(c.decided_by_user_id == user.id for c in item.clearances):
            raise HTTPException(status_code=403, detail="A clearance decision-maker cannot provide the final authority action for the same release.")
        item.final_authority_role = role
        item.final_action_reference = payload.final_action_reference
        item.final_action_date = payload.final_action_date
        item.final_action_note = payload.final_action_note
    elif target == ReleaseStatus.COMPLETED:
        if role not in AUTHORITY_ROLES:
            raise HTTPException(status_code=403, detail="Only the competent authority may complete a release.")
        if item.status != ReleaseStatus.AUTHORITY_ACTION_RECORDED:
            raise HTTPException(status_code=409, detail="A recorded competent-authority action is required before completion.")
        if not item.final_action_reference or not item.final_action_date or not item.final_action_note:
            raise HTTPException(status_code=409, detail="Complete authority-action details are required before completion.")
        ok, missing = _required_clearances_met(item)
        if not ok:
            raise HTTPException(status_code=409, detail={"message": "Required clearances are incomplete.", "missing_clearances": missing})
    else:
        raise HTTPException(status_code=403, detail="This role cannot perform the requested transition.")

    old = item.status
    try:
        validate_transition(old, target, RELEASE_TRANSITIONS)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    item.status = target
    if target == ReleaseStatus.COMPLETED:
        from app.models.entities import utc_now
        item.completed_at = utc_now()
    _audit(db, item, user, "RELEASE_STATUS_CHANGED", {"status": old.value}, {"status": target.value}, payload.reason)
    db.commit()
    db.refresh(item)
    return _serialize(item)


def _serialize(item: ReleaseRequest) -> dict:
    return {
        "id": item.id,
        "deposit_id": item.deposit_id,
        "request_reference": item.request_reference,
        "release_method": item.release_method.value,
        "status": item.status.value,
        "requested_by_user_id": item.requested_by_user_id,
        "final_authority_role": item.final_authority_role,
        "final_action_reference": item.final_action_reference,
        "final_action_date": item.final_action_date.isoformat() if item.final_action_date else None,
        "final_action_note": item.final_action_note,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "clearances": [
            {"unit": c.unit.value, "status": c.status.value, "outcome_note": c.outcome_note,
             "decided_by_user_id": c.decided_by_user_id,
             "decided_at": c.decided_at.isoformat() if c.decided_at else None}
            for c in item.clearances
        ],
    }
