# Execution and verification contract

Phase 10 acceptance passed on 2026-10-04: 198 PostgreSQL tests, migration
20261002_0010 applied to development. See PHASE10_ACCEPTANCE.md for actual results,
terminal-failure states, recovery semantics and limitations. The contract below
defines the original confirmation-only scope implemented by app/execution.

Phase 9 `Controls.evaluate` records action-specific authorization; it never
executes. `Controls.current(authorization_id)` locks case, correlation context,
authorization, applicable policy, synthetic payment/ledger/confirmation rows
and, where needed, human approval. It revalidates source observations, current
Supervisor recommendation, case state, policy hash, evidence fingerprint,
expiry and action-specific approval. Call it within the execution transaction,
as trusted `WORKER`; commit no intermediate preflight effects.

Initial operation: `REPLAY_CONFIRMATION`. ActionRequest binds synthetic
payment ID and stable idempotency key. Monetary transfers and ledger writes
are not permitted. Payment must already be SETTLED, one matching POSTED debit
must exist in source and normalized evidence, no confirmed/uncertain source
confirmation may exist, and policy/duplicate/blast-radius checks must pass.

Implement durable action scheduling/execution using the existing worker,
TaskPayload versions, leases and fencing. Link action to the exact authorization
and approval IDs. Lock case before task, and coordinate lock order with controls
and incident correlation. Do not mark PREPARE_EXECUTION successful until this
real implementation exists. Use stable logical keys protected by PostgreSQL
uniqueness; caller retry keys must not duplicate confirmation effects.

Only after locked preflight passes may execution move case through APPROVED /
EXECUTION_QUEUED / EXECUTING. Controls bind the pre-execution case state, so
validate before these trusted transitions, not after changing its snapshot.
Persist actual action effect, task result, audit and verification scheduling
atomically where possible. No external banking side effect is allowed.

Independent verification must reread payment, ledger, confirmation and event
processing state, compare expected/actual results, exclude duplicate effects
and check unchanged monetary state. The executor's success flag is insufficient.
Only verified success permits RESOLVED; discrepancies escalate and retain
history. Retries must check whether the confirmation already exists before
repeating any write. Test partial failures, lease loss, recovery and uncertain
completion. No compensation for monetary actions is claimed.

Policy prerequisites: operators must supply an explicitly active, versioned
synthetic-controls-1.0 policy. Nothing creates approving default policies.
Development authentication is fail-closed in production and remains unsuitable
as enterprise identity. No live LLM calls are authorized.

## Subsequent counterfactual extension (0011 accepted 2026-10-04)

The original 0010 contract and acceptance remain historical. The added 0011
source has an optional, persisted, bounded `REPLAY_CONFIRMATION` counterfactual.
Its preview does not authorize execution; the execution worker rechecks the
projection under the existing lease and action authorization, and post-action
verification remains independent. PostgreSQL acceptance passed: 29 targeted
tests and 222 full regression tests. Development is at 0011 with existing
records preserved. See `PHASE10_COUNTERFACTUAL_EXTENSION.md`.
