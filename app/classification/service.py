from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification.models import AssessmentHistory
from app.classification.priority import PriorityEngine, recommend_routing
from app.classification.rules import Classifier, RuleBasedClassifier
from app.ingestion.models import EventRecord, ExceptionEvidence
from app.models.domain import AuditLog, Case, ExceptionRecord


ASSESSMENT_VERSION = "case-assessment-1.0"
REQUIRED_SOURCES = {
    "PAYMENT_CONFIRMATION_MISMATCH": {"payments"},
    "RECONCILIATION_MISMATCH": {"payments", "ledger"},
    "API_PROCESSING_FAILURE": {"api_gateway"},
    "WORKFLOW_EXCEPTION": {"workflow"},
    "CONFLICTING_RECORDS": {"payments", "confirmations"},
    "DUPLICATE_EVENT": {"confirmations"},
    "DOCUMENT_STATUS_EXCEPTION": {"documents"},
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ClassificationService:
    def __init__(
        self,
        session: Session,
        classifier: Classifier | None = None,
        priority_engine: PriorityEngine | None = None,
        confirmation_window: timedelta = timedelta(minutes=5),
        workflow_deadline: timedelta = timedelta(minutes=30),
        clock: Any = None,
    ):
        self.session = session
        self.classifier = classifier or RuleBasedClassifier()
        self.priority_engine = priority_engine or PriorityEngine()
        self.confirmation_window = confirmation_window
        self.workflow_deadline = workflow_deadline
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def evaluate(self, exception_id: str, reason: str | None = None, *, commit: bool = True) -> dict[str, Any]:
        exception = self.session.get(ExceptionRecord, exception_id)
        if exception is None:
            raise LookupError("exception_not_found")
        case = self.session.execute(
            select(Case).where(Case.id == exception.case_id).with_for_update()
        ).scalar_one()
        previous_case_priority = case.priority
        previous_case_sla_deadline = _utc(case.sla_deadline).isoformat() if case.sla_deadline else None
        now = _utc(self.clock())

        linked_events = self.session.execute(
            select(EventRecord)
            .join(ExceptionEvidence, ExceptionEvidence.event_record_id == EventRecord.id)
            .where(ExceptionEvidence.exception_id == exception.id)
            .order_by(EventRecord.occurred_at, EventRecord.ingested_at, EventRecord.id)
        ).scalars().all()
        references = {exception.source_reference} if exception.source_reference else set()
        references.update(event.entity_reference for event in linked_events)
        events = list(linked_events)
        if references:
            related = self.session.execute(
                select(EventRecord)
                .where(EventRecord.entity_reference.in_(references))
                .order_by(EventRecord.occurred_at, EventRecord.ingested_at, EventRecord.id)
            ).scalars().all()
            by_id = {event.id: event for event in events}
            by_id.update({event.id: event for event in related})
            events = list(by_id.values())
        events.sort(key=lambda event: (_utc(event.occurred_at), _utc(event.ingested_at), event.id))

        classification = self.classifier.classify(
            exception.exception_type,
            events,
            now,
            self.confirmation_window,
            self.workflow_deadline,
            missing_evidence=not linked_events,
        )
        category_names = {item["category"] for item in classification["categories"]}
        observed_sources = {event.source_system for event in events}
        evidence_complete = bool(events) and all(
            required.issubset(observed_sources)
            for category in category_names
            if (required := REQUIRED_SOURCES.get(category)) is not None
        )
        if not category_names or "UNKNOWN_EXCEPTION" in category_names:
            evidence_complete = False

        payment_events = self.session.execute(
            select(EventRecord).where(EventRecord.source_system == "payments")
        ).scalars().all()
        priority = self.priority_engine.calculate(
            classification["categories"],
            events,
            payment_events,
            case.created_at,
            now,
            evidence_complete,
        )
        routing = recommend_routing(
            classification["categories"],
            events,
            classification["uncertainty_flags"],
            duplicate_effect_risk=priority["input_facts"]["potential_duplicate_monetary_effect"],
        )

        sla_started_at = _utc(case.sla_started_at or case.created_at)
        sla_duration = timedelta(hours=priority["sla_duration_hours"])
        sla_deadline = sla_started_at + sla_duration
        sla = {
            "started_at": sla_started_at.isoformat(),
            "deadline": sla_deadline.isoformat(),
            "rule_version": priority["rule_version"],
            "duration_hours": priority["sla_duration_hours"],
        }
        assessment = {
            "assessment_version": ASSESSMENT_VERSION,
            "classification": classification,
            "priority": priority,
            "routing": routing,
            "sla": sla,
        }

        latest = self.session.execute(
            select(AssessmentHistory)
            .where(AssessmentHistory.exception_id == exception.id)
            .order_by(AssessmentHistory.revision.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is None:
            previous_values = {
                "priority": previous_case_priority,
                "sla_deadline": previous_case_sla_deadline,
                "recommended_specialists": [],
            }
        else:
            previous_values = {
                "priority": latest.assessment.get("priority", {}).get("level"),
                "sla_deadline": latest.assessment.get("sla", {}).get("deadline"),
                "recommended_specialists": latest.assessment.get("routing", {}).get("recommended_specialists", []),
            }
        assessment["change_context"] = {"previous_values": previous_values}
        if latest is not None and self._comparable(latest.assessment) == self._comparable(assessment):
            self.session.commit() if commit else self.session.flush()
            return {"changed": False, "revision": latest.revision, "assessment": latest.assessment}

        previous_assessment = latest.assessment if latest is not None else None
        change_reasons = self._change_reasons(previous_assessment, assessment)
        if latest is None and previous_case_priority != priority["level"]:
            change_reasons.append("priority_changed")
        revision = 1 if latest is None else latest.revision + 1
        history_reason = reason.strip() if reason and reason.strip() else "; ".join(change_reasons)
        assessment["change_reasons"] = change_reasons
        assessment["requested_reason"] = reason.strip() if reason and reason.strip() else None

        case.priority = priority["level"]
        case.sla_started_at = sla_started_at
        case.sla_deadline = sla_deadline
        case.sla_rule_version = priority["rule_version"]
        self.session.add(
            AssessmentHistory(
                id=str(uuid4()),
                exception_id=exception.id,
                case_id=case.id,
                revision=revision,
                assessment_version=ASSESSMENT_VERSION,
                classification_source=classification["classification_source"],
                operational_eligible=classification["operational_eligible"],
                change_reason=history_reason,
                assessment=assessment,
            )
        )
        self._write_audits(case.id, exception.id, revision, change_reasons, assessment)
        self.session.commit() if commit else self.session.flush()
        return {"changed": True, "revision": revision, "assessment": assessment}

    def get_exception_assessment(self, exception_id: str) -> dict[str, Any] | None:
        latest = self.session.execute(
            select(AssessmentHistory)
            .where(AssessmentHistory.exception_id == exception_id)
            .order_by(AssessmentHistory.revision.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is None:
            return None
        return self._with_sla_runtime(latest.assessment)

    def get_case_assessment(self, case_id: str) -> dict[str, Any] | None:
        latest = self.session.execute(
            select(AssessmentHistory)
            .where(AssessmentHistory.case_id == case_id)
            .order_by(AssessmentHistory.revision.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is None:
            return None
        return self._with_sla_runtime(latest.assessment)

    def get_history(self, exception_id: str) -> list[dict[str, Any]]:
        rows = self.session.execute(
            select(AssessmentHistory)
            .where(AssessmentHistory.exception_id == exception_id)
            .order_by(AssessmentHistory.revision)
        ).scalars().all()
        return [
            {
                "revision": row.revision,
                "assessment_version": row.assessment_version,
                "classification_source": row.classification_source,
                "operational_eligible": row.operational_eligible,
                "change_reason": row.change_reason,
                "created_at": _utc(row.created_at).isoformat(),
                "assessment": self._with_sla_runtime(row.assessment),
            }
            for row in rows
        ]

    @staticmethod
    def _comparable(assessment: dict[str, Any]) -> str:
        comparable = json.loads(json.dumps(assessment, sort_keys=True))
        comparable.get("classification", {}).pop("classification_timestamp", None)
        comparable.pop("change_reasons", None)
        comparable.pop("requested_reason", None)
        comparable.pop("change_context", None)
        return json.dumps(comparable, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _change_reasons(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
        if previous is None:
            return ["initial_assessment"]
        reasons = []
        previous_classification = previous.get("classification", {})
        current_classification = current.get("classification", {})
        previous_categories = [item.get("category") for item in previous_classification.get("categories", [])]
        current_categories = [item.get("category") for item in current_classification.get("categories", [])]
        if previous_categories != current_categories or previous_classification.get("rule_version") != current_classification.get("rule_version"):
            reasons.append("classification_changed")
        if previous_classification.get("supporting_evidence_references") != current_classification.get("supporting_evidence_references"):
            reasons.append("evidence_changed")
        if previous.get("priority", {}).get("level") != current.get("priority", {}).get("level"):
            reasons.append("priority_changed")
        if previous.get("routing", {}).get("recommended_specialists") != current.get("routing", {}).get("recommended_specialists"):
            reasons.append("routing_changed")
        if previous.get("sla", {}).get("deadline") != current.get("sla", {}).get("deadline"):
            reasons.append("sla_recalculated")
        if not reasons:
            reasons.append("assessment_rules_or_facts_changed")
        return reasons

    def _with_sla_runtime(self, assessment: dict[str, Any]) -> dict[str, Any]:
        result = json.loads(json.dumps(assessment))
        deadline = datetime.fromisoformat(result["sla"]["deadline"])
        remaining_seconds = (deadline - _utc(self.clock())).total_seconds()
        result["sla"]["remaining_seconds"] = max(0, int(remaining_seconds))
        result["sla"]["overdue"] = remaining_seconds < 0
        result["priority"]["action_authorization"] = "NOT_EVALUATED"
        return result

    def _write_audits(
        self,
        case_id: str,
        exception_id: str,
        revision: int,
        reasons: list[str],
        assessment: dict[str, Any],
    ) -> None:
        audit_events = {
            "initial_assessment": ("exception_classified", "Exception classified and routed using deterministic rules."),
            "classification_changed": ("classification_revised", "Exception classification changed."),
            "evidence_changed": ("classification_evidence_updated", "Classification evidence references changed."),
            "priority_changed": ("priority_changed", "Case priority changed under synthetic rules."),
            "routing_changed": ("specialist_routing_changed", "Recommended specialist routing changed."),
            "sla_recalculated": ("sla_recalculated", "Case SLA deadline was recalculated from its original start time."),
            "assessment_rules_or_facts_changed": ("assessment_updated", "Assessment inputs or rule versions changed."),
        }
        for reason in reasons:
            event_type, summary = audit_events.get(reason, ("assessment_updated", "Assessment inputs or rule versions changed."))
            audit = AuditLog(
                id=str(uuid4()),
                case_id=case_id,
                entity_type="exception",
                entity_id=exception_id,
                event_type=event_type,
                summary=summary,
                details={
                    "revision": revision,
                    "reason": reason,
                    "classification_rule_version": assessment["classification"]["rule_version"],
                    "priority_rule_version": assessment["priority"]["rule_version"],
                    "routing_rule_version": assessment["routing"]["rule_version"],
                    "priority": assessment["priority"]["level"],
                    "specialists": assessment["routing"]["recommended_specialists"],
                    "previous_values": assessment["change_context"]["previous_values"],
                },
            )
            self.session.add(audit)
