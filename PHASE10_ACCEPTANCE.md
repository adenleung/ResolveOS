# Phase 10 acceptance checkpoint — 2026-10-04

## Accepted counterfactual extension at 0011

| Run | Result |
| --- | --- |
| Supplied Phase 10 PostgreSQL suite | 27 passed, 36.65s |
| Final targeted Phase 10 PostgreSQL suite | 29 passed, 38.64s |
| Final complete regression on PostgreSQL | 222 passed, 264.64s |

Final reports: `phase10-test-results.xml` and `backend-test-results.xml`.
Both have zero failures, errors and skips; no warnings were reported. The full
suite includes 16 offline projection unit tests. Two integration tests were
added to exercise changed policy after simulation-bound submission and concurrent
execution of the same fenced task: one effect commits and the other worker is
fenced. No production-code repair was necessary and existing assertions remain.

Coverage includes stale source evidence, revoked action approval, policy changes,
duplicate submissions/effects, concurrent claims/execution/reconciliation, failed
observed verification, precommit rollback, expired leases and worker recovery.
The complete suite also checks separate local worker processes. Preview persists
only a hypothetical report and audit; it neither creates action permission nor
writes banking tables. Submit and execution retain `Controls.current`; execution
regenerates the projection before effects. A separate fenced verification task
rereads source monetary state, confirmation identity and normalized processing.
Only actual verified success resolves the case.

Migration 0011 follows 0010 directly, references existing cases/authorizations/
operations, constrains report outcome and allows one report per bound operation.
It adds no banking columns or data transformations. Each final verifier applied
0001–0011 on a fresh disposable database, downgraded to 0006 (including dropping
0011) and re-upgraded to 0011 before tests. Successful disposable databases were
removed. These are empty-schema round trips, not preservation of dropped reports.

After acceptance, development `resolveos` was confirmed at 0010 and backed up
using PostgreSQL custom-format `pg_dump` to local ignored `resolveos-pre-0011.dump`.
Only 0011 was applied. All 37 existing application tables have identical row
counts and full-row SHA-256 hashes before/after; the new report table is empty.
See `phase10-counterfactual-migration-results.json` and the guarded
`apply_phase10_checkpoint.py` script. Development was never truncated or downgraded.

Limits: only deterministic synthetic confirmation replay is supported. Simulation
reports have application integrity checks, not database immutability against
privileged writers. Downgrade deletes reports; re-upgraded queued operations with
missing reports fail closed and require review. No real banking integration,
production identity/tenancy, multi-host failover or enterprise-scale performance
acceptance is claimed. No paid LLM calls occurred. Phase 11 remains unstarted.

## Historical original 0010 acceptance

Acceptance passed for the existing synthetic confirmation-only scope. This pass
stops after Phase 10. No counterfactual simulation, memory, ML or frontend work
was added.

## Failure causes and repairs

- Phase 10 imported the Phase 6 session fixture, which committed cleanup of only
  queue/review tables. Execution tests committed actions, banking rows, events,
  exceptions and authorizations through independent worker connections. Those
  records survived test boundaries; a rollback of the fixture session could not
  remove committed changes made by other connections.
- Phase 3's global exception/category assertion and Phase 4's normal-case zero
  exception assertion encountered those unrelated records. Phase 7's provenance,
  Phase 8's advisory-only and Phase 9's no-execution assertions encountered 12
  actions left by earlier Phase 10 tests.
- Phase 5's global ActionRecord.one() failed with multiple records. Its subsequent
  cleanup never ran, leaving its own action linked to a detected case. Four later
  fixture setups then attempted to delete that case and hit actions_case_id_fkey.
- tests/conftest.py now provides committed setup/finally teardown of all public
  application tables in one FK-respecting TRUNCATE statement, without CASCADE.
  Alembic metadata is retained. A verifier-created database name, ownership marker
  and actual connection database must match. Other PostgreSQL targets are refused;
  lock timeout exposes leaked worker transactions instead of suppressing errors.
  Test bodies retain all original assertions and constraints.
- verify_backend.py sets the ownership marker and supports ordered file selection
  and separate JUnit report paths. Tests use disposable databases, never reset
  the development database, and keep live inference disabled.
- The shared synthetic authorization fixture now uses PostgreSQL time for its
  generated observation timestamps. Positive setup assertions report actual
  control rejection reasons. One intermediate expanded run had 11 passes and
  10 authorization-setup failures; the underlying rejection reasons were not
  captured in that run. They did not reproduce on the next run. Clock alignment
  removes the host/database clock dependency, but is not claimed as a proven
  diagnosis of that intermediate failure. Final validations below all passed.

## Terminal execution lifecycle

Previously, queue failure only changed WorkTask; the operation/action could stay
QUEUED or VERIFYING indefinitely. ExecutionEngine.reconcile_terminal now handles
bound dead letters with case/correlation/task/operation lock order. It refreshes
and rechecks terminal status and authorization/action binding under locks.

- Execution failure before the local atomic effect: FAILED_EXECUTION.
- Failure after an effect while verification remains unfinished:
  VERIFICATION_UNCERTAIN; no successful VerificationResult is invented.
- Both outcomes escalate the case, request explicit human review and atomically
  persist operation/action state, task history and audit. Failed independent
  verification likewise requests review and never resolves the case.
- Worker and protected failure API reconcile after committing the task failure.
  Maintenance retries the durable handoff after interruptions. This brief
  eventual handoff avoids holding task locks while acquiring case locks.
- Original lease fencing, authorization freshness, human approval checks,
  logical-effect idempotency and separate verification remain in place.

Tests cover exhausted errors, expired worker leases, elapsed deadlines in both
stages, rollback during reconciliation, concurrent reconciliation, revoked
authorization, precommit crash rollback, stale completion, duplicate execution,
corrupted independent verification and replacement-worker recovery.

## Actual validation

| Run | Result |
| --- | --- |
| Final targeted Phase 10 | 21 passed, 30.51s |
| Earlier isolation run: Phase 10 → 3 → 4 → 5, before final expansion | 75 passed, 89.02s |
| Final reverse order: Phase 5 → 4 → 3 → 10 | 78 passed, 103.15s |
| Final full PostgreSQL suite, Phase 10 collected before Phases 3–5 | 198 passed, 255.27s |

Final runs had no failures, setup errors or skips; no warnings were reported.
Inspect phase10-test-results.xml, phase10-isolation-first-results.xml,
phase10-isolation-last-results.xml and backend-test-results.xml. The earlier
75-test report contains the earlier 18-test Phase 10 suite; the final suite has
21 Phase 10 tests and preserves all 177 preceding regression tests.

Each verifier run applied fresh migrations 0001–0010, downgraded to 0006 and
re-upgraded successfully before testing. Development upgrade first verified
revision 0009 and absence of execution_operations, then applied only 0010.
All 36 existing application table row counts were preserved, including 22 cases
and zero actions. New execution_operations is empty. Alembic head and development
revision are both 20261002_0010; phase10-migration-results.json records the check.

## Limits and checkpoint

Only synthetic confirmation replay is supported. Payment and ledger monetary
state cannot be mutated. No remote banking effects, paid model calls, live AI
verification, enterprise identity, multi-host recovery or production scalability
are claimed. Terminal escalation is a human handoff, not automatic permission to
reopen or execute another action. Maintenance/worker execution must be explicitly
operated to recover an interrupted failure handoff. Failed-run disposable
databases retained by the verifier remain diagnostic resources.

Git was not found and this directory has no .git repository. Source, documentation
and test reports provide the checkpoint; no commit was created. Phases 11–14
remain outside this completed repair pass.
