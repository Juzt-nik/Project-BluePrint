from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_authenticated_user, is_institution_user, normalized_role, require_roles
from app.db.session import get_db
from app.models.entities import Institution, User
from app.schemas.institution import InstitutionCreate, InstitutionRead

router = APIRouter(prefix="/institutions", tags=["institutions"])


@router.post("", response_model=InstitutionRead, status_code=status.HTTP_201_CREATED)
def create_institution(
    payload: InstitutionCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin")),
):
    existing = db.query(Institution).filter_by(institution_code=payload.institution_code).first()
    if existing:
        raise HTTPException(status_code=409, detail="Institution code already exists.")
    item = Institution(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("", response_model=list[InstitutionRead])
def list_institutions(
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    query = db.query(Institution)
    if is_institution_user(user):
        if not user.institution_id:
            return []
        query = query.filter(Institution.id == user.institution_id)
    elif normalized_role(user) not in {"admin", "case_officer", "clearance_officer", "approval_authority", "auditor", "technical_admin"}:
        raise HTTPException(status_code=403, detail="You are not permitted to view institutions.")
    return query.order_by(Institution.legal_name).all()
