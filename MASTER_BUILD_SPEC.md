# ResolveOS Master Build Spec Summary

ResolveOS is a modular-monolith operations platform implementing Phases 1–14, preserving PostgreSQL as its system of record. Phase 12 has no operational ML model. Phase 13 adds evidence-backed read-only intelligence; Phase 14 adds isolated shadow controls, historical replay and telemetry. Exact validation and development migration status are in CURRENT_STATE.md and PHASE14_ACCEPTANCE.md. Phase 15 proceeds only after the Phase 14 remote checkpoint; Phase 16 remains optional future scope.

## Implemented scope

- Phase 14: PostgreSQL-enforced read-only shadow inspection, constrained isolated
  observations, comparison with actual verification, historical replay and measured
  telemetry. No shadow, advisory or ML component gains operational authority.

- Phase 13: bounded, protected, evidence-backed operational intelligence and
  prevention hypotheses using existing PostgreSQL history. No operational writes,
  automatic policy changes, new schema or causation claims. See PHASE13_ACCEPTANCE.md.

- Phase 11: independently verified case memory, human publication and governed
  correction/revocation/supersession, bounded PostgreSQL retrieval and optional
  Risk-investigator context. Historical knowledge cannot replace current evidence
  or authorize remediation; relevant policy changes mark old guidance outdated.
  See PHASE11_CONTRACTS.md for lifecycle, data model and access boundaries.

- Phase 7: read-only specialist investigations, configurable live-disabled OpenAI integration, real evidence validation, bounded durable execution and protected findings APIs.
- Phase 8: independent Supervisor source validation, disagreement detection, bounded targeted follow-up, durable recommendations/history and protected APIs. No authorization or execution.

- Phase 1: FastAPI startup, validated settings, SQLAlchemy models, Alembic migrations, deterministic case lifecycle, and audit records.
- Phase 2: reproducible synthetic banking payments, ledger entries, confirmations, API logs, workflow state, policies, and versioned simulator APIs.
- Phase 3: versioned event envelopes, explicit source adapters, durable/idempotent event ingestion, deterministic event-time detectors, exception/case creation, evidence history, and versioned ingestion/detection APIs.
- Phase 4: versioned deterministic classification, explainable synthetic priorities and SLAs, specialist routing, append-only assessment/audit history, and versioned case-assessment APIs.
- Phase 5: deterministic observed-evidence incident correlation, lifecycle and historical membership, safe split/merge, PostgreSQL idempotency and versioned incident APIs. Shared investigation never authorizes a banking action.
- Phase 6: PostgreSQL durable orchestration, fenced leasing, routing, retries/recovery, SLA monitoring, workflow review and protected APIs. Future capabilities remain scheduling contracts only.

## Phase 3 boundaries

- Runtime detection consumes normalized observed records only. It does not use simulator scenario labels or the test-only ground-truth mapping.
- Duplicate delivery is deduplicated by `(source_system, event_id)` and is not treated as a duplicate-payment incident.
- PostgreSQL unique indexes protect event and detection identities across repeated or concurrent execution.
- There is no message broker, scheduler, frontend, AI investigator, autonomous remediation, incident clustering, or trained ML model in this phase.
- The synthetic environment has no document-status source table, so a document adapter is not currently supported.
- Priority weights and SLA durations are synthetic configuration examples, not OCBC operational-risk policy.

Later ML experiments can implement the `Classifier` contract documented in [ARCHITECTURE.md](ARCHITECTURE.md); classifications remain advisory and cannot authorize actions.

## Phase 10 counterfactual extension (0011 accepted)

A deterministic, confirmation-only simulation predicts the append-only synthetic confirmation and unchanged monetary state before execution. Previews can be viewed before a separate human action approval, never bypass it. An operation-bound prediction is checked for freshness during fenced execution; independent verification still decides whether the action worked. Revision 0011 passed PostgreSQL acceptance with 29 targeted and 222 full regression tests; see PHASE10_COUNTERFACTUAL_EXTENSION.md.
