# Live runner RuntimeError fix — 11 October 2026

The saved live attempt `artifacts/20261010T165439-live-6510ae/` made four real requests: two Technology turns and two Transaction turns. Both outputs reported NEEDS_ADDITIONAL_EVIDENCE. The original report contained no stored task snapshot and the disposable database was no longer available, so original persisted transitions cannot be independently reconstructed. The saved outputs were replayed offline through the unchanged native investigators and orchestrator to establish the exact failing branch.

Root cause: `InvestigationRunner.coordinate()` sends incomplete specialist results to `OrchestrationService._request_review()`, which schedules REQUEST_HUMAN_REVIEW and moves the case to AWAITING_HUMAN. Supervisor is deliberately not scheduled for that path. The runner's next `assert_read_only_queue()` rejected the human-review task because it was outside ALLOWLIST, raising `RuntimeError("unrelated_or_unsafe_queue_task")`. Its outer handler reduced this to RuntimeError and exported no task/evidence records before cleanup. This was a harness mismatch with a legitimate escalation, not a Supervisor validation failure, follow-up investigation or unexpected banking action.

The reproduction before the fix failed with the same four processed stages and `setup_or_harness_error`. See `artifacts/runtimeerror-before-fix.xml`. Offline replay of the actual saved tool requests and structured outputs now appears in `artifacts/runtimeerror-replay/recorded-replay/`; only synthetic identities, evidence IDs and time windows are rebound to the new disposable database. Four offline model turns occur, with no OpenAI requests.

Minimal fix: recognize same-case, unclaimed human-review tasks only as a terminal observation. The read-only execution ALLOWLIST is unchanged. Human review is never claimed or activated; actions, verification tasks and unrelated cases still fail the guard. Already-processed human review is rejected. Incomplete findings remain incomplete and Supervisor is never forced to run.

The task loop now exports case records and a limited queue projection in its inner finally block, before the owned database is dropped. Reports record fixed safe error codes, current stage, last processed stage and last successfully completed task stage. Arbitrary exception messages, HTTP headers, settings and connection URLs are not exported. Unknown errors receive an exception-class code; known queue errors distinguish unrelated work, unsafe task types and unexpectedly processed human review. Human review records `human_review_required` without a harness error.

The historical Transaction model output called an uncited confirmation finding SUPPORTED and represented status_code as string "504" against integer 504. Offline replay confirmed the unchanged native validator labels these INSUFFICIENT_EVIDENCE and CONTRADICTED respectively. Its prose tying the absent confirmation to timeout remains an unverified causal interpretation. No validation, fencing, policy or Supervisor behavior changed.

Fifteen focused runner tests passed after the fix, including actual-output replay, safe error reporting, snapshot retention on an injected harness failure, unrelated/action-task rejection alongside human review, and PowerShell propagation of a real incomplete offline runner's exit code 1. See `artifacts/runtimeerror-after-fix.xml`. The normal offline launcher case still completed Supervisor review and returned 0 (`artifacts/20261010T170445-offline-8cf39e/`). Targeted backend regressions passed 103 tests, zero failures/errors/skips, in 351.68 seconds. They covered orchestration, investigators, Supervisor, hardening and grounding, with fresh migrations and a downgrade/upgrade round trip. Results are recorded separately in `artifacts/runtimeerror-backend.xml` and its log. The latest 15-test runner verification includes added diagnostics/replay/launcher cases beyond the runner cases collected in that earlier-started backend run; a full unrelated backend suite was not repeated.

No paid OpenAI request was made during this fix. The historical live attempt is not a successful live multi-agent evaluation; Supervisor execution remains unconfirmed and the reproduced native path skips it. A retry can safely produce human review and exit 1 again if evidence remains incomplete. Do not interpret that expected escalation as a successful Supervisor test.

After offline verification, retry only one bounded case locally from the ResolveOS directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-LiveAITest.ps1
```

Inspect `stop_reason`, `error_code` (if present), `last_completed_stage`, `records`, `queue_snapshot` and evaluation checks in the new results.json. Scope and spending limits are unchanged.
# Subsequent evidence-contract correction

The historical string/integer 504 mismatch described below is corrected by the [HTTP status contract fix](HTTP_STATUS_ACCEPTANCE_REPORT.md). Historical artifacts are preserved; new evaluations distinguish supported and rejected predicates and report legitimate skipped Supervisor checks as NOT RUN. Human-review fencing is unchanged.

