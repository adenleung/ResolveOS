# Current State

## Active Phase 14 recovery build

Phase 13 was accepted and remotely verified at
`ba0367d46260b9195b1506ebfb79a973ad98465b` before Phase 14 began.
Dedicated shadow/replay, telemetry and verified-backup migration tooling are now
implemented. Exact Phase 14 validation, development migration and remote checkpoint
are recorded in PHASE14_ACCEPTANCE.md. Shadow is non-executable; offline ML remains
disabled. Phase 15 starts after the Phase 14 checkpoint is pushed and verified.
Acceptance: 18 targeted, 69 safety and 350 final full PostgreSQL tests passed,
zero failures/errors/skips. Development upgraded to 0013 after verified backup
restoration; all 43 existing tables retained identical full-row hashes.

## Historical Phase 13 recovery checkpoint

The accepted Phase 12 backend was recovered at `f0ed616`; neither reported newer
checkpoint nor frontend files were recoverable. Fresh baseline: 311 PostgreSQL
tests passed. `app/intelligence` now adds bounded evidence-backed read-only
analytics, conservative contributing-factor hypotheses, workflow durations and
incident history. Phase 13 accepted: 21 targeted and 332 full PostgreSQL tests passed;
all 311 prior tests retained. Exact validation and remote backup
status are recorded in PHASE13_ACCEPTANCE.md. Development remains at 0012 and
has not been modified. Phase 14 begins only after Phase 13 is pushed and verified.

## Historical Phase 12 evaluation checkpoint — 2026-10-04

- Offline dataset readiness, point-in-time features, incident/scenario-aware splits,
  experiment metadata and governance are implemented in `app/ml`. Final acceptance
  status is recorded in `PHASE12_ACCEPTANCE.md`.
- Full Phases 1–11 backend commit `fdd9006` was confirmed on local main and GitHub
  before changes. Historical statements that Git was unavailable describe the
  earlier Phase 11 session, not this verified checkpoint.
- Actual development revision remains `20261004_0012`; no schema or development
  data changes. Dataset: 2 payments, 10 events, 2 API exceptions, one scenario and
  one simulator family key; zero validated independent families/training examples.
- All five use cases retain deterministic rules. No model trained, enabled or
  integrated; no inference adapter. XGBoost/LightGBM unavailable. Optional sklearn
  toy validation is blocked by Windows Application Control rejecting native ML DLLs.
- See `PHASE12_DATASET_READINESS.md`, `PHASE12_MODEL_COMPARISON.md` and
  `PHASE12_MODEL_GOVERNANCE.md` for exact findings, evidence and limitations.
- Stop after Phase 12. Phase 13 and frontend remain unstarted.
- Dataset-inadequate framework-only acceptance passed: **311 full PostgreSQL
  tests in 755.460s**, **43 targeted tests in 79.366s**, zero failures/errors/skips.
  All 268 prior tests are retained. Trained-estimator validation remains blocked;
  this is not approval to serve a model. See `PHASE12_ACCEPTANCE.md`.

## Historical Phase 11 checkpoint — PostgreSQL accepted 2026-10-04

