# Baseline audit — 10 October 2026

Scope: backend, evaluation, tests and documentation. All frontend files and assets are frozen. This is a synthetic prototype, not a production banking assessment.

## Source integrity

The supplied extracted directory was not a Git working tree. Recovered the supplied `ResolveOS-phase16.bundle` into a local `hardening` branch using fetch and mixed reset, without checking out or overwriting files. Baseline HEAD: `26871f7acd3c269401aca327fb2a013b9d35dc8e`. Recent history includes Phase 16 milestones and Phase 15 `8e6a977`. No remote push is authorized or claimed.

There is one pre-existing working-tree difference: `frontend/next-env.d.ts` imports development-generated Next types rather than production-generated types. It is preserved. `artifacts/frontend-baseline-hashes.json` records the 54 frontend source/config/asset files present before hardening, excluding dependency/build caches. The original Downloads ZIP and supplied bundle remain immutable references.

Read README, CURRENT_STATE, RECOVERY_HANDOFF, Phase 15/16 acceptance, the supplied technology guide (available without the `(1)` suffix), and the OCBC briefing found in Downloads/Telegram Desktop. Source extractions are recorded in artifacts. The technology guide predates Phase 15 acceptance; the recovered implementation/history takes precedence. Official PS2 calls for detection, evidence, investigation, controlled resolution/escalation and measurement of resolution time/manual steps. Official judging weights are absent.

## Environment and database

Python 3.13 is available via `py -3.13`; FastAPI, SQLAlchemy, Alembic, psycopg and pytest import successfully. Docker Desktop has an existing PostgreSQL container on port 5433, separate from an unrelated service on 5432. Only newly generated `resolveos_backend_verify_*` databases are used for destructive fixtures. No development reset, truncate, downgrade or migration is performed.

The 13 migrations have one head, `20261004_0013`. The existing verifier freshly applied the entire migration chain, downgraded the disposable database to `20261002_0006`, and upgraded to head successfully. This validates empty-database migration execution, not populated persistent-database downgrade safety. Full fresh test results will be appended when the running baseline suite finishes. Raw output: `artifacts/baseline-postgres.log`; JUnit: `artifacts/baseline-postgres.xml`.

Live inference remains disabled. No credentials are printed or reused. Offline providers establish contract/workflow behavior only. Requirements are lower-bounded, not a reproducible lock; an observed environment manifest is needed. Native ML remains optional and the existing dataset reports do not establish operational model readiness.

## Capability and gap register

Fresh baseline tests are pending in this initial assessment; historical 354-pass Phase 15 and 71-pass/283-skip Phase 16 reports are not counted as current evidence. Acceptance status must be read with the subsequent baseline-results appendix.

