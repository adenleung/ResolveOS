# Phase 18 — Scenario C acceptance and live handoff

**LIVE MODEL TEST NOT RUN.** No paid calls were authorized or made. No credentials were inspected. Offline success does not demonstrate real GPT Supervisor completion.

## Design and source sufficiency

The [pre-implementation design and Evidence Sufficiency Matrix](PHASE18_DESIGN.md) map operational questions to real registered tools, available fields, temporal boundaries and unavailable internal diagnostics. The latest historical B output requested post-timeout confirmation/retry records. C supplies those observations without claiming the initial timeout's internal cause is known.

The missing-confirmation exception is genuinely detected with only the initial records present. Native classification routes Technology and Transaction before any successful acknowledgement exists. After native ROUTE_CASE completes, fixture ingestion records a confirmation-only retry accepted (HTTP202), acknowledgement receipt (CONFIRMED), completed retry response (HTTP200) and reconciliation observation (RECONCILED). Those events use real PostgreSQL wall timestamps and are ingested after detection. Detection attaches the later evidence to the existing exception with LATE_EVIDENCE_RECEIVED; it does not resolve the case. No Supervisor task is directly created by the runner.

Payment and ledger remain SETTLED / POSTED, one SGD100 debit, ending balance900 against the fixture's starting balance1000. The existing ledger schema associates payment FK and ledger transaction ID; it has no independent account identifier. No account API or application diagnostic connector was invented. Historical PENDING and subsequent CONFIRMED records have distinct source identities; they are a lifecycle, not contradictory same-time statements. The later `/health` response establishes only that observation.

The runner performs a deterministic pre-model sufficiency audit through registered role tools. Eight required operational observations must be accessible, otherwise it fails before a provider request. Generated IDs, final source dataset, observation timestamps, ground truth and audit hashes are frozen before the first model turn. The prior plan is retained separately. The final evaluation rechecks hashes; modification is a failure. Source-qualified lifecycle checks supplement generic field-value checks, so a response on `/health` cannot substitute for retry response evidence.

Follow-up fixture creation can add only the declared confirmed receipt to simulator confirmation history. A guard rejects any payment, ledger or existing-confirmation mutation before establishing the investigation bank-state baseline. This fixture is not model remediation. After investigation starts, bank records must remain unchanged. Authorization, approval, action, operation and verification tables must remain empty.

## Final observed offline run

Actual PowerShell command `-Scenario C -Offline` returned exit 0 on the final harness revision:

- [REPORT](artifacts/20261010T231043-offline-d518a2/REPORT.md)
- [Machine results and task/tool history](artifacts/20261010T231043-offline-d518a2/results.json)
- [Frozen ground truth](artifacts/20261010T231043-offline-d518a2/ground-truth.json)
- [Synthetic dataset](artifacts/20261010T231043-offline-d518a2/synthetic-input.json)
- [Source timestamps and identities](artifacts/20261010T231043-offline-d518a2/source-observations.json)
- [Pre-model sufficiency audit](artifacts/20261010T231043-offline-d518a2/evidence-sufficiency.json)
- [Frozen hashes](artifacts/20261010T231043-offline-d518a2/frozen-input-hashes.json)
- [Sanitized turn telemetry](artifacts/20261010T231043-offline-d518a2/requests.jsonl)

Technology and Transaction both completed through native InvestigationRunner. Technology called get_api_request and get_event_timeline. Transaction called get_payment, get_ledger_entries, get_confirmation_events and get_transaction_timeline. Risk was not routed. Native coordination scheduled REQUEST_SUPERVISOR_REVIEW only after the validated specialist completions. Native Supervisor persisted an advisory ESCALATE outcome with 14 independently checked supported conclusions and both specialist hypotheses retained as UNVERIFIED_INTERPRETATION. The case ended ESCALATED, not RESOLVED. No authorization or execution occurred. The disposable database was dropped.

All **18 applicable checks passed**. These are deterministic provider fixtures exercising native mechanics. They copy observed field values from returned tools; they never operate in the live branch, rewrite GPT outputs or manufacture a Supervisor task. The real model can still select an incomplete outcome and take the native human-review path.

## Three evaluation layers

| Layer | Observed offline result / live limitation |
|---|---|
| Mechanical integration | Native ingestion, two-phase detection/evidence attachment, classification, routing, tools, specialists and Supervisor completed; correct task order persisted |
| Evidence correctness | 14/14 accepted specialist predicates independently matched cited retrieved typed source values; no contradicted, insufficient or unevaluated findings in this positive fixture. Eight of eight required accessible lifecycle observations were examined and cited. Supervisor rechecked all 14 conclusions. These small-fixture counts are not population accuracy estimates. |
| Operational reasoning | Internal cause remains unknown; source chronology and no-execution safety are inspectable. Free-text GPT chronology, causal calibration and recommendation usefulness are NOT RUN and require separate manual review. |

