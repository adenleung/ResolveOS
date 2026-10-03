# Phase 14 — shadow, replay and reliability acceptance

**Accepted within the local synthetic prototype scope.** Final full PostgreSQL
regression: **350 passed, 0 failed/errors/skipped in 732.454s**. All 332 prior tests
remain passing. An earlier full run also passed 350 tests in 704.369s.
Targeted shadow/replay: **18 passed, 0 failed/errors/skipped in 32.291s**.
Existing controls/execution/simulation safety: **69 passed, 0 failed/errors/skipped
in 126.922s**. Each run applied fresh migrations and a disposable downgrade/re-upgrade.
Phase 13 checkpoint `ba0367d46260b9195b1506ebfb79a973ad98465b` was pushed and
verified on GitHub before Phase 14 began.

## Implementation and authority boundaries

`app/reliability` provides authenticated, bounded case shadow evaluation, shadow
history, comparison with actual independently established case outcomes, historical
decision replay and operational telemetry. WORKER and OPERATIONS_REVIEWER are
server-derived identities. Production development authentication remains refused.

Shadow calls the same deterministic calculation as operational controls, under a
PostgreSQL repeatable-read, READ ONLY transaction with a 5-second statement timeout.
Inspection acquires no row locks and creates no decision, authorization, approval,
action, simulation, verification or banking record. A separate transaction persists
only the isolated shadow observation. Its database constraint enforces SHADOW,
NOT_EVALUATED and execution_permitted=false. Fingerprints deduplicate concurrent
requests. Shadow identifiers cannot be consumed by operational authorization or
execution. Read-only Controls objects explicitly reject authorize/current/approve.
Default operational lock ordering and checks remain intact.

Comparison reports current case status, the latest verification reference and
whether a successful independent verification matches a VERIFIED operation/action
and RESOLVED case. It labels hypothetical shadow outcomes and whether verification
was later; it does not assert causation or automatically modify proposals.

Replay uses the maximum of occurrence, ingestion and case-link/retrieval times.
An independently retrieved earlier observation can establish availability before
a delayed detector link. Missing or mismatched event provenance is omitted.
Approvals are reconstructed from immutable history rather than current status.
Classification, specialist/Supervisor interpretation, deterministic controls,
policy version/hash, human history, hypothetical simulation, actual execution audit,
independent verification and incident membership changes remain distinct.
Mutable policy content cannot be reconstructed after in-place edits; that limitation
is explicit. Each record kind is capped at 500 with visible truncation. Later source
observations are separated from evidence available at the requested historical time.

Telemetry separates current global queue/shadow counts and retries beyond the first
attempt from bounded last-30-day measured durations, SLA exposure, escalations,
recurrences and verified outcomes. Optional ML is explicitly not operational.
No provider or offline ML result enters shadow controls or execution.

## Reproducibility and failure coverage

The 18 new PostgreSQL tests cover read-only enforcement, no operational/source
mutation, separate database constraints, unusable shadow IDs, freshness/inactive
policy/unsupported conclusion failures, concurrent idempotency, replay occurrence/
ingestion/link/retrieval cutoffs, unknown provenance, later approvals, hypothetical
versus independently verified execution, authenticated APIs, strict request fields,
case grants and unavailable optional ML.

Existing Phase 9–10 tests exercise duplicate delivery/execution, stale evidence,
revocation, policy changes, expired fences, concurrent execution, worker interruption,
failed/uncertain verification and explicit escalation. Full regression also retains
queue concurrency/dead-letter/recovery, unavailable providers and memory-isolation
tests. Tests use separately named disposable PostgreSQL databases, never development.
The synthetic fixture workflows in tests/test_phase6_postgres.py,
tests/test_phase9_postgres.py and tests/test_phase10_postgres.py are repeatable and
use the actual control/execution/verification engines. Phase 15 adds employee-facing
demonstration journeys after this checkpoint is remotely verified.

This verifies local PostgreSQL synthetic behavior, not production distributed
failover, real banking effects, tenant authentication or live-provider availability.
No paid model calls or monetary transfer execution occur.

## Migration and evidence

Additive `20261004_0013` creates only shadow_evaluations. Development migration is
guarded by passing reports, exact database/port/revision and cluster identity.
verify_phase14_development_migration.py creates a custom-format ignored backup,
restores it into a disposable database and checks every existing full-row hash.
It exercises a populated 0012 → 0013 → 0012 → 0013 round trip there before upgrading
development. No development downgrade, truncate or reset is performed.
The migration report records backup integrity and preserved existing table hashes.
Development is now at **20261004_0013**. Backup restoration and the populated
disposable round trip passed. All **43 existing application tables** retain identical
row counts and complete content hashes; the new shadow table is empty. The failed
fixture database was verified empty and removed. No existing test assertion was
weakened, no test skipped, and no development data reset.

Evidence files: phase14-targeted-results.xml, phase14-safety-results.xml,
phase14-final-full-regression-results.xml, phase14-development-migration-results.json.

Protected endpoints under /api/v1/reliability:

- POST/GET /cases/{id}/shadow
- GET /cases/{id}/shadow-comparison
- GET /cases/{id}/replay?as_of={timezone-aware timestamp}
- GET /telemetry

Phase 15 starts only after this accepted phase is committed, pushed and the remote
SHA is verified.
