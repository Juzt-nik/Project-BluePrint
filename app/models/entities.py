from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    DepositStatus, DepositMethod, CaseType, CaseStatus, FindingKind,
    FindingSeverity, FindingStatus, ClearanceUnit, ClearanceStatus,
    ReleaseMethod, ReleaseStatus, DocumentType, VerificationSourceType
)


def enum_type(enum_cls, name: str):
    return SAEnum(enum_cls, name=name, values_callable=lambda cls: [e.value for e in cls])


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow,
                                                  onupdate=datetime.utcnow, nullable=False)


class Institution(TimestampMixin, Base):
    __tablename__ = "institutions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    institution_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_type: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    users: Mapped[list["User"]] = relationship(back_populates="institution")
    deposits: Mapped[list["Deposit"]] = relationship(back_populates="institution")


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id", ondelete="RESTRICT"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo_account: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    institution: Mapped[Institution | None] = relationship(back_populates="users")


class Deposit(TimestampMixin, Base):
    __tablename__ = "deposits"
    __table_args__ = (
        UniqueConstraint("institution_id", "internal_reference", name="uq_deposit_institution_reference"),
        Index("ix_deposits_status_maturity", "status", "security_term_end_date"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False, index=True)
    internal_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    deposit_method: Mapped[DepositMethod] = mapped_column(enum_type(DepositMethod, "deposit_method"), nullable=False)
    status: Mapped[DepositStatus] = mapped_column(enum_type(DepositStatus, "deposit_status"), default=DepositStatus.DRAFT, nullable=False, index=True)
    security_term_start_date: Mapped[date | None] = mapped_column(Date)
    security_term_end_date: Mapped[date | None] = mapped_column(Date)
    applicable_rule_reference: Mapped[str | None] = mapped_column(String(150))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    institution: Mapped[Institution] = relationship(back_populates="deposits")
    instruments: Mapped[list["Instrument"]] = relationship(back_populates="deposit", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="deposit")
    cases: Mapped[list["Case"]] = relationship(back_populates="deposit")
    release_requests: Mapped[list["ReleaseRequest"]] = relationship(back_populates="deposit")


class Instrument(TimestampMixin, Base):
    __tablename__ = "instruments"
    __table_args__ = (
        Index("ix_instrument_reference_bank", "issuing_bank_name", "instrument_reference"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deposit_id: Mapped[str] = mapped_column(ForeignKey("deposits.id", ondelete="RESTRICT"), nullable=False, index=True)
    instrument_type: Mapped[str] = mapped_column(String(50), nullable=False, default="FDR")
    instrument_reference: Mapped[str | None] = mapped_column(String(120))
    issuing_bank_name: Mapped[str | None] = mapped_column(String(200))
    branch_or_ifsc: Mapped[str | None] = mapped_column(String(100))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date)
    maturity_date: Mapped[date | None] = mapped_column(Date)
    source_type: Mapped[VerificationSourceType] = mapped_column(
        enum_type(VerificationSourceType, "verification_source_type"),
        default=VerificationSourceType.SUBMITTED_BY_INSTITUTION, nullable=False
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    replaced_instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id", ondelete="SET NULL"))
    deposit: Mapped[Deposit] = relationship(back_populates="instruments")
    documents: Mapped[list["Document"]] = relationship(back_populates="instrument")


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deposit_id: Mapped[str] = mapped_column(ForeignKey("deposits.id", ondelete="RESTRICT"), nullable=False, index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"), index=True)
    document_type: Mapped[DocumentType] = mapped_column(enum_type(DocumentType, "document_type"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    sha256_checksum: Mapped[str | None] = mapped_column(String(64))
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    watermark_label: Mapped[str | None] = mapped_column(String(120))
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    deposit: Mapped[Deposit] = relationship(back_populates="documents")
    instrument: Mapped[Instrument | None] = relationship(back_populates="documents")


class Case(TimestampMixin, Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deposit_id: Mapped[str] = mapped_column(ForeignKey("deposits.id", ondelete="RESTRICT"), nullable=False, index=True)
    case_type: Mapped[CaseType] = mapped_column(enum_type(CaseType, "case_type"), nullable=False)
    status: Mapped[CaseStatus] = mapped_column(enum_type(CaseStatus, "case_status"), default=CaseStatus.OPEN, nullable=False, index=True)
    assigned_to_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)
    deposit: Mapped[Deposit] = relationship(back_populates="cases")
    events: Mapped[list["CaseEvent"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class CaseEvent(Base):
    __tablename__ = "case_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(60))
    to_status: Mapped[str] = mapped_column(String(60), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    case: Mapped[Case] = relationship(back_populates="events")


class VerificationFinding(TimestampMixin, Base):
    __tablename__ = "verification_findings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deposit_id: Mapped[str] = mapped_column(ForeignKey("deposits.id", ondelete="RESTRICT"), nullable=False, index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[FindingKind] = mapped_column(enum_type(FindingKind, "finding_kind"), nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(enum_type(FindingSeverity, "finding_severity"), default=FindingSeverity.MEDIUM, nullable=False)
    status: Mapped[FindingStatus] = mapped_column(enum_type(FindingStatus, "finding_status"), default=FindingStatus.OPEN, nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    source_type: Mapped[VerificationSourceType] = mapped_column(enum_type(VerificationSourceType, "finding_source_type"), nullable=False)
    resolved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClearanceRecord(TimestampMixin, Base):
    __tablename__ = "clearance_records"
    __table_args__ = (UniqueConstraint("release_request_id", "unit", name="uq_release_clearance_unit"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    release_request_id: Mapped[str] = mapped_column(ForeignKey("release_requests.id", ondelete="RESTRICT"), nullable=False, index=True)
    unit: Mapped[ClearanceUnit] = mapped_column(enum_type(ClearanceUnit, "clearance_unit"), nullable=False)
    status: Mapped[ClearanceStatus] = mapped_column(enum_type(ClearanceStatus, "clearance_status"), default=ClearanceStatus.NOT_STARTED, nullable=False)
    assigned_to_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    outcome_note: Mapped[str | None] = mapped_column(Text)
    evidence_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"))
    decided_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReleaseRequest(TimestampMixin, Base):
    __tablename__ = "release_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deposit_id: Mapped[str] = mapped_column(ForeignKey("deposits.id", ondelete="RESTRICT"), nullable=False, index=True)
    request_reference: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    release_method: Mapped[ReleaseMethod] = mapped_column(enum_type(ReleaseMethod, "release_method"), nullable=False)
    status: Mapped[ReleaseStatus] = mapped_column(enum_type(ReleaseStatus, "release_status"), default=ReleaseStatus.DRAFT, nullable=False, index=True)
    requested_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    final_authority_role: Mapped[str | None] = mapped_column(String(100))
    final_action_reference: Mapped[str | None] = mapped_column(String(150))
    final_action_date: Mapped[date | None] = mapped_column(Date)
    final_action_note: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deposit: Mapped[Deposit] = relationship(back_populates="release_requests")
    clearances: Mapped[list[ClearanceRecord]] = relationship(cascade="all, delete-orphan")


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    recipient_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    deposit_id: Mapped[str | None] = mapped_column(ForeignKey("deposits.id", ondelete="SET NULL"), index=True)
    release_request_id: Mapped[str | None] = mapped_column(ForeignKey("release_requests.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_status: Mapped[str] = mapped_column(String(40), default="PENDING", nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id", ondelete="SET NULL"), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    before_state: Mapped[dict | None] = mapped_column(JSON)
    after_state: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
