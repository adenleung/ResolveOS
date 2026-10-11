# Final backend hardening acceptance — 10 October 2026

**Partial mission acceptance; no 95/100 or production-readiness claim.** Fixed demonstrated verification, replay-integrity, evidence-grounding and temporal-memory weaknesses. Added actual headless evidence export, fair offline A/B/C measurement, offline AI contracts, explicit Option B experiment, component-unavailability evaluation, read-only diagnostics, runtime-process smoke, pinned observed constraints and reproducible handoff. PostgreSQL, modular monolith, durable queue, current controls, action-specific review, independent verification, human-reviewed memory and all frontend files are preserved.

Fresh final regression: **377 passed, zero failures/skips**, versus 354 fresh original tests. Clean isolated Python environment and another freshly migrated database also passed **377**, zero failures/skips. Critical safety gate 69 passed. Seven headless outcomes, 300 matched offline observations, 30 AI contract checks, twelve memory queries and ten component-unavailability runs are independently linked artifacts, not folded into test totals. 54 frontend files match session-start bytes; the pre-existing next-env.d.ts difference remains untouched.

The most important discovered defect was false closure after ledger balance changed: initial smoke traces retain this failure; current snapshot and verifier compare balance and the final cohort contains zero false verified outcomes. This is a finite synthetic gate, not a real-world zero-error guarantee. No additional source action was justified. No live provider, real bank, customer data, trained operational ML, timed employee study or GitHub push was used.

| Area | Baseline | Final | Evidence |
|---|---|---|---|
| Backend reliability | 354 fresh baseline tests; balance omitted | 377 final tests; balance protected | Final JUnit, critical-safety.xml |
| End-to-end resolution | Three existing demo journeys | Seven headless recorded scenarios | headless-demo.json |
| Operational value | No matched study | 300 offline observations; no proven advantage over A | operational.json/.csv |
| AI investigation accuracy | Live unmeasured | Live remains unmeasured; 30 offline checks | ai-contract-evaluation.json |
| Escalation / human routing | Existing tests | Frozen offline cohorts with explicit precision/recall | operational.json |
| Memory retrieval | Overlap/recency | Snapshot cutoff; experimental Option B, original default retained | memory-evaluation.json; temporal tests |
| Remediation coverage | Confirmation replay only | Same safe action; broader actions deferred | coverage matrix |
| Banking realism | Existing synthetic scenarios | Seven detailed exception specifications | banking-exception-catalogue.json |
| Security | Scoped tools/controls | Conflict replay, partial predicate and temporal fixes; controls preserved | Phase 6–11 and new tests |
| Worker recovery | Existing fenced queue | Fresh concurrency/process/failure tests and headless lease recovery | Final JUnit |
| Token efficiency | Live unmeasured | No new AI calls; remains unmeasured | Offline provider metadata |
| Cost / verified resolution | Unmeasured | Human-only assumption model; measured total unknown | operational metadata; cost report |

## Conservative internal estimate

| Internal criterion | Maximum | Baseline | Current | Point rationale / evidence |
|---|---|---|---|---|
| Operational value / banking relevance | 20 | 8 | 11 | Catalogue and matched offline study; no employee/live superiority evidence |
| Backend integration / execution | 20 | 18 | 19 | 354 baseline/full final JUnit, seven headless journeys; narrow action coverage |
| Reliability / security / controls | 20 | 14 | 18 | Measured critical balance fix, replay/grounding/time fixes, real concurrency; production failover absent |
| AI accuracy / evidence | 15 | 5 | 7 | 30 contracts and PostgreSQL grounding; actual model accuracy unknown |
| Memory / workflow efficiency | 10 | 6 | 7 | Temporal safety and small Option B comparison; no investigation benefit study |
| Benchmark / demonstration | 10 | 2 | 7 | 300 replayable offline observations, failure records and assumptions; no live/human study |
| Documentation / handoff | 5 | 4 | 5 | Source-backed reports, commands, history and archive integrity verification |

Baseline estimate 57/100; current estimate 74/100. These are subjective internal engineering estimates, not official competition weights or observed probability. Each award is bounded by cited evidence and deductions for unverified areas. The official six judging headings were read from the supplied OCBC briefing; UX/presentation are not reassessed because the frontend is frozen. The target 95 is not established. Live AI quality, actual operational value, broader safe remediation, memory generalization and recovery/load evidence explain the remaining gap.

Business finding: A and C achieve equivalent rule-covered offline resolution; this does not prove an AI advantage. B adds scripted review overhead while preserving control/verification standards. Human cost/time remain assumptions, infrastructure/model costs unknown. Option B improves top-rank ordering on a tiny constructed corpus and is retained as an opt-in experiment; no significance or investigation benefit is claimed.

## Reproduce

Use Python 3.11+ (observed 3.13), a PostgreSQL administrative connection with disposable database creation permission, and `py -3.13 -m pip install -r requirements.txt -c requirements-hardening-constraints.txt`. Set DATABASE_URL in the process environment without saving or printing secrets. Existing local synthetic compose maps PostgreSQL to 5433; use 127.0.0.1 where appropriate. These commands create/own disposable databases; no development reset is allowed.

```powershell
py -3.13 verify_backend.py --report docs/hardening/artifacts/final-postgres.xml
py -3.13 run_headless_demo.py --scenario all
py -3.13 run_operational_benchmark.py
py -3.13 run_stage_metrics.py
py -3.13 run_ai_contract_evaluation.py
py -3.13 run_memory_evaluation.py
py -3.13 run_agent_ablation.py
py -3.13 verify_hardening_runtime.py
py -3.13 write_hardening_reports.py
```

Do not use these integration fixtures directly on a shared database. Dataset generation refuses to alter an existing frozen set; use a new version/directory for a changed study. Before a benchmark rerun, choose a new --output path to retain earlier results. JSONL preserves completed observations if execution is interrupted. A final accepted report requires complete JSON and zero false closure; a partial run is not acceptance. The normal verifier retains its generated failed-test database on failure for diagnosis; no shared database is targeted. Evaluation runners remove their owned disposable database even on error.

Known limitations and acceptance needed are in FINAL_GAP_REGISTER.md. Archive file receipt and hashes are generated by package_hardening.py; original ZIP remains untouched. Local Git checkpoints recover original history and hardening changes; no remote update is claimed. Full user mission remains incomplete in the areas explicitly marked partial/deferred/not run.
# Live evidence contract addendum — 11 October 2026

The HTTP status evidence contract and live-runner evaluation have a separate [updated acceptance report](../live-ai/HTTP_STATUS_ACCEPTANCE_REPORT.md). This addendum preserves the historical hardening results below. No new live-model tests were run for this fix; supported saved predicates were revalidated offline, and native human-review escalation remains in force.

