# ResolveOS Architecture

## Phase 13 operational intelligence

`app/intelligence` reads existing normalized evidence, assessments, durable task
history, investigations, independent verifications, approvals and incident history.
Typed protected `/api/v1/intelligence` reports use read-only PostgreSQL transactions,
bounded case/record/reference cohorts and explicit truncation. No simulator label
tables, model provider or new database schema is used. Hypotheses are advisory
associations, never causation or authorization. Completed duration medians exclude
incomplete/future/invalid intervals; verified resolution requires the independent
execution/verification chain. Current status/SLA projections are labelled separately
from measured historical intervals. See PHASE13_ACCEPTANCE.md.

## Phase 12 offline ML evaluation and governance

`app/ml` is an isolated offline evaluation package. Operational classification,
correlation, routing, investigators, Supervisor, controls, execution and reviewed
memory do not import it. Features are allowlisted numeric observations, validated
under `observed-intake-1.0`; source event occurrence, ingestion and evidence-link
times enforce intake availability. Dataset metadata/hidden scenario labels and
current SLA projections never enter this feature schema.

Reviewed synthetic manifests, incident/scenario-aware splits, train-only scaling,
validation-only parameter selection and independent test metrics are recorded in
reproducible experiment reports. Optional CPU estimator libraries are outside
operational requirements. Training is blocked when readiness fails. Registration
metadata is experimental only; there is no promotion, serving or runtime training.
Actual data is inadequate; no adapter is enabled and no bank/control schema changes
are required. Optional estimator smoke execution was blocked by Windows Application
Control on native ML DLLs; the trained path remains unverified. The dataset-inadequate
scope passed 311 full / 43 targeted tests. See PHASE12_ACCEPTANCE.md and the
three Phase 12 dataset/comparison/governance reports. Phase 13 is unstarted.

## Phase 11 reviewed operational memory

`app/memory` adds governed historical context to the modular monolith. Migration
`20261004_0012` follows `20261002_0011` and adds memory families, immutable summary
versions, evidence links, human review/correction/supersession history and retrieval
audits. Foreign keys reuse cases, normalized source evidence, independent
verification, deterministic action authorization and versioned policies.

Publication requires a resolved case and actual independently verified Phase 10
execution, intact supporting records, proper action authorization and explicit
OPERATIONS_REVIEWER approval under `reviewed-memory-1.0`. CANDIDATE and
PENDING_REVIEW are never trusted retrieval results. Rejected, revoked and
superseded versions are excluded. Corrections create a fresh candidate and
preserve old content; publication retires its predecessor atomically. Source-case
and memory locks, unique version numbers and one-active-version partial uniqueness
prevent conflicting reviewers. Version state, reviewer decisions and AuditLog
entries commit together in caller-owned transactions.

Risk's existing `get_previous_verified_cases` interface performs indexed,
deterministic PostgreSQL retrieval on demand: category and authorized case filters,
50-candidate window, shared-source ranking, stable recency ordering, default top 5
(maximum 10), bounded JSON context and compact evidence references. No embeddings,
vector storage, model calls or full banking documents are added. The optional
worker access adapter is a trusted server capability, not model arguments.

Retrieved summaries are labelled HISTORICAL CONTEXT — NOT CURRENT EVIDENCE OR
AUTHORIZATION. Source text is untrusted data; similarity does not establish the
new case's cause. Historical IDs never enter current tool evidence or accepted
findings. The specialist prompt is versioned `specialist-1.1`. Failed retrieval
rolls back its separate short transaction and returns unavailable; normal
investigation proceeds. Supervisor, deterministic controls, approval, execution
and independent verification retain their existing source and authorization checks.

Retrieval rechecks source and publication fingerprints. Invalid supporting records,
corrected verification, withdrawn approvals and unreviewed overwrites fail closed;
explicit reviewer reconciliation records revocation. A changed/expired relevant
policy retains historical facts while marking guidance outdated. Unrelated policy
changes do not invalidate knowledge; every new action requires current controls.

