from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_authenticated_user, normalized_role, require_roles
from app.db.session import get_db
from app.models.entities import AuditEvent, Deposit, Institution, User
from app.models.enums import DepositStatus
from app.schemas.deposit import DepositCreate, DepositRead, DepositTransitionRequest
from app.workflow.state_machine import DEPOSIT_TRANSITIONS, InvalidTransition, validate_transition

router = APIRouter(prefix="/deposits", tags=["deposits"])
STAFF_ROLES = {"admin", "scrutiny_officer", "clearance_officer", "competent_authority", "auditor"}


def _visible_deposit_query(db: Session, user: User):
    query = db.query(Deposit)
    if normalized_role(user) == "institution_rep":
        if not user.institution_id:
            return query.filter(Deposit.id == "__no_access__")
        query = query.filter(Deposit.institution_id == user.institution_id)
    elif normalized_role(user) not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="You are not authorized to access deposits.")
    return query


@router.post("", response_model=DepositRead, status_code=status.HTTP_201_CREATED)
def create_deposit(
    payload: DepositCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    role = normalized_role(user)
    if role == "institution_rep":
        if not user.institution_id or payload.institution_id != user.institution_id:
            raise HTTPException(status_code=403, detail="You can only register deposits for your institution.")
    elif role not in {"admin", "scrutiny_officer"}:
        raise HTTPException(status_code=403, detail="You are not authorized to create deposits.")

    institution = db.get(Institution, payload.institution_id)
    if not institution or not institution.is_active:
        raise HTTPException(status_code=404, detail="Active institution not found.")
    duplicate = db.query(Deposit).filter_by(
        institution_id=payload.institution_id,
        internal_reference=payload.internal_reference,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Internal reference already exists for this institution.")
    item = Deposit(**payload.model_dump(), status=DepositStatus.DRAFT, created_by_user_id=user.id)
    db.add(item)
    db.flush()
    db.add(AuditEvent(
        institution_id=item.institution_id,
        actor_user_id=user.id,
        entity_type="deposit",
        entity_id=item.id,
        action="DEPOSIT_CREATED",
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
    query = _visible_deposit_query(db, user)
    if institution_id:
        if normalized_role(user) == "institution_rep" and institution_id != user.institution_id:
            raise HTTPException(status_code=403, detail="You can only view your institution's deposits.")
        query = query.filter(Deposit.institution_id == institution_id)
    return query.order_by(Deposit.created_at.desc()).all()


@router.get("/{deposit_id}", response_model=DepositRead)
def get_deposit(
    deposit_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    item = _visible_deposit_query(db, user).filter(Deposit.id == deposit_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Deposit not found.")
    return item


@router.post("/{deposit_id}/transition", response_model=DepositRead)
def transition_deposit(
    deposit_id: str,
    payload: DepositTransitionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    item = _visible_deposit_query(db, user).filter(Deposit.id == deposit_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Deposit not found.")

    role = normalized_role(user)
    if role == "institution_rep":
        # Institution users may submit their own draft or respond to clarification only.
        allowed = (item.status == DepositStatus.DRAFT and payload.target_status == DepositStatus.SUBMITTED) or (
            item.status == DepositStatus.CLARIFICATION_REQUIRED and payload.target_status == DepositStatus.SUBMITTED
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Institution representatives cannot make this status change.")
    elif role not in {"admin", "scrutiny_officer", "competent_authority"}:
        raise HTTPException(status_code=403, detail="You are not authorized to change deposit status.")

    old_status = item.status
    try:
        validate_transition(old_status, payload.target_status, DEPOSIT_TRANSITIONS)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    item.status = payload.target_status
    db.add(AuditEvent(
        institution_id=item.institution_id,
        entity_type="deposit",
        entity_id=item.id,
        actor_user_id=user.id,
        action="DEPOSIT_STATUS_CHANGED",
        before_state={"status": old_status.value},
        after_state={"status": payload.target_status.value},
        reason=payload.reason,
        is_synthetic=True,
    ))
    db.commit()
    db.refresh(item)
    return item
