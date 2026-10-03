from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.models import DetectionHistory, EventRecord, ExceptionEvidence
from app.models.domain import AuditLog, Case, Evidence, ExceptionRecord


SUCCESS_PAYMENT_STATES = {"SETTLED", "SUCCESS", "SUCCEEDED", "COMPLETED"}
CONFIRMED_STATES = {"CONFIRMED", "SUCCESS", "SUCCEEDED"}
INCOMPLETE_WORKFLOW_STATES = {
    "PENDING",
    "PROCESSING",
    "RECONCILING",
    "AWAITING_CONFIRMATION",
    "WAITING_FOR_RETRY",
    "WAITING_FOR_LATE_EVENT",
    "INVESTIGATING",
    "DOCUMENT_REQUIRED",
    "REVIEW_REQUIRED",
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ExceptionDetectionService:
    def __init__(
        self,
        session: Session,
        confirmation_window: timedelta = timedelta(minutes=5),
        workflow_deadline: timedelta = timedelta(minutes=30),
        api_timeout_ms: int = 30_000,
        clock: Callable[[], datetime] | None = None,
    ):
        self.session = session
        self.confirmation_window = confirmation_window
        self.workflow_deadline = workflow_deadline
        self.api_timeout_ms = api_timeout_ms
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run(self, *, entity_reference: str | None = None, commit: bool = True) -> dict[str, Any]:
        now = _utc(self.clock())
        query = select(EventRecord).order_by(EventRecord.occurred_at, EventRecord.id).with_for_update()
        if entity_reference is not None:
            query = query.where(EventRecord.entity_reference == entity_reference)
        events = self.session.execute(query).scalars().all()
        grouped: dict[str, list[EventRecord]] = {}
        for event in events:
            grouped.setdefault(event.entity_reference, []).append(event)

        findings: list[dict[str, Any]] = []
        for entity_reference, group in grouped.items():
            payment = self._first(group, "payment.recorded")
            confirmations = [event for event in group if event.source_system == "confirmations"]
            if payment is not None:
                findings.extend(self._payment_findings(entity_reference, payment, group, confirmations, now))
            findings.extend(self._api_findings(group))
            findings.extend(self._workflow_findings(group, now))

        created = 0
        updated = 0
        for finding in findings:
            changed = self._persist_finding(finding, now)
            if changed == "created":
                created += 1
            elif changed == "updated":
                updated += 1

        for entity_reference, group in grouped.items():
            payment = self._first(group, "payment.recorded")
            if payment is None:
                continue
            detection_key = f"payment_confirmation_missing:{entity_reference}"
            exception = self.session.execute(
                select(ExceptionRecord).where(ExceptionRecord.detection_key == detection_key)
            ).scalar_one_or_none()
            if exception is None or exception.detected_at is None:
                continue
            late_confirmations = [
                event
                for event in group
                if event.source_system == "confirmations"
                and str(event.payload.get("confirmation_status", "")).upper() in CONFIRMED_STATES
                and _utc(event.ingested_at) > _utc(exception.detected_at)
            ]
            for confirmation in late_confirmations:
                changed = self._persist_finding(
                    self._finding(
                        detection_key,
                        "PAYMENT_CONFIRMATION_MISSING",
                        entity_reference,
                        exception.description,
                        [payment, confirmation],
                        confirmation.occurred_at,
                        exception.severity,
                    ),
                    now,
                )
                if changed == "updated":
                    updated += 1

        for event in events:
            event.processing_status = "PROCESSED"
            event.processing_attempts += 1
            event.last_error = None
        self.session.commit() if commit else self.session.flush()
        return {
            "events_processed": len(events),
            "detections_created": created,
            "detections_updated": updated,
            "detected_at": now.isoformat(),
        }

    def _payment_findings(
        self,
        entity_reference: str,
        payment: EventRecord,
        group: list[EventRecord],
        confirmations: list[EventRecord],
        now: datetime,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        payment_status = str(payment.payload.get("payment_status", "")).upper()
        in_window = now < _utc(payment.occurred_at) + self.confirmation_window
        successful_confirmation = any(
            str(event.payload.get("confirmation_status", "")).upper() in CONFIRMED_STATES
            and _utc(event.occurred_at) <= now
            for event in confirmations
        )

        if payment_status in SUCCESS_PAYMENT_STATES | {"PENDING"} and not successful_confirmation and not in_window:
            findings.append(
                self._finding(
                    f"payment_confirmation_missing:{entity_reference}",
                    "PAYMENT_CONFIRMATION_MISSING",
                    entity_reference,
                    "Required payment confirmation was not observed within the processing window.",
                    [payment],
                    payment.occurred_at,
                    "HIGH",
                )
            )

        ledger_events = [event for event in group if event.source_system == "ledger"]
        latest_ledgers: dict[str, EventRecord] = {}
        for event in ledger_events:
            previous = latest_ledgers.get(event.source_record_reference)
            if previous is None or (_utc(event.occurred_at), event.ingested_at) > (
                _utc(previous.occurred_at), previous.ingested_at
            ):
                latest_ledgers[event.source_record_reference] = event
        for ledger in latest_ledgers.values():
            amount_mismatch = str(payment.payload.get("amount")) != str(ledger.payload.get("amount"))
            currency_mismatch = str(payment.payload.get("currency")) != str(ledger.payload.get("currency"))
            if amount_mismatch or currency_mismatch:
                findings.append(
                    self._finding(
                        f"reconciliation_mismatch:{entity_reference}",
                        "RECONCILIATION_MISMATCH",
                        entity_reference,
                        "Payment and ledger amount or currency values disagree.",
                        [payment, ledger],
                        max(_utc(payment.occurred_at), _utc(ledger.occurred_at)),
                        "HIGH",
                    )
                )
                break

        for confirmation in confirmations:
            confirmation_status = str(confirmation.payload.get("confirmation_status", "")).upper()
            conflicting = confirmation_status == "CONFLICTING" or (
                confirmation_status in CONFIRMED_STATES and payment_status not in SUCCESS_PAYMENT_STATES
            )
            if conflicting:
                findings.append(
                    self._finding(
                        f"system_state_conflict:{entity_reference}",
                        "CONFLICTING_SYSTEM_RECORDS",
                        entity_reference,
                        "Payment and confirmation systems report incompatible states.",
                        [payment, confirmation],
                        max(_utc(payment.occurred_at), _utc(confirmation.occurred_at)),
                        "HIGH",
                    )
                )
                break

        for confirmation in confirmations:
            if confirmation.payload.get("is_duplicate") or str(confirmation.payload.get("confirmation_status", "")).upper() == "REPLAYED":
                findings.append(
                    self._finding(
                        f"duplicate_business_event:{entity_reference}:{confirmation.event_type}",
                        "DUPLICATE_EVENT",
                        entity_reference,
                        "The source system marked a repeated logical confirmation event.",
                        [confirmation],
                        confirmation.occurred_at,
                        "MEDIUM",
                    )
                )
                break
        return findings

    def _api_findings(self, group: list[EventRecord]) -> list[dict[str, Any]]:
        findings = []
        for event in group:
            if event.source_system != "api_gateway":
                continue
            status_code = int(event.payload.get("status_code", 0))
            latency = int(event.payload.get("latency_ms", 0))
            if status_code >= 500 or latency >= self.api_timeout_ms:
                findings.append(
                    self._finding(
                        f"api_processing_failure:{event.source_record_reference}",
                        "API_PROCESSING_FAILURE",
                        event.entity_reference,
                        "A synthetic banking API request failed or exceeded the timeout threshold.",
                        [event],
                        event.occurred_at,
                        "HIGH",
                    )
                )
        return findings

    def _workflow_findings(self, group: list[EventRecord], now: datetime) -> list[dict[str, Any]]:
        findings = []
        latest_by_workflow: dict[str, EventRecord] = {}
        for event in group:
            if event.source_system != "workflow":
                continue
            previous = latest_by_workflow.get(event.source_record_reference)
            if previous is None or (_utc(event.occurred_at), event.ingested_at) > (
                _utc(previous.occurred_at), previous.ingested_at
            ):
                latest_by_workflow[event.source_record_reference] = event

        for event in latest_by_workflow.values():
            status = str(event.payload.get("workflow_status", "")).upper()
            if (
                event.source_system == "workflow"
                and status in INCOMPLETE_WORKFLOW_STATES
                and now >= _utc(event.occurred_at) + self.workflow_deadline
            ):
                findings.append(
                    self._finding(
                        f"workflow_incomplete:{event.source_record_reference}",
                        "WORKFLOW_EXCEPTION",
                        event.entity_reference,
                        "A workflow remained incomplete beyond its configured deadline.",
                        [event],
                        event.occurred_at,
                        "MEDIUM",
                    )
                )
        return findings

    @staticmethod
    def _first(events: list[EventRecord], event_type: str) -> EventRecord | None:
        matches = [event for event in events if event.event_type == event_type]
        return max(matches, key=lambda event: (_utc(event.occurred_at), event.ingested_at)) if matches else None

    @staticmethod
    def _finding(
        detection_key: str,
        exception_type: str,
        entity_reference: str,
        description: str,
        evidence: list[EventRecord],
        event_occurred_at: datetime,
        severity: str,
    ) -> dict[str, Any]:
        return {
            "detection_key": detection_key,
            "exception_type": exception_type,
            "entity_reference": entity_reference,
            "description": description,
            "evidence": evidence,
            "event_occurred_at": _utc(event_occurred_at),
            "severity": severity,
        }

    def _persist_finding(self, finding: dict[str, Any], detected_at: datetime) -> str:
        exception = self.session.execute(
            select(ExceptionRecord).where(ExceptionRecord.detection_key == finding["detection_key"])
        ).scalar_one_or_none()
        created = exception is None
        if created:
            digest = hashlib.sha256(finding["detection_key"].encode()).hexdigest()[:24]
            case_id = f"case-{digest}"
            case = Case(
                id=case_id,
                case_number=f"CASE-{digest.upper()}",
                external_ref=finding["entity_reference"],
                summary=finding["description"],
                priority=finding["severity"],
            )
            exception = ExceptionRecord(
                id=f"exception-{digest}",
                case_id=case_id,
                exception_type=finding["exception_type"],
                description=finding["description"],
                severity=finding["severity"],
                source_reference=finding["entity_reference"],
                detection_key=finding["detection_key"],
                detected_at=detected_at,
                condition_status="OPEN",
            )
            self.session.add_all([case, exception])
            self.session.flush()

        new_evidence = 0
        for event in finding["evidence"]:
            exists = self.session.execute(
                select(ExceptionEvidence.id).where(
                    ExceptionEvidence.exception_id == exception.id,
                    ExceptionEvidence.event_record_id == event.id,
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue
            self.session.add(
                ExceptionEvidence(
                    id=str(uuid4()), exception_id=exception.id, event_record_id=event.id, linked_at=detected_at
                )
            )
            self.session.add(
                Evidence(
                    id=str(uuid4()),
                    case_id=exception.case_id,
                    source_system=event.source_system,
                    source_record_id=event.source_record_reference,
                    relevant_event_timestamp=event.occurred_at,
                    retrieval_timestamp=detected_at,
                    payload=event.payload,
                    integrity_metadata={"event_record_id": event.id, "event_id": event.event_id},
                )
            )
            new_evidence += 1

        if created:
            self.session.add(
                AuditLog(
                    id=str(uuid4()),
                    case_id=exception.case_id,
                    entity_type="exception",
                    entity_id=exception.id,
                    event_type="exception_detected",
                    summary=f"Detected {exception.exception_type} from synthetic source events.",
                    details={"detection_key": exception.detection_key, "evidence_count": new_evidence},
                )
            )
            self.session.add(
                DetectionHistory(
                    id=str(uuid4()),
                    exception_id=exception.id,
                    event_type="DETECTED",
                    summary=exception.description,
                    detected_at=detected_at,
                    event_occurred_at=finding["event_occurred_at"],
                    details={"evidence_count": new_evidence},
                )
            )
            return "created"

        if new_evidence:
            if exception.exception_type == "PAYMENT_CONFIRMATION_MISSING" and any(
                event.source_system == "confirmations" for event in finding["evidence"]
            ):
                exception.condition_status = "LATE_EVIDENCE_RECEIVED"
            self.session.add(
                DetectionHistory(
                    id=str(uuid4()),
                    exception_id=exception.id,
                    event_type="EVIDENCE_ADDED",
                    summary="Additional source evidence was attached to the existing exception.",
                    detected_at=detected_at,
                    event_occurred_at=finding["event_occurred_at"],
                    details={"evidence_count": new_evidence, "condition_status": exception.condition_status},
                )
            )
            self.session.add(
                AuditLog(
                    id=str(uuid4()),
                    case_id=exception.case_id,
                    entity_type="exception",
                    entity_id=exception.id,
                    event_type="exception_evidence_updated",
                    summary="Additional source evidence was attached to the existing exception.",
                    details={"evidence_count": new_evidence, "condition_status": exception.condition_status},
                )
            )
            return "updated"
        return "unchanged"