Development HTTP endpoints reuse existing disabled-by-default identity. Production
retrieval requires explicit case/source grants; no enterprise tenant schema or
production identity provider is claimed. Publication history is application guarded,
not protected against arbitrary privileged SQL writes. Downgrade drops Phase 11
tables and preserves Phase 1–10 source/audit rows. See PHASE11_CONTRACTS.md and
PHASE11_ACCEPTANCE.md for exact validation and limitations. Phase 12 status is
recorded in the offline evaluation section above.

## Phase 10 counterfactual extension (0011; PostgreSQL accepted 2026-10-04)

`app/execution/simulation.py` generates a bounded, model-free hypothetical replay
projection from the existing Controls authorization snapshot, predicting one new
synthetic confirmation and zero new payment/ledger effects. The report is linked
to authorization and optionally an execution operation (`counterfactual_simulations`).
Preview validates the action, active policy and fresh evidence, but permits preview
before *human approval*; it records only the hypothetical report and audit.
Submission still requires actual action authorization, creates an operation-bound
projection atomically, and the fenced execution handler regenerates and compares
the projection after calling `Controls.current`. Independent verification reads
actual bank/event state and compares it with the persisted predicted state; a
successful simulation NEVER resolves a case or grants execution permission.
API: `POST /authorizations/{id}/simulate` and `GET /cases/{id}/simulations`
under the existing `/api/v1` prefix, with development-only WORKER identity.
Migration 0011 adds `counterfactual_simulations`. See
`PHASE10_COUNTERFACTUAL_EXTENSION.md` for validation limits and follow-up checks.

Acceptance: 29 targeted PostgreSQL tests and 222 full regression tests passed.
Development is at 0011; all 37 pre-existing application tables were preserved.
Simulation reports are application-guarded, not database-immutable against
privileged writers. Downgrading 0011 drops persisted simulation reports; queued
operations without reports fail closed after re-upgrade and require review.

## Phase 10 synthetic execution and independent verification

`app/execution` binds each operation to a deterministic authorization and a
unique logical confirmation effect. Protected action submission/read APIs and
durable bound PREPARE_EXECUTION/REQUEST_VERIFICATION workers use existing queues,
case lifecycle and audit. Locked freshness/approval preflight occurs before
execution transitions; local confirmation, normalized event, audit and verification
scheduling commit atomically under a valid worker fence. Payment and ledger writes
are prohibited. A separate task rereads source monetary state, confirmation identity
and normalized event processing; only verified success resolves the case.

Bound dead letters are reconciled to FAILED_EXECUTION or VERIFICATION_UNCERTAIN,
with human review, case escalation and audit. Queue failure commits before a
repeatable reconciliation transaction to preserve case-before-task lock order;
maintenance recovers an interrupted handoff. Failed independent verification also
requests human review. Migration 0010 adds execution_operations. Acceptance:
198 PostgreSQL tests passing; see PHASE10_ACCEPTANCE.md for exact limits/results.

## Phase 9 deterministic controls

`app/controls` separates action eligibility from AI recommendation and workflow
approval. The initial allowlist contains only synthetic `REPLAY_CONFIRMATION`.
Operators must supply an active Policy/PolicyVersion with validated
`synthetic-controls-1.0` content; no approving policy is created automatically.
Controls inspect explicit simulator source columns plus latest normalized
observations. Hidden scenario/root-cause attributes are never selected.

Authorization binds case/state/generation, assessments, Supervisor review hash,
evidence/source fingerprints, action parameters and idempotency key, policy
content/version/effective date and expiration. Outcomes are AUTO_ELIGIBLE,
HUMAN_APPROVAL_REQUIRED, BLOCKED and ESCALATED. Missing/contradictory evidence,
duplicate monetary indicators and expired/inactive policy fail closed.

