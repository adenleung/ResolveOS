# Phase 12 model comparison — 2026-10-04

**Retain deterministic rules for every use case. No operational model trained,
evaluated, selected or enabled.** Dataset readiness fails before model fitting.
Exact machine-readable outcomes are in `phase12-model-comparison.json`.

| Candidate | ResolveOS benchmark status | Operational metrics |
|---|---|---|
| Existing deterministic rules (mandatory baseline) | Blocked: no independent labelled evaluation population | Not estimable |
| Logistic Regression | Blocked by dataset readiness | Not estimable |
| Decision Tree | Blocked by dataset readiness | Not estimable |
| Random Forest | Blocked by dataset readiness | Not estimable |
| XGBoost | Blocked by dataset; optional library unavailable | Not estimable |
| LightGBM | Blocked by dataset; optional library unavailable | Not estimable |

This table applies separately to classification, SLA, routing, operational risk
and pairwise correlation. Null/absent scores do not mean zero errors or zero
latency. No critical error rate can be measured without validated labels. No
specialist/LLM calls avoided, token savings, resolution-time reduction, escalation
correctness or human-review reduction is claimed. DBSCAN was not run: clustering
ground truth and adequate independent families are absent.

The framework supports restrained two-configuration searches, train-only scaling,
validation macro-F1 selection, one untouched test evaluation per experiment,
CPU/single-worker trees, library/configuration/dataset/split versions, training
wall time, per-row p95 inference time, serialized in-memory model size and Python
allocation peaks. Allocation peaks exclude native-library/process memory and
are not a process resource guarantee. Baseline outputs must be frozen from the
existing implementations: classifier/routing/SLA rules, deterministic control
escalation and DeterministicCorrelationEngine.evaluate_pair respectively.
The intake snapshot helper implements the classification baseline. Other baseline
exporters await task-specific validated datasets; the manifest requires their
reviewed output and never derives labels from them.

Metrics include macro F1, per-class precision/recall, confusion matrices, critical
errors with explicit denominators, UNKNOWN prediction counts, binary PR-AUC
(average precision), Brier scores, reliability bins and thresholds .25/.5/.75.
Binary rule outputs receive the same probability metrics where they are 0/1.
Natural estimator probabilities are evaluated without post-hoc calibration;
future fitted calibration requires training-only folds. Family bootstrap intervals
use 200 fixed-seed resamples of complete families for F1 gain. Routing and
multi-category classification currently use joint-set labels; per-role/category
analysis remains required before integration. Pairwise scores are not clustering
scores or proof of common causation.

Optional dependencies were installed only in ignored workspace `.ml-deps` for
estimator smoke validation. `verify_ml_framework.py` is designed to train Logistic
Regression, Decision Tree and Random Forest on deliberately separable **toy
fixtures** and check reproducibility, calibration metrics and metadata. Execution
was **blocked before any model fit**: Windows Application Control blocked native
ML DLL loading (`_special_ufuncs` in the first attempt, `_argkmin_classmode` in the
final attempt). No successful estimator
smoke validation or calibration validation is claimed. The runner now records
library import failures as UNAVAILABLE and retains rules. Evidence and installed
versions are in `phase12-framework-smoke.json`; optional requirements are pinned.
XGBoost/LightGBM were neither installed nor smoke tested. An environment permitting
these established libraries is needed before accepting the trained-model path.

The no-training branch is reproducible even without any ML dependencies, tested
for every use case, and is the actual Phase 12 deployment decision.
