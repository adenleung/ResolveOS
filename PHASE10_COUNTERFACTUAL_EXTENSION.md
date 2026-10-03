# Phase 10 counterfactual extension — implementation handoff

## Current acceptance — 2026-10-04

**Accepted on PostgreSQL; source and development revision 20261002_0011.**
Final targeted: **29 passed in 38.64s**. Full regression: **222 passed in
264.64s**. Zero failures/errors/skips; no warnings reported. The supplied
27-test Phase 10 suite first passed in 36.65s; two checks were then added for
post-submission policy changes and concurrent execution of a simulation-bound
task. No runtime fixes or weakened assertions were necessary.

Fresh 0001–0011 upgrade, downgrade to 0006 and re-upgrade passed in both final
verifier runs. Development upgrade followed acceptance and a PostgreSQL backup;
all 37 existing application tables retained identical row counts and row hashes.
Reports: `phase10-test-results.xml`, `backend-test-results.xml`,
`phase10-counterfactual-migration-results.json`. See `PHASE10_ACCEPTANCE.md`.
No paid LLM calls. Phase 11 remains unstarted.

## Scope implemented in this ZIP

- Added deterministic, bounded, **hypothetical-only** `REPLAY_CONFIRMATION` projection in `app/execution/simulation.py`. It uses only the explicit bank/evidence fields already captured by `Controls`, never simulator hidden scenario/root-cause labels. It predicts appending **one synthetic confirmation**, no new payment or ledger entry, and expected normalized event processing. It does **not** mutate banking tables or call an LLM.
- `ExecutionEngine.preview` uses `Controls.current(..., require_approval=False)` to validate current evidence, policy and Supervisor recommendation. It persists an auditable counterfactual **without bypassing subsequent human approval**. API: `POST /api/v1/authorizations/{authorization_id}/simulate` (development `WORKER` identity) and bounded `GET /api/v1/cases/{case_id}/simulations`.
- At `ExecutionEngine.submit`, a fresh operation-bound projection is persisted atomically with action, queue task and audit. Only a PASS projection proceeds. Repeated submissions reuse the existing operation/projection.
- At execution, `Controls.current(...)` still rechecks authorization, active policy, case/source evidence and human approval, then the worker checks a fenced operation-bound simulation against a newly generated projection. A missing, blocked, altered or stale projection fails closed **before any synthetic confirmation write**.
- Independent verification rereads source payment, ledger, synthetic confirmation and normalized event state. It additionally compares observed effects with the stored prediction. Differences escalate for human review. A prediction never substitutes for observed verification.
- Added Alembic `20261002_0011` to persist linked simulation reports, and integration tests in `tests/test_phase10_postgres.py` for preview vs approval, durable reporting, idempotence, stale evidence, projection tampering, post-execution divergence and revoked human approval.

## Historical ZIP-authoring validation (superseded by PostgreSQL acceptance above)

- **20 passed** in the offline focused unit/foundation test selection, including **14 counterfactual unit tests** (`tests/test_phase10_simulation_unit.py`).
- Python AST/syntax parsing passed for app and tests.
- Migration 0011 schema creation and downgrade passed using an in-memory **SQLite DDL smoke test**. That does NOT validate the PostgreSQL migration chain.
- **PostgreSQL regression, new PostgreSQL integration tests, migration application to development, and live OpenAI testing were NOT run here.** This execution environment has no PostgreSQL server or `psycopg` Python driver. The previous 198-passing-test report is a **historical Phase 10 baseline only**, not an acceptance claim for this extension.
- The original user's `.env`, `.db`, cached results and test database marker are excluded from the deliverable ZIP. No database or secret has been modified on the user's machine.

## Original validation checklist (completed by the acceptance above)

1. Back up the development database and project before schema changes. Check the existing revision is `20261002_0010`.
2. Apply Alembic `upgrade head` to reach `20261002_0011`, preserving existing data. Never use the disposable-test database cleaner on a development/production database.
3. Run `python verify_backend.py --targeted --phase 10` for Phase 10 (including six new PostgreSQL tests) on a verifier-owned disposable database. Run `python verify_backend.py` for the full regression and migration round-trip.
4. Exercise preview -> human approval -> submit -> execution -> independent verification and stale/blocked flows. Confirm no monetary changes and verify audit/provenance links.
5. Investigate any regression or migration failure before promoting the extension checkpoint. This checklist is now completed; `CURRENT_STATE.md` records accepted revision 0011.

## Boundaries and known limits

Only the existing synthetic confirmation replay supports counterfactuals. This is a deterministic transition forecast, **not** a causal guarantee, an autonomous permission grant, a money-transfer simulation, or a realistic multi-system production simulator. A counterfactual can be previewed for an otherwise valid but not-yet-approved action; actual remediation still requires action-specific approval where configured. Current API auth is development-grade and production multi-tenancy is not established.

Reports are protected by application checks rather than database immutability
against privileged writers. Downgrading 0011 drops simulation reports; a
re-upgraded queued operation lacking its projection fails closed and needs review.
Migration round trips were verified on disposable empty schemas; no production
rollback, multi-host recovery or production scalability claim is made.