- Reviewed operational memory passed PostgreSQL acceptance. Source and development Alembic are `20261004_0012`, following the accepted Phase 10 `20261002_0011` checkpoint. Full regression: **268 passed in 666.32s**, no failures/errors/skips/warnings; all original 222 tests remain passing. Evidence: `phase11-full-regression-results.xml`.
- Final targeted Phase 11 tests: **46 passed in 160.08s**. Existing investigator/Supervisor baseline: **39 passed in 138.22s**, with one optional pytest-cache permissions warning. Unchanged Phase 9–10 safety suite: **69 passed in 180.25s**, no failures/errors/skips/warnings. Original Phase 10 XML reports are preserved.
- Candidate/pending/active/rejected/revoked/superseded lifecycle, explicit human publication, immutable summary versions, corrected source references, withdrawal/flagging, independent verified execution provenance, normalized evidence fingerprints and audit are implemented.
- Risk's existing memory tool now performs bounded PostgreSQL retrieval on demand. Historical data remains outside current evidence and authorization; missing/failed retrieval preserves investigation. Supervisor, controls and banking execution remain independent.
- Source and publication integrity failures exclude records immediately; explicit reviewer reconciliation persists revocation. Relevant policy changes retain historical facts and mark old remediation guidance outdated. Production requires an explicit server access adapter; existing development authentication is unchanged.
- See `PHASE11_CONTRACTS.md` and `PHASE11_ACCEPTANCE.md`. Phase 12 remains unstarted. Git is unavailable; no commit created.
- Dedicated fresh upgrade, populated **0012 -> 0011 -> 0012** round trip and reflected model/schema constraints/indexes passed. All 38 Phase 1–10 source/audit tables retained identical row counts and content hashes. Actual candidate EXPLAIN used `ix_memory_retrieval` and `operational_memories_pkey`; one local retrieval returned 1,772 JSON bytes in 0.132026s using 24 SQL statements including audit. This is not an enterprise load/latency claim. Evidence: `phase11-migration-results.json`.
- Development upgrade followed final validation and a fresh custom-format recovery backup, `resolveos-pre-0012.dump`, verified with pg_restore --list and cluster identity. All 38 existing tables retained identical row counts/content hashes; five new memory tables are empty. Evidence: `phase11-development-migration-results.json`. Development was not truncated or downgraded.
- Successful verifier databases and the empty disposable database retained by the diagnosed initial new-test failure were removed. Acceptance is complete for the documented synthetic scope. Ready for a separately authorized Phase 12 handoff; **stop after Phase 11**.

## Historical Phase 10 counterfactual checkpoint — PostgreSQL accepted 2026-10-04

- Persisted hypothetical `REPLAY_CONFIRMATION` projections passed PostgreSQL acceptance: **29 targeted tests in 38.64s; 222 full regression tests in 264.64s**, zero failures/errors/skips and no reported warnings. The supplied 27-test targeted suite also passed in 36.65s before adding explicit policy-change and concurrent-execution checks. No runtime safety controls or existing assertions were changed.
- Both verifier runs applied fresh 0001–0011 migrations, downgraded to 0006 and re-upgraded to 0011 on disposable databases. Successful test databases were removed.
- Development database `resolveos` upgraded **0010 → 0011** after acceptance and a custom-format PostgreSQL backup. All **37 existing application tables** retained identical row counts and full-row content hashes. The new simulation table is empty. Evidence: `phase10-counterfactual-migration-results.json`; backup: local ignored `resolveos-pre-0011.dump`.
- Simulations cannot authorize actions, resolve cases or write banking records. Execution retains fresh deterministic controls, action-specific approval, unique effect identity, worker fencing and independent observed verification. No paid LLM calls occurred.
- **Stop after Phase 10. Phase 11 remains unstarted.** See `PHASE10_ACCEPTANCE.md` and `PHASE10_COUNTERFACTUAL_EXTENSION.md` for limits and review findings.

## Historical original 0010 engineering checkpoint

- Last completed phase: **Phase 10**, accepted against PostgreSQL on 2026-10-04. This repair pass is finished. **Stop here; do not begin Phase 11 or additional features without a new instruction.**
- Full regression: **198 passed in 255.27s**, zero failures/errors/skips; no warnings reported. Targeted Phase 10: **21 passed in 30.51s**. Reverse order (Phases 5, 4, 3, 10): **78 passed in 103.15s**. Full collection runs Phase 10 before Phases 3-5 and passes all 78 relevant tests as part of the 198-test regression.
- Reports: `backend-test-results.xml`, `phase10-test-results.xml`, `phase10-isolation-last-results.xml`, `PHASE10_ACCEPTANCE.md` and `phase10-migration-results.json`. Earlier intermediate results and limitations are recorded in the acceptance report.
- Alembic source and development revision: **20261002_0010**. Fresh 0001-0010 upgrade, downgrade to 0006 and re-upgrade passed. Development upgrade verified 0009/absent execution table first and preserved row counts in all 36 existing application tables, including 22 cases; no development data reset.
- Original 179-pass/6-failure/4-error regression came from queue-only fixtures leaking committed banking/action records. Guarded per-test committed cleanup now isolates all application tables in verifier-owned disposable databases while retaining Alembic metadata. Assertions and foreign keys were preserved; no tests skipped or exceptions suppressed.
- Terminal execution failure projects DEAD_LETTER into FAILED_EXECUTION (before effect) or VERIFICATION_UNCERTAIN (effect awaiting verification). Operation/action, case escalation, human review and audit/history persist together. Task failure is committed first to preserve case-before-task lock order; interrupted reconciliation is recovered by worker maintenance. Actual failed verification also requests human review; only independent verified success resolves a case.
- Execution remains **synthetic REPLAY_CONFIRMATION only**, with no payment/ledger writes. AI cannot authorize actions; freshness, explicit human approval, idempotency and lease fencing remain mandatory.
- Live OpenAI calls remain disabled. Provider integration has fake-model and mocked transport verification only; live-provider operation is unverified.
- Git executable and .git repository remain unavailable. File/report checkpoints saved; **no commit created**.
- Phases 11-13 are unstarted. Phase 14 has cross-phase security/recovery coverage but its dedicated acceptance is incomplete. Frontend was not implemented; counterfactual simulation was added and accepted subsequently at 0011 as recorded above.