| Capability / implementation | Actual behavior and coverage | Weakness / impact | Severity; action; effort; acceptance |
|---|---|---|---|
| Ingestion: app/ingestion; Phase 2/3 tests | Validated envelopes, per-source event uniqueness, detection keys, persisted evidence | Duplicate identity with different content silently treated as retry; concurrent receipt increments use read/modify/write | P1; reject conflicting replays and atomically count exact retries; small; real concurrent replay tests |
| Lifecycle: app/domain/case_service.py, orchestration/service.py; lifecycle/Phase 6 tests | Explicit allowed transitions, terminal states, attributed transition audit | Application state machine is present; no justified replacement | Preserve; enumerate matrix and rerun regressions |
| Queue: app/orchestration; Phase 6 tests | SKIP LOCKED claims, PostgreSQL clock, leases, ownership tokens, retries, dead letter, review | Strong pre-existing real concurrent connection/process tests; production failover not established | P0 fresh tests; preserve queue; no second engine |
| Specialists: app/investigation; Phase 7 tests | Scoped sanitized observation snapshots, bounded tools, output schemas, source recheck, advisory findings | Field predicate validator ignores cited records missing that field: reproduced SUPPORTED for mixed complete/incomplete citations | P1; preserve contradiction distinction and require complete predicate citations; small; adversarial unit plus Supervisor regressions |
| Supervisor: app/supervisor; Phase 8 tests | Cross-checks sources, stale results, contradictions, capped targeted review, no authority | Source `.get(field)` conflates absent field with observed null | P1; use explicit field-presence predicate; small; grounding regressions |
| Controls: app/controls; Phase 9 tests | Action/policy/source fingerprint, action-specific approval, current-state recheck | Enterprise auth/tenancy absent by design; not solved by dev tokens | Preserve local controls; blocked production readiness; fresh stale/revocation tests |
| Execution: app/execution; Phase 10 tests | Confirmation-only effect, unique logical key, fenced atomic transaction, independent source verification | Narrow action coverage; additional monetary remediation unsafe/unjustified | Preserve action allowlist; evaluate coverage before expansion |
| Memory: app/memory; Phase 11 tests | Reviewed verified history, versioning, permissions, integrity, stale-policy labels, 50 candidate/10 result/byte caps | Current-time retrieval can admit memories reviewed after an investigation snapshot; overlap+recency can favor stale guidance | P1; explicit snapshot cutoff, measured Option B experiment; medium; temporal and ranking safety tests |
| ML: app/ml; Phase 12 tests | Offline feature/dataset/governance evaluation | Dataset inadequacy; no trained operational model | Preserve deterministic routing; no false accuracy claims |
| Intelligence: app/intelligence; Phase 13 tests | Bounded cohorts, explicit missing durations/truncation, references | No fair A/B/C operational study or human timing study | P0; runnable measured backend cohort plus clearly modelled human baseline; medium |
| Shadow/replay: app/reliability; Phase 14 tests | Non-executable shadow reports, replay with historical reconstruction limits | Present policies cannot always be reconstructed as history | Preserve limitation; fresh regression |
| Workbench APIs: app/workbench; Phase 15 tests | Protected case, evidence, approval, memory, lab reads | Full browser-to-PostgreSQL acceptance outstanding and frontend frozen | Read-only/API contract regression; no UI changes |
| Headless demonstration: app/demo.py | Three real persisted journeys and worker services | Existing CLI writes fixed Phase 15 report/env, limited scenario selection and record export | P0; separate disposable CLI using existing services, expanded evidence export; medium |
| AI/business/cost evaluation | Existing offline ML and shadow reports | No live model accuracy, human study, rigorous ablations or cost per verified resolution | P0/P1; offline evaluations first; live/human claims blocked; no invented benefits |
| Delivery | Source bundle and historical XML supplied | No fresh hardening handoff/archive | P1; source/artifact package with secret/cache exclusions and integrity manifest |

## Baseline acceptance criteria

Never proceed beyond a failed critical safety invariant. Fresh database tests must establish no unauthorized/duplicate effects, no stale-worker commits, no false closure, action-specific approvals and independent verification. New changes must preserve API fields, migration history, reviewed memory and frontend hashes. Benchmarks must retain failure/censoring, expose denominators and label offline/modelled results. The final gap register must distinguish verified, deferred and blocked work; 95/100 is a target, not an entitlement.

## Fresh baseline result

The original full-suite process, started before source edits and collecting/importing the original modules, completed with **354 passed, 0 failed, 0 skipped in 549.08 seconds**. Migration round trip passed. This is fresh baseline evidence, not the archived Phase 15 result. Subsequent smoke failure injection identified a critical gap absent from that suite: changing `SyntheticLedgerEntry.balance_after` after execution was not included in the verification snapshot, producing false closure. The original smoke result is retained as `artifacts/operational-smoke-balance-gap.json`; acceptance stopped until the control snapshot and independent verifier included balance. Relevant new/control/execution regressions then passed: 69 tests, zero failures/skips. Old authorizations now require reevaluation because their incomplete snapshot differs from the strengthened current snapshot; historical records are not rewritten.