Migration 0009 adds control_authorizations and separate action_approvals/history.
Existing Decision and HumanApproval entities remain usable; old workflow reviews
cannot satisfy action approval. Server-derived role and assignee checks,
approval/rejection/further-investigation/revocation and freshness checks apply.
`Controls.current` must be called immediately before Phase 10 execution in the
same locking transaction. Phase 9 does not mutate banking source data.

Protected versioned APIs: `/cases/{id}/controls/evaluate`,
`/cases/{id}/authorizations`, `/action-approvals/{id}/decision` and `/history`.
Read APIs inherit development operational roles; enterprise tenancy and policy
administration remain future integration work. Phase 9 passed 24 targeted tests
and the full 177-test PostgreSQL suite; CURRENT_STATE.md records the checkpoint.

## Phase 7 specialist investigations

Phase 8 adds `app/supervisor`: independent stored-source/evidence
validation, predicate disagreement checks, structured provider review, fenced
acceptance, versioned review history and targeted bounded reinvestigation.
Supervisor outputs remain advisory and leave `AWAITING_DECISION` for controls.
Follow-up uses existing queue tasks and preserves unaffected specialists' active
accepted results. Discovery preserves these targeted consumer replacements until
assessment or incident context changes. Paid inference remains disabled.
Phase 8 passed its 11 targeted tests and full 153-test PostgreSQL regression.
See CURRENT_STATE.md and PHASE9_CONTRACTS.md for the controls handoff.

`app/investigation` implements Transaction, Technology and Risk handlers using
the existing durable queue. Provider injection is trusted server configuration;
standard tests inject a deterministic model. OpenAI Responses integration uses
structured function arguments/output, environment credentials, pinned model
metadata, no server-side response storage and an explicit disabled-by-default
live setting. Current implementation follows the official function-calling and
structured-output contracts:
https://developers.openai.com/api/docs/guides/function-calling and
https://developers.openai.com/api/docs/guides/structured-outputs.

Each role has a fixed Pydantic tool allowlist. Tools read whitelisted normalized
source events, with bounded immutable as-of snapshots and per-attempt caching.
Neither simulator ORM objects nor hidden labels enter model context. Cross-case
access is rejected outside explicit shared technology incident context. Source
text remains untrusted tool output and cannot grant write permissions.

Model calls run after snapshot transactions commit. Short transactions renew
leases between iterations. Acceptance locks cases in stable order, acquires the
correlation advisory lock before the task lock, rechecks lease/deadline,
assessment/incident/evidence stamps and each retrieved source projection, then
atomically persists evidence, findings, task result, attempt telemetry and
downstream coordination. The queue's builtin `complete` guard remains intact;
only the investigator's validated acceptance path completes specialist tasks.

`investigation_runs` stores unique task/attempt provenance and structured output.
Existing evidence and investigator findings are reused. Exact observed field
predicates are deterministically checked; prose and hypotheses remain model
interpretations. Explicit incomplete outcomes request review; all required
specialists must succeed before Supervisor scheduling. Shared results never
resolve or authorize consumers. Unimplemented specialist types stay unavailable.

Protected APIs expose `/cases/{id}/investigations`,
`/cases/{id}/investigation-evidence`, and `/investigations/stats`. They inherit the
existing disabled-by-default development authentication and broad operational
roles; production authentication and tenant isolation remain future work.

Current sources lack service-health records and case-to-policy applicability;
these tools report unavailable. Phase 11 implements reviewed historical memory.
Related transaction
discovery beyond authorized case context is unavailable. Remote integration is
implemented but has only mocked transport verification; no paid calls occurred.
Model timeouts must fit within half the worker lease; the provider has no hidden
retry loop. Queue attempt/backoff limits handle transient failures. Token/cost
preflight uses conservative request byte counts and configured pricing; actual
usage is recorded when supplied. See PHASE8_CONTRACTS.md for Supervisor handoff.