## Implemented

- Phase 1 foundation: FastAPI startup, settings, PostgreSQL configuration, Alembic, domain models, case lifecycle, and audit persistence.
- Phase 2 synthetic banking source system: payments, ledger entries, confirmation events, technology/API logs, workflows, policies, and reproducible scenarios.
- Phase 3 event ingestion: UTC `EventEnvelope`, schema validation, five explicit synthetic source adapters, exact event deduplication, durable rejected-record reporting, processing state, and replay-safe ingestion.
- Phase 3 detection: deterministic confirmation-window, reconciliation, state-conflict, API failure, duplicate business event, and overdue-workflow rules.
- Qualifying detections create one stable exception and operational case, link actual source records as evidence, and append audit and detection-history entries. Late confirmation evidence updates the original exception without deleting its detection history.
- Versioned APIs trigger synthetic ingestion and detection, list and retrieve exceptions/evidence, and expose processing statistics.
- Phase 4: deterministic, versioned classification supports payment confirmation mismatch, reconciliation mismatch, API failure, workflow exceptions, conflicting records, duplicate events, document status when supplied, and unknown conditions. Multiple categories and uncertainty flags are retained.
- Versioned synthetic priority/SLA scoring records applied rules and input facts; case SLA start is stable across reclassification, while deadline/remaining/overdue reflect the current priority and time.
- Deterministic specialist routing can recommend multiple queues and uses human triage when classification information is missing or uncertain. Classification and priority do not authorize actions.
- Assessment revisions are append-only, include prior values/reasons and evidence references, and create audit entries only for material changes.
- Phase 5: versioned deterministic incident correlation using current observed source features and Phase 4 assessments. Explicit source identifiers support suspected groups across time windows; weak similarity remains unknown and incompatible identifiers reject relationships.
- Incident lifecycle, evidence summaries, append-only correlation history, membership correction, split (including ungrouped singletons), and evidence-backed merge of confirmed incidents.
- Stable incident keys, one active incident per case, transaction advisory/row locks, bounded candidate/pair processing and conservative re-evaluation on truncated searches.
- Incident correlation never reads simulator tables or hidden ground-truth labels. API response identifiers are explicit observed data; scenario-derived simulator incident keys are excluded. Grouping leaves case state, actions, decisions and authorizations unchanged.
- Phase 6: PostgreSQL durable orchestration with versioned payloads, idempotent tasks, case/incident consumers, fenced worker leases, bounded retries/backoff, dead-letter/requeue, crash recovery and deadline handling.
- Deterministic classification/routing/SLA handlers coordinate eligible case work. Phases 7-10 add specialist, Supervisor and bound synthetic execution/verification handlers; unavailable capabilities remain scheduling contracts without placeholder results.
- Human workflow reviews support role/assignee permissions, assignment, approve/reject/reinvestigation, deadlines, evidence freshness, history and audit. Workflow approval does not create action authorization or execution.
- Shared technology investigation context and individual case work are reconciled after classification and incident split/merge changes. Bounded polling, fair scheduling, operational statistics and protected versioned APIs are available.

- Phase 7: Transaction, Technology and Risk investigators with restricted normalized-evidence tools, bounded provider execution, fenced durable findings and a configurable live-disabled OpenAI adapter.
- Phase 8: Supervisor evidence cross-checking, disagreement detection, targeted bounded reinvestigation and durable advisory recommendations.
- Phase 9: deterministic policy/source/recommendation checks, authorization snapshots and separate action-bound human approvals with freshness/expiration/revocation checks.
- Phase 10: durable synthetic confirmation replay, independent source/event verification, idempotency, atomic local effects, crash recovery, terminal failure reconciliation, explicit human escalation and protected action/read APIs.

