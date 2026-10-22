"""Shared pytest fixtures for API and release workflow tests."""
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import get_authenticated_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import Deposit, Institution, User
from app.models.enums import DepositMethod, DepositStatus


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def data(db_session: Session):
    institution_a = Institution(
        institution_code="DEMO-A", legal_name="Demo Institution A", is_synthetic=True
    )
    institution_b = Institution(
        institution_code="DEMO-B", legal_name="Demo Institution B", is_synthetic=False
    )
    db_session.add_all([institution_a, institution_b])
    db_session.flush()

    institution_user = User(
        email="rep-a@example.test",
        display_name="Institution A Rep",
        role="institution_representative",
        institution_id=institution_a.id,
        is_active=True,
    )
    auditor = User(
        email="auditor@example.test", display_name="Demo Auditor",
        role="auditor", is_active=True,
    )
    case_officer = User(
        email="officer@example.test", display_name="Demo Officer",
        role="case_officer", is_active=True,
    )
    db_session.add_all([institution_user, auditor, case_officer])
    db_session.flush()

    deposit_a = Deposit(
        institution_id=institution_a.id,
        internal_reference="FDR-A-001",
        deposit_method=DepositMethod.FDR,
        status=DepositStatus.DRAFT,
        created_by_user_id=institution_user.id,
    )
    deposit_b = Deposit(
        institution_id=institution_b.id,
        internal_reference="FDR-B-001",
        deposit_method=DepositMethod.FDR,
        status=DepositStatus.DRAFT,
    )
    db_session.add_all([deposit_a, deposit_b])
    db_session.commit()
    return {
        "institution_a": institution_a,
        "institution_b": institution_b,
        "institution_user": institution_user,
        "auditor": auditor,
        "case_officer": case_officer,
        "deposit_a": deposit_a,
        "deposit_b": deposit_b,
    }


@pytest.fixture()
def client(db_session: Session):
    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def use_user():
    def _use_user(user: User):
        app.dependency_overrides[get_authenticated_user] = lambda: user
    return _use_user