## Architectural direction

ResolveOS follows a modular monolith structure so the initial foundation can support future domain expansion without premature microservice decomposition.

### Core layers

- API layer: FastAPI app and versioned health endpoints
- Configuration layer: Pydantic settings with env validation and structured logging
- Persistence layer: SQLAlchemy models and Alembic migrations
- Domain layer: case-state lifecycle and deterministic transitions
- Audit layer: immutable-style audit event records tied to observed entities

## Persistence model

The database is the system of record. The initial schema includes:

- cases
- exceptions
- incidents
- case_incidents
- evidence
- investigator_findings
- decisions
- actions
- human_approvals
- verification_results
- policies
- policy_versions
- audit_logs

The schema intentionally keeps the first pass minimal and avoids speculative tables that are not required by the current roadmap.

## Case lifecycle

The lifecycle is enforced through `CaseLifecycleService`, which only allows transitions explicitly mapped in the transition table. This prevents invalid direct state jumps and keeps status changes inside the domain service.

## Audit strategy

Audit records are written as append-like event entries storing the entity type, entity id, event type, summary, and structured details. This is intentionally simple but durable and traceable.

## Event ingestion and detection

Synthetic payment, ledger, confirmation, API-log, and workflow records are collected by explicit `SourceAdapter` implementations. Each adapter returns mappings validated by `EventEnvelope`, including UTC occurrence time, source identity, entity/correlation references, schema version, source-record reference, and source payload. `EventIngestionService` persists each accepted event independently and records validation/persistence errors durably.

PostgreSQL enforces unique `(source_system, event_id)` values. A repeated delivery is telemetry, not a duplicate-payment incident. The deterministic `ExceptionDetectionService` processes the normalized event store, uses configured confirmation/workflow/API windows, and applies stable detection keys protected by a unique index.

Exceptions reference actual event records and existing case evidence. A detection creates a case in `DETECTED`, writes an audit entry, and appends detection history. Late evidence links to the original exception and adds history; historical detection records are retained. Event time, ingestion time, and detection time remain distinct.

## Classification, priority, and routing

`Classifier` in `app/classification/rules.py` defines the stable result contract; `RuleBasedClassifier` is the current implementation. It evaluates observed normalized events and returns one or more categories, rule/version, supporting event references, features, explanation, UTC classification time, uncertainty flags, optional score, source, and operational eligibility. Unsupported cases remain `UNKNOWN_EXCEPTION`; contradictory evidence can produce multiple categories and a `conflicting_evidence` flag.

`PriorityEngine` applies versioned, configurable synthetic scoring using observed impact, record count, duplicate-monetary-effect evidence, synthetic system criticality, case age, and evidence completeness. These values are illustrative engineering configuration, not OCBC operational-risk policy. Priority affects urgency/SLA only; `action_authorization` remains `NOT_EVALUATED`.

`recommend_routing` recommends multiple specialist queues from the actual categories and source attributes. Missing or uncertain classification adds `HUMAN_TRIAGE`. A repeated confirmation alone does not imply duplicate payment risk; the risk signal requires distinct payment entities sharing observed idempotency keys.

`ClassificationService.evaluate(exception_id, reason)` locks the case, calculates the current assessment, and appends a revision only when the material snapshot changes. Assessment history stores category, priority inputs/rules, routing, and SLA. `Case.sla_started_at` is initialized once; later priority changes recalculate the deadline from that original start. Case priority/SLA are current projections, while assessment rows and relevant audit entries retain prior values.

The versioned endpoints classify or re-evaluate exceptions, retrieve assessment history, and expose current case priority/SLA and specialist routing. Classification is advisory; it does not authorize actions or invoke investigators.

## Future ML experiments

Future Decision Tree, Random Forest, or Gradient Boosting implementations can satisfy the `Classifier` protocol and return the same result shape with a model source/version and optional score. They must remain advisory and must not independently authorize an action. Training, model registry, and model-serving infrastructure are not part of Phase 4.

