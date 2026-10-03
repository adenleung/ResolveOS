# Phase 12 governance and deployment decision

**Decision: RETAIN_DETERMINISTIC. Experimental evaluation is isolated from all
operational handlers. No inference adapter or model serving endpoint exists.**

`app/ml` has no write dependency on banking/control/execution/memory services.
The snapshot helper reads PostgreSQL evidence; the benchmark works on reviewed
synthetic manifests. No startup, worker, Supervisor or control code imports it.
Models cannot approve reviews, authorize remediation, modify banking data,
suppress escalation, replace current evidence or trust memory as authorization.
No runtime training, automatic promotion, operational-memory retraining, live
banking or paid LLM calls are added.

## Predefined promotion gates

Policy `ml-acceptance-1.0` is recorded before interpreting test metrics: minimum
.03 absolute macro-F1 improvement; positive lower bound of the family bootstrap
gain interval; no increase in critical errors; minimum .95 critical-class recall;
held-out family generalization and separate scenario/temporal challenge where
supported; p95 inference <=50ms and artifact <=10MB on documented hardware;
interpretable output, independently verified fallback and measured operational
benefit under mandatory investigator/escalation controls. Binary tasks additionally
need non-degrading Brier score and critical-positive recall at a predeclared
operational threshold. These are synthetic prototype criteria, not bank policy.
Human review must approve labels, error analysis, resources and benefit before
integration. Passing a dataset floor or topping an accuracy ranking is insufficient.

The runner always retains rules; it implements no promotion method. Gate thresholds
are recorded, not an automated certification. No model currently qualifies.

## Registration and provenance

`registration(report, model_name)` rejects untrained models, invalid versions,
unknown models, incompatible dataset/features/policy and configuration mismatch.
It produces EXPERIMENTAL metadata with operational_enabled=false and
action_authorization=NOT_EVALUATED. Versions hash dataset, task, split, seed,
feature schema, dependencies and selected hyperparameters. Reports hash complete
dataset bytes and record train/validation/test indices, configuration, libraries,
metrics and measurements. Metadata is an offline record, not an operational
registry or signed model artifact. Trained pickles are measured in memory only;
no pickle is loaded from external input or committed. There are no approved models.

Future prediction audit requirements: source evidence snapshot and prediction
time, feature/schema hash, registered artifact hash, model/config version, output,
confidence/abstention, elapsed time, deterministic baseline, fallback reason and
NOT_EVALUATED authorization. This phase records experiment provenance; it does not
produce operational prediction audits because inference is absent.

## Drift, rollback and future serving requirements

Before a future adapter, define synthetic monitored populations and fixed training
reference distributions: feature missingness, unsupported inputs, schema mismatch,
source mix, score/calibration/label drift, critical recall and p95 latency. Review
incident-family and scenario-segment changes; do not auto-retrain or interpret
unreviewed findings as labels. Initial alerts should trigger human review and
disable advice while deterministic processing continues. Numerical drift thresholds
must be calibrated on an adequate reference dataset rather than invented here.

Rollback currently requires no action: rules already run exclusively. A future
approved adapter must support a default-off configuration, independent kill switch,
bounded process-level inference deadline, freshness/schema checks, explicit
UNKNOWN/ABSTAIN, missing-artifact and timeout fallback, and immutable prediction
audits. Disable the adapter and preserve its audit/report/artifact hashes; never
roll back banking records as a model rollback. Human task-specific review must
precede any separately authorized integration change.

Inference timeout, unavailable serving model, runtime fallback and operational
prediction-audit integration tests are **not applicable** because the conditional
inference adapter was not justified or implemented. Offline unavailable-library,
readiness and artifact/schema rejection checks are present. Existing Phase 9–11
tests remain the authority for the unchanged authorization chain.
