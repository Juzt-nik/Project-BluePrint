from app.models.entities import ClearanceRecord, Deposit, ReleaseRequest
from app.models.enums import ClearanceStatus, ClearanceUnit, DepositStatus, ReleaseMethod, ReleaseStatus


def test_maturity_does_not_auto_complete_release(client, data, db_session):
    from app.core.security import get_authenticated_user
    from app.main import app
    # Create a release request through ORM to isolate the gate under test.
    deposit = data["deposit_a"]
    deposit.status = DepositStatus.MATURED
    item = ReleaseRequest(
        deposit_id=deposit.id, request_reference="REL-GATE-001",
        release_method=ReleaseMethod.FDR_RPGF, status=ReleaseStatus.AWAITING_CLEARANCES,
        requested_by_user_id=data["institution_user"].id,
    )
    db_session.add(item)
    db_session.flush()
    for unit in (ClearanceUnit.PGRC, ClearanceUnit.VIGILANCE, ClearanceUnit.RELEVANT_CELL_OR_BUREAU):
        db_session.add(ClearanceRecord(release_request_id=item.id, unit=unit, status=ClearanceStatus.NOT_STARTED))
    db_session.commit()
    app.dependency_overrides[get_authenticated_user] = lambda: data["case_officer"]
    response = client.post(f"/api/v1/release-requests/{item.id}/transition", json={"target_status": "READY_FOR_AUTHORITY"})
    assert response.status_code == 409
    db_session.refresh(item)
    assert item.status == ReleaseStatus.AWAITING_CLEARANCES


def test_clearance_decision_endpoint_rejects_non_clearance_role(client, data, db_session):
    from app.core.security import get_authenticated_user
    from app.main import app
    deposit = data["deposit_a"]
    item = ReleaseRequest(
        deposit_id=deposit.id, request_reference="REL-GATE-002",
        release_method=ReleaseMethod.FDR_RPGF, status=ReleaseStatus.AWAITING_CLEARANCES,
        requested_by_user_id=data["institution_user"].id,
    )
    db_session.add(item)
    db_session.flush()
    db_session.add(ClearanceRecord(release_request_id=item.id, unit=ClearanceUnit.PGRC, status=ClearanceStatus.PENDING))
    db_session.commit()
    app.dependency_overrides[get_authenticated_user] = lambda: data["case_officer"]
    response = client.post(
        f"/api/v1/release-requests/{item.id}/clearances/PGRC",
        json={"status": "CLEARED", "outcome_note": "not authorized"},
    )
    assert response.status_code == 403