## Phase 5 incident correlation

`IncidentCorrelationService` loads detected cases and their latest Phase 4 assessments, discovers candidates through indexed entity/trace/evidence queries, and passes normalized observed features to `DeterministicCorrelationEngine` (`deterministic-correlation-1.0`). Source discovery is separate from case evidence: another case sharing a trace cannot supply its identifiers to the seed case. The engine never queries simulator tables, scenario labels, expected root causes, or test ground truth. API response bodies can explicitly supply `incident_identifier` or `dependency_failure_id`; the simulator-generated payment `incident_key` is excluded, including from legacy payment envelopes.

Exact incident/dependency failure identifiers can span time windows. Entity matches require compatible event time; trace matches additionally require a shared service/endpoint and error family. Similar source, category, dependency, error, or timestamp alone yields `UNKNOWN`. Explicit incompatible incident identifiers reject a relationship; conflicting current identifiers require review. Groups require one shared strong identifier across all members, rather than assuming chains of pairwise similarity imply a common cause. Evidence references and observed contradictions accompany the assessment; no confidence percentage is invented.

Current features select the latest observation per source record by event time, ingestion time, then record ID. Original events, detection timestamps, assessment revisions, and correlation history remain stored. Re-evaluation can remove unsupported suspected memberships, reject groups with fewer than two members, and append changed evidence even when membership is unchanged. Truncated searches cannot remove membership. Investigating/confirmed memberships require explicit operator review; repeated observations cannot confirm incidents automatically. Manual exclusions survive automatic reruns.

Incident status is separate from case status: `SUSPECTED -> INVESTIGATING -> CONFIRMED -> RESOLVED`, with rejection from suspected/investigating and explicit split/merge operations. Confirmation requires current supported membership, source evidence for each case, a reason, and resolution of contradictions. Addition validates current classification and shared source evidence; removal retains the prior link with its removal time/reason. Split partitions all members, creates suspected children, and leaves singleton partitions ungrouped. Merge requires two confirmed incidents, evidence on both sides and shared observed identifiers; source incidents and association history remain available. Split children are not automatically merged back together.

Migration `20261002_0005` extends existing incidents and case associations, adds append-only correlation history and run records, and introduces a partial unique index for one active incident per case. Existing unique incident keys provide stable logical identity. All correlation and lifecycle mutations acquire the same PostgreSQL transaction advisory lock; row locks and database constraints provide additional protection. Each service mutation commits history, membership, and audit changes together. This intentionally serializes incident writes; tested concurrency uses two in-process sessions, not multi-host deployment.

`/api/v1/incidents` supports trigger (`POST /correlate`), listing/detail, `/cases`, `/evidence`, `/history`, `/re-evaluate`, status transitions, membership edits, split and merge. Summaries expose current case/incident status, affected systems, timestamps, shared features, rule version, evidence and unresolved contradictions. Read and mutation routes use configured correlation limits. Trigger batches use `after_case_id` pagination. A separate run record captures operational settings and work counts.

## Performance and Phase 6 extension points

Defaults bound seeds to 200 cases (maximum 500), candidates to 1,000, observations to 10,000 and comparisons to 5,000. Feature construction currently scans bounded observations for each candidate: O(C * E). Identifier buckets and anchor comparisons avoid unrestricted all-pairs comparison; pairing/grouping cost is approximately O(F + P), plus sorting, where F is feature memberships and P is the capped comparison count. Conservative anchor selection can miss valid subgroups when the anchor is incompatible; candidate truncation is reported and may require narrower batches or operator review. Linked historical evidence and investigation summaries can still grow with record history.