## PostgreSQL migration

The current migration state is recorded in the active checkpoint above. The following Phase 1-6 migration/test details are historical evidence, not the current head.

The complete Alembic chain (`0001` through `0006`) applied successfully to a separate fresh PostgreSQL database. Revision `0006` also passed downgrade to `0005` and upgrade back to head before full regression. Successful temporary verification databases were removed afterward. Downgrade refuses live cases using Phase 6 queued states rather than silently rewriting them.

## Historical Phase 1-6 verification

- Full Phase 1-6 suite on fresh PostgreSQL: **114 passed in 125.25s, no warnings or skipped tests**. All 79 Phase 1-5 tests remain passing, with 35 Phase 6 tests added. Inspectable test output: `phase6-test-results.xml`.
- No test warnings remain. Starlette's TestClient warning was resolved by using its supported `httpx2` transport.
- At the Phase 6 checkpoint, PostgreSQL migration head was `20261002_0006`; fresh chain and `0006` downgrade/upgrade passed.
- Phase 5 tests cover single/unknown exceptions, strong observed grouping, unrelated simultaneous failures, distinct causes sharing a trace, replay, repeated and concurrent runs, delayed/out-of-order evidence, late confirmations and contradictions, reclassification, evidence refresh, manual exclusion, split/merge, history preservation, API evidence and ground-truth isolation, and unchanged case authorization records.
- A 150-payment synthetic workload inspected bounded processing and query behavior: 18 correlation SQL statements, 50 candidates and 10 pair comparisons under configured limits. An actual `EXPLAIN (ANALYZE, BUFFERS)` entity lookup used `ix_event_records_entity_reference`. This does not establish enterprise scalability or real-world incident accuracy.
- Phase 6 verified valid/invalid transitions, relevant specialist routing, duplicate scheduling, independent-session claims and locked-row skipping, expiry/renewal/fencing, crash/restart/rollback recovery, retry exhaustion/dead-letter/requeue, atomic handler rollback, fair priority scheduling, SLA escalation, rerouting, human permissions/assignment/freshness, workflow-versus-action approval, shared incident work, split/merge, audit and unavailable-handler boundaries.
- Two separately spawned worker processes contended for one task: exactly one claim committed. Multi-host, network-partition and failover behavior remain unverified.
- A 250-case/task queue measured 20 claims plus claim history/audit in **0.2181s, 26 SQL statements**. `EXPLAIN (ANALYZE, BUFFERS)` of the actual priority claim query used `ix_tasks_ready_priority`. Detailed measurement: `phase6-workload-results.json`. This is one local synthetic measurement, not an enterprise performance guarantee.

## Event and detector behavior

- Exact repeated deliveries are counted and ignored as new events; this is not a duplicate-payment exception.
- Missing-confirmation detection uses a configurable event-time window. Source occurrence time, ingestion time, and detection time remain distinct.
- Detection evaluates the latest payment, ledger, and workflow snapshots for each source record; historical events remain stored.
- A late confirmation adds source evidence and append-only history to the existing exception.
- PostgreSQL enforces uniqueness for source event identity, exception detection identity, and exception/evidence links.
- Runtime adapters do not read `tests/ground_truth.py` or expose scenario/root-cause labels.

## API paths

- `POST /api/v1/ingestion/synthetic`
- `GET /api/v1/ingestion/status`
- `POST /api/v1/detection/run`
- `GET /api/v1/detection/stats`
- `GET /api/v1/exceptions`
- `GET /api/v1/exceptions/{exception_id}`
- `POST /api/v1/exceptions/{exception_id}/classify`
- `POST /api/v1/exceptions/{exception_id}/classify/re-evaluate`
- `GET /api/v1/exceptions/{exception_id}/classification`
- `GET /api/v1/cases/{case_id}/priority`
- `GET /api/v1/cases/{case_id}/routing`
- `POST /api/v1/incidents/correlate`
- `GET /api/v1/incidents` and `GET /api/v1/incidents/{incident_id}`
- `GET /api/v1/incidents/{incident_id}/cases`, `/evidence`, `/history`
- `POST /api/v1/incidents/{incident_id}/re-evaluate`
- `PATCH /api/v1/incidents/{incident_id}/status`
- `POST /api/v1/incidents/{incident_id}/cases`
- `DELETE /api/v1/incidents/{incident_id}/cases/{case_id}?reason=...`
- `POST /api/v1/incidents/{incident_id}/split` and `/merge`
- `GET /api/v1/cases/{case_id}/orchestration` and `/tasks`
- `POST /api/v1/cases/{case_id}/orchestrate`
- `POST /api/v1/orchestration/poll` and `/maintenance`
- `GET /api/v1/orchestration/stats` and `/health`
- Protected `POST /api/v1/orchestration/worker/claim`
- Protected `POST /api/v1/orchestration/tasks/{task_id}/renew`, `/run`, `/fail`, `/requeue`
- `GET /api/v1/reviews` and `/reviews/{review_id}/history`
- `POST /api/v1/reviews/{review_id}/assign` and `/decision`

