from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Protocol

from app.correlation.features import CaseCorrelationFeatures


CORRELATION_RULE_VERSION = "deterministic-correlation-1.0"
STRONG_IDENTIFIER_ORDER = ("incident_identifier", "dependency_failure_id", "entity", "correlation")


class CorrelationStrategy(Protocol):
    rule_version: str

    def correlate(
        self,
        features: list[CaseCorrelationFeatures],
        event_time_window: timedelta,
        max_candidate_pairs: int,
    ) -> dict[str, Any]: ...


class DeterministicCorrelationEngine:
    rule_version = CORRELATION_RULE_VERSION

    def correlate(
        self,
        features: list[CaseCorrelationFeatures],
        event_time_window: timedelta,
        max_candidate_pairs: int,
    ) -> dict[str, Any]:
        by_case = {feature.case_id: feature for feature in features}
        buckets: dict[tuple[str, str], set[str]] = {}
        for feature in features:
            for token in feature.strong_tokens:
                feature_type, value = token.split(":", 1)
                buckets.setdefault((f"strong:{feature_type}", value), set()).add(feature.case_id)
            for weak in feature.weak_features:
                feature_type, value = weak.split(":", 1)
                buckets.setdefault((f"weak:{feature_type}", value), set()).add(feature.case_id)

        candidate_pairs: dict[tuple[str, str], set[tuple[str, str]]] = {}
        truncated = False
        def bucket_order(item):
            feature_type, value = item[0]
            kind, name = feature_type.split(":", 1)
            return (0, STRONG_IDENTIFIER_ORDER.index(name), value) if kind == "strong" else (1, name, value)

        for (feature_type, value), case_ids in sorted(buckets.items(), key=bucket_order):
            ordered = sorted(case_ids)
            if len(ordered) < 2:
                continue
            anchor = ordered[0]
            for candidate in ordered[1:]:
                pair = tuple(sorted((anchor, candidate)))
                candidate_pairs.setdefault(pair, set()).add((feature_type, value))
                if len(candidate_pairs) >= max_candidate_pairs:
                    truncated = True
                    break
            if truncated:
                break

        pair_results: list[dict[str, Any]] = []
        strong_edges: list[tuple[str, str, dict[str, Any]]] = []
        for (left_id, right_id), candidate_features in sorted(candidate_pairs.items()):
            result = self.evaluate_pair(
                by_case[left_id], by_case[right_id], event_time_window, candidate_features
            )
            pair_results.append(result)
            if result["outcome"] == "STRONG":
                strong_edges.append((left_id, right_id, result))

        groups = self._groups(strong_edges, by_case)
        grouped_case_ids = {case_id for group in groups for case_id in group["case_ids"]}
        unknown_cases = [feature for feature in features if feature.case_id not in grouped_case_ids]
        return {
            "groups": groups,
            "pair_results": pair_results,
            "comparisons": len(candidate_pairs),
            "truncated": truncated,
            "unknown_case_ids": [feature.case_id for feature in unknown_cases],
        }

    def evaluate_pair(
        self,
        left: CaseCorrelationFeatures,
        right: CaseCorrelationFeatures,
        event_time_window: timedelta,
        candidate_features: set[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        contradictions: list[dict[str, Any]] = []
        shared_strong: list[dict[str, str]] = []
        left_incidents = left.strong_identifiers.get("incident_identifier", set())
        right_incidents = right.strong_identifiers.get("incident_identifier", set())
        if len(left_incidents) > 1 or len(right_incidents) > 1:
            return self._pair_result(left, right, "UNKNOWN", [],
                left.evidence_references + right.evidence_references,
                [{"kind": "conflicting_current_incident_identifiers", "left": sorted(left_incidents), "right": sorted(right_incidents)}],
                "Current source observations identify multiple incidents; review is required.")
        if left_incidents and right_incidents and not left_incidents.intersection(right_incidents):
            contradictions.append(
                {
                    "kind": "incompatible_incident_identifiers",
                    "left": sorted(left_incidents),
                    "right": sorted(right_incidents),
                }
            )

        for feature_type in STRONG_IDENTIFIER_ORDER:
            shared = left.strong_identifiers.get(feature_type, set()) & right.strong_identifiers.get(feature_type, set())
            shared_strong.extend(
                {"feature_type": feature_type, "value": value, "strength": "STRONG"}
                for value in sorted(shared)
            )

        if contradictions:
            return self._pair_result(left, right, "REJECTED", [],
                left.evidence_references + right.evidence_references, contradictions,
                "Different source incident identifiers are incompatible.")

        if shared_strong:
            durable = any(item["feature_type"] in {"incident_identifier", "dependency_failure_id"} for item in shared_strong)
            same_entity = bool(left.strong_identifiers.get("entity", set()) & right.strong_identifiers.get("entity", set()))
            if not durable and (not self._within_window(left, right, event_time_window) or
                                (not same_entity and not (left.dependencies & right.dependencies and left.error_families & right.error_families))):
                return self._pair_result(left, right, "UNKNOWN", shared_strong,
                    self._evidence_for_shared(left, right, shared_strong),
                    [{"kind": "identifier_requires_compatible_event_time_and_dependency"}],
                    "Entity or trace identity requires compatible event time and supporting dependency/error evidence.")
            if not left.evidence_complete or not right.evidence_complete:
                contradictions.append({"kind": "incomplete_evidence"})
                return self._pair_result(
                    left,
                    right,
                    "UNKNOWN",
                    shared_strong,
                    self._evidence_for_shared(left, right, shared_strong),
                    contradictions,
                    "A strong identifier matches, but supporting source evidence is incomplete.",
                )
            if "UNKNOWN_EXCEPTION" in left.categories or "UNKNOWN_EXCEPTION" in right.categories:
                contradictions.append({"kind": "unsupported_classification"})
                return self._pair_result(
                    left,
                    right,
                    "UNKNOWN",
                    shared_strong,
                    self._evidence_for_shared(left, right, shared_strong),
                    contradictions,
                    "The cases share an identifier, but at least one classification is unsupported.",
                )
            return self._pair_result(
                left,
                right,
                "STRONG",
                shared_strong,
                self._evidence_for_shared(left, right, shared_strong),
                self._unresolved_conflicts(left) + self._unresolved_conflicts(right),
                "Cases share an exact observed incident, entity, or correlation identifier.",
            )

        shared_weak = sorted(left.weak_features & right.weak_features)
        if shared_weak and self._within_window(left, right, event_time_window):
            if left.incident_identifiers and right.incident_identifiers:
                contradictions.append(
                    {
                        "kind": "similar_features_but_distinct_incident_identifiers",
                        "left": sorted(left.incident_identifiers),
                        "right": sorted(right.incident_identifiers),
                    }
                )
                return self._pair_result(
                    left,
                    right,
                    "REJECTED",
                    [],
                    [],
                    contradictions,
                    "Service/error similarity and time proximity conflict with distinct source incident identifiers.",
                )
            return self._pair_result(
                left,
                right,
                "UNKNOWN",
                [{"feature_type": key.split(":", 1)[0], "value": key.split(":", 1)[1], "strength": "WEAK"} for key in shared_weak],
                self._evidence_for_weak(left, right, shared_weak),
                [{"kind": "weak_similarity_is_not_shared_cause_evidence"}],
                "Service, error-family, or category similarity within the time window is insufficient to establish a common incident.",
            )
        return self._pair_result(left, right, "UNRELATED", [], [], [], "No compatible correlation rule matched.")

    @staticmethod
    def _pair_result(
        left: CaseCorrelationFeatures,
        right: CaseCorrelationFeatures,
        outcome: str,
        shared_features: list[dict[str, str]],
        evidence_references: list[dict[str, Any]],
        contradictions: list[dict[str, Any]],
        explanation: str,
    ) -> dict[str, Any]:
        return {
            "case_ids": sorted([left.case_id, right.case_id]),
            "outcome": outcome,
            "shared_features": shared_features,
            "evidence_references": evidence_references,
            "contradictions": contradictions,
            "explanation": explanation,
        }

    @staticmethod
    def _within_window(
        left: CaseCorrelationFeatures, right: CaseCorrelationFeatures, window: timedelta
    ) -> bool:
        if left.time_start is None or right.time_start is None:
            return False
        if left.time_end and right.time_start > left.time_end:
            gap = right.time_start - left.time_end
        elif right.time_end and left.time_start > right.time_end:
            gap = left.time_start - right.time_end
        else:
            gap = timedelta(0)
        return gap <= window

    @staticmethod
    def _evidence_for_shared(
        left: CaseCorrelationFeatures,
        right: CaseCorrelationFeatures,
        shared: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        references: dict[str, dict[str, Any]] = {}
        for feature in shared:
            token = f"{feature['feature_type']}:{feature['value']}"
            for case in (left, right):
                for reference in case.strong_evidence.get(token, []):
                    references.setdefault(reference["event_record_id"], reference)
        return list(references.values())

    @staticmethod
    def _evidence_for_weak(
        left: CaseCorrelationFeatures,
        right: CaseCorrelationFeatures,
        shared: list[str],
    ) -> list[dict[str, Any]]:
        by_id = {reference["event_record_id"]: reference for feature in (left, right) for reference in feature.evidence_references}
        return list(by_id.values())

    @staticmethod
    def _unresolved_conflicts(feature: CaseCorrelationFeatures) -> list[dict[str, Any]]:
        conflicts = []
        if "conflicting_evidence" in feature.uncertainty_flags or "CONFLICTING_RECORDS" in feature.categories:
            conflicts.append({"kind": "classification_conflict", "case_id": feature.case_id})
        return conflicts

    def _groups(
        self,
        edges: list[tuple[str, str, dict[str, Any]]],
        by_case: dict[str, CaseCorrelationFeatures],
    ) -> list[dict[str, Any]]:
        # A chain of different identifiers must not imply a common cause.
        token_edges: dict[str, list[tuple[str, str]]] = {}
        for left, right, result in edges:
            for feature in result["shared_features"]:
                token = f"{feature['feature_type']}:{feature['value']}"
                token_edges.setdefault(token, []).append((left, right))
        groups: list[dict[str, Any]] = []
        visited: set[str] = set()
        order = lambda token: (STRONG_IDENTIFIER_ORDER.index(token.split(":", 1)[0]), token)
        for chosen in sorted(token_edges, key=order):
            component = {case_id for pair in token_edges[chosen] for case_id in pair} - visited
            if len(component) < 2:
                continue
            known_identifiers = [by_case[case_id].incident_identifiers for case_id in component
                                 if by_case[case_id].incident_identifiers]
            if known_identifiers and not set.intersection(*known_identifiers):
                continue
            visited.update(component)
            feature_type, value = chosen.split(":", 1)
            references: dict[str, dict[str, Any]] = {}
            for case_id in component:
                for reference in by_case[case_id].strong_evidence.get(chosen, []):
                    references.setdefault(reference["event_record_id"], reference)
            shared = [{"feature_type": feature_type, "value": value, "strength": "STRONG"}]
            contradictions = [
                contradiction
                for case_id in sorted(component)
                for contradiction in self._unresolved_conflicts(by_case[case_id])
            ]
            groups.append(
                {
                    "case_ids": sorted(component),
                    "correlation_key": f"{feature_type}:{value}",
                    "shared_features": shared,
                    "evidence_references": list(references.values()),
                    "contradictions": contradictions,
                    "details": {
                        "systems": sorted({system for case_id in component for system in by_case[case_id].systems}),
                        "categories": sorted({category for case_id in component for category in by_case[case_id].categories}),
                        "time_start": min(by_case[case_id].time_start for case_id in component if by_case[case_id].time_start).isoformat(),
                        "time_end": max(by_case[case_id].time_end for case_id in component if by_case[case_id].time_end).isoformat(),
                    },
                }
            )
        return groups
