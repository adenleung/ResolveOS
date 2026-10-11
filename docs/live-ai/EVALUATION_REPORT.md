# ResolveOS live-AI runner handoff

Update, 11 October 2026: the user ran a subsequent four-request live attempt that did not complete Supervisor review. Its harness error has been reproduced and fixed offline; see [RUNTIMEERROR_FIX.md](RUNTIMEERROR_FIX.md). The original handoff evidence below remains historical, and no new paid test was made for this repair.

Live-model tests: **NOT RUN**. Codex did not access the user's working terminal key or send an OpenAI request. Live GPT performance, token consumption, latency, billed cost and live Supervisor quality are unmeasured. The delivered runner is intended for one explicit local execution.

## Observed offline workflow

The final PowerShell rehearsal is recorded in `artifacts/20261010T165339-offline-ed62a0/`. It used disposable PostgreSQL and deterministic providers with the existing InvestigationRunner and SupervisorRunner. The script is unchanged in its operational path for live mode; only the injected providers differ.

| Component | Observed offline result | Live result |
| --- | --- | --- |
| Ingestion / detection / classification / routing | Native services completed | NOT RUN |
| Technology Investigator | Retrieved API source via authorized tool; 504 predicate independently matched | NOT RUN |
| Transaction Investigator | Retrieved payment source via authorized tool; SETTLED predicate independently matched | NOT RUN |
| Risk Investigator | Not routed for this scenario; no task forced | NOT RUN / conditional |
| Supervisor | Native review accepted evidence and recorded ESCALATE | NOT RUN |
| Banking safety | No authorizations, approvals, actions, execution operations or verification records; payment, ledger and confirmation state unchanged | NOT RUN |

Fifteen automated case checks passed. Exact observation accuracy was 2/2 for the predefined payment-status and API-status targets. Two specialist tool calls occurred, each retrieving current source evidence. Specialist and Supervisor source IDs and typed values were rechecked independently by the test runner, and all AI authorization flags remained NOT_EVALUATED. No unsupported accepted predicate appeared. This says nothing about GPT's free-text hallucination rate or causal analysis quality: the offline outputs were deliberately deterministic.

The synthetic payment was SGD 100, SETTLED, with one POSTED debit and no confirmation receipt; its confirmation-service request recorded HTTP 504 and 31,000 ms latency. Detection generated two exceptions for that same payment. Only the missing-confirmation case was queued; the API-failure case remained unscheduled. The scoped task guard rejected any unrelated or execution task before claiming, and the normal queue's default execution handlers were removed from this runner's queue instance.

No policy or production backend behavior was changed. The disposable database was dropped after export. All 54 frozen frontend source files matched the existing preserved baseline, including the user's pre-existing `next-env.d.ts` difference. Dashboard and Pixel Operations Room files were not edited.

## Regression evidence

Nine focused runner guard tests passed, covering global request/token/cost limits, shared accounting across providers, unknown-usage failure reservations (including missing native usage telemetry), no retry after failure, usage overruns, pre-claim rejection of unsafe/unrelated tasks, and specialist/Supervisor source rechecks rejecting a falsely labelled SUPPORTED predicate. See `artifacts/runner-guards.xml`.

The full backend regression passed **386 tests, zero failures, errors or skips**, in 1,064.52 seconds. Fresh migrations and a downgrade/upgrade round trip also passed. Results are recorded in `artifacts/backend-regression.xml` and `artifacts/backend-regression.log`. The suite includes existing specialist grounding, cross-case tool denial, fabricated citations, Supervisor disagreement, uncertain-case escalation, independent authorization and execution fencing. These are offline tests in fresh owned PostgreSQL, not paid model tests. After the final runner-only usage-telemetry guard was added, its focused nine-test suite and the complete single-case offline rehearsal passed again; the unchanged production backend suite was not repeated.

The PowerShell launcher installed the existing dependencies in an ignored virtual environment and completed an offline run. A direct launcher exit-code check returned 0. It introduces no additional package requirements; installation uses `requirements.txt` and `requirements-hardening-constraints.txt`.

## Findings and limits

The normal WorkQueue includes execution handlers even when specialist handlers are passed explicitly. The runner therefore narrows its instance allowlist and checks every queued task before activation and claiming. The normal worker is not invoked. Focused queue-poison tests verify the guard. No production queue change was needed.

An initial rehearsal stopped because no DATABASE_URL was configured in Codex's process (`artifacts/offline-smoke/`). The runner now uses the documented local synthetic PostgreSQL default when settings provide no URL. Subsequent direct and launcher rehearsals passed. This was a runner setup correction, not an existing backend defect. No investigator, Supervisor, policy, frontend or banking action code was changed for this mission.

The existing orchestrator routes incomplete specialist findings to human review before scheduling Supervisor. A truthful GPT response listing missing evidence may exercise that branch. The runner will record the incomplete workflow and failed Supervisor-completion check instead of manufacturing completion. Supervisor REINVESTIGATE schedules follow-up work, but the runner stops after that first review to bound spending. Risk remains conditional on the actual classifier's routing.

Live limits are fixed to one case, ten model requests, 120,000 conservatively budgeted tokens and USD 0.15 estimated cost across all roles. Actual provider usage is recorded when observable; failures retain conservative unknown-usage reservations and halt calls. Actual invoiced cost remains unknown. These estimates use standard uncached rates documented in README, not an account billing API.

Read each raw model output beside the validated persisted result. Exact-field predicates are independently checked; prose and hypotheses remain interpretations. Assess root-cause restraint, missing evidence and free-text hallucinations manually against `ground-truth.json`. A natural live disagreement is not guaranteed, and an absent disagreement cannot prove model review quality. Even an automated live pass would apply only to this synthetic case and would not demonstrate production readiness.

Run and inspection instructions: [README.md](README.md).