## Future classifier interface

`Classifier` is a stable protocol implemented by `RuleBasedClassifier`. Future Decision Tree, Random Forest, or Gradient Boosting experiments can return the same categories/evidence/explanation/uncertainty/source/version/eligibility contract, optionally with a score. Models remain advisory and cannot authorize actions. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Limitations and deferred scope

- The synthetic schema has no document-status source records, so that adapter is not supported yet.
- Adapters currently collect synthetic tables as a batch; incremental source cursors and automatic source scheduling remain future integration work; the case worker is implemented and explicitly started.
- Detection and correlation remain deterministic. Specialists and Supervisor are implemented with fake-model tests and live-disabled OpenAI integration. Deterministic controls and synthetic confirmation replay/verification remain accepted; reviewed memory is implemented in Phase 11. ML and analytics remain future phases. Frontend is excluded.
- PostgreSQL concurrency verification uses independent sessions and separate local worker processes; multi-host load testing remains unverified.
- Synthetic priority weights and SLA durations are examples only, not OCBC policy. Document classification/routing can consume normalized document events, but Phase 3 has no document source adapter.
- Incident writes are serialized by a PostgreSQL transaction advisory lock. Query caps and conservative anchor comparisons can miss valid subgroups; truncation must be reviewed or processed with narrower batches. Evidence history and summaries can grow beyond the observation cap. JSON identifier scans, assessment aggregation and O(candidate cases * bounded observations) feature extraction are known bottlenecks.
- Automatic re-evaluation corrects suspected memberships; investigating/confirmed memberships require explicit operator review. Confirmation requires current evidence and resolved contradictions; shared identity alone is not proof of a root cause.
- Existing legacy payment envelopes containing the earlier simulator-derived incident field are ignored by correlation and filtered from incident evidence responses; stored records/history are preserved. The development database was not destructively reset.
- Orchestration requires PostgreSQL and an explicitly started CLI worker or protected internal API calls. It does not start background processing automatically. Discovery/reconciliation is eventual through bounded polling, including consumers attaching to replaced shared work.
- Development HTTP identity is disabled by default and cannot run in production. A real identity provider, deployment/process supervision and operational policy are required for production. The CLI is a trusted process with database credentials.
- Unimplemented tasks remain `WAITING_HANDLER`. Transaction, Technology and Risk handlers activate only with an explicitly configured provider. Phase 7 accepts validated results through its fenced service; builtin task completion still rejects future handlers.
- Queue statistics/source revision aggregates and inherited Phase 4 global payment-event priority scoring can scan growing history; incident routing serializes with correlation writes. Current synthetic results do not establish enterprise readiness.

## Phase 7 handoff

Phase 7 implements `TaskPayload`/`InvestigationResult` plus specialist output. Phase 8 implements `SupervisorOutput` and independent source validation, recommendations and targeted review history. Phase 9 implements independent deterministic controls. Phase 10 implements only synthetic confirmation replay and independent verification; see PHASE10_CONTRACTS.md for its scope and acceptance checkpoint. Banking authorization and outcomes remain independently case-scoped.

## Relevant architectural decisions

- The project remains a modular monolith with PostgreSQL as the authoritative runtime store.
- Event and exception identities are enforced by database constraints, not application checks alone.
- Case-state transitions remain enforced by `CaseLifecycleService`; detected cases start in `DETECTED`.
- Audit and detection history preserve initial detections and subsequent evidence updates.
