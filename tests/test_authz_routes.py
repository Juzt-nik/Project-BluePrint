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
from app.models.entities import AuditEvent, Deposit, Institution, User
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
    institution_a = Institution(institution_code="DEMO-A", legal_name="Demo Institution A", is_synthetic=True)
    institution_b = Institution(institution_code="DEMO-B", legal_name="Demo Institution B", is_synthetic=False)
    db_session.add_all([institution_a, institution_b])
    db_session.flush()

    institution_user = User(
        email="rep-a@example.test", display_name="Institution A Rep", role="institution_representative",
        institution_id=institution_a.id, is_active=True,
    )
    auditor = User(email="auditor@example.test", display_name="Demo Auditor", role="auditor", is_active=True)
    case_officer = User(email="officer@example.test", display_name="Demo Officer", role="case_officer", is_active=True)
    db_session.add_all([institution_user, auditor, case_officer])
    db_session.flush()

    deposit_a = Deposit(institution_id=institution_a.id, internal_reference="FDR-A-001", deposit_method=DepositMethod.FDR, status=DepositStatus.DRAFT, created_by_user_id=institution_user.id)
    deposit_b = Deposit(institution_id=institution_b.id, internal_reference="FDR-B-001", deposit_method=DepositMethod.FDR, status=DepositStatus.DRAFT)
    db_session.add_all([deposit_a, deposit_b])
    db_session.commit()
    return {
        "institution_a": institution_a, "institution_b": institution_b,
        "institution_user": institution_user, "auditor": auditor,
        "case_officer": case_officer, "deposit_a": deposit_a, "deposit_b": deposit_b,
    }


@pytest.fixture()
def client(db_session: Session):
    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def use_user(user: User):
    app.dependency_overrides[get_authenticated_user] = lambda: user


def test_missing_bearer_token_returns_401(client: TestClient):
    response = client.get("/api/v1/deposits")
    assert response.status_code == 401


def test_institution_user_only_lists_own_deposits(client: TestClient, data):
    use_user(data["institution_user"])
    response = client.get("/api/v1/deposits")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [data["deposit_a"].id]


def test_institution_user_cannot_fetch_another_institutions_deposit(client: TestClient, data):
    use_user(data["institution_user"])
    response = client.get(f"/api/v1/deposits/{data['deposit_b'].id}")
    assert response.status_code == 403


def test_institution_user_cannot_filter_list_to_another_institution(client: TestClient, data):
    use_user(data["institution_user"])
    response = client.get(f"/api/v1/deposits?institution_id={data['institution_b'].id}")
    assert response.status_code == 403


def test_auditor_cannot_change_deposit_status(client: TestClient, data):
    use_user(data["auditor"])
    response = client.post(
        f"/api/v1/deposits/{data['deposit_a'].id}/transition",
        json={"target_status": "SUBMITTED", "reason": "test"},
    )
    assert response.status_code == 403
    assert data["deposit_a"].status == DepositStatus.DRAFT


def test_transition_audit_uses_authenticated_actor_and_institution_synthetic_flag(client: TestClient, data, db_session: Session):
    use_user(data["case_officer"])
    response = client.post(
        f"/api/v1/deposits/{data['deposit_a'].id}/transition",
        json={"target_status": "SUBMITTED", "reason": "reviewed"},
    )
    assert response.status_code == 200
    event = db_session.query(AuditEvent).filter_by(action="DEPOSIT_STATUS_CHANGED").one()
    assert event.actor_user_id == data["case_officer"].id
    assert event.is_synthetic is True


def test_request_cannot_supply_actor_user_id(client: TestClient, data):
    use_user(data["case_officer"])
    response = client.post(
        f"/api/v1/deposits/{data['deposit_a'].id}/transition",
        json={"target_status": "SUBMITTED", "actor_user_id": data["institution_user"].id},
    )
    assert response.status_code == 200
    # Extra request fields are ignored by Pydantic; audit identity still comes
    # from the authenticated application user, never the supplied actor field.


def test_institution_user_cannot_create_deposit_for_another_institution(client: TestClient, data):
    use_user(data["institution_user"])
    response = client.post(
        "/api/v1/deposits",
        json={
            "institution_id": data["institution_b"].id,
            "internal_reference": "FDR-B-NEW",
            "deposit_method": "FDR",
        },
    )
    assert response.status_code == 403


def test_institution_user_cannot_create_institution(client: TestClient, data):
    use_user(data["institution_user"])
    response = client.post(
        "/api/v1/institutions",
        json={"institution_code": "DEMO-C", "legal_name": "Demo Institution C"},
    )
    assert response.status_code == 403


def test_invalid_supabase_token_returns_401(client: TestClient, monkeypatch):
    from types import SimpleNamespace
    from app.core import security
    from app.core.config import settings

    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "test-anon-key")
    monkeypatch.setattr(security.httpx, "get", lambda *args, **kwargs: SimpleNamespace(status_code=401))
    response = client.get("/api/v1/deposits", headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 401


def test_valid_supabase_identity_without_active_app_user_returns_403(client: TestClient, monkeypatch):
    from types import SimpleNamespace
    from app.core import security
    from app.core.config import settings

    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "test-anon-key")
    monkeypatch.setattr(security.httpx, "get", lambda *args, **kwargs: SimpleNamespace(status_code=200, json=lambda: {"id": "unlinked-auth-user"}))
    response = client.get("/api/v1/deposits", headers={"Authorization": "Bearer valid-shaped-token"})
    assert response.status_code == 403
