# Phase 7 investigator starting point

## Phase 11 extension

Risk's existing `get_previous_verified_cases({exception_type})` interface now
returns reviewed historical context with empty current evidence and
NOT_EVALUATED action authorization. The scoped current category is mandatory;
historical references never enter the current evidence validator/materializer.
Retrieval is optional, on demand and cached; unavailable memory does not fail
the task. Current source tools, leases, budgets and acceptance checks remain.
The updated prompt is versioned `specialist-1.1`. See PHASE11_CONTRACTS.md.

Phase 6 implements scheduling contracts only. The canonical schemas are `TaskPayload` and `InvestigationResult` in `app/orchestration/contracts.py`. No future task can claim success through the Phase 6 built-in worker.

## Input v1.0

The durable payload includes:

- `task_version=1.0`, `workflow_version=case-orchestration-1.0`.
- Case ID and investigation task type; optional incident ID/context.
- Assessment IDs and classification rule versions used for scheduling.
- Observed evidence references and `evidence_truncated`.
- Read-only permitted tool scope: `READ_CASE_EVIDENCE`, optional `READ_INCIDENT_CONTEXT`.
- UTC task deadline and scheduling reason.

A claimed task envelope additionally carries task ID, lease owner, token, expiry, and attempt number. Shared technology work has one immutable owner payload and explicit per-case task consumers. Context includes affected case IDs and a correlation-history revision; it confers no shared authorization.

## Result v1.0

`InvestigationResult` requires task ID, lease token, assessment IDs, attempt number, nonempty summary and an outcome:

- `COMPLETED`
- `NEEDS_ADDITIONAL_EVIDENCE`
- `FAILED`
- `TIMED_OUT`
- `ESCALATION_REQUIRED`

Evidence references, structured findings and an error code are optional explicit fields. `action_authorization` is constrained to `NOT_EVALUATED`. Results cannot authorize a banking action.

## Required Phase 7 implementation

Add actual investigator handlers before enabling their task types. Validate payload/result versions, tool permissions, scope, deadlines and evidence completeness. Execute remote tools outside long PostgreSQL transactions. Renew leases in short transactions and recheck task status, owner, token, expiry, attempt and assessment/incident context when accepting results. A stale or cancelled worker must not persist findings or case transitions.

Persist real results and findings with evidence/audit references in the same fenced transaction as task completion and downstream coordination. Handle additional-evidence requests, failures, timeouts and escalation explicitly. Coordinate all required individual/shared investigation results before moving a case to `AWAITING_DECISION`; never resolve all consumers just because incident work completed.

The Phase 6 worker intentionally permits claims/completion only for deterministic built-ins. Phase 7 must introduce a handler registry and fenced investigator-result acceptance, rather than loosening this guard without implementations. Supervisor, action controls/authorization, execution, verification, ML and frontend remain separate future capabilities.
