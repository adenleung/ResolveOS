# Phase 12 dataset readiness — 2026-10-04

**Not ready for any of the five supervised operational use cases.** The
authoritative source is the existing development PostgreSQL database, read in a
repeatable-read, read-only transaction by `verify_phase12.py`; exact aggregate
evidence is in `phase12-dataset-readiness.json`. No database contents were changed.

The repository checkpoint was verified before edits: local `main` and GitHub
`refs/heads/main` both contained full backend commit
`fdd900653ecd360e0ac3e2458f7732b9ebc3a6b5`. The worktree was clean. The accepted
JUnit reports contain 268 full, 46 memory and 69 Phase 9–10 safety tests. Actual
development Alembic revision is `20261004_0012`.

## Grain, population and provenance

| Finding | Actual checkpoint |
|---|---:|
| Simulator scenario templates | 13 |
| Distinct scenarios in development | 1 (`api_timeout`) |
| Payments / ledger / confirmations / logs / workflows | 2 each |
| Normalized events | 10 |
| Detected exceptions / rule assessments | 2 each |
| Cases | 22; not all represent detected simulator exceptions |
| Simulator incident keys | 1 |
| Independently validated incident families | 0 |
| Investigation runs / independent verification outcomes | 0 / 0 |
| Validated training examples, each use case | 0 |
| Exact duplicate normalized event identities | 0 |
| Near-duplicate payment shapes (scenario and status) | 1 redundant shape |

The two exceptions are both API_PROCESSING_FAILURE. This is a one-class
population, not a classification benchmark. Two payments sharing an incident key
cannot be counted as two independent incidents; the simulator key is itself not
independent causation evidence. Shape duplication is a narrow, explicitly defined
check, not an exhaustive fuzzy-duplicate assessment.

Scenario/root-cause/outcome/incident-key fields on the two payments have no nulls.
Those complete fields are hidden simulator metadata, not validated ML targets.
Event identities are unique. No event is future-dated relative to this audit, but
confirmation occurrence times are later than their ingestion times. Both clocks
must therefore be checked at each historical prediction cutoff. The audit stores
per-source time ranges. Required feature missingness cannot be profiled as a
training matrix because no validated labelled matrix exists.

## Risks and downstream implications

- High: scenario names are embedded in payment, idempotency, correlation,
  workflow and ledger identifiers; descriptions also name the scenario. Never
  feed these strings or hidden labels to an encoder.
- High: most status/workflow/error patterns and the reconciliation delta are
  fixed by template. Randomized amounts and beneficiaries do not establish
  independent causal diversity. Observed scenario distributions cannot be
  compared when only one scenario is represented.
- High: generation uses wall-clock timestamps even with a fixed random seed.
  Reproducibility requires frozen snapshots or an explicitly controlled clock.
- High: final case states, revised current SLAs, verification outcomes, findings
  and later reviewer decisions leak information when used at intake.
- High: no SLA trajectory outcomes, reviewed specialist utility, validated
  escalation target or independently annotated positive/negative incident pairs
  exist. Rule routing and assessments are baseline predictions, not ground truth.
- Medium: reviewed Phase 11 memory is historical context only. Publication does
  not validate a classification/routing/SLA training label automatically.

Backend tests validate software contracts. Their fixture count is not the sample
size of a validated ML dataset. No temporal generalization, class-balanced score,
uncertainty interval or operational benefit can be estimated here.

## Reproducible evaluation dataset specification

The offline manifest consumed by `run_ml_benchmark.py` contains exactly
`dataset_version` (`synthetic-evaluation-1.0`), `synthetic_only` (true), `task`,
integer `seed`, boolean `scenario_holdout`, and `rows`. Each row has exactly:
`id`, `family`, `scenario`, timezone-aware ISO `prediction_at`, `features`,
`label`, `label_provenance`, `baseline`, and boolean `critical`.

IDs/family/scenario are split/provenance metadata, never features. Features use
`observed-intake-1.0`: five source record counts, system count, observed API failure
and timeout counts, case age, observed event span, evidence availability. All
are finite nonnegative numbers; count fields are integral. Missing required
features and unknown schemas fail closed. No imputer is needed. StandardScaler
is fitted on training rows only. Intake snapshots use evidence links and event
occurrence/ingestion timestamps no later than the cutoff, and reuse the actual
RuleBasedClassifier. Current SLA projections, retry/task counters, incident size,
memory and historical findings are excluded because this checkpoint does not
establish a complete historical reconstruction contract for them.

Label provenance must be `reviewed_synthetic_annotation` or
`independent_simulator_outcome`. This is an operator assertion in an offline
manifest, not cryptographic proof; reviewers must inspect supporting annotation
and trajectory records before approving a dataset. Unreviewed AI labels fail
schema validation. Do not relabel baseline outputs as independent annotations.

Required improvements per use case:

| Use case | Required synthetic evidence and evaluation unit |
|---|---|
| Classification | Independent reviewed category sets at detection; preserve multiple categories and UNKNOWN; canonical sorted joint-set labels for this harness; add category-level analysis before any integration |
| SLA | Frozen active-case landmark and original SLA/deadline history; independently generated terminal/breach times; right-censor unresolved cases rather than labelling them negative; binary 0/1 |
| Routing | Reviewed required role sets plus actual calls, duration and outcomes under unchanged mandatory-role controls; joint role-set labels; per-role and safety analysis needed before integration |
| Risk | Reviewed additional-investigation/escalation outcomes, current mandatory escalation recorded separately; binary 0/1; no suppression of mandated escalation |
| Correlation | Independent positive/negative incident-family pair annotations, including hard negatives; connected-component grouping over both pair endpoints; versioned pair-specific relational features must be added before operationally meaningful correlation benchmarks |

Generate independent causal families across templates, variations, mixed failures,
missing evidence, delayed arrival and unfamiliar patterns. A new random seed alone
is insufficient. Freeze dataset bytes, clocks, annotations, baseline rule outputs
and source revisions. The readiness floor is 30 independent families per label,
with at least 10 per label in train and 5 each in validation/test; this is a
minimum engineering gate, not statistical proof of adequacy. Label provenance
and independence still require review. Use incident-family 60/20/20 partitions
(rounded to retain three nonempty partitions), fixed seed, and a separate
scenario-family holdout. Scenario groups are unioned when incidents span scenarios.
For pair data, connected components must be constructed before passing `family`.
Large pair graphs may make independent splitting impossible; reject that dataset.
Temporal holdout remains deferred until there are enough dated independent families.

Run `python verify_phase12.py` with an explicitly configured development
DATABASE_URL. It exports aggregates only. Run future approved manifests separately
with `python run_ml_benchmark.py manifest.json --output report.json` and optional
`requirements-ml.txt`. Never use the development data as a mutable training store.
