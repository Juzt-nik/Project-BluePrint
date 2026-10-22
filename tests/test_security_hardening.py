from app.models.entities import ClearanceRecord, Deposit, Document, ReleaseRequest, User
from app.models.enums import (
    ClearanceStatus,
    ClearanceUnit,
    DepositStatus,
    DocumentType,
    ReleaseMethod,
    ReleaseStatus,
)


def make_release(db_session, data, *, reference="REL-SEC-001", status=ReleaseStatus.AWAITING_CLEARANCES, requester=None):
    deposit = data["deposit_a"]
    deposit.status = DepositStatus.MATURED
    item = ReleaseRequest(
        deposit_id=deposit.id,
        request_reference=reference,
        release_method=ReleaseMethod.FDR_RPGF,
        status=status,
        requested_by_user_id=(requester or data["institution_user"]).id,
    )
    db_session.add(item)
    db_session.flush()
    for unit in (
        ClearanceUnit.PGRC,
        ClearanceUnit.VIGILANCE,
        ClearanceUnit.RELEVANT_CELL_OR_BUREAU,
    ):
        db_session.add(
            ClearanceRecord(
                release_request_id=item.id,
                unit=unit,
                status=ClearanceStatus.NOT_STARTED,
            )
        )
    db_session.commit()
    return item


def add_user(db_session, *, email, role, institution_id=None):
    user = User(
        email=email,
        display_name=email.split("@")[0],
        role=role,
        institution_id=institution_id,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_auditor_cannot_upload_financial_document(client, data, use_user, monkeypatch):
    from app.api.routes import documents as document_routes

    use_user(data["auditor"])
    monkeypatch.setattr(
        document_routes, "upload_private_object",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("storage must not be called")),
    )
    response = client.post(
        f"/api/v1/deposits/{data['deposit_a'].id}/documents",
        data={"document_type": "FDR_COPY"},
        files={"file": ("test.pdf", b"%PDF-1.7 test", "application/pdf")},
    )
    assert response.status_code == 403


def test_technical_admin_cannot_download_financial_document(client, data, db_session, use_user, monkeypatch):
    from app.api.routes import documents as document_routes

    doc = Document(
        deposit_id=data["deposit_a"].id,
        document_type=DocumentType.FDR_COPY,
        original_filename="demo.pdf",
        storage_key=f"institutions/{data['institution_a'].id}/demo.pdf",
        is_synthetic=True,
    )
    db_session.add(doc)
    technical_admin = add_user(db_session, email="tech@example.test", role="technical_admin")
    db_session.commit()
    use_user(technical_admin)
    monkeypatch.setattr(
        document_routes, "download_private_object",
        lambda key: (_ for _ in ()).throw(AssertionError("storage must not be called")),
    )
    response = client.get(f"/api/v1/documents/{doc.id}/download")
    assert response.status_code == 403


def test_clearance_cannot_be_decided_until_assigned(client, data, db_session, use_user):
    from app.models.enums import ClearanceUnit

    item = make_release(db_session, data, reference="REL-SEC-002")
    officer = add_user(db_session, email="clearance-unassigned@example.test", role="clearance_officer")
    use_user(officer)
    response = client.post(
        f"/api/v1/release-requests/{item.id}/clearances/{ClearanceUnit.PGRC.value}",
        json={"status": "CLEARED", "outcome_note": "Checked"},
    )
    assert response.status_code == 409


def test_only_assigned_clearance_officer_can_decide(client, data, db_session, use_user):
    item = make_release(db_session, data, reference="REL-SEC-003")
    record = db_session.query(ClearanceRecord).filter_by(
        release_request_id=item.id, unit=ClearanceUnit.PGRC
    ).one()
    assigned = add_user(db_session, email="assigned@example.test", role="clearance_officer")
    other = add_user(db_session, email="other-clearance@example.test", role="clearance_officer")
    record.assigned_to_user_id = assigned.id
    record.status = ClearanceStatus.PENDING
    db_session.commit()
    use_user(other)
    response = client.post(
        f"/api/v1/release-requests/{item.id}/clearances/PGRC",
        json={"status": "CLEARED", "outcome_note": "Checked"},
    )
    assert response.status_code == 403


def test_case_officer_can_assign_clearance_to_active_clearance_officer(client, data, db_session, use_user):
    item = make_release(db_session, data, reference="REL-SEC-004", status=ReleaseStatus.DOCUMENT_REVIEW)
    officer = add_user(db_session, email="assigned-valid@example.test", role="clearance_officer")
    use_user(data["case_officer"])
    response = client.post(
        f"/api/v1/release-requests/{item.id}/clearances/PGRC/assign",
        json={"assigned_to_user_id": officer.id},
    )
    assert response.status_code == 200
    assert any(
        clearance["unit"] == "PGRC"
        and clearance["status"] == "PENDING"
        for clearance in response.json()["clearances"]
    )
    db_session.refresh(item)
    record = db_session.query(ClearanceRecord).filter_by(
        release_request_id=item.id, unit=ClearanceUnit.PGRC
    ).one()
    assert record.assigned_to_user_id == officer.id


