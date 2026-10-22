from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import can_review_deposits, get_authenticated_user, is_institution_user, normalized_role, require_roles
from app.db.session import get_db
from app.models.entities import AuditEvent, Deposit, Institution, User
from app.models.enums import DepositStatus
from app.schemas.deposit import DepositCreate, DepositRead, DepositTransitionRequest
from app.workflow.state_machine import DEPOSIT_TRANSITIONS, InvalidTransition, validate_transition

router = APIRouter(prefix="/deposits", tags=["deposits"])


@router.post("", response_model=DepositRead, status_code=status.HTTP_201_CREATED)
def create_deposit(
    payload: DepositCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("institution_representative")),
):
    institution = db.get(Institution, payload.institution_id)
    if not institution or not institution.is_active:
        raise HTTPException(status_code=404, detail="Active institution not found.")
    if is_institution_user(user) and user.institution_id != institution.id:
        raise HTTPException(status_code=403, detail="You may only create deposits for your own institution.")
    duplicate = db.query(Deposit).filter_by(institution_id=payload.institution_id, internal_reference=payload.internal_reference).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Internal reference already exists for this institution.")
    item = Deposit(**payload.model_dump(), status=DepositStatus.DRAFT, created_by_user_id=user.id)
    db.add(item)
    db.flush()
    db.add(AuditEvent(
        institution_id=item.institution_id, entity_type="deposit", entity_id=item.id,
        actor_user_id=user.id, action="DEPOSIT_CREATED",
        after_state={"status": item.status.value, "internal_reference": item.internal_reference},
        is_synthetic=institution.is_synthetic,
    ))
    db.commit()
    db.refresh(item)
    return item


@router.get("", response_model=list[DepositRead])
def list_deposits(
    institution_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    query = db.query(Deposit)
    if is_institution_user(user):
        if not user.institution_id:
            return []
        query = query.filter(Deposit.institution_id == user.institution_id)
    elif normalized_role(user) not in {"admin", "case_officer", "clearance_officer", "approval_authority", "auditor", "technical_admin"}:
        raise HTTPException(status_code=403, detail="You are not permitted to view deposits.")
    if institution_id:
        if is_institution_user(user) and institution_id != user.institution_id:
            raise HTTPException(status_code=403, detail="You may only view your own institution's deposits.")
        query = query.filter(Deposit.institution_id == institution_id)
    return query.order_by(Deposit.created_at.desc()).all()


@router.get("/{deposit_id}", response_model=DepositRead)
def get_deposit(
    deposit_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    item = db.get(Deposit, deposit_id)
    if not item:
        raise HTTPException(status_code=404, detail="Deposit not found.")
    if is_institution_user(user) and item.institution_id != user.institution_id:
        raise HTTPException(status_code=403, detail="You may only view your own institution's deposits.")
    if not is_institution_user(user) and normalized_role(user) not in {"admin", "case_officer", "clearance_officer", "approval_authority", "auditor", "technical_admin"}:
        raise HTTPException(status_code=403, detail="You are not permitted to view deposits.")
    return item


@router.post("/{deposit_id}/transition", response_model=DepositRead)
def transition_deposit(
    deposit_id: str,
    payload: DepositTransitionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    # Institutions submit and clarify through dedicated workflows; they cannot
    # directly mutate regulatory lifecycle state. Auditors/admins are read-only.
    if not can_review_deposits(user):
        raise HTTPException(status_code=403, detail="You are not permitted to change deposit status.")
    item = db.get(Deposit, deposit_id)
    if not item:
        raise HTTPException(status_code=404, detail="Deposit not found.")
    old_status = item.status
    try:
        validate_transition(old_status, payload.target_status, DEPOSIT_TRANSITIONS)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    institution = db.get(Institution, item.institution_id)
    item.status = payload.target_status
    db.add(AuditEvent(
        institution_id=item.institution_id, entity_type="deposit", entity_id=item.id,
        actor_user_id=user.id, action="DEPOSIT_STATUS_CHANGED",
        before_state={"status": old_status.value}, after_state={"status": payload.target_status.value},
        reason=payload.reason, is_synthetic=bool(institution and institution.is_synthetic),
    ))
    db.commit()
    db.refresh(item)
    return item
