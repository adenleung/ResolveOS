from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from app.classification.models import AssessmentHistory
from app.correlation.engine import CORRELATION_RULE_VERSION, DeterministicCorrelationEngine
from app.correlation.features import CaseCorrelationFeatures, build_case_features, event_reference
from app.correlation.models import IncidentCorrelationHistory, IncidentCorrelationRun
from app.ingestion.models import EventRecord, ExceptionEvidence
from app.models.domain import AuditLog, Case, CaseIncident, ExceptionRecord, Incident


INCIDENT_STATUSES = {"SUSPECTED", "INVESTIGATING", "CONFIRMED", "RESOLVED", "REJECTED", "SPLIT", "MERGED"}
ACTIVE_INCIDENT_STATUSES = {"SUSPECTED", "INVESTIGATING", "CONFIRMED"}
TRANSITIONS = {
    "SUSPECTED": {"INVESTIGATING", "REJECTED"},
    "INVESTIGATING": {"CONFIRMED", "REJECTED"},
    "CONFIRMED": {"RESOLVED"},
    "RESOLVED": set(),
    "REJECTED": set(),
    "SPLIT": set(),
    "MERGED": set(),
}
CORRELATION_ADVISORY_LOCK = 202610020005


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class IncidentCorrelationService:
    def __init__(
        self,
        session: Session,
        engine: DeterministicCorrelationEngine | None = None,
        event_time_window: timedelta = timedelta(minutes=30),
        batch_size: int = 200,
        candidate_limit: int = 1000,
        event_limit: int = 10_000,
        candidate_pair_limit: int = 5_000,
        clock: Any = None,
    ):
        self.session = session
        self.engine = engine or DeterministicCorrelationEngine()
        self.event_time_window = event_time_window
        self.batch_size = min(max(batch_size, 1), 500)
        self.candidate_limit = max(candidate_limit, self.batch_size)
        self.event_limit = max(event_limit, self.batch_size)
        self.candidate_pair_limit = max(candidate_pair_limit, 1)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run(self, after_case_id: str | None = None, case_ids: Iterable[str] | None = None) -> dict[str, Any]:
        now = _utc(self.clock())
        self._acquire_correlation_lock()
        if case_ids is None:
            seed_case_ids = self._page_case_ids(after_case_id)
        else:
            seed_case_ids = sorted(set(case_ids))[: self.batch_size]
        seed_rows = self._load_rows(case_ids=set(seed_case_ids))
        next_cursor = self._next_cursor(seed_case_ids[-1]) if seed_case_ids and case_ids is None else None
        run_record = IncidentCorrelationRun(
            id=str(uuid4()),
            rule_version=self.engine.rule_version,
            status="RUNNING",
            started_at=now,
            completed_at=None,
            cases_examined=len(seed_case_ids),
            candidate_pairs_examined=0,
            groups_created=0,
            memberships_added=0,
            ungrouped_cases=0,
            settings={
                "event_time_window_seconds": int(self.event_time_window.total_seconds()),
                "batch_size": self.batch_size,
                "candidate_limit": self.candidate_limit,
                "event_limit": self.event_limit,
                "candidate_pair_limit": self.candidate_pair_limit,
                "after_case_id": after_case_id,
            },
        )
        self.session.add(run_record)
        self.session.flush()

        if not seed_rows:
            run_record.status = "COMPLETED"
            run_record.completed_at = now
            self.session.commit()
            return {
                "run_id": run_record.id,
                "rule_version": run_record.rule_version,
                "cases_examined": 0,
                "candidate_pairs_examined": 0,
                "groups_created": 0,
                "memberships_added": 0,
                "ungrouped_cases": 0,
                "next_after_case_id": None,
            }

        rows, observations, linked_by_exception, incident_ids_by_entity, candidate_truncated = self._expand_candidates(
            seed_rows, now
        )
        features = self._make_case_features(rows, observations, linked_by_exception, incident_ids_by_entity)
        correlation = self.engine.correlate(
            features,
            self.event_time_window,
            self.candidate_pair_limit,
        )
        pair_results = correlation["pair_results"]
        groups = correlation["groups"]
        run_record.candidate_pairs_examined = correlation["comparisons"]

        feature_by_case = {feature.case_id: feature for feature in features}
        seed_case_set = set(seed_case_ids)
        self._record_pair_outcomes(run_record.id, pair_results, feature_by_case, now)
        groups_by_case = {
            case_id: group for group in groups for case_id in group["case_ids"]
        }
        run_record.ungrouped_cases = len(seed_case_set - set(groups_by_case))
        if not candidate_truncated and not correlation["truncated"]:
            self._reconcile_suspected_memberships(seed_case_set, groups_by_case, feature_by_case, run_record.id, now)
        self.session.flush()

        created, added = self._apply_groups(groups, feature_by_case, rows, run_record.id, now)
        run_record.groups_created = created
        run_record.memberships_added = added
        self._record_ungrouped(seed_case_set, groups_by_case, feature_by_case, run_record.id, now)
        run_record.status = "COMPLETED"
        run_record.completed_at = _utc(self.clock())
        self.session.commit()
        return {
            "run_id": run_record.id,
            "rule_version": run_record.rule_version,
            "cases_examined": run_record.cases_examined,
            "candidate_cases_examined": len(features),
            "candidate_pairs_examined": run_record.candidate_pairs_examined,
            "groups_created": created,
            "memberships_added": added,
            "ungrouped_cases": run_record.ungrouped_cases,
            "candidate_search_truncated": candidate_truncated or correlation["truncated"],
            "next_after_case_id": next_cursor,
        }

    def _acquire_correlation_lock(self) -> None:
        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            self.session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": CORRELATION_ADVISORY_LOCK}
            )

    def _load_rows(
        self,
        case_ids: set[str] | None = None,
        after_case_id: str | None = None,
        limit: int | None = None,
        exception_ids: set[str] | None = None,
    ) -> list[tuple[ExceptionRecord, Case, Any]]:
        latest_revision = (
            select(
                AssessmentHistory.exception_id.label("exception_id"),
                func.max(AssessmentHistory.revision).label("revision"),
            )
            .group_by(AssessmentHistory.exception_id)
            .subquery()
        )
        query = (
            select(ExceptionRecord, Case, AssessmentHistory)
            .join(Case, Case.id == ExceptionRecord.case_id)
            .outerjoin(latest_revision, latest_revision.c.exception_id == ExceptionRecord.id)
            .outerjoin(
                AssessmentHistory,
                and_(
                    AssessmentHistory.exception_id == latest_revision.c.exception_id,
                    AssessmentHistory.revision == latest_revision.c.revision,
                ),
            )
            .where(ExceptionRecord.detection_key.is_not(None))
            .order_by(Case.id, ExceptionRecord.id)
        )
        if exception_ids is not None:
            query = query.where(ExceptionRecord.id.in_(exception_ids))
        if case_ids is not None:
            query = query.where(Case.id.in_(case_ids))
        if after_case_id is not None:
            query = query.where(Case.id > after_case_id)
        if limit is not None:
            query = query.limit(limit)
        return list(self.session.execute(query).all())

    def _next_cursor(self, last_case_id: str) -> str | None:
        exists = self.session.execute(
            select(ExceptionRecord.id)
            .join(Case, Case.id == ExceptionRecord.case_id)
            .where(ExceptionRecord.detection_key.is_not(None), Case.id > last_case_id)
            .limit(1)
        ).scalar_one_or_none()
        return last_case_id if exists else None

    def _page_case_ids(self, after_case_id: str | None) -> list[str]:
        query = (
            select(Case.id)
            .join(ExceptionRecord, ExceptionRecord.case_id == Case.id)
            .where(ExceptionRecord.detection_key.is_not(None))
            .distinct()
            .order_by(Case.id)
            .limit(self.batch_size)
        )
        if after_case_id is not None:
            query = query.where(Case.id > after_case_id)
        return list(self.session.execute(query).scalars().all())

    def _expand_candidates(
        self,
        seed_rows: list[tuple[ExceptionRecord, Case, Any]],
        now: datetime,
    ) -> tuple[list[tuple[ExceptionRecord, Case, Any]], list[EventRecord], dict[str, list[EventRecord]], dict[str, set[str]], bool]:
        seed_exception_ids = {exception.id for exception, _case, _assessment in seed_rows}
        seed_case_ids = {case.id for _exception, case, _assessment in seed_rows}
        linked = self._linked_events(seed_exception_ids)
        linked_by_exception: dict[str, list[EventRecord]] = {}
        for exception_id, event in linked:
            linked_by_exception.setdefault(exception_id, []).append(event)

        entity_refs = {
            str(exception.source_reference)
            for exception, _case, _assessment in seed_rows
            if exception.source_reference
        }
        correlations = {event.correlation_id for _exception_id, event in linked if event.correlation_id}
        entity_refs.update(event.entity_reference for _exception_id, event in linked)

        incident_ids_by_entity: dict[str, set[str]] = {}
        source_events = self._events_for_identifiers(entity_refs, correlations)
        incident_keys = {str(event.payload[key]) for event in source_events if event.source_system != "payments"
                         for key in ("incident_identifier", "dependency_failure_id") if event.payload.get(key)}
        if incident_keys:
            related = self.session.execute(
                select(EventRecord).where(EventRecord.source_system != "payments", or_(
                    EventRecord.payload["incident_identifier"].as_string().in_(incident_keys),
                    EventRecord.payload["dependency_failure_id"].as_string().in_(incident_keys),
                )).order_by(EventRecord.occurred_at.desc(), EventRecord.id).limit(self.event_limit)
            ).scalars().all()
            entity_refs.update(event.entity_reference for event in related)

        observation_events = self._events_for_identifiers(entity_refs, correlations)
        weak_events = self._recent_api_candidates([event for _exception_id, event in linked])
        event_by_id = {event.id: event for event in observation_events}
        event_by_id.update({event.id: event for event in weak_events})
        event_by_id.update({event.id: event for _exception_id, event in linked})
        observations = list(event_by_id.values())[: self.event_limit]

        observed_event_ids = {event.id for event in observations}
        candidate_exception_ids = set(seed_exception_ids)
        if observed_event_ids:
            candidate_exception_ids.update(
                self.session.execute(
                    select(ExceptionEvidence.exception_id)
                    .where(ExceptionEvidence.event_record_id.in_(observed_event_ids))
                    .distinct()
                    .limit(self.candidate_limit)
                ).scalars().all()
            )
        active_incident_ids = self.session.execute(
            select(CaseIncident.incident_id).where(
                CaseIncident.case_id.in_(seed_case_ids), CaseIncident.removed_at.is_(None)
            )
        ).scalars().all()
        if active_incident_ids:
            related_case_ids = self.session.execute(
                select(CaseIncident.case_id).where(
                    CaseIncident.incident_id.in_(active_incident_ids), CaseIncident.removed_at.is_(None)
                )
            ).scalars().all()
            candidate_exception_ids.update(
                self.session.execute(
                    select(ExceptionRecord.id).where(ExceptionRecord.case_id.in_(related_case_ids))
                ).scalars().all()
            )

        candidate_truncated = len(candidate_exception_ids) >= self.candidate_limit or len(observations) >= self.event_limit
        if candidate_truncated:
            available_slots = max(0, self.candidate_limit - len(seed_exception_ids))
            candidate_exception_ids = seed_exception_ids | set(sorted(candidate_exception_ids - seed_exception_ids)[:available_slots])
        rows = self._load_rows(exception_ids=candidate_exception_ids, limit=self.candidate_limit + len(seed_exception_ids))
        all_exception_ids = {exception.id for exception, _case, _assessment in rows}
        linked_by_exception = {}
        candidate_linked = self._linked_events(all_exception_ids)
        for exception_id, event in candidate_linked:
            linked_by_exception.setdefault(exception_id, []).append(event)
        candidate_entities = {
            str(exception.source_reference)
            for exception, _case, _assessment in rows
            if exception.source_reference
        }
        candidate_entities.update(event.entity_reference for _exception_id, event in candidate_linked)
        candidate_correlations = {event.correlation_id for _exception_id, event in candidate_linked if event.correlation_id}
        candidate_observations = self._events_for_identifiers(candidate_entities, candidate_correlations)
        observations_by_id = {event.id: event for event in observations}
        observations_by_id.update({event.id: event for event in candidate_observations})
        return rows, list(observations_by_id.values())[: self.event_limit], linked_by_exception, incident_ids_by_entity, candidate_truncated or len(observations_by_id) >= self.event_limit

    def _linked_events(self, exception_ids: set[str]) -> list[tuple[str, EventRecord]]:
        if not exception_ids:
            return []
        rows = self.session.execute(
            select(ExceptionEvidence.exception_id, EventRecord)
            .join(EventRecord, EventRecord.id == ExceptionEvidence.event_record_id)
            .where(ExceptionEvidence.exception_id.in_(exception_ids))
            .order_by(EventRecord.occurred_at, EventRecord.id)
        ).all()
        return [(exception_id, event) for exception_id, event in rows]

    def _events_for_identifiers(self, entity_refs: set[str], correlations: set[str]) -> list[EventRecord]:
        conditions = []
        if entity_refs:
            conditions.append(EventRecord.entity_reference.in_(entity_refs))
        if correlations:
            conditions.append(EventRecord.correlation_id.in_(correlations))
        if not conditions:
            return []
        return self.session.execute(
            select(EventRecord)
            .where(or_(*conditions))
            .order_by(EventRecord.occurred_at.desc(), EventRecord.id)
            .limit(self.event_limit)
        ).scalars().all()

    def _recent_api_candidates(self, seed_events: list[EventRecord]) -> list[EventRecord]:
        if not seed_events:
            return []
        start = min(_utc(event.occurred_at) for event in seed_events) - self.event_time_window
        end = max(_utc(event.occurred_at) for event in seed_events) + self.event_time_window
        rows = self.session.execute(
            select(EventRecord)
            .where(
                EventRecord.source_system == "api_gateway",
                EventRecord.occurred_at >= start,
                EventRecord.occurred_at <= end,
            )
            .order_by(EventRecord.occurred_at.desc())
            .limit(min(self.event_limit, self.batch_size * 20))
        ).scalars().all()
        return [
            event
            for event in rows
            if int(event.payload.get("status_code", 0)) >= 500
            or int(event.payload.get("latency_ms", 0)) >= 30_000
            or event.payload.get("error_type")
        ]

    def _make_case_features(
        self,
        rows: list[tuple[ExceptionRecord, Case, Any]],
        observations: list[EventRecord],
        linked_by_exception: dict[str, list[EventRecord]],
        incident_ids_by_entity: dict[str, set[str]],
    ) -> list[CaseCorrelationFeatures]:
        by_case: dict[str, list[tuple[ExceptionRecord, Case, Any]]] = {}
        for row in rows:
            by_case.setdefault(row[1].id, []).append(row)
        results = []
        for case_id, case_rows in sorted(by_case.items()):
            entity_refs = {exception.source_reference for exception, _case, _assessment in case_rows if exception.source_reference}
            case_linked: dict[str, EventRecord] = {}
            linked_ids: set[str] = set()
            correlations: set[str] = set()
            for exception, _case, _assessment in case_rows:
                for event in linked_by_exception.get(exception.id, []):
                    case_linked[event.id] = event
                    linked_ids.add(event.id)
                    if event.correlation_id:
                        correlations.add(event.correlation_id)
                    entity_refs.add(event.entity_reference)
            related = {
                event.id: event
                for event in observations
                if event.entity_reference in entity_refs
            }
            related.update(case_linked)
            assessments = [
                {
                    "assessment": history.assessment,
                    "operational_eligible": history.operational_eligible,
                }
                for _exception, _case, history in case_rows
                if history is not None
            ]
            results.append(
                build_case_features(
                    case_id,
                    [exception.id for exception, _case, _assessment in case_rows],
                    assessments,
                    list(related.values()),
                    linked_ids,
                )
            )
        return results

    def _record_pair_outcomes(
        self,
        run_id: str,
        pair_results: list[dict[str, Any]],
        features: dict[str, CaseCorrelationFeatures],
        now: datetime,
    ) -> None:
        for result in pair_results:
            if result["outcome"] not in {"UNKNOWN", "REJECTED"}:
                continue
            self._history(
                run_id,
                None,
                "CANDIDATE_EVALUATED",
                result["outcome"],
                None,
                result["case_ids"],
                result["shared_features"],
                result["evidence_references"],
                result["contradictions"],
                {"explanation": result["explanation"]},
                now,
            )

    def _record_ungrouped(
        self,
        seed_case_ids: set[str],
        groups_by_case: dict[str, dict[str, Any]],
        features: dict[str, CaseCorrelationFeatures],
        run_id: str,
        now: datetime,
    ) -> None:
        paired = {
            case_id
            for feature in features.values()
            for case_id in (feature.case_id,)
        }
        for case_id in sorted(seed_case_ids - set(groups_by_case)):
            feature = features.get(case_id)
            if feature is None:
                continue
            self._history(
                run_id,
                None,
                "CASE_EVALUATED",
                "UNKNOWN",
                None,
                [case_id],
                [],
                feature.evidence_references,
                [{"kind": "no_strong_grouping_evidence"}],
                {"feature_summary": feature.summary(), "pair_evaluated": case_id in paired},
                now,
            )

    def _reconcile_suspected_memberships(
        self,
        seed_case_ids: set[str],
        groups_by_case: dict[str, dict[str, Any]],
        features: dict[str, CaseCorrelationFeatures],
        run_id: str,
        now: datetime,
    ) -> None:
        if not seed_case_ids:
            return
        links = self.session.execute(
            select(CaseIncident, Incident)
            .join(Incident, Incident.id == CaseIncident.incident_id)
            .where(CaseIncident.case_id.in_(seed_case_ids), CaseIncident.removed_at.is_(None))
            .with_for_update()
        ).all()
        touched_incidents: set[str] = set()
        for link, incident in links:
            group = groups_by_case.get(link.case_id)
            supported = group is not None and incident.incident_key == f"correlation-v1:{group['correlation_key']}"
            # Split children require an explicit review before their grouping is changed.
            if ":split:" in incident.incident_key:
                supported = group is not None
            if incident.status != "SUSPECTED" or supported:
                continue
            feature = features.get(link.case_id)
            evidence = feature.evidence_references if feature else []
            link.removed_at = now
            link.removal_reason = "Current evidence no longer supports a strong correlation."
            touched_incidents.add(incident.id)
            self._history(
                run_id,
                incident.id,
                "MEMBERSHIP_REMOVED",
                "RECLASSIFIED_UNGROUPED",
                incident.incident_key,
                [link.case_id],
                [],
                evidence,
                [{"kind": "strong_correlation_no_longer_present"}],
                {"removal_reason": link.removal_reason},
                now,
            )
            self._audit(incident.id, link.case_id, "incident_case_disassociated", "Case membership removed after correlation evidence changed.", {"reason": link.removal_reason})

        self.session.flush()
        for incident_id in touched_incidents:
            incident = self.session.get(Incident, incident_id)
            active = self.session.execute(
                select(CaseIncident).where(
                    CaseIncident.incident_id == incident_id,
                    CaseIncident.removed_at.is_(None),
                ).with_for_update()
            ).scalars().all()
            if len(active) >= 2:
                continue
            for link in active:
                link.removed_at = now
                link.removal_reason = "Incident no longer has sufficient correlated cases."
                self._history(
                    run_id,
                    incident_id,
                    "MEMBERSHIP_REMOVED",
                    "INSUFFICIENT_MEMBERS",
                    incident.incident_key,
                    [link.case_id],
                    [],
                    features.get(link.case_id).evidence_references if link.case_id in features else [],
                    [{"kind": "incident_requires_multiple_cases"}],
                    {"removal_reason": link.removal_reason},
                    now,
                )
            previous_status = incident.status
            incident.status = "REJECTED"
            self._history(
                run_id,
                incident_id,
                "STATUS_CHANGED",
                "REJECTED",
                incident.incident_key,
                [link.case_id for link in active],
                [],
                [],
                [{"kind": "insufficient_correlated_members"}],
                {"previous_status": previous_status, "new_status": "REJECTED"},
                now,
            )
            self._audit(incident.id, None, "incident_status_changed", "Suspected incident rejected after membership evidence changed.", {"previous_status": previous_status, "new_status": "REJECTED"})

    def _apply_groups(
        self,
        groups: list[dict[str, Any]],
        features: dict[str, CaseCorrelationFeatures],
        rows: list[tuple[ExceptionRecord, Case, Any]],
        run_id: str,
        now: datetime,
    ) -> tuple[int, int]:
        row_by_case = {case.id: (exception, case) for exception, case, _assessment in rows}
        groups_created = 0
        memberships_added = 0
        for group in groups:
            case_ids = group["case_ids"]
            active_links = self.session.execute(
                select(CaseIncident, Incident)
                .join(Incident, Incident.id == CaseIncident.incident_id)
                .where(CaseIncident.case_id.in_(case_ids), CaseIncident.removed_at.is_(None))
                .with_for_update()
            ).all()
            incident_by_id = {incident.id: incident for _link, incident in active_links}
            if len(incident_by_id) > 1:
                self._history(
                    run_id,
                    None,
                    "GROUP_EVALUATED",
                    "UNKNOWN",
                    group["correlation_key"],
                    case_ids,
                    group["shared_features"],
                    group["evidence_references"],
                    [{"kind": "cases_already_belong_to_distinct_incidents"}],
                    {"incident_ids": sorted(incident_by_id)},
                    now,
                )
                continue

            incident = next(iter(incident_by_id.values()), None)
            created = False
            if incident is not None and incident.status not in {"SUSPECTED", "INVESTIGATING"}:
                self._history(
                    run_id,
                    incident.id,
                    "GROUP_EVALUATED",
                    "REQUIRES_HUMAN_REVIEW",
                    group["correlation_key"],
                    case_ids,
                    group["shared_features"],
                    group["evidence_references"],
                    group["contradictions"],
                    {"incident_status": incident.status},
                    now,
                )
                continue
            if incident is None:
                incident_key = f"correlation-v1:{group['correlation_key']}"
                incident = self.session.execute(
                    select(Incident).where(Incident.incident_key == incident_key).with_for_update()
                ).scalar_one_or_none()
                if incident is not None and incident.status not in {"SUSPECTED", "INVESTIGATING"}:
                    self._history(
                        run_id,
                        incident.id,
                        "GROUP_EVALUATED",
                        "REQUIRES_HUMAN_REVIEW",
                        group["correlation_key"],
                        case_ids,
                        group["shared_features"],
                        group["evidence_references"],
                        group["contradictions"],
                        {"incident_status": incident.status},
                        now,
                    )
                    continue
                if incident is None:
                    members = [row_by_case[case_id][0] for case_id in case_ids if case_id in row_by_case]
                    severity = max((member.severity for member in members), key=self._severity_rank, default="MEDIUM")
                    incident = Incident(
                        id=str(uuid4()),
                        incident_key=incident_key,
                        incident_type="CORRELATED_OPERATIONAL_EXCEPTIONS",
                        severity=severity,
                        description="Suspected shared operational incident based on observed source evidence.",
                        status="SUSPECTED",
                        correlation_rule_version=self.engine.rule_version,
                    )
                    self.session.add(incident)
                    self.session.flush()
                    created = True

            existing_case_ids = {
                link.case_id
                for link, _incident in active_links
                if link.incident_id == incident.id
            }
            to_add = [case_id for case_id in case_ids if case_id not in existing_case_ids]
            manual_removals = self.session.execute(select(IncidentCorrelationHistory).where(
                IncidentCorrelationHistory.incident_id == incident.id,
                IncidentCorrelationHistory.operation == "CASE_REMOVED",
            )).scalars().all()
            excluded = {case_id for item in manual_removals for case_id in item.case_ids}
            to_add = [case_id for case_id in to_add if case_id not in excluded]
            case_ids = [case_id for case_id in case_ids if case_id not in excluded or case_id in existing_case_ids]
            if not created and not to_add:
                latest = self.session.execute(select(IncidentCorrelationHistory).where(
                    IncidentCorrelationHistory.incident_id == incident.id,
                    IncidentCorrelationHistory.operation.in_(["INCIDENT_CREATED", "MEMBERSHIP_UPDATED", "EVIDENCE_UPDATED"])
                ).order_by(IncidentCorrelationHistory.created_at.desc(), IncidentCorrelationHistory.id.desc()).limit(1)).scalar_one_or_none()
                if latest is not None and latest.shared_features == group["shared_features"] and latest.evidence_references == group["evidence_references"] and latest.contradictions == group["contradictions"]:
                    continue

            operation = "INCIDENT_CREATED" if created else ("MEMBERSHIP_UPDATED" if to_add else "EVIDENCE_UPDATED")
            outcome = "SUSPECTED"
            history = self._history(
                run_id,
                incident.id,
                operation,
                outcome,
                group["correlation_key"],
                case_ids,
                group["shared_features"],
                group["evidence_references"],
                group["contradictions"],
                {
                    **group["details"],
                    "incident_status": incident.status,
                    "classification_categories": {
                        case_id: sorted(features[case_id].categories) for case_id in case_ids
                    },
                },
                now,
            )
            self.session.flush()
            for case_id in to_add:
                active_elsewhere = self.session.execute(
                    select(CaseIncident)
                    .where(CaseIncident.case_id == case_id, CaseIncident.removed_at.is_(None))
                    .with_for_update()
                ).scalar_one_or_none()
                if active_elsewhere is not None:
                    continue
                self.session.add(
                    CaseIncident(
                        id=str(uuid4()),
                        case_id=case_id,
                        incident_id=incident.id,
                        relationship_type="CORRELATED",
                        correlation_history_id=history.id,
                    )
                )
                memberships_added += 1
                self._audit(
                    incident.id,
                    case_id,
                    "incident_case_associated",
                    "Case associated with a suspected incident based on observed strong identifiers.",
                    {"history_id": history.id, "correlation_key": group["correlation_key"]},
                )
            if created:
                groups_created += 1
                self._audit(
                    incident.id,
                    None,
                    "incident_created_suspected",
                    incident.description,
                    {"history_id": history.id, "case_ids": case_ids, "correlation_key": group["correlation_key"]},
                )
        return groups_created, memberships_added

    def _history(
        self,
        run_id: str | None,
        incident_id: str | None,
        operation: str,
        outcome: str,
        correlation_key: str | None,
        case_ids: list[str],
        shared_features: list[dict[str, Any]],
        evidence_references: list[dict[str, Any]],
        contradictions: list[dict[str, Any]],
        details: dict[str, Any],
        now: datetime,
    ) -> IncidentCorrelationHistory:
        history = IncidentCorrelationHistory(
            id=str(uuid4()),
            correlation_run_id=run_id,
            incident_id=incident_id,
            operation=operation,
            outcome=outcome,
            correlation_key=correlation_key,
            rule_version=self.engine.rule_version,
            case_ids=case_ids,
            shared_features=shared_features,
            evidence_references=evidence_references,
            contradictions=contradictions,
            details=details,
            created_at=now,
        )
        self.session.add(history)
        return history

    def _audit(
        self,
        incident_id: str,
        case_id: str | None,
        event_type: str,
        summary: str,
        details: dict[str, Any],
    ) -> None:
        self.session.add(
            AuditLog(
                id=str(uuid4()),
                case_id=case_id,
                entity_type="incident",
                entity_id=incident_id,
                event_type=event_type,
                summary=summary,
                details=details,
            )
        )

    @staticmethod
    def _severity_rank(severity: str) -> int:
        return {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}.get(str(severity).upper(), 0)

    def list_incidents(
        self, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        query = (
            select(Incident, func.count(CaseIncident.id))
            .outerjoin(
                CaseIncident,
                and_(CaseIncident.incident_id == Incident.id, CaseIncident.removed_at.is_(None)),
            )
            .group_by(Incident.id)
            .order_by(Incident.created_at.desc(), Incident.id)
        )
        if status:
            query = query.where(Incident.status == status.upper())
        rows = self.session.execute(query.offset(offset).limit(limit)).all()
        return [
            {
                "incident_id": incident.id,
                "incident_key": incident.incident_key,
                "incident_type": incident.incident_type,
                "severity": incident.severity,
                "status": incident.status,
                "active_case_count": active_count,
                "created_at": _utc(incident.created_at).isoformat(),
                "updated_at": _utc(incident.updated_at).isoformat(),
            }
            for incident, active_count in rows
        ]

    def incident_summary(self, incident_id: str) -> dict[str, Any] | None:
        incident = self.session.get(Incident, incident_id)
        if incident is None:
            return None
        rows = self.session.execute(
            select(CaseIncident, Case)
            .join(Case, Case.id == CaseIncident.case_id)
            .where(CaseIncident.incident_id == incident.id, CaseIncident.removed_at.is_(None))
            .order_by(Case.case_number)
        ).all()
        case_ids = [case.id for _link, case in rows]
        event_rows = self._case_event_records(case_ids)
        evidence = {event.id: event_reference(event) for event in event_rows}
        latest_correlation = self.session.execute(
            select(IncidentCorrelationHistory)
            .where(
                IncidentCorrelationHistory.incident_id == incident.id,
                IncidentCorrelationHistory.operation.in_(
                    ["INCIDENT_CREATED", "MEMBERSHIP_UPDATED", "SPLIT_CREATED", "INCIDENT_MERGED", "EVIDENCE_UPDATED"]
                ),
            )
            .order_by(IncidentCorrelationHistory.created_at.desc(), IncidentCorrelationHistory.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        contradictions = latest_correlation.contradictions if latest_correlation else []
        shared_features = latest_correlation.shared_features if latest_correlation else []
        event_times = [_utc(event.occurred_at) for event in event_rows]
        return {
            "incident_id": incident.id,
            "incident_key": incident.incident_key,
            "incident_type": incident.incident_type,
            "severity": incident.severity,
            "status": incident.status,
            "merged_into_id": incident.merged_into_id,
            "correlation_rule_version": incident.correlation_rule_version,
            "created_at": _utc(incident.created_at).isoformat(),
            "updated_at": _utc(incident.updated_at).isoformat(),
            "case_ids": case_ids,
            "cases": [
                {
                    "case_id": case.id,
                    "case_number": case.case_number,
                    "status": case.status.value if hasattr(case.status, "value") else str(case.status),
                    "priority": case.priority,
                }
                for _link, case in rows
            ],
            "affected_systems": sorted({event.source_system for event in event_rows}),
            "shared_observed_features": shared_features,
            "relevant_timestamps": {
                "first_event_at": min(event_times).isoformat() if event_times else None,
                "last_event_at": max(event_times).isoformat() if event_times else None,
                "incident_created_at": _utc(incident.created_at).isoformat(),
            },
            "evidence_references": list(evidence.values()),
            "unresolved_contradictions": contradictions,
        }

    def incident_history(self, incident_id: str) -> list[dict[str, Any]]:
        rows = self.session.execute(
            select(IncidentCorrelationHistory)
            .where(IncidentCorrelationHistory.incident_id == incident_id)
            .order_by(IncidentCorrelationHistory.created_at, IncidentCorrelationHistory.id)
        ).scalars().all()
        return [
            {
                "id": row.id,
                "correlation_run_id": row.correlation_run_id,
                "operation": row.operation,
                "outcome": row.outcome,
                "correlation_key": row.correlation_key,
                "rule_version": row.rule_version,
                "case_ids": row.case_ids,
                "shared_features": row.shared_features,
                "evidence_references": row.evidence_references,
                "contradictions": row.contradictions,
                "details": row.details,
                "created_at": _utc(row.created_at).isoformat(),
            }
            for row in rows
        ]

    def incident_evidence(self, incident_id: str) -> list[dict[str, Any]] | None:
        if self.session.get(Incident, incident_id) is None:
            return None
        case_ids = self._active_case_ids(incident_id)
        return [event_reference(event) | {"payload": {
            key: value for key, value in event.payload.items()
            if key not in {"scenario_name", "expected_root_cause", "root_cause"}
            and not (event.source_system == "payments" and key == "incident_identifier")
        }} for event in self._case_event_records(case_ids)]

    def transition_status(
        self,
        incident_id: str,
        new_status: str,
        reason: str,
        evidence_event_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        incident = self._locked_incident(incident_id)
        target = new_status.upper()
        if target not in INCIDENT_STATUSES or target in {"SPLIT", "MERGED"}:
            raise ValueError("unsupported_incident_status")
        if target not in TRANSITIONS.get(incident.status, set()):
            raise ValueError(f"invalid_incident_transition:{incident.status}:{target}")
        if not reason.strip():
            raise ValueError("reason_required")
        case_ids = self._active_case_ids(incident.id)
        event_ids = set(evidence_event_ids or [])
        case_events = self._case_event_records(case_ids)
        available = {event.id for event in case_events}
        if target == "CONFIRMED":
            if len(case_ids) < 2:
                raise ValueError("confirmation_requires_multiple_cases")
            if not event_ids or not event_ids.issubset(available):
                raise ValueError("confirmation_requires_incident_source_evidence")
            prior_strong_history = self.session.execute(
                select(IncidentCorrelationHistory)
                .where(IncidentCorrelationHistory.incident_id == incident.id)
                .order_by(IncidentCorrelationHistory.created_at.desc())
            ).scalars().all()
            strong_refs = {
                reference.get("event_record_id")
                for item in prior_strong_history
                for feature in (item.shared_features or [])
                if feature.get("strength") == "STRONG"
                for reference in (item.evidence_references or [])
            }
            if not event_ids.intersection(strong_refs):
                raise ValueError("confirmation_evidence_must_support_a_strong_correlation")
            features = self._current_features(case_ids)
            current = self.engine.correlate(list(features.values()), self.event_time_window, self.candidate_pair_limit)
            if not any(set(group["case_ids"]) == set(case_ids) for group in current["groups"]):
                raise ValueError("confirmation_requires_current_supported_membership")
            if any(group["contradictions"] for group in current["groups"] if set(group["case_ids"]) == set(case_ids)):
                raise ValueError("confirmation_requires_resolution_of_contradictions")
            for case_id in case_ids:
                own_events = {event.id for event in self._case_event_records([case_id])}
                if not event_ids.intersection(own_events):
                    raise ValueError("confirmation_requires_evidence_for_each_case")

        previous = incident.status
        now = _utc(self.clock())
        incident.status = target
        refs = [event_reference(event) for event in case_events if event.id in event_ids]
        self._history(
            None,
            incident.id,
            "STATUS_CHANGED",
            target,
            incident.incident_key,
            case_ids,
            [],
            refs,
            [],
            {"previous_status": previous, "new_status": target, "reason": reason.strip()},
            now,
        )
        self._audit(incident.id, None, "incident_status_changed", f"Incident status changed from {previous} to {target}.", {"previous_status": previous, "new_status": target, "reason": reason.strip()})
        if target == "REJECTED":
            self._deactivate_memberships(incident, case_ids, reason.strip(), now)
        self.session.commit()
        return self.incident_summary(incident.id) or {}

    def add_case(
        self,
        incident_id: str,
        case_id: str,
        reason: str,
        evidence_event_ids: list[str],
    ) -> dict[str, Any]:
        incident = self._locked_incident(incident_id)
        if incident.status not in {"SUSPECTED", "INVESTIGATING"}:
            raise ValueError("case_addition_requires_open_incident")
        if not reason.strip():
            raise ValueError("reason_required")
        case = self.session.get(Case, case_id)
        if case is None:
            raise LookupError("case_not_found")
        active = self.session.execute(
            select(CaseIncident).where(CaseIncident.case_id == case_id, CaseIncident.removed_at.is_(None)).with_for_update()
        ).scalar_one_or_none()
        if active is not None:
            if active.incident_id == incident.id:
                return self.incident_summary(incident.id) or {}
            raise ValueError("case_already_belongs_to_another_incident")
        existing_cases = self._active_case_ids(incident.id)
        if not existing_cases:
            raise ValueError("manual_add_requires_existing_incident_members")
        prior_events = self._case_event_records(existing_cases)
        new_events = self._case_event_records([case_id])
        common, references = self._shared_strong_evidence(prior_events, new_events)
        current_features = self._current_features(existing_cases + [case_id])
        new_feature = current_features.get(case_id)
        if new_feature is None or not all(
            self.engine.evaluate_pair(feature, new_feature, self.event_time_window)["outcome"] == "STRONG"
            for member_id, feature in current_features.items() if member_id != case_id
        ):
            raise ValueError("case_addition_requires_compatible_current_classification_and_evidence")
        supplied_ids = set(evidence_event_ids)
        available_ids = {event.id for event in prior_events + new_events}
        if not common or not supplied_ids or not supplied_ids.issubset(available_ids):
            raise ValueError("case_addition_requires_shared_strong_source_evidence")
        if not supplied_ids.intersection({reference["event_record_id"] for reference in references}):
            raise ValueError("provided_evidence_does_not_support_shared_identifier")
        if not supplied_ids.intersection({event.id for event in new_events}) or not supplied_ids.intersection({event.id for event in prior_events}):
            raise ValueError("case_addition_requires_evidence_from_both_sides")
        now = _utc(self.clock())
        history = self._history(
            None,
            incident.id,
            "CASE_ADDED",
            "ASSOCIATED",
            incident.incident_key,
            existing_cases + [case_id],
            common,
            references,
            [],
            {"reason": reason.strip(), "added_case_id": case_id},
            now,
        )
        self.session.flush()
        self.session.add(
            CaseIncident(
                id=str(uuid4()),
                case_id=case_id,
                incident_id=incident.id,
                relationship_type="MANUAL_CORRELATION",
                correlation_history_id=history.id,
            )
        )
        self._audit(incident.id, case_id, "incident_case_associated", "Case manually associated using supporting source evidence.", {"history_id": history.id, "reason": reason.strip()})
        self.session.commit()
        return self.incident_summary(incident.id) or {}

    def remove_case(self, incident_id: str, case_id: str, reason: str) -> dict[str, Any]:
        incident = self._locked_incident(incident_id)
        if incident.status not in {"SUSPECTED", "INVESTIGATING"}:
            raise ValueError("confirmed_or_closed_incident_requires_split")
        if not reason.strip():
            raise ValueError("reason_required")
        link = self.session.execute(
            select(CaseIncident)
            .where(
                CaseIncident.incident_id == incident.id,
                CaseIncident.case_id == case_id,
                CaseIncident.removed_at.is_(None),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if link is None:
            raise LookupError("active_incident_case_link_not_found")
        now = _utc(self.clock())
        evidence = [event_reference(event) for event in self._case_event_records([case_id])]
        link.removed_at = now
        link.removal_reason = reason.strip()
        self._history(
            None,
            incident.id,
            "CASE_REMOVED",
            "DISASSOCIATED",
            incident.incident_key,
            [case_id],
            [],
            evidence,
            [],
            {"reason": reason.strip()},
            now,
        )
        self._audit(incident.id, case_id, "incident_case_disassociated", "Case removed from incident membership.", {"reason": reason.strip()})
        self.session.flush()
        remaining = self._active_case_ids(incident.id)
        if len(remaining) < 2 and incident.status == "SUSPECTED":
            self._deactivate_memberships(incident, remaining, "Insufficient cases remain for a suspected incident.", now)
            incident.status = "REJECTED"
            self._history(None, incident.id, "STATUS_CHANGED", "REJECTED", incident.incident_key, remaining, [], [], [], {"previous_status": "SUSPECTED", "reason": "Insufficient cases remain for a suspected incident."}, now)
            self._audit(incident.id, None, "incident_status_changed", "Suspected incident rejected after case removal.", {"new_status": "REJECTED"})
        self.session.commit()
        return self.incident_summary(incident.id) or {}

    def split_incident(self, incident_id: str, groups: list[list[str]], reason: str) -> dict[str, Any]:
        incident = self._locked_incident(incident_id)
        if incident.status not in {"SUSPECTED", "INVESTIGATING", "CONFIRMED"}:
            raise ValueError("incident_cannot_be_split_in_current_status")
        if not reason.strip() or len(groups) < 2 or any(not group for group in groups):
            raise ValueError("split_requires_reason_and_multiple_case_groups")
        flattened = [case_id for group in groups for case_id in group]
        current = set(self._active_case_ids(incident.id))
        if len(flattened) != len(set(flattened)) or set(flattened) != current:
            raise ValueError("split_groups_must_partition_all_active_cases")
        now = _utc(self.clock())
        all_events = self._case_event_records(current)
        refs = [event_reference(event) for event in all_events]
        history = self._history(
            None,
            incident.id,
            "INCIDENT_SPLIT",
            "SPLIT",
            incident.incident_key,
            sorted(current),
            [],
            refs,
            [],
            {"groups": groups, "reason": reason.strip()},
            now,
        )
        for link in self.session.execute(
            select(CaseIncident).where(CaseIncident.incident_id == incident.id, CaseIncident.removed_at.is_(None)).with_for_update()
        ).scalars().all():
            link.removed_at = now
            link.removal_reason = reason.strip()
        self.session.flush()
        incident.status = "SPLIT"
        child_ids = []
        ungrouped_case_ids = []
        for index, case_group in enumerate(groups):
            if len(case_group) == 1:
                ungrouped_case_ids.extend(case_group)
                self._audit(incident.id, case_group[0], "incident_case_disassociated", "Case left ungrouped during incident split.", {"reason": reason.strip(), "history_id": history.id})
                continue
            digest = hashlib.sha256("|".join(sorted(case_group)).encode()).hexdigest()[:16]
            child = Incident(
                id=str(uuid4()),
                incident_key=f"correlation-v1:split:{incident.id}:{digest}",
                incident_type=incident.incident_type,
                severity=incident.severity,
                description=f"Suspected child incident created by splitting {incident.id}.",
                status="SUSPECTED",
                correlation_rule_version=self.engine.rule_version,
            )
            self.session.add(child)
            self.session.flush()
            child_history = self._history(
                None,
                child.id,
                "SPLIT_CREATED",
                "SUSPECTED",
                child.incident_key,
                sorted(case_group),
                [],
                [event_reference(event) for event in self._case_event_records(case_group)],
                [],
                {"parent_incident_id": incident.id, "parent_history_id": history.id, "group_index": index, "reason": reason.strip()},
                now,
            )
            self.session.flush()
            for case_id in case_group:
                self.session.add(
                    CaseIncident(
                        id=str(uuid4()),
                        case_id=case_id,
                        incident_id=child.id,
                        relationship_type="SPLIT_FROM",
                        correlation_history_id=child_history.id,
                    )
                )
                self._audit(child.id, case_id, "incident_case_associated", "Case assigned to a child incident during split.", {"parent_incident_id": incident.id, "history_id": child_history.id})
            child_ids.append(child.id)
        self._audit(incident.id, None, "incident_split", "Incident split into separately suspected groups.", {"child_incident_ids": child_ids, "reason": reason.strip(), "history_id": history.id})
        self.session.commit()
        return {"incident_id": incident.id, "status": incident.status, "child_incident_ids": child_ids, "ungrouped_case_ids": ungrouped_case_ids}

    def merge_incidents(
        self,
        target_id: str,
        source_id: str,
        reason: str,
        evidence_event_ids: list[str],
    ) -> dict[str, Any]:
        if target_id == source_id:
            raise ValueError("cannot_merge_incident_into_itself")
        if not reason.strip():
            raise ValueError("reason_required")
        self._acquire_correlation_lock()
        incidents = self.session.execute(
            select(Incident).where(Incident.id.in_([target_id, source_id])).order_by(Incident.id).with_for_update()
        ).scalars().all()
        by_id = {incident.id: incident for incident in incidents}
        if target_id not in by_id or source_id not in by_id:
            raise LookupError("incident_not_found")
        target = by_id[target_id]
        source = by_id[source_id]
        if target.status != "CONFIRMED" or source.status != "CONFIRMED":
            raise ValueError("merge_requires_two_confirmed_incidents")
        target_cases = self._active_case_ids(target.id)
        source_cases = self._active_case_ids(source.id)
        target_events = self._case_event_records(target_cases)
        source_events = self._case_event_records(source_cases)
        shared, references = self._shared_strong_evidence(target_events, source_events)
        supplied = set(evidence_event_ids)
        if not shared or not supplied or not supplied.issubset({event.id for event in target_events + source_events}):
            raise ValueError("merge_requires_shared_strong_evidence_and_source_references")
        if not supplied.intersection({reference["event_record_id"] for reference in references}):
            raise ValueError("merge_evidence_does_not_support_shared_identifiers")
        if not supplied.intersection({event.id for event in target_events}) or not supplied.intersection({event.id for event in source_events}):
            raise ValueError("merge_requires_evidence_from_both_incidents")

        now = _utc(self.clock())
        all_cases = sorted(set(target_cases + source_cases))
        target_history = self._history(
            None, target.id, "INCIDENT_MERGED", "CONFIRMED", target.incident_key, all_cases,
            shared, references, [], {"source_incident_id": source.id, "reason": reason.strip()}, now
        )
        source_history = self._history(
            None, source.id, "INCIDENT_MERGED", "MERGED", source.incident_key, all_cases,
            shared, references, [], {"merged_into_id": target.id, "reason": reason.strip()}, now
        )
        self.session.flush()
        source_links = self.session.execute(
            select(CaseIncident).where(CaseIncident.incident_id == source.id, CaseIncident.removed_at.is_(None)).with_for_update()
        ).scalars().all()
        for link in source_links:
            link.removed_at = now
            link.removal_reason = f"Merged into incident {target.id}: {reason.strip()}"
        self.session.flush()
        for link in source_links:
            self.session.add(
                CaseIncident(
                    id=str(uuid4()),
                    case_id=link.case_id,
                    incident_id=target.id,
                    relationship_type="MERGED_FROM",
                    correlation_history_id=target_history.id,
                )
            )
        source.status = "MERGED"
        source.merged_into_id = target.id
        self._audit(target.id, None, "incident_merged", "Confirmed incident merged with another confirmed incident.", {"source_incident_id": source.id, "reason": reason.strip(), "history_id": target_history.id})
        self._audit(source.id, None, "incident_merged_into", "Incident merged into a confirmed incident.", {"merged_into_id": target.id, "reason": reason.strip(), "history_id": source_history.id})
        self.session.commit()
        return self.incident_summary(target.id) or {}

    def reevaluate_incident(self, incident_id: str) -> dict[str, Any]:
        incident = self.session.get(Incident, incident_id)
        if incident is None:
            raise LookupError("incident_not_found")
        case_ids = self._active_case_ids(incident_id)
        return self.run(case_ids=case_ids)

    def _locked_incident(self, incident_id: str) -> Incident:
        self._acquire_correlation_lock()
        incident = self.session.execute(
            select(Incident).where(Incident.id == incident_id).with_for_update()
        ).scalar_one_or_none()
        if incident is None:
            raise LookupError("incident_not_found")
        return incident

    def _current_features(self, case_ids: list[str]) -> dict[str, CaseCorrelationFeatures]:
        rows = self._load_rows(case_ids=set(case_ids))
        linked = self._linked_events({row[0].id for row in rows})
        by_exception: dict[str, list[EventRecord]] = {}
        for exception_id, event in linked:
            by_exception.setdefault(exception_id, []).append(event)
        features = self._make_case_features(rows, self._case_event_records(case_ids), by_exception, {})
        return {feature.case_id: feature for feature in features}

    def _active_case_ids(self, incident_id: str) -> list[str]:
        return list(
            self.session.execute(
                select(CaseIncident.case_id)
                .where(CaseIncident.incident_id == incident_id, CaseIncident.removed_at.is_(None))
                .order_by(CaseIncident.case_id)
            ).scalars().all()
        )

    def _case_event_records(self, case_ids: Iterable[str]) -> list[EventRecord]:
        case_ids = list(set(case_ids))
        if not case_ids:
            return []
        linked = self.session.execute(
            select(EventRecord)
            .join(ExceptionEvidence, ExceptionEvidence.event_record_id == EventRecord.id)
            .join(ExceptionRecord, ExceptionRecord.id == ExceptionEvidence.exception_id)
            .where(ExceptionRecord.case_id.in_(case_ids))
            .order_by(EventRecord.occurred_at, EventRecord.id)
        ).scalars().unique().all()
        entities = {event.entity_reference for event in linked}
        return self.session.execute(select(EventRecord).where(
            EventRecord.entity_reference.in_(entities)
        ).order_by(EventRecord.occurred_at, EventRecord.id)).scalars().all() if entities else []

    def _shared_strong_evidence(
        self, left_events: list[EventRecord], right_events: list[EventRecord]
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        left_map = self._strong_event_map(left_events)
        right_map = self._strong_event_map(right_events)
        shared_tokens = set(left_map) & set(right_map)
        shared = []
        refs: dict[str, dict[str, Any]] = {}
        for token in sorted(shared_tokens):
            feature_type, value = token.split(":", 1)
            shared.append({"feature_type": feature_type, "value": value, "strength": "STRONG"})
            for reference in left_map[token] + right_map[token]:
                refs.setdefault(reference["event_record_id"], reference)
        return shared, list(refs.values())

    def _strong_event_map(self, events: list[EventRecord]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        latest = {}
        for event in events:
            key = (event.source_system, event.source_record_reference)
            previous = latest.get(key)
            if previous is None or (_utc(event.occurred_at), _utc(event.ingested_at), event.id) > (_utc(previous.occurred_at), _utc(previous.ingested_at), previous.id):
                latest[key] = event
        events = list(latest.values())
        for event in events:
            tokens = []
            if event.entity_reference:
                tokens.append(f"entity:{event.entity_reference}")
            if event.correlation_id:
                tokens.append(f"correlation:{event.correlation_id}")
            incident_id = event.payload.get("incident_identifier") if event.source_system != "payments" else None
            if incident_id:
                tokens.append(f"incident_identifier:{incident_id}")
            dependency_id = event.payload.get("dependency_failure_id")
            if dependency_id:
                tokens.append(f"dependency_failure_id:{dependency_id}")
            reference = event_reference(event)
            for token in tokens:
                result.setdefault(token, []).append(reference)
        return result

    def _deactivate_memberships(self, incident: Incident, case_ids: list[str], reason: str, now: datetime) -> None:
        for link in self.session.execute(
            select(CaseIncident)
            .where(CaseIncident.incident_id == incident.id, CaseIncident.removed_at.is_(None))
            .with_for_update()
        ).scalars().all():
            link.removed_at = now
            link.removal_reason = reason
            self._history(
                None,
                incident.id,
                "MEMBERSHIP_REMOVED",
                "DISASSOCIATED",
                incident.incident_key,
                [link.case_id],
                [],
                [event_reference(event) for event in self._case_event_records([link.case_id])],
                [],
                {"reason": reason},
                now,
            )
            self._audit(incident.id, link.case_id, "incident_case_disassociated", "Case membership ended with incident rejection.", {"reason": reason})
