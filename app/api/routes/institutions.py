from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Institution
from app.schemas.institution import InstitutionCreate, InstitutionRead

router = APIRouter(prefix="/institutions", tags=["institutions"])


@router.post("", response_model=InstitutionRead, status_code=status.HTTP_201_CREATED)
def create_institution(payload: InstitutionCreate, db: Session = Depends(get_db)):
    existing = db.query(Institution).filter_by(institution_code=payload.institution_code).first()
    if existing:
        raise HTTPException(status_code=409, detail="Institution code already exists.")
    item = Institution(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("", response_model=list[InstitutionRead])
def list_institutions(db: Session = Depends(get_db)):
    return db.query(Institution).order_by(Institution.legal_name).all()
