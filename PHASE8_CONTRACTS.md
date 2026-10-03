# Supervisor integration contract

## Phase 11 historical context boundary

Reviewed memory is an optional investigator aid. It does not become Supervisor
evidence or a verified observation for the current case. Historical IDs stay
outside accepted current source references, while Supervisor still independently
cross-checks stored/current evidence and exact predicates. Its output schema,
targeted reinvestigation, recommendations and action-authorization boundary are
unchanged. See PHASE11_CONTRACTS.md and PHASE11_ACCEPTANCE.md for regression proof.

Implemented by `app/supervisor`; migration `20261002_0008` stores unique
task/attempt reviews, snapshots, structured recommendations and telemetry.
Output schema: `SupervisorOutput` in `app/investigation/contracts.py`.
Protected history endpoint: `/api/v1/cases/{case_id}/supervisor-reviews`.
Worker test injection: `run_once(..., supervisor_provider=provider)`; live
OpenAI uses the same adapter with `output_model=SupervisorOutput` and remains
explicitly disabled. No Supervisor tool execution is permitted.

Phase 7 creates `REQUEST_SUPERVISOR_REVIEW` only after every active required
specialist consumer has a current, completed, supported investigation result.
Incomplete results request human workflow review. Unsupported specialist roles
remain unavailable and prevent successful coordination.

Supervisor input must include case ID, generation, current assessment IDs,
evidence stamp, active individual/shared task IDs, immutable investigation
results, persisted evidence IDs and corresponding normalized event IDs. Shared
technology findings remain incident-scoped; no per-case conclusion is implied.

Result version `1.0` must carry supported/rejected conclusions, unresolved
issues, targeted additional checks, proposed action, evidence references,
escalation reasons, review version, model/prompt provenance, and
`action_authorization=NOT_EVALUATED`.

Revalidate persisted evidence and source records independently. Do not treat
model prose as verified because an observed field predicate matches. Only
`verified_observation` has deterministic support; free-text findings and
hypotheses require review. Bound reinvestigation cycles and target relevant
specialists. Fence acceptance against current leases, assessments, evidence and
incident context. Preserve earlier review/investigation history.

Execution stays in the Phase 6 worker with remote inference outside database
transactions. Supervisor recommendations never grant action authorization.
Phase 9 controls must independently evaluate proposed action, current policy,
permissions, human approval and preconditions.
