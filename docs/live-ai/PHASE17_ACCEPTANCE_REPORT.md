# Phase 17 — Scenario B native investigation validation

**LIVE MODEL TEST NOT RUN.** No paid API requests were made and no credentials were inspected. This is an offline implementation and local-live-test handoff, not evidence of live Supervisor completion.

## Inspection and design

The [pre-implementation design decision](PHASE17_DESIGN.md) documents the native completion gate and previous scenario's material evidence gaps. Inspected components include investigation contracts/provider/service/tools/validation, Supervisor service, configuration, ingestion/detection, queue ownership, disposable database/test fixtures, native offline providers, the existing runner and launcher. The latest historical live run `20261010T223409-live-adc754` remained incomplete and is unchanged.

Scenario B retains a settled SGD100 payment and matching posted debit with balance900; it adds a PENDING acknowledgement, reconciliation awaiting confirmation, and a later HTTP200 health request after the initial HTTP504 /31000ms gateway observation. Sources share identifiers, amount/currency and bounded timestamps. There is no successful confirmation and no fabricated technical causation. Gateway health evidence is retrieved through `get_service_logs`/`get_api_request`; the existing dedicated `get_service_health` tool still reports UNAVAILABLE. No new health connector was added.

Both scenarios are selected with `--scenario A|B` or launcher `-Scenario A|B`. Omitted selection defaults to A for command compatibility. One scenario runs in each newly created database/artifact directory. Ground truth, source record IDs and synthetic input are saved before the first model turn; no grading rubric or expected outcome enters prompts or tool metadata. Source values are naturally visible as evidence.

## Observed offline results

The native classifier routed Transaction and Technology. Risk was not routed. Both specialist services retrieved evidence through permitted tools and completed. Native `InvestigationRunner.coordinate()` scheduled Supervisor; no direct Supervisor task was injected. Native Supervisor independently reviewed and persisted an ESCALATE advisory result, with no banking authorization or execution. Offline providers demonstrate orchestration mechanics only and are not an unbiased model-quality test.

The first offline rehearsal exposed a deterministic-provider gap: its payment-only query omitted ledger and confirmation evidence, so the stricter B observation rubric correctly failed. The offline provider was fixed to call all three existing Transaction tools; expectations and source truth were not relaxed. The failing artifact is preserved at `artifacts/20261010T223957-offline-8b8009`. It was a fixture deficiency, not a production agent or orchestration defect.

Representative complete rehearsal: [REPORT](artifacts/20261010T224116-offline-53b1f7/REPORT.md), [results](artifacts/20261010T224116-offline-53b1f7/results.json), [dataset](artifacts/20261010T224116-offline-53b1f7/synthetic-input.json), [truth](artifacts/20261010T224116-offline-53b1f7/ground-truth.json). The final revision's artifacts are linked in the verification addendum below.

| Evaluation | Scope and observed evidence |
|---|---|
| Investigation correctness | Four required predicates: SETTLED, POSTED, PENDING and HTTP504; all observed in the completed offline rehearsal |
| Grounding precision | Seven accepted specialist predicates independently matched their retrieved source IDs and exact typed values; seven out of seven for this fixture only |
| Evidence completeness | Payment, ledger, pending confirmation, initial timeout and later health request retrieved; broader internal service diagnostics remain unavailable |
| Unsupported predicates | None accepted in the completed offline rehearsal; negative citation/type tests remain required |
| Contradiction handling | Existing Supervisor disagreement, changed-source and fabricated-reference regressions exercise negative branches; the B fixture does not contain a same-source contradiction |
| Causal reasoning | Not independently established: timeout and pending acknowledgement correlate; internal cause remains unknown |
| Escalation | Operational review remains advisory; an injected incomplete B provider causes native human review and no Supervisor, with exit 1 |
| Supervisor quality | Native output persisted and citations rechecked offline; actual GPT review quality NOT RUN |
| Tool reliability | Inspect per-agent tool telemetry; dedicated health and cross-transaction tools remain unavailable by architecture |
| Tokens, requests, cost | Zero OpenAI requests; offline token usage is not real provider telemetry. Actual billed cost unobserved |
| Latency | Per-turn wall time exported; deterministic rehearsal latency is not live model latency |

