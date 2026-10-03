from app.audit import AuditEvent, AuditEventType


def test_create_audit_event():
    event = AuditEvent(
        entity_type="case",
        entity_id="case-1",
        event_type=AuditEventType.CASE_CREATED,
        summary="Created case",
        details={"source": "ingestion"},
    )
    assert event.entity_type == "case"
    assert event.event_type == AuditEventType.CASE_CREATED
    assert event.summary == "Created case"
