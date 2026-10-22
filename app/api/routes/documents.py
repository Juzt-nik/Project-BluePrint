from __future__ import annotations

import hashlib
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.security import get_authenticated_user, is_institution_user, normalized_role
from app.db.session import get_db
from app.models.entities import AuditEvent, Deposit, Document, Institution, User
from app.models.enums import DocumentType
from app.services.storage import download_private_object, upload_private_object

router = APIRouter(tags=["documents"])

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def _check_deposit_access(deposit: Deposit, user: User, *, upload: bool = False) -> Institution:
    role = normalized_role(user)
    if is_institution_user(user):
        if deposit.institution_id != user.institution_id:
            raise HTTPException(status_code=403, detail="You may only access documents for your own institution.")
        if upload and deposit.status.value not in {"DRAFT", "CLARIFICATION_REQUIRED"}:
            raise HTTPException(status_code=409, detail="Documents can only be uploaded while a deposit is editable.")
    elif role not in {"admin", "case_officer", "clearance_officer", "approval_authority", "auditor", "technical_admin"}:
        raise HTTPException(status_code=403, detail="You are not permitted to access deposit documents.")
    institution = deposit.institution
    if institution is None:
        raise HTTPException(status_code=404, detail="Institution not found.")
    return institution


@router.post(
    "/deposits/{deposit_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=dict,
)
async def upload_document(
    deposit_id: str,
    document_type: DocumentType = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    deposit = db.get(Deposit, deposit_id)
    if deposit is None:
        raise HTTPException(status_code=404, detail="Deposit not found.")
    institution = _check_deposit_access(deposit, user, upload=True)

    content_type = (file.content_type or "").lower().split(";")[0].strip()
    extension = ALLOWED_CONTENT_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(status_code=415, detail="Only PDF, JPEG, and PNG documents are accepted.")
    filename = (file.filename or "document").replace("\\", "/").split("/")[-1]
    filename = re.sub(r"[^A-Za-z0-9._ -]", "_", filename).strip(" .")[:200]
    if not filename or not filename.lower().endswith(extension):
        raise HTTPException(status_code=415, detail="File extension does not match the accepted content type.")

    content = await file.read(MAX_DOCUMENT_BYTES + 1)
    await file.close()
    if not content:
        raise HTTPException(status_code=400, detail="Empty documents are not accepted.")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds the 10 MiB size limit.")
    # Basic signature checks prevent trusting the client-supplied MIME type alone.
    signatures = {
        "application/pdf": content.startswith(b"%PDF-"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
    }
    if not signatures[content_type]:
        raise HTTPException(status_code=415, detail="File contents do not match the declared document type.")

    document_id = str(uuid4())
    key = f"institutions/{institution.id}/deposits/{deposit.id}/{document_id}{extension}"
    upload_private_object(key, content, content_type)

    doc = Document(
        id=document_id,
        deposit_id=deposit.id,
        document_type=document_type,
        original_filename=filename,
        storage_key=key,
        sha256_checksum=hashlib.sha256(content).hexdigest(),
        version_number=1,
        is_synthetic=bool(institution.is_synthetic),
        watermark_label="SYNTHETIC DEMO — NOT A VALID FINANCIAL INSTRUMENT" if institution.is_synthetic else None,
        uploaded_by_user_id=user.id,
    )
    try:
        db.add(doc)
        db.add(AuditEvent(
            institution_id=institution.id,
            entity_type="document",
            entity_id=document_id,
            actor_user_id=user.id,
            action="DOCUMENT_UPLOADED",
            after_state={
                "deposit_id": deposit.id,
                "document_type": document_type.value,
                "sha256_checksum": doc.sha256_checksum,
                "is_synthetic": doc.is_synthetic,
            },
            is_synthetic=bool(institution.is_synthetic),
        ))
        db.commit()
        db.refresh(doc)
    except Exception:
        db.rollback()
        # The object remains private if metadata persistence fails. An operator
        # can reconcile orphan objects; no public URL is created.
        raise HTTPException(status_code=500, detail="Document metadata could not be saved; contact an administrator.")
    return {
        "id": doc.id,
        "deposit_id": doc.deposit_id,
        "document_type": doc.document_type.value,
        "original_filename": doc.original_filename,
        "sha256_checksum": doc.sha256_checksum,
        "version_number": doc.version_number,
        "is_synthetic": doc.is_synthetic,
        "uploaded_at": doc.uploaded_at.isoformat(),
    }


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    deposit = db.get(Deposit, doc.deposit_id)
    if deposit is None:
        raise HTTPException(status_code=404, detail="Deposit not found.")
    _check_deposit_access(deposit, user)
    content, stored_content_type = download_private_object(doc.storage_key)
    # Force download, avoid interpreting uploaded documents as active content.
    safe_name = re.sub(r'[^A-Za-z0-9._ -]', '_', doc.original_filename).strip(" .") or "document"
    return Response(
        content=content,
        media_type=stored_content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