Free-text review criteria: confirm the payment/ledger and pending acknowledgement are distinguished; do not call a health response proof of initial outage causation; distinguish known later availability from internal diagnostics; reject fabricated retry histories; check proposed next steps are advisory and uncertainty is explicit. Subjective correctness and causal quality require manual review. No ROI or general accuracy claim follows from this small fixture.

## Safety and evaluation

The HTTP status fix, evidence IDs, temporal windows, source correspondence, leases and task allowlist remain unchanged. No production backend investigation, authorization or execution policy was altered for Phase 17. Neither runner nor providers call banking action handlers. Unexpected or unrelated tasks fail the queue guard; human review stays outside the claim allowlist. Risk is never injected. All bank-state snapshots and authorization/action/operation tables are checked.

Supported and rejected findings remain separate. Valid human-review bypasses have Supervisor checks NOT RUN, never PASS. Incomplete or failed evaluations return exit 1. A safe Scenario B escalation can be a valid operational outcome while failing the full Supervisor objective; reports state this separately. A naturally reached Supervisor may recommend, reinvestigate or escalate within the predefined advisory outcome classes. Follow-up tasks are recorded and left unprocessed after the first Supervisor review.

Limits remain one case, 10 requests, 120000 combined accounted tokens, three specialist turns, twelve tool calls, 2048 output tokens/request and USD0.15 conservative estimate. Unknown billed usage retains reservations and stops further calls; no automatic retry/fallback or repeated live run was added. Estimated spending is not actual billing.

## Verification status

Scenario-specific tests passed 3/3. The final focused runner/grounding and affected PostgreSQL runs are recorded in the verification addendum. Existing Scenario A saved-output replay continues to test human review without Supervisor and without execution. Frozen frontend checks and archive integrity are recorded separately.

## Verification addendum

- Final harness/grounding revision: **52 passed**, zero failures, in 30.40 seconds; [JUnit](artifacts/phase17-final-runner.xml). This run follows the operational-reporting and expected classification-category corrections.
- Final direct Scenario B rehearsal: [REPORT](artifacts/20261010T224400-offline-50e4a5/REPORT.md) and [results](artifacts/20261010T224400-offline-50e4a5/results.json). Both specialists completed, native Supervisor ran, all 15 checks passed, zero paid requests, database dropped.
- Actual PowerShell `-Scenario B -Offline` launcher returned 0: [REPORT](artifacts/20261010T224416-offline-3d70bf/REPORT.md) and [results](artifacts/20261010T224416-offline-3d70bf/results.json).
- [Integrity record](artifacts/phase17-integrity.json): source SHA256 hashes and all 54 frozen frontend files verified. Prior live artifacts were not rewritten.
- Affected PostgreSQL phase 7–9 plus grounding/runner/scenario batch: **115 passed**, zero failures, in 226.46 seconds; [JUnit](artifacts/phase17-postgres.xml). Fresh migration upgrade/downgrade/upgrade passed and the database was dropped. This batch began before the final reporting/category-label edits; the final 52-test harness run above verifies those edits. Production backend components were not changed during Phase 17.

## One-command local live handoff

From the ResolveOS folder, in your terminal with its existing environment key:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-LiveAITest.ps1 -Scenario B
```

This command performs **one bounded paid run** when you choose to execute it. No key argument/file is needed. Add `-Offline` for an unpaid rehearsal. Scenario A remains selectable with `-Scenario A`.

Inspect the newest artifact's `REPORT.md`, `results.json`, `requests.jsonl`, `synthetic-input.json` and `ground-truth.json`. Verify actual request roles include SUPERVISOR, the persisted review outcome and source checks pass, and safety tables remain empty. A successful HTTP response alone is insufficient. If GPT reports material missing evidence, expect human review and exit 1; do not override it. Live acceptance and production readiness remain unproven.
