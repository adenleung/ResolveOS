# Local live AI integration test

The user subsequently executed a historical live attempt: **ATTEMPTED, not passed**, with four requests and no confirmed Supervisor execution. See [the RuntimeError fix report](RUNTIMEERROR_FIX.md). This repair was verified offline; Codex made no paid requests or credential inspection. Run the command below in the VS Code PowerShell terminal where your existing environment key works.

From the `ResolveOS` directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-LiveAITest.ps1
```

This explicitly opts into one paid synthetic case. The launcher creates an ignored Python 3.13 virtual environment and installs the existing `requirements.txt` using the existing observed constraints. No new dependency or OpenAI SDK is required. Python 3.13 and the existing local PostgreSQL service must be available. Subsequent runs reuse the virtual environment. Every invocation is a new case and may incur a new small charge; no automatic repeat or benchmark runs occur.

The runner uses the configured `DATABASE_URL` from the environment or ResolveOS settings. If absent, it uses the documented synthetic Docker endpoint at localhost port 5433. Only loopback PostgreSQL endpoints are permitted. The PostgreSQL account needs CREATE DATABASE permission. It creates a random `resolveos_backend_verify_<10hex>` database, applies the existing migrations there, exports results, and drops that owned database in the existing helper's `finally` block. It never migrates, truncates, seeds, or drains the admin/development database. A forced process termination can leave the owned test database behind; its name is recorded in results when creation succeeds. No real bank connection or real customer data is used.

The executable reads `OPENAI_API_KEY` only in its locally invoked `--live` branch, never persists it, and uses the native `OpenAIProvider`. It does not accept a key argument. Keep the key in your working terminal's environment. Settings, environment dumps, URLs, HTTP headers and arbitrary exception strings are excluded from exported results. The native provider's fixed Responses API endpoint is retained, with `store=false` and no provider retry.

## What runs

The scenario has a settled SGD 100 payment, one matching posted debit, no confirmation record after 15 minutes, and a confirmation API observation with HTTP 504 / 31,000 ms. Timeout is an observed symptom; evidence does not prove it caused the absent confirmation. Ground truth is written before investigation and is never sent to the model.

The existing ingestion and detection services create a missing-confirmation exception and an API-failure exception for this same synthetic payment. Only the missing-confirmation case is scheduled. The second detected case remains unscheduled and is listed in the report. Classification routes Transaction and Technology. Risk runs only if the classifier actually routes it; no Risk task is injected to increase calls. Native investigators retrieve evidence using role-scoped tools, and the native validator checks their outputs. Native Supervisor reviews accepted findings when the orchestrator schedules it. Supervisor evidence comes from the validated stored references and current source rechecks; it has no model-selected retrieval tools.

The queue is checked before activation and claiming. An unrelated case or unsafe task type stops the test with a specific harness error. A same-case, never-claimed `REQUEST_HUMAN_REVIEW` is an expected terminal observation; it remains outside the execution allowlist and is never claimed. The runner stops with `human_review_required`, retains the task/evidence snapshot, and returns exit code 1 because Supervisor execution and the full evaluation are incomplete. Execution handlers are removed from the queue instance even though the normal queue registers them by default. No action control evaluation, approval, execution service or confirmation replay is invoked. No policy definition is edited. Bank-state snapshots and empty authorization/action/operation/verification tables provide independent safety checks.

The test stops after one Supervisor review, at a provider failure, or at a budget boundary. Targeted follow-ups remain recorded and unprocessed. If a specialist reports incomplete evidence, the existing orchestrator may send the case directly to human review and never schedule Supervisor. This is reported as an incomplete multi-agent test, not silently overridden. A recommendation without safe escalation/follow-up fails the case's escalation check even though it remains advisory.

## Fixed limits

- Model: `gpt-4.1-mini-2025-04-14`.
- One case; at most 10 model requests across all roles and Supervisor.
- At most three iterations and twelve tool calls per investigator; at most 2,048 output tokens per request.
- Aggregate token allowance 120,000; estimated-cost allowance USD 0.15. Per-agent limits are also applied by existing runners.
- USD 0.40 per million input tokens and USD 1.60 per million output tokens, standard uncached rates checked against [official OpenAI documentation](https://developers.openai.com/api/docs/models/gpt-4.1-mini) on 2026-10-10. Cached input savings are deliberately not credited.
- Preflight reservations include serialized strict tool/output schemas and 4,096 tokens of protocol allowance. These are conservative estimates, not the server's tokenizer or a billing guarantee. Reported usage replaces reservations after a successful response. A failed/unknown-usage request retains its reservation and stops further calls; no retry occurs. Actual invoiced cost is not observable through the native provider. Account billing remains the authoritative charge record.

Missing or zero native usage telemetry also retains the reservation and halts requests. The caps cannot be increased through command-line arguments. Run a broader paid workload only after deciding to authorize that additional work.

## Inspect the results

Each invocation creates a unique directory under `docs/live-ai/artifacts/`:

- `REPORT.md`: mode, live execution status and automated checks.
- `results.json`: synthetic ground truth, raw structured model outputs, separately validated persisted findings, routing assessments, source observations, evidence provenance, task and tool history, Supervisor results, usage, latency, estimated cost, and safety checks.
- `requests.jsonl`: one record per attempted model turn; tool names/arguments and structured responses, no HTTP headers or settings.
- `ground-truth.json`: predefined facts and quality rubric, kept out of prompts.

Exit code 0 means all automated checks passed for that invocation; 1 means a check failed or setup/execution stopped. Inspect `error_code`, failed checks, investigator telemetry and queued task results. A live status of RUN records an execution attempt, not a success claim: always inspect the checks. Failed provider calls retain unknown-usage reservations; a recorded FAILED investigation must not be treated as a validated model result.

Grounding is independently rechecked against retrieved source IDs and exact typed field values. Only predicates are independently verified. Surrounding prose, causal explanations, hypotheses, missing-evidence wording and unsupported free-text assertions require manual review against ground truth. The runner exports them but does not claim an automated hallucination detector can prove their correctness. Confirm that the timeout is treated as a hypothesis for the missing confirmation, that confirmation receipt / downstream health / causal trace are identified as unresolved, and that uncertainty leads to review rather than authorization.

Supported predicates are evaluated separately from contradicted, insufficient and unevaluated findings. Legitimately skipped Supervisor checks show `NOT RUN` (JSON check value `null`); the workflow remains incomplete with exit code 1. The provider requires integer HTTP status predicates. A documented compatibility conversion accepts only canonical three-digit ASCII HTTP status strings for `status_code`, with an audit record, without converting source evidence or other fields. See the [HTTP status acceptance report](HTTP_STATUS_ACCEPTANCE_REPORT.md).

Supervisor disagreement, fabricated citations and unsafe claims are tested in the existing offline regressions. One natural live case does not guarantee a disagreement occurs; do not count an absent disagreement as proof of live disagreement-detection quality. Automated observation accuracy measures the settled-payment and 504 predicates; it is not an overall semantic accuracy score. Even a successful live invocation establishes only this synthetic test's scope, not production readiness.

For an unpaid local rehearsal use the same command with `-Offline`. Deterministic providers exercise the native runners and database workflow; those results are explicitly labelled NOT RUN for live-model tests.

For direct execution with an already configured Python environment:

```powershell
py -3.13 run_live_ai_test.py --live
```

Phase 17 adds an independently selectable corroborated scenario. Use `powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-LiveAITest.ps1 -Scenario B` for one local bounded paid run, or append `-Offline` for an unpaid rehearsal. `-Scenario A` retains the original case; omission defaults to A. No live Scenario B result is claimed by the offline implementation. See [Phase 17 acceptance and review criteria](PHASE17_ACCEPTANCE_REPORT.md).

The subsequent [completion-gate audit](COMPLETION_GATE_ACCEPTANCE_REPORT.md) distinguishes advisory completion from definitive causal diagnosis and action eligibility. It clarifies material evidence gaps and forwards unverified specialist hypotheses to Supervisor without changing native completion or authorization rules. The saved live outcome remains incomplete; no new live behavior is claimed.

Phase 18 adds `-Scenario C` / `--scenario C`, a detected exception followed by post-detection acknowledgement/retry/reconciliation evidence. Use `powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-LiveAITest.ps1 -Scenario C -Offline` for rehearsal. The same command without `-Offline` explicitly invokes one bounded paid local run. Ground truth, source observations and a pre-model tool sufficiency audit are hash-frozen. See [Phase 18 acceptance, artifacts and live review criteria](PHASE18_ACCEPTANCE_REPORT.md).
