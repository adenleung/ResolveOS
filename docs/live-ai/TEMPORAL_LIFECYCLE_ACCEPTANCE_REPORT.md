# Temporal lifecycle evidence guidance correction

**Revised live-model behavior: NOT RUN.** No paid requests were made and no credentials were inspected. Historical live evidence is unchanged.

## Confirmed cause and minimal correction

Inspected specialist instructions, shared Finding/Output contracts, provider schema generation, exact evidence validator, role tools, native completion/coordination and Scenario C source-qualified evaluation. In [the saved C run](artifacts/20261010T232007-live-c0f77d/results.json), Transaction combined two observations under one `confirmation_status == CONFIRMED` predicate. Its citations are `4dc549f5-ad61-4503-ab87-4390b109b3f8` (PENDING, 2026-10-10 23:06:09 UTC) and `c89dcdef-d3b3-45f4-acd6-cb239ff156bf` (CONFIRMED, 23:20:10 UTC). The validator correctly requires every cited source to support the exact value and returns CONTRADICTED. This is a contradicted predicate, not proof that the underlying lifecycle is inconsistent.

The prior instructions required splitting multi-field claims but did not explicitly address different temporal values of the same field. Finding's claim and citation fields also lacked this guidance. Model intent cannot be proven from output alone; this is the identified contract ambiguity, not a claim about the model's private reasoning.

Specialist prompt version 1.4 now requires one observed field/value at a specific source event or occurrence time, with separately cited predicates for each temporal state. Lifecycle summaries may connect these observations; they must use occurred_at rather than ingestion order and must not invent timestamps. Multiple citations remain permissible only when each independently supports the exact predicate. Simultaneous conflicting observations remain potential material contradictions. Finding descriptions carry the same requirements into the existing provider schema and shared Supervisor Finding contract. No new output field, coercion, splitting, claim rewriting or validator acceptance rule was introduced.

The validator, authorized tools, native completion gate, orchestration, Supervisor service, policies and execution service are unchanged. The C evaluator already checks source-qualified lifecycle predicates separately and does not need relaxed grading. Historical Transaction output still revalidates CONTRADICTED and incomplete. The historical Technology output remains incomplete. No Supervisor was scheduled by the revalidation.

## Separate Technology audit

Technology retrieved gateway records through get_service_logs and get_api_request; get_service_health reported UNAVAILABLE. Its four supported status predicates establish initial HTTP504, retry HTTP202, retry HTTP200 and a separate later health HTTP200. These records do not establish internal resource saturation, dependency delays, continuous availability, or causal recovery.

Its declared missing evidence is internal service logs around the initial timeout, with unresolved diagnostic questions retained in hypotheses. The saved summary nevertheless infers a transient issue causing the timeout and later resolution/mitigation. Those causal statements are model interpretations, not independently supported conclusions. This recurring diagnostic request is not a validator-imposed requirement for definitive causation: existing completion semantics allow bounded advisory completion with supported observations and nonblocking unresolved questions. The model itself declared the logs missing and selected incomplete status. That outcome is preserved; no root-cause logs were invented, missing evidence removed or COMPLETED outcome forced. Determining whether revised guidance improves real reasoning requires a future live run and manual review.

## Verification and limitations

- [Affected PostgreSQL phases 7–9, grounding, runner, completion semantics and A/B/C regressions](artifacts/temporal-lifecycle-postgres.xml): **143 passed**, zero failures, 327.47 seconds. Fresh migration upgrade/downgrade/upgrade passed and the owned database was dropped. Production code was finalized before this batch; the additional saved-output/provider-description checks are covered by the final focused run below.
- [Focused PostgreSQL temporal suite](artifacts/temporal-lifecycle-final.xml): **12 passed**, zero failures, 18.10 seconds; fresh migration upgrade/downgrade/upgrade and disposable database cleanup passed. This includes the real native snapshot test for future occurrence/ingestion exclusion and legitimate historical evidence retention.
- [Final focused saved-output and contract checks](artifacts/temporal-lifecycle-saved.xml): **13 passed**, one deliberately deselected database test, zero failures, 1.37 seconds. This additionally tests both actual saved C model outputs without rewriting their claims or outcomes, and guidance propagation into both strict provider schemas.
- [Actual PowerShell C offline rehearsal](artifacts/20261010T232904-offline-cdefa0/REPORT.md): exit 0, all 18 checks passed, native Transaction/Technology and Supervisor completed, advisory ESCALATE, zero API requests, no banking execution, database dropped. Deterministic fixtures do not demonstrate GPT-quality improvement.
- [Integrity record](artifacts/temporal-lifecycle-integrity.json): all 54 frozen frontend files match baseline. Eleven audited native files remain byte-for-byte unchanged from Phase 18; only specialist instructions and contract descriptions/version changed. Packaging adds the new regression file. Historical artifacts and prior archives are preserved.

Coverage includes separately cited lifecycle observations, mixed-state citations, same-time material conflicts, wrong source and unretrieved/foreign citations, future records, historical record retention, existing stale/superseded-source Supervisor safeguards, unchanged human escalation and authorization rejection. Incorrect narrative chronology is explicitly **not certified** by field equality: the regression demonstrates this boundary rather than claiming an automated temporal-language validator exists. Independently checked source times remain available for manual comparison. Separate supported predicates alone do not prove source consistency, causation, lifecycle completeness or action eligibility. The full backend suite and revised live model were not run.

## Bounded local handoff

From ResolveOS, with the existing key in your own terminal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-LiveAITest.ps1 -Scenario C
```

This performs one paid case only when you execute it: at most ten requests, 120000 accounted tokens and USD0.15 conservative estimated cap. No automatic retries or additional benchmark were added. Add `-Offline` for an unpaid rehearsal. Inspect the printed artifact directory's REPORT.md, results.json and requests.jsonl; compare each confirmation predicate's citations and source occurrence times, review causal prose separately, and retain native human review if either investigator remains incomplete. A/B selectors and default A remain intact. No production-readiness conclusion is made.
