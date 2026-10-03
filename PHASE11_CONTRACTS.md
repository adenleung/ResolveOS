# Phase 11 reviewed operational memory

Memory is optional historical context. It cannot supply current evidence,
establish the new case's cause, authorize an action or resolve a case.

## Publication and human feedback

`MemoryService.candidate(case_id, CandidateRequest, MemoryAccess)` checks the
actual completed Phase 10 outcome: RESOLVED case, latest successful independent
verification, VERIFIED operation/action, bound deterministic authorization,
and action-specific human approval where required. It checks normalized
supporting evidence against its case/source events. Supporting events must have
occurred and been ingested by the verified outcome. Only the existing independently verified synthetic
confirmation workflow is eligible; arbitrary success flags and AI conclusions
are insufficient. Failed/unresolved cases remain in existing history.

Lifecycle: CANDIDATE -> PENDING_REVIEW -> ACTIVE, with explicit authorized human
APPROVE. REJECT closes proposals. REVOKE/WITHDRAW/FLAG remove active records from
retrieval; flagging a draft rejects it. CORRECT creates a new candidate version
and preserves the old text and links. Corrected drafts are rejected immediately;
an existing active version remains available until its replacement is approved
unless it is flagged/revoked or fails supporting-record checks. Approval of the
replacement supersedes its predecessor atomically. To correct supporting
references or outcomes, supply both new verification_id and evidence_ids;
the new independently verified source must pass the same checks and fresh review.

Review requires server-issued OPERATIONS_REVIEWER identity and case/source
access. All consequential operations record actor, UTC timestamp, reason,
before/after state, replacement reference and content hash in MemoryReview,
plus existing AuditLog entries. Source-case -> memory-family -> version locks
serialize reviewers; PostgreSQL enforces one active version per family and
unique version numbers. No feedback trains or fine-tunes a model.

The service flushes but never commits. Its caller must commit the source check,
version state, supersession, review and audit together or roll back everything.
HTTP requests and on-demand investigator retrieval use separate short sessions.

## Trust and freshness

`reviewed-memory-1.0` is the initial deterministic governance contract. Each
publication must meet it. Retrieval rechecks this contract, case category,
the verification/authorization/approval chain, normalized confirmation processing,
support fingerprints and publication content hash. Invalid or inaccessible
records fail closed. Source revocation, corrected outcomes, changed evidence,
withdrawn approval or unreviewed overwrite exclude the record immediately.
`reconcile(version_id, access)` persists an authorized invalidation as REVOKED
with audit; routine reads do not mutate publication state.

Policy checks concern the source action's applicable policy only. Changes to
unrelated policies leave historical facts and guidance labels unchanged. An
expired/inactive/changed relevant policy retains verified historical facts but
marks guidance OUTDATED_REMEDIATION_GUIDANCE. Otherwise guidance is labelled
REQUIRES_CURRENT_CONTROLS. Neither label grants current permission.

## Retrieval and investigator boundary

`retrieve(current_case_id, category, access, top_k=5, context_bytes=8000)` requires
the category to exist in the current case. PostgreSQL selects at most 50 active
candidates by indexed category/status and stable newest-first order, excluding
the current case and unauthorized historical cases. Eligible candidates rank
by shared source-system count, then recency and stable ID. Results cap at 10
(default 5); serialized JSON context caps at 16,000 bytes (default 8,000).
Supporting references cap at 20 per version. Evidence reads are batched per
candidate. Truncation is explicit; the bounded window can omit older matches.

Results include historical case, reviewed summary/failure pattern, previously
verified outcome, verification/action references, policy version, review and
source timestamps, source/evidence references, similarity explanation and limits.
They carry `HISTORICAL CONTEXT — NOT CURRENT EVIDENCE OR AUTHORIZATION.`;
`evidence` stays empty and `action_authorization` stays NOT_EVALUATED.
Summaries remain untrusted human interpretation for prompt-injection purposes.

Risk's existing `get_previous_verified_cases({exception_type})` interface is
preserved. Calls are on demand, cached per attempt, subject to existing tool,
token and cost budgets, and use a one-second SQL statement timeout. Historical
IDs never enter the current-evidence set or findings materialization. The
specialist prompt is versioned specialist-1.1. Investigators still query current
sources; Supervisor and deterministic action controls keep their existing checks.
Missing matches and failed retrieval/audit do not fail the investigation.

MemoryAccess is a trusted server capability, never a model/HTTP-supplied role
or ACL. Development/test follows existing broad operational case access and
can narrow it by explicit case/source grants. Default investigator retrieval
also restricts sources to those in its current snapshot. Production retrieval
requires explicit case/source grants through a trusted memory_access_provider
passed to InvestigationRunner or run_once. The repository has no tenant schema
or enterprise identity provider: enterprise tenancy is not claimed. A future
identity adapter must derive grants from tenant/user/case/source ACLs. Existing
development HTTP auth remains disabled by default and unavailable in production.

## Schema and API

Migration `20261004_0012` follows `20261002_0011`. Tables:
operational_memories, memory_versions, memory_evidence, memory_reviews and
memory_retrievals. Existing case/evidence/event/verification/authorization/policy
identifiers are foreign keys. Only compact summaries, fingerprints and references
are stored, with no duplicate banking documents or vector/embedding store.

Protected `/api/v1` endpoints:

- POST /cases/{case_id}/memory/candidates
- POST /memory/versions/{version_id}/review
- POST /memory/versions/{version_id}/reconcile
- GET /cases/{case_id}/memory (bounded reviewer listing)
- GET /memory/versions/{version_id}/history (bounded reviewer history)
- GET /cases/{case_id}/memory/retrieve

Downgrade drops Phase 11 memory/version/link/review/retrieval tables; it preserves
Phase 1–10 source and existing audit records. It is destructive to memory artifacts
and needs a backup for restoration. Applications guard version immutability;
privileged database writers can bypass application governance. No banking-write,
execution or action-approval API is exposed by the memory service.

## Phase 12 boundary

This phase adds no training datasets, classifiers, embeddings, paid API calls,
frontend or real banking integrations. Phase 12 can separately define reproducible
advisory benchmarks with explicit authorization; memory feedback must not silently
become training data. Stop after Phase 11 acceptance.