Review criteria for a future live result: distinguish settlement from acknowledgement, initial pending from subsequent receipt, accepted retry from completed response, and synthetic reconciliation observation from independently verified resolution. Do not claim the timeout caused the delay or that HTTP200 proves full recovery. No further payment instruction should be proposed as an automatic response. Existing action eligibility and approvals remain separate. Mark materially missing evidence when the proposed assessment actually depends on it; preserve nonblocking internal diagnostic questions in hypotheses. Inspect Supervisor cross-checking and its handling of those uncertainties rather than counting only its request.

No held-out generalization claim is made. Identity/timestamps vary each invocation, but this remains one designed operational fixture. No repeated paid trials, live prompt tuning, expected-answer injection or threshold adjustment occurred.

## Regression and preservation evidence

- Initial C-specific adversarial suite: **7 passed**, zero failures, in 24.86 seconds; [JUnit](artifacts/phase18-lifecycle.xml).
- Final harness/grounding/semantics/A/B/C suite after fixture mutation fencing: **68 passed**, zero failures, in 66.24 seconds; [JUnit](artifacts/phase18-final-runner.xml).
- Broader affected PostgreSQL result is recorded in the final addendum. The complete backend suite was not executed and is not claimed.
- Negative coverage includes wrong/foreign citations, wrong source values, invalid HTTP forms, unsupported composite claims, contradictory evidence, material gaps, stale/expired leases, unrelated and executable tasks, failed provider calls, authorization attempts, source changes, global budgets, missing receipt before any provider call, frozen truth tampering, and unexpected ledger mutation during fixture follow-up.
- Existing A/B and saved live-output regression behavior is retained. Historical live reports and earlier source ZIPs were not overwritten.
- [Integrity record](artifacts/phase18-integrity.json) confirms all 54 frozen frontend files and 13 native backend files match the preserved completion-gate archive. No native provider, contracts, prompts, validator, tools, Supervisor, queue, detection, classification, control or execution service changed for Phase 18. Changes are limited to the existing harness/launcher, tests, packaging and new documentation/artifacts.

## Budget and paid local handoff

Limits remain one selected case per invocation, ten model requests total, 120000 accounted tokens, USD0.15 conservative estimated cap, three specialist iterations, twelve tool calls and 2048 output tokens per request. Failed or uncertain usage stays reserved and stops subsequent calls; no retry, fallback or background paid benchmark was added. Native model remains gpt-4.1-mini-2025-04-14. Real provider input/output tokens, attempted/completed calls, per-turn latency and estimated costs are exported when observable; actual billing remains unobserved. Offline zero provider usage is not GPT telemetry.

Unpaid local rehearsal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-LiveAITest.ps1 -Scenario C -Offline
```

When you explicitly choose to execute **one bounded paid run** in your own terminal with its existing environment key:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-LiveAITest.ps1 -Scenario C
```

No new dependencies or manual migrations are required beyond the existing Python3.13/PostgreSQL setup; the launcher reuses its isolated backend environment and each run owns a new migrated database. A/B selectors and legacy default A remain supported. Inspect the new artifact directory printed by the launcher. Exit 1 means incomplete or failed objective; safe human escalation is not an unsafe banking result and must not be overridden to reach Supervisor. Expected live status remains **LIVE MODEL TEST NOT RUN** until actual persisted provider evidence is available. No production-readiness claim is made.

## Final verification addendum

Affected PostgreSQL phases 7–9 plus grounding, runners, completion semantics and A/B/C: **131 passed**, zero failures, in 291.07 seconds; [JUnit](artifacts/phase18-postgres.xml). Fresh migration upgrade/downgrade/upgrade passed, and the owned database was dropped. This batch began before the final follow-up fixture mutation guard was added; the final 68-test runner suite and PowerShell rehearsal above verify that guard and the final harness revision. All native backend components remained unchanged throughout this phase. The full backend suite was not run.

Offline Scenario C acceptance is achieved within this deterministic synthetic scope. Native Supervisor participation is demonstrated offline with persisted records; real GPT Supervisor completion is **NOT RUN**. The complete source ZIP is produced with CRC, per-file SHA256 and frontend baseline verification; its adjacent package receipt records archive identity. Prior source archives are preserved.
