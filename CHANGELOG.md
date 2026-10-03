# Changelog

## 0.13.0 - 2026-10-04

- Recovered and freshly verified the complete Phase 12 checkpoint; newer reported
  commits and frontend source were unavailable.
- Added protected, typed, bounded read-only recurring-exception, bottleneck,
  hypothesis, prevention and incident-relationship analytics over actual evidence.
- Added 21 PostgreSQL tests; no operational schema, source writes, model authority
  or existing safety assertions changed. See PHASE13_ACCEPTANCE.md.

## 0.12.0 - 2026-10-04

- Added read-only actual-data readiness audit, strict point-in-time numeric feature
  schema and historical PostgreSQL evidence snapshot extraction.
- Added reviewed synthetic dataset contracts, incident/scenario-aware fixed-seed
  splits, optional CPU model comparison framework and experimental registration.
- Recorded inadequate data for all five use cases; retained deterministic rules.
  No model or inference adapter enabled; no schema or authorization-chain changes.
- Added safety, feature, split, compatibility and unavailable-library regression
  tests and dataset/comparison/governance/acceptance reports.
- Optional native estimator validation blocked by Windows Application Control;
  trained-model path remains unverified. See PHASE12_ACCEPTANCE.md.
- Accepted dataset-inadequate branch: 311 full PostgreSQL tests in 755.460s,
  43 targeted in 79.366s; all prior 268 tests retained, no failures/errors/skips.

## 0.11.0 - 2026-10-04

- Implemented reviewed operational memory with explicit publication, rejection,
  withdrawal/revocation/flagging, immutable corrections and atomic supersession.
- Added PostgreSQL migration `20261004_0012`, source/evidence/verification/policy
  references, review content hashes, lifecycle constraints, active-version
  uniqueness, retrieval index and audit provenance.
- Replaced Risk's memory placeholder with bounded, deterministic, optional
  historical retrieval. Historical IDs cannot become current evidence or action
  authorization; failed retrieval preserves investigation. Specialist prompt 1.1.
- Revalidate source trust and publication integrity on retrieval. Retain facts
  under relevant policy changes while explicitly marking old guidance outdated.
- Added protected development APIs and trusted server case/source access grants;
  production requires an explicit access adapter. No ML training, paid inference,
  frontend or real banking integrations.
- Phase 11 targeted: 46 passed in 160.08s. Existing Phase 9–10 safety: 69 passed
  in 180.25s. Full PostgreSQL regression: 268 passed in 666.32s; no failures,
  errors, skips or warnings in the final runs. Original Phase 10 reports preserved.
- Fresh and populated migration round trips and reflected constraints/indexes
  passed. Development upgraded 0011 -> 0012 after a checked custom-format recovery
  backup; row counts/content hashes preserved in all 38 existing tables. Five new
  memory tables are empty. PHASE11_ACCEPTANCE.md records exact results and limits.
- Git unavailable; no commit. Stop after Phase 11; Phase 12 remains unstarted.

## 0.10.0 - 2026-10-04

- Accepted durable synthetic confirmation replay and independent verification.
  No monetary transfer or ledger write is permitted; deterministic authorization,
  explicit human approval, freshness, logical idempotency and leases remain enforced.
- Repaired PostgreSQL fixture contamination with guarded per-test committed
  cleanup in verifier-owned disposable databases. Preserved all assertions and
  FK constraints; aligned synthetic control fixture timestamps to PostgreSQL.
- Added terminal execution/verification failure reconciliation, durable action
  states, human escalation/review and audit, including interrupted recovery and
  concurrent reconciliation tests. Failed verification also requests human review.
- Final Phase 10: 21 passed in 30.51s. Reverse-order isolation: 78 passed in
  103.15s. Full PostgreSQL regression: 198 passed in 255.27s; no failures/errors/skips.
- Fresh 0001-0010 migration and downgrade to 0006/re-upgrade passed. Development
  upgraded from 0009 to 0010 with row counts preserved in 36 existing tables.
