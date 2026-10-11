# Technology completion and cross-specialist evidence audit

**Revised live-model behavior: NOT RUN.** No paid calls or credential inspection. The historical live result remains incomplete and is not rewritten.

## Persisted evidence and diagnosis

Audited [Scenario C live results](artifacts/20261010T235050-live-f655d5/results.json), recorded tool arguments/outputs, source timestamps and identities, native prompts/contracts/validation, tool filtering, completion coordination and Supervisor evidence consolidation. Transaction completed with seven supported predicates. Technology selected NEEDS_ADDITIONAL_EVIDENCE with four supported predicates and two missing-evidence entries. All 15 applicable checks passed; three Supervisor checks were NOT RUN. The workflow ended AWAITING_HUMAN with no Supervisor. Passing applicable grounding/safety checks is not full workflow completion or proof of surrounding prose.

Technology called get_service_logs for 23:40–23:50 UTC, get_api_request for the case trace, and get_service_health for the same window. The initial timeout occurred at 23:35:52; the retry occurred just after 23:50:53. That logs window excluded both. Nevertheless, get_api_request returned all four gateway observations, so the timeout/retry statuses were available and correctly cited. The dedicated health tool returned UNAVAILABLE. Neither gateway tool supplies internal application diagnostics.

Technology did **not** call get_event_timeline. Its persisted references contain only four api_gateway records, not the confirmation or reconciliation records. Transaction retrieved the wider lifecycle through its own authorized tools. The frozen dataset shows the PENDING and CONFIRMED events, payment/ledger and workflow observations share the case correlation ID and were present before Technology's snapshot. An offline replay through the existing Technology dispatcher proves get_event_timeline returns these records within the authorized trace. This is not unavailable cross-specialist access: it is an unused, permitted source-evidence path.

The evaluator's lifecycle coverage aggregates retrieved and supported citations across specialists; Transaction supplies the confirmation/workflow coverage. Passing those checks does not mean Technology retrieved the same evidence or that its missing-evidence request has been satisfied. The unchanged workflow-complete check still requires every required specialist to complete and native Supervisor review to run.

The precise observed blockers are the model's declared internal diagnostic gap and its requested confirmation-impact assessment. A causal explanation for model behavior cannot be proven from output alone. The demonstrated contract/discoverability gap is that every role previously received the common instructions plus its role name, without a Technology-specific responsibility boundary; the timeline description named the tool but did not explain its cross-source contents. The model examined gateway outcomes and requested impact information without retrieving the existing cross-source timeline.

## Operational boundaries

| Question | Evidence and responsibility |
|---|---|
| Technical observations | Technology assesses request/error/retry chronology, narrow availability observations and limitations of technical interpretation. |
| Recorded confirmation impact | The authorized timeline exposes pending/confirmed acknowledgement, workflow and payment/ledger observations. Technology can inspect these when material to its assessment, without duplicating Transaction's full assessment. HTTP200 alone does not prove receipt or monetary consistency. |
| Payment/ledger consistency | Transaction's existing payment, ledger and confirmation tools support its operational assessment. Its completion is not an answer Technology can assume or cite without evidence retrieval. |
| Internal timeout cause | Network, overload and downstream dependencies remain hypotheses. Internal diagnostics are absent. They are material to definitive diagnosis or a remedy depending on that diagnosis, but not inherently required to report the bounded observed state and recommend diagnostic review. |
| Broader/systemic impact | This case's trace does not prove absence of effects on other customers, transactions or dependencies. Such a materially required assessment still needs evidence or human escalation. |
| Consolidated review | Native Supervisor consolidates independently validated specialist findings, source references and unverified hypotheses after all required specialist outcomes are COMPLETED. It cannot bypass a specialist's declared material gap. |
| Authorization | Specialist completion and Supervisor advice do not establish action eligibility. Independent deterministic controls, approval and execution fencing remain separate. |

The second request is materially reasonable relative to Technology's limited retrieved evidence. For this case's recorded acknowledgement/workflow state, those observations are accessible but unexamined by Technology, and Transaction has already independently assessed them. Requiring every specialist to repeat the entire Transaction assessment would be unnecessary duplication. Conversely, broader causal/downstream impact is not established by those records. The wording does not establish which broader claim the model intended, so no automatic downgrade of its missing evidence is justified.

## Minimal correction and safety

Specialist prompt version 1.5 adds Technology-only responsibility guidance: use the existing authorized event timeline before declaring material observed confirmation impact missing; distinguish gateway observations from internal diagnostics; preserve unknown cause; do not assume another specialist's conclusion, duplicate its full assessment or defer a material gap to reach Supervisor. Transaction and Risk instruction text is unchanged. Tool descriptions clarify the timeline's cross-source scope and that get_service_logs supplies normalized gateway observations, not internal logs. No expected case values, IDs, outcomes or other specialist answers are injected.

No tool registration or access grant changed. Dispatch filtering, scope/correlation checks, snapshot temporal restrictions, acceptance, strict validator and native coordinate method are unchanged. No claim is split, upgraded or accepted because another specialist completed. Both saved missing-evidence entries, hypotheses and NEEDS_ADDITIONAL_EVIDENCE revalidate unchanged. Unretrieved confirmation citations still fail. Native human review is preserved; no Supervisor task is manually created.

## Verification

- [Affected PostgreSQL phases 7–9 plus grounding, runner, semantics, temporal and A/B/C suites](artifacts/technology-scope-postgres.xml): **150 passed**, zero failures, 343.45 seconds. Fresh migration upgrade/downgrade/upgrade passed and the owned database was dropped. This batch began before the final narrowing that restored Transaction/Risk instruction text; the final focused run below verifies delivered instructions on that final revision. Validation, dispatch, completion and deterministic controls were unchanged across both revisions. The complete backend suite was not run.
- Initial focused saved-evidence/role/tool tests: **3 passed**, zero failures, 0.43 seconds; [JUnit](artifacts/technology-scope-unit.xml).
- [Final focused suite](artifacts/technology-scope-final.xml): **4 passed**, zero failures, 9.49 seconds. It includes the real native offline C path, captures delivered Technology/Transaction instructions and checks empty action/approval/authorization/operation/verification records. Native Supervisor ran through coordination, zero API requests were made and the owned database was dropped.
- [Integrity](artifacts/technology-scope-integrity.json): all 54 frozen frontend files preserved. Tool dispatch, specialist snapshot/acceptance/coordination and ten other audited native files are unchanged from the temporal correction. Changes are limited to prompt version, Technology instructions, descriptions, tests and packaging inclusion.

The existing grounding, incomplete-outcome/human-review, uncertainty propagation, wrong-citation, authorization rejection, queue fencing, source changes and A/B/C suites remain in the affected regression batch. No new dependencies. No current paid test or model-quality improvement is claimed.

## Next action

Inspect the audit and rehearse locally with `powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-LiveAITest.ps1 -Scenario C -Offline`. After offline verification, an optional separately chosen single bounded live C run can test whether GPT now uses get_event_timeline and distinguishes material assessment gaps from nonblocking diagnostics. Do not launch repeated paid prompt tuning. Review actual tool retrieval, both missing-evidence entries, source-qualified impact findings and causal calibration. If the model still identifies a material gap, retain human escalation; do not override it to obtain Supervisor execution.