Indexed entity, correlation, event-time and exception-evidence lookups narrow discovery. JSON identifier predicates and latest-assessment aggregation can scan historical rows; these and the global incident-write lock are known bottlenecks. A 150-payment synthetic workload inspected actual PostgreSQL query behavior (18 correlation SQL statements, 50 candidate cases, 10 pair comparisons with configured truncation); `EXPLAIN ANALYZE` used the entity-reference index. This is a bounded engineering check, not enterprise-scale or incident-accuracy validation.

`CorrelationStrategy` is a small versioned protocol returning groups, evidence-bearing pair outcomes, comparison counts, truncation and ungrouped cases. Later experimental DBSCAN, hierarchical, or embedding strategies can implement this contract, evaluated against this deterministic baseline; no clustering model is implemented. Phase 6 can consume incident summaries/history and case assessments. One shared investigation does not confer shared authorization: actions, approvals, decisions and verification remain case-scoped. Future remediation must separately check each case's preconditions, duplicate risk, authorization and outcome. Phase 5 creates no investigators, orchestration, remediation or frontend.

## Phase 6 durable orchestration

`app/orchestration` adds PostgreSQL durable scheduling through migration `20261002_0006`. Detection still creates cases. Explicit case scheduling or bounded case-ID polling discovers operational work; the API does not start a worker implicitly. `python -m app.orchestration.worker --poll` runs a trusted local worker, and `--once` runs one bounded iteration. Polling cycles back to the beginning after its last page, revisiting changed evidence, classifications and memberships.

Every earlier `CaseLifecycleService` transition remains valid. New `INVESTIGATION_QUEUED` and `EXECUTION_QUEUED` states distinguish scheduling from actual work. Unsupported classifications use the existing `AWAITING_HUMAN` state. Phase 6 does not drive execution, verification or resolution. Human `APPROVED` means workflow approval; future control-engine authorization remains `NOT_EVALUATED`.

Tasks store type/payload/workflow versions, owning case, optional incident, assessment/evidence snapshot, UTC scheduling/deadline times, priority, attempts/budget, owner/token/expiry, result, error and unique idempotency identity. Task consumers associate shared work with individual cases. Separate task/review history and existing audit logs preserve scheduling, claiming, renewal, completion, retry, failure, cancellation, human intervention and lifecycle/incident coordination changes. Completed task identities remain unique; explicit evidence/context changes or reinvestigation create new generations rather than rewriting old work.

Queue statuses are `PENDING`, `RUNNING`, `RETRY_WAIT`, `COMPLETED`, `DEAD_LETTER`, `CANCELLED`, and `WAITING_HANDLER`. Built-in handlers are only `CLASSIFY_CASE`, `REEVALUATE_CASE`, `ROUTE_CASE`, and `CHECK_SLA`. Specialist, supervisor, execution preparation and verification tasks remain `WAITING_HANDLER`, cannot be claimed by this worker and never report placeholder success. Human review acts through a separate workflow review API. Unavailable task deadlines can fail explicitly and request operational review.

### Leasing and transaction boundaries

Claims use short `SELECT FOR UPDATE SKIP LOCKED` transactions, increment attempts and assign new random fencing tokens. PostgreSQL `clock_timestamp()` is authoritative, including after lock waits. Clock reads suppress ORM autoflush to prevent persistence of an intermediate status/lease combination. Database constraints validate status, lease and attempt fields. Expired committed leases become bounded retries or terminal failure; rolled-back claims remain claimable.

Handlers lock case before task, validate owner/token/expiry, perform deterministic database work and revalidate the fence before completion. Effects, assessment revisions, follow-up tasks, audit and completion commit together. `ClassificationService.evaluate(..., commit=False)` joins this transaction; its existing default still commits for Phase 4 callers. SQL statement/lock waits are bounded by the lease duration. Expiry during a handler rolls back its effects. Recovery skips locked transactions until PostgreSQL releases them. There is no network or LLM work in these transactions.