- Corrected current checkpoints and roadmap; PHASE10_ACCEPTANCE.md records
  intermediate failures and practical limits. Git unavailable; no commit.
  No live model calls, counterfactual simulation or Phase 11 continuation.

## 0.9.0 - 2026-10-02

- Added deterministic, action-bound synthetic controls and policy/source/review
  validation. AI recommendations and workflow approvals cannot authorize actions.
- Added migration 0009, immutable authorization decisions, separate human action
  approval/history, expiration/revocation and current-source/policy revalidation.
- Added protected controls/authorization/approval APIs. No banking data mutation.
- Verified 24 targeted PostgreSQL tests in 17.53s and full regression:
  177 passed in 242.78s, no warnings/skips/failures. Fresh 0001-0009 chain and
  downgrade/upgrade passed. Development revision 20261002_0009.
- Git remains unavailable; no commit claimed. No live model calls. Phase 10 next.

## 0.8.0 - 2026-10-02

- Added independent Supervisor source/evidence validation, stale-assessment and
  superseded-source checks, disagreement detection and structured model reviews.
- Added bounded targeted reinvestigation preserving unaffected specialist
  results; fixed polling to preserve targeted consumer replacements. Unresolved
  review cycles escalate. Recommendations cannot authorize or execute actions.
- Added durable Supervisor review provenance in migration `20261002_0008`,
  protected history API and existing-worker integration. Reused the configurable
  provider interface; fake Supervisor tests need no credentials.
- Verified 11 targeted tests in 34.14s and complete PostgreSQL regression:
  **153 passed in 275.05s**, no warnings/skips/failures. Fresh 0001-0008 chain,
  downgrade to 0006 and upgrade passed; development database is at 0008.
- Documented exact Phase 9 controls handoff. Phases 9-14 remain unimplemented.
  No live inference, ML training, remediation or frontend; no Git available.

## 0.7.0 - 2026-10-02

- Added Transaction, Technology and Risk investigators, role-specific Pydantic
  tools over real normalized observations, bounded model loops and immutable
  as-of evidence snapshots. Unavailable source capabilities are explicit.
- Added live-disabled configurable OpenAI Responses adapter; deterministic model
  and mocked transport tests require no credentials. No live calls performed.
- Added migration `20261002_0007`, unique durable task attempts, fenced source
  validation and atomic evidence/findings/result/audit acceptance. Reused the
  Phase 6 worker and queue; preserved unavailable-handler completion guards.
- Added protected findings/history/evidence/statistics APIs and Phase 8 contracts.
- Verified full PostgreSQL regression: 142 passed in 234.45s; final targeted
  tests: 28 passed in 52.60s. No failures, warnings or skips. Fresh migration
  chain and downgrade/upgrade passed; development database upgraded to 0007.
- No action authorization or remediation. Git unavailable; no commit created.

## 0.6.0 - 2026-10-02

- Added migration `20261002_0006` for durable tasks/consumers/history, workflow reviews/history, case generations, queued states and queue/SLA indexes.
- Added PostgreSQL `SKIP LOCKED` claims, server-clock leases, fencing, retries/backoff, deadline expiry, dead-letter/requeue and restart recovery.
- Reused classification in atomic worker transactions; added specialist routing, incident sharing and split/merge reconciliation, SLA review/escalation, operational statistics and a local worker CLI.
- Added permission-checked review assignment and workflow approve/reject/reinvestigation, current-evidence checks, history/audit and protected versioned APIs. Disabled-by-default development identity refuses production use; invalid settings no longer silently become development configuration.
- Preserved earlier transitions and kept approval distinct from action authorization. Future investigator/supervisor/execution/verification handlers remain unavailable.
- Verified all 114 Phase 1-6 PostgreSQL tests without warnings/skips, fresh migration chain and `0006` downgrade/upgrade. Independent sessions and separate local worker processes tested concurrency; multi-host correctness remains unverified.
- Measured 250-case/task queue: 20 claims in 0.2181s, 26 SQL statements, actual poll plan used `ix_tasks_ready_priority`. No enterprise-scale claim.
- Documented exact Phase 7 contracts. Stopped after Phase 6.