def test_not_applicable_does_not_satisfy_mandatory_clearance(client, data, db_session, use_user):
    item = make_release(db_session, data, reference="REL-SEC-005")
    for record in item.clearances:
        record.status = ClearanceStatus.CLEARED
    item.clearances[0].status = ClearanceStatus.NOT_APPLICABLE
    db_session.commit()
    use_user(data["case_officer"])
    response = client.post(
        f"/api/v1/release-requests/{item.id}/transition",
        json={"target_status": "READY_FOR_AUTHORITY"},
    )
    assert response.status_code == 409
    assert "missing_clearances" in response.json()["detail"]


def test_clearance_decision_maker_cannot_be_final_authority(client, data, db_session, use_user):
    authority = add_user(db_session, email="authority@example.test", role="approval_authority")
    item = make_release(
        db_session,
        data,
        reference="REL-SEC-006",
        status=ReleaseStatus.READY_FOR_AUTHORITY,
    )
    for record in item.clearances:
        record.status = ClearanceStatus.CLEARED
        record.decided_by_user_id = authority.id if record.unit == ClearanceUnit.PGRC else data["case_officer"].id
        record.outcome_note = "Reviewed"
    db_session.commit()
    use_user(authority)
    response = client.post(
        f"/api/v1/release-requests/{item.id}/transition",
        json={
            "target_status": "AUTHORITY_ACTION_RECORDED",
            "final_action_reference": "AUTH-001",
            "final_action_date": "2026-10-23",
            "final_action_note": "Approved for test",
        },
    )
    assert response.status_code == 403


def test_release_request_isolation_applies_to_single_item(client, data, db_session, use_user):
    other_deposit = data["deposit_b"]
    item = ReleaseRequest(
        deposit_id=other_deposit.id,
        request_reference="REL-SEC-007",
        release_method=ReleaseMethod.FDR_RPGF,
        status=ReleaseStatus.DRAFT,
        requested_by_user_id=None,
    )
    db_session.add(item)
    db_session.commit()
    use_user(data["institution_user"])
    response = client.get(f"/api/v1/release-requests/{item.id}")
    assert response.status_code == 403


def test_assigned_clearance_officer_can_record_decision_and_audit_actor(client, data, db_session, use_user):
    from app.models.entities import AuditEvent

    item = make_release(db_session, data, reference="REL-SEC-008")
    officer = add_user(db_session, email="valid-clearance@example.test", role="clearance_officer")
    record = db_session.query(ClearanceRecord).filter_by(
        release_request_id=item.id, unit=ClearanceUnit.PGRC
    ).one()
    record.assigned_to_user_id = officer.id
    record.status = ClearanceStatus.PENDING
    db_session.commit()
    use_user(officer)
    response = client.post(
        f"/api/v1/release-requests/{item.id}/clearances/PGRC",
        json={"status": "CLEARED", "outcome_note": "Verified against the submitted record"},
    )
    assert response.status_code == 200
    db_session.refresh(record)
    assert record.status == ClearanceStatus.CLEARED
    assert record.decided_by_user_id == officer.id
    event = db_session.query(AuditEvent).filter_by(
        action="RELEASE_CLEARANCE_DECIDED", entity_id=item.id
    ).one()
    assert event.actor_user_id == officer.id


def test_platform_admin_cannot_record_regulatory_clearance(client, data, db_session, use_user):
    item = make_release(db_session, data, reference="REL-SEC-009")
    admin = add_user(db_session, email="platform-admin@example.test", role="admin")
    record = db_session.query(ClearanceRecord).filter_by(
        release_request_id=item.id, unit=ClearanceUnit.PGRC
    ).one()
    record.assigned_to_user_id = admin.id
    record.status = ClearanceStatus.PENDING
    db_session.commit()
    use_user(admin)
    response = client.post(
        f"/api/v1/release-requests/{item.id}/clearances/PGRC",
        json={"status": "CLEARED", "outcome_note": "Admin bypass attempt"},
    )
    assert response.status_code == 403


def test_institution_cannot_request_its_own_clarification_status(client, data, db_session, use_user):
    item = make_release(
        db_session, data, reference="REL-SEC-010", status=ReleaseStatus.DOCUMENT_REVIEW
    )
    use_user(data["institution_user"])
    response = client.post(
        f"/api/v1/release-requests/{item.id}/transition",
        json={"target_status": "CLARIFICATION_REQUIRED", "reason": "try to alter review state"},
    )
    assert response.status_code == 403
