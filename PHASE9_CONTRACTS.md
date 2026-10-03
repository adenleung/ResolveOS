# Deterministic controls starting contract

Phase 8 stores immutable `SupervisorReview` records. Only outcome
`RECOMMENDATION` is an eligible advisory input to Phase 9. The case remains
`AWAITING_DECISION`; no action or authorization record is created.

Input must include case ID, current assessment IDs/generation/evidence stamp,
accepted Supervisor task/review ID, proposed action and evidence IDs. Before
evaluating controls, independently revalidate current source observations and
the Supervisor snapshot; a historical recommendation is not current permission.

Implement the initial action allowlist around `REPLAY_CONFIRMATION`, with a
synthetic payment ID and stable idempotency key. No monetary transfer action is
allowed. Choose a versioned synthetic policy using the existing `Policy` and
`PolicyVersion` or explicitly applicable synthetic policy records; never infer
applicability from an LLM suggestion or silently create an approving policy.

Evaluate role, case state, required payment/ledger/confirmation evidence,
duplicate effects, amount/affected-case/blast-radius limits, active policy
version/effective window, action preconditions, idempotency and approval needs.
Fail closed for unknown actions, incomplete evidence, expired/missing policies,
unresolved contradictions and stale source state.

Persist immutable outcomes `AUTO_ELIGIBLE`, `HUMAN_APPROVAL_REQUIRED`, `BLOCKED`,
or `ESCALATED`, with rule explanations and policy/evidence/action fingerprints.
Reuse existing domain entities where adequate, extending them with migration
0009 where necessary. Human action approval is separate from Phase 6 workflow
approval: bind authenticated server identity, assigned role, action parameters,
policy and evidence versions, expiration/revocation and decision history.

Phase 10 must lock/recheck authorization, policy, approval and source state just
before execution and independently verify afterward. Phase 9 executes nothing.
Add protected versioned read/control/approval APIs and actual PostgreSQL tests
for stale approvals, policy changes, role rejection and AI authorization bypass.

Current limitations: development-only authentication; no control handler,
authorization records, action approvals or remediation implementation yet.