## 0.5.0 - 2026-10-02

- Completed existing deterministic incident correlation with versioned observed features, explicit identifiers, event-time compatibility, unknown/rejected outcomes, and supporting evidence.
- Removed scenario-derived simulator incident keys from runtime correlation and payment ingestion; added explicitly observed API incident/dependency identifiers.
- Added lifecycle operations, safe membership edits, split/merge history, source-backed summaries and versioned incident APIs using configured limits.
- Protected stable incident identity and active membership with PostgreSQL constraints, transaction advisory/row locks, and conservative handling of truncated searches.
- Preserved original detection times, manual exclusions, historical associations and case-specific authorization; refreshed evidence adds history without recreating incidents.
- Verified migration `20261002_0005`, fresh migration chain and downgrade/upgrade; expanded PostgreSQL regression and synthetic query inspection. See CURRENT_STATE.md for executed results and limitations.
- Documented the strategy interface and Phase 6 boundaries; stopped after Phase 5.

## 0.4.0 - 2026-10-02

### Added

- Versioned deterministic classification for supported exception families, multiple applicable categories, evidence references, uncertainty flags, explanations, and unknown conditions.
- Configurable synthetic priority scoring with stored rule versions and input facts, priority-based SLA deadlines, remaining time, overdue status, and stable SLA start timestamps.
- Deterministic multi-specialist routing with explicit human-triage fallback and duplicate monetary-effect distinction.
- Append-only assessment history, priority/SLA/routing revisions, and audit records for material changes only.
- Versioned classification/re-evaluation, assessment history, case priority/SLA, and routing APIs.
- PostgreSQL integration tests for supported/unknown/ambiguous classifications, late evidence, priority/SLA boundaries and changes, routing, idempotency, evidence provenance, and concurrent assessment.

### Changed

- Added migration `20261002_0004` for case SLA fields and unique assessment revisions.
- Documented the `Classifier` protocol for later advisory ML experiments; no models are trained in this phase.

## 0.3.0 - 2026-10-02

### Added

- Versioned normalized event contract and explicit adapters for synthetic payments, ledger entries, confirmations, API logs, and workflows.
- Durable event storage with UTC event/ingestion timestamps, schema validation, exact delivery deduplication, processing state, and persisted ingestion errors.
- Deterministic event-time exception detection for confirmation gaps, reconciliation mismatches, conflicting source states, API failures/timeouts, replayed confirmation events, and overdue workflows.
- Stable PostgreSQL detection uniqueness, operational case creation, source-event evidence links, append-only detection history, and audit entries for initial detections and later evidence.
- Versioned ingestion, detection, exception, evidence, and statistics APIs.
- PostgreSQL integration coverage for replay, delay, late events, source mismatches, invalid records, transaction failure, interruption, concurrency, and runtime label isolation.
- Phase 4 adapter and worker integration contracts in the architecture documentation.

### Changed

- The synthetic reconciliation mismatch now contains a real amount discrepancy in the ledger record.
- Starlette TestClient now uses its supported `httpx2` transport instead of deprecated `httpx`.

## 0.1.0 - 2026-10-02

### Added

- FastAPI application shell with health and readiness endpoints
- environment-driven settings validation
- structured logging configuration
- SQLAlchemy database manager and base model setup
- initial core domain schema for cases, incidents, evidence, decisions, actions, approvals, verification, policy, and audit records
- deterministic case lifecycle service and transition enforcement
- Alembic migration scaffolding for the Phase 1 schema
- Docker Compose for local PostgreSQL
- initial Pytest coverage for config, lifecycle, database, and audit behaviors
- project documentation for the Phase 1 implementation

### Deferred

- synthetic banking environment
- AI orchestration and specialist investigators
- ML governance and analytics features
- dashboard UX