Independent-session tests verify scheduling/claim exclusivity, locked-row skipping, recovery, stale fencing and atomic rollback. Two separately spawned processes also claimed one task exactly once between them. Restart and interrupted-transaction persistence are tested locally. Multi-host operation, partitions, database failover and exactly-once external effects are unverified. Phase 7 must execute remote investigation outside long transactions and fence result acceptance afterward.

### Routing, incidents and review

Routing uses current Phase 4 recommendations and stored classification versions, schedules only relevant specialists and sends unsupported/ambiguous cases to human triage. Evidence/assessment and incident fingerprints drive rerouting. Superseded tasks and consumer links are retained. Technology investigation may be shared per incident snapshot; transaction/risk and other case-specific work remain separate. Incident membership is read under Phase 5's transaction advisory lock. Obsolete shared technology work is cancelled immediately when replacement context is scheduled; other consumers attach on subsequent bounded polls. Split/merge changes never resolve or authorize affected cases. Oversized incident context falls back to case-specific work with an audit reason.

SLA checks reuse Phase 4's original start and current deadline. Retries/rerouting never restart the SLA. Overdue cases receive one breach review per generation, and expired human reviews escalate explicitly. Reviews store role/optional assignee, reason, assessment/evidence snapshot, deadline and history. Assignment, approve/reject/request more investigation, closed/expired protection, and current evidence/assessment/incident freshness checks are enforced. A decision supersedes other open reviews. Workflow approval creates neither an action nor an action-authorization `HumanApproval` record; execution preparation remains unavailable.

All orchestration and review endpoints require server-derived identity. The development mechanism is disabled by default, requires distinct worker/reviewer bearer secrets of at least 24 characters and assigns separate roles. Clients cannot supply their role or decision actor. It runs only under `APP_ENV=development` or `test`; production access returns 503 even when enabled. Invalid settings now fail validation instead of silently becoming development configuration. This is not production authentication. The CLI is a trusted process with database credentials; production requires a real identity provider and deployment controls.

### Operations and limits

- Case endpoints: `/api/v1/cases/{id}/orchestration`, `/tasks`, and `POST /orchestrate`.
- Operations: `/api/v1/orchestration/poll`, `/maintenance`, `/stats`, `/health`.
- Protected workers: `/api/v1/orchestration/worker/claim` and `/orchestration/tasks/{id}/renew`, `/run`, `/fail`, `/requeue`.
- Workflow review: `/api/v1/reviews`, `/reviews/{id}/history`, `POST /assign`, `POST /decision`.

Status/history responses hide lease tokens; protected claims/renewals expose the required lease envelope. Lists/history are paginated. Statistics include statuses, retries, oldest queue age, SLA breaches and active worker leases.

Ready work follows priority; after the fairness interval, oldest eligible work runs first. Partial indexes support separate priority and age paths without sorting the full queue by a calculated score. Defaults are 60-second leases, 3 attempts, exponential backoff from 5 seconds capped at 300 seconds, 100 cases/tasks per poll (maximum 500), 300-second fairness and 60-second SLA checks. Requeue requires terminal failed built-in work, a reason, eligible case, valid deadline and increased attempt budget (maximum 10). Attempts/history are never reset.

Classification handlers cap cases at 100 exceptions. Shared context caps membership and assessments at 500; evidence snapshots cap references at 2,000 and flag truncation. Task-history responses cap events at 5,000 per task page. Queue readiness, deadlines, leases and case/incident queries are indexed. Statistics and source revision aggregates still scan history, and inherited Phase 4 priority scoring still reads the payment event store. Incident routing serializes with Phase 5 writes. These remain bottlenecks; measurements in CURRENT_STATE.md do not establish enterprise scalability.

Phase 7's exact payload, result and fenced acceptance responsibilities are documented in [PHASE7_CONTRACTS.md](PHASE7_CONTRACTS.md). No investigator, Supervisor, controls, remediation, ML or frontend implementation is included in Phase 6.
