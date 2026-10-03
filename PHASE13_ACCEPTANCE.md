# Phase 13 — operational intelligence acceptance

**Accepted within the synthetic prototype scope.** Targeted PostgreSQL:
**21 passed, 0 failed, 0 skipped** in 24.825s. Full PostgreSQL regression:
**332 passed, 0 failed, 0 skipped** in 509.741s (all 311 prior tests retained).
Evidence: `phase13-targeted-results.xml`, `phase13-full-regression-results.xml`.
Both runs applied fresh migrations and downgrade/re-upgrade in disposable databases.
The diagnosed failed fixture database was verified empty and removed.

## Recovery and baseline

Initial local main and remote main matched `f0ed616ff2462602fbd538ec67f9b59bb2c61292`.
The working tree was clean. Branches, all-reachable log, reflog, stashes and full
unreachable-object inspection contained no Phase 13–15 source. `d5a8afb` and
`006b52c` were not local objects; direct remote fetches could not find either ref.
No recoverable frontend source existed. No destructive Git command was used.

Fresh baseline: **311 passed, 0 failed, 0 skipped in 494.290s**, evidence
`recovery-baseline-results.xml`. PostgreSQL development connectivity and actual
revision `20261004_0012` were verified. Every regression uses a separately created
disposable PostgreSQL database; fresh migration, downgrade to 0006 and re-upgrade
are exercised by the existing verifier. Development is never reset or truncated.

## Implemented

- `app/intelligence`: strict typed report and relationship schemas, bounded
  read-only service and authenticated versioned APIs.
- GET `/api/v1/intelligence/report`: category frequency, observed system/endpoint
  recurrence, persisted escalation/handover/investigation/reinvestigation and
  missing-evidence/verification-failure observations, conservative hypotheses and
  candidate prevention improvements.
- GET `/api/v1/intelligence/incidents/{incident_id}/relationships`: current and
  removed memberships, split/merge history, observed shared features, evidence
  references and contradictions. No graph database.
- Duration metrics: detection-to-first-classification, first investigation claim
  waiting time, per-attempt runtime, human action-approval waiting time (including
  rejection), execution queue-to-effect, effect-to-independent-verification,
  combined execution-to-verification and total independently verified resolution.
- Intervals with missing/future end timestamps are incomplete; negative intervals
  are invalid, never clamped into successful zero-duration observations. Completed
  medians exclude both. Parallel attempts are not summed into case resolution time.
- Verified resolution requires the latest independent confirmation verification,
  its actual VERIFIED execution action and current RESOLVED case; a case flag or
  prior successful verification alone is insufficient.
- Every finding includes calculation method, cohort window, stable persisted
  references, affected cases, explicit uncertainty and query/reference caps.

Read APIs use PostgreSQL read-only transactions with 5s statement timeout.
Server-issued WORKER/OPERATIONS_REVIEWER identities are required. A trusted service
scope can narrow case grants; empty grants return an empty cohort. Incident reads
fail closed if any membership/history refers outside a narrowed grant. Existing
development authentication remains disabled by default and unavailable in production.
Enterprise tenant identity/ACL integration remains outside the synthetic prototype.

## Limits and semantics

Reports select at most 500 cases created within an explicit window (default 30
days, maximum 365), 2,000 rows per record kind and 20 references per finding.
Truncation is visible; partial counts are not population-wide rates. Categories
can overlap; revisions do not multiply exception counts. API recurrence requires
an actual observed failure, not simply presence of a log. Reported investigator
missing-evidence claims remain interpretations. Reinvestigation means another
attempt for the same case/role, not mandatory parallel roles counted as rework.

Overview status/priority/current-SLA fields are current projections for the selected
cohort, not historical status reconstruction or a historical SLA-breach rate.
Older active cases outside the cohort are excluded. No LLM, simulator ground-truth,
trained ML or policy/routing modification is used. Hypotheses never establish
common causation or authorize remediation. Repeated observations are not assumed
to be independent incident families.

## Tests and changes

21 new tests cover actual recurrence/counts, latest revisions, scopes, empty data,
incomplete/future/negative intervals, truncation/window validation, source isolation,
missing evidence, split/merge history, protected typed APIs, production auth rejection,
actual independent execution verification, rejected-approval waiting time and
queue/attempt duration arithmetic. An added fixture initially failed because it
looked for investigator work before the existing classification handler ran; it was
corrected to drain the existing orchestration workflow. Existing tests were unchanged.

No migration is necessary; development stays at `20261004_0012`. New source:
`app/intelligence/{__init__,contracts,service,api}.py`,
`tests/test_phase13_postgres.py`. Integration: `app/main.py`. Documentation:
CURRENT_STATE, ARCHITECTURE, MASTER_BUILD_SPEC, PHASES, CHANGELOG, README and this report.
Optional libraries, environment credentials and database dumps are excluded.

`phase13-observed-report.json` records the actual read-only development cohort:
22 open cases, 2 exceptions, 2 current overdue SLAs and zero independently verified
resolutions. These are persisted observations, not illustrative dashboard numbers.

Phase 14 must not begin until this phase's passing checkpoint is committed,
pushed and the GitHub SHA verified.
