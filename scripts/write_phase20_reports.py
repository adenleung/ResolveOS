"""Source-backed Phase 20 documentation; no model calls or fabricated review."""
import json
import hashlib
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];DOC=ROOT/'docs/evaluation/phase20'
def doc(name,text): (DOC/name).write_text(text.strip()+'\n',encoding='utf-8')
def main():
    offline_dir=DOC/'artifacts/final-v11-offline';rules_dir=DOC/'artifacts/final-v11-rules'
    if not (offline_dir/'results.json').exists(): offline_dir=DOC/'artifacts/pilot-offline'
    if not (rules_dir/'results.json').exists(): rules_dir=DOC/'artifacts/pilot-rules'
    offline=json.loads((offline_dir/'results.json').read_text());rules=json.loads((rules_dir/'results.json').read_text())
    history=json.loads((DOC/'artifacts/historical-replay-v3/historical-results.json').read_text())
    counts=offline['metrics'];table=['| Historical artifact | Saved investigators | Supervisor | Replay scope |','|---|---|---|---|']
    for h in history:
        roles='; '.join(f"{r['role']}: {r.get('historical_outcome',r['status'])}" for r in h.get('replays',[]))
        table.append(f"| {Path(h['source']).name} | {roles or 'Not enough saved records'} | {'RAN' if h.get('supervisor_historically_ran') else 'NOT RUN / not confirmed'} | {h.get('status','Current-contract offline replay; no new calls')} |")
    historical_table='\n'.join(table)
    layertext=f'''Current deterministic offline: {len(offline['cases'])} cases; detection {counts['detection_accuracy']['numerator']}/{counts['detection_accuracy']['denominator']}, classification and routing 10/10. Accepted predicates {counts['grounding_precision']['numerator']}/{counts['grounding_precision']['denominator']}; required facts {counts['required_fact_coverage']['numerator']}/{counts['required_fact_coverage']['denominator']}. Four native Supervisor reviews, five human escalations, one no-exception control. These are fixture mechanics, not GPT quality. All ten external reasoning verdicts remain INCONCLUSIVE / NOT REVIEWED. No completion or escalation is certified by a predicate count.'''
    doc('EVIDENCE_SUFFICIENCY_RUBRIC.md','''# Evidence sufficiency rubric
Evaluator phase20-quality-1.1 is independent research code and never writes operational tables. Source field questions and role owners are frozen in quality_rubric before model turns. Per-case experiment configuration freezes evaluator source SHA256, experiment source SHA256, native prompt hashes/version and limits. Frozen truth remains private to the runner/scorer, not prompt/tool metadata. Version 1.1 adds per-role atomic predicate coverage including currency; tool retrieval alone is not evidence that the required field was cited. Earlier prototypes remain version 1.0 and are not overwritten.

Every missing-evidence string initially receives AMBIGUOUS_MATERIALITY. A keyword match is never used to decide semantics. An expert supplies role, exact missing-item index/hash, registered criterion ID, rationale and whether the recommendation requires the cause. Two independent completed reviews must agree on verdict/dimensions/binding identities before binding is used. Different rationales do not imply disagreement. Adjudication requires a third reviewer, packet hash and both exact review hashes; disputed bindings remain unaccepted until separately reconciled by reviewers.

The bound criterion yields MATERIAL_OPERATIONAL_GAP when required for the role/explicit cause-dependent recommendation, otherwise NONBLOCKING_DIAGNOSTIC_GAP. Additional classifications are orthogonal: CROSS_SPECIALIST_INFORMATION for another owner (never automatically nonmaterial); ACCESSIBLE_BUT_NOT_RETRIEVED from actual authorized ToolDispatcher coverage; UNAVAILABLE_SOURCE for absent internal-diagnostic/health/applicability connectors. An already retrieved observation is separately labelled and requires review of whether the claimed gap actually refers to more information. A field-level source availability result does not establish semantic equivalence to arbitrary prose.

Root cause may be nonblocking for recorded state but material to a remedy relying on causation. No universal rule marks root-cause requests unnecessary. Authoritative receipt can be genuinely absent even if PENDING/FAILED acknowledgement rows exist. No hypothesis is moved out of missing_evidence; no saved finding is split/repaired; no investigator is promoted. Rubric/binding errors fail the evaluator, not quietly generate a favourable judgement.''')
    doc('SPECIALIST_SCOPE_EVALUATION.md','''# Specialist responsibility evaluation
Transaction requirements cover recorded payment, ledger, acknowledgement and reconciliation fields. Technology requirements cover gateway status/latency, observed retry chronology and confirmation/workflow impact available on authorized timelines. Risk requirements cover relevant financial/duplicate/approval observations only when natively routed. Requirements use declared source types and source-qualified fields; policy applicability remains unavailable. They are frozen research questions, not new operational completion rules.

Source access is independently probed using the existing ToolDispatcher on the investigator's same-case, as-of eligible snapshot. Cross-case identities and future observations are excluded. Superseded versions of the same source reference are not required retrieval; different source references can represent lifecycle events. Unavailable service health is not substituted by a later HTTP200 /health observation. No role is required to call all tools or duplicate another specialist's complete assessment.

Free-text role alignment and recommendation dependence remain NOT REVIEWED. The existing role contract already tells Technology to use get_event_timeline for material payment-confirmation impact, retaining diagnostic uncertainty. No native prompt, validator, coordination gate, Supervisor or policy service was modified during Phase 20. Saved prompt 1.5 output shows ongoing misses; this warrants measurement, not another automatic prompt adjustment.''')
    doc('TOOL_SELECTION_ANALYSIS.md',f'''# Tool-selection analysis
{layertext}

Each quality-evaluation.json exports role tools, called names/statuses/IDs, actual read-only availability probes, retrieved source types, current role-relevant available/retrieved/omitted event IDs and exact coverage numerator/denominator. Failed/denied calls and explicit UNAVAILABLE responses remain separate. Duplicate names are candidates only: native telemetry lacks arguments, so repeated names may have different filters. No penalty applies for avoiding an irrelevant tool.

Historical saved GPT: 20261010T235050-live-f655d5 Technology used get_service_logs, get_api_request and unavailable get_service_health, without get_event_timeline. Authorized replay exposes confirmation/payment/ledger/workflow observations it did not retrieve. 20261011T000752-live-454cab again omits the timeline despite prompt 1.5. This is observed tool-selection weakness, not proof that every claimed missing diagnostic is nonmaterial. Actual missed IDs and source identities are in [historical replay](artifacts/historical-replay-v3/historical-results.json).

Scope exclusions and relevance are explicit. Source-only deterministic providers already know how to query broad timelines; their retrieval coverage is not evidence of GPT tool-selection reliability.''')
    doc('ESCALATION_CALIBRATION.md','''# Completion and escalation calibration
Research verdicts: CORRECT_COMPLETION, CORRECT_ESCALATION, UNNECESSARY_ESCALATION, UNSAFE_COMPLETION, INCONCLUSIVE. Only two finalized agreeing expert reviews or a provenance-checked adjudication finalize a decision. Missing/disputed reviews remain inconclusive. Known native safety failures retain independent critical flags even if an expert gives a favourable narrative verdict.

Unnecessary escalation rate = unnecessary / reviewed escalations (correct + unnecessary). Unsafe completion rate = unsafe / reviewed completions (correct + unsafe). Correct completion rate uses the same completion population. Correct escalation recall = correct escalation / adjudicated cases requiring escalation (correct escalation + unsafe completion). Counts/denominators and inconclusive populations are always exported; zero denominators are NOT APPLICABLE/null. With no external expert reviews, all current reasoning populations have zero evaluable denominator.

Native human-review proportion is a workflow observation, not evidence of calibrated reasoning. A Supervisor advisory ESCALATE following supported specialist completion differs from specialist incompletion blocking Supervisor. Integration can succeed when native human escalation correctly preserves an incomplete result. Phase 19 fixture expected-decision checks are retained for regression acceptance, but the Phase 20 integration layer ignores the expected decision and does not award reasoning correctness. More completions are never the optimization target.''')
    doc('HISTORICAL_FAILURE_ANALYSIS.md',f'''# Historical saved-model analysis
New live calls: **NOT RUN**. Ten historical directories inspected; eight retain specialist records, two do not. Replays are current-contract validations of existing model outputs, not fresh GPT experiments. Older A artifacts lack source authorization templates; their scalar predicate replay does not establish complete tool/context provenance. Original source/hash files are preserved and rehashed after replay.

{historical_table}

Observed temporal-composite failure: saved C 20261010T231900-live-fb9d64 contains a Transaction lifecycle claim citing different states with one expected value. Current offline validation retains the finding and rejects mismatched citations; it does not split or upgrade it. Actual occurred_at chronology is separately exported; narrative ordering remains expert review. The saved canonical HTTP504 string in A may be normalized by the already documented historical compatibility rule during current-contract replay; this is not retroactive historical success.

Observed retrieval failure: C 20261010T235050-live-f655d5 Technology missed available timeline observations while requesting confirmation impact. Transaction completed; Technology did not; no Supervisor. Latest saved C 20261011T000752-live-454cab has both roles incomplete, four historical requests, 14981 input + 2127 output tokens and no Supervisor. Both request diagnostic information; Technology again does not call timeline. Hypothesized network/overload/dependency causes remain unverified.

Engineering interpretation: role guidance alone has not guaranteed appropriate retrieval or causal calibration. Unnecessary escalation is a candidate requiring a recommendation-specific expert assessment, not an automatic conclusion. Legitimate missing receipt, unsupported predicates and unverified composite findings remain blocking. No saved safe escalation is relabelled a successful Supervisor run. All materiality requests are initially ambiguous; semantic expert binding is needed. No new prompt changes are made.''')
    doc('MODEL_QUALITY_SCORECARD.md',f'''# Model quality scorecard
**LIVE MODEL EVALUATION NOT RUN.** Historical GPT and current deterministic mechanics are separate populations. External narrative review: NOT REVIEWED. No arbitrary composite score.

{layertext}

Evidence metrics remain source-qualified n/d; causal/narrative chronology is not inferred from equality. Per-case quality files retain rejected predicates, gaps, hypotheses, roles, Supervisor context and multiple diagnostics. Toolkit availability is not a proof of broad service recovery or action eligibility. [Offline suite]({offline_dir.relative_to(DOC).as_posix()}/results.json); [rules suite]({rules_dir.relative_to(DOC).as_posix()}/results.json).

Provider request/input/output/accounted-token/cost fields are zero in unpaid runs. Fixture turn counts and latency are separate. Actual billing remains null/unobserved. Historical request counts are not added to current usage. Case and provider wall times are not operator labour savings. Unsafe completion and integrity failures independently fail acceptance; reviewed narrative decisions cannot erase them.''')
    doc('BASELINE_COMPARISON.md',f'''# Rules-only versus assisted comparison
{layertext}

Both tracks share deterministic ingestion/detection/classification/routing, verified 10/10. Native rules-prefix snapshots inside each assisted case share exact input identities. The standalone rules track uses fresh equivalent fixtures and stops at its actual capability boundary. Baseline advisory synthesis and model Supervisor review are CAPABILITY NOT AVAILABLE IN BASELINE, not zero accuracy.

Additional observed offline capabilities: source-tool collection, independently checked atomic findings, uncertainty transfer and four native Supervisor reviews. These fixture mechanics add no demonstrated GPT reliability or labour value. Human escalation is retained and review burden is unmeasured. Unavailable policy mapping/internal diagnostics are unchanged. Direct comparison is limited to shared capabilities. Model latency/cost and expert narrative quality require an authorized live evaluation; employee time/ROI require a blinded counterbalanced operator study with measured active time, rework and quality. No hypothetical human timing is used.''')
    doc('HUMAN_REVIEW_RUBRIC.md','''# Independent human review
Each case contains review-packet.json binding the complete native records/truth hashes, plus review-template.json. Inspect results.json, source-observations.json, ground-truth.json and quality-evaluation.json alongside the packet, including the Supervisor and tool histories. The review command verifies frozen files, truth/record packet hashes and observation equality before accepting any review. Make two external copies, record anonymous reviewer code and independent comments, and assess grounded observations, technical interpretation, causal calibration, gap materiality, recommendation, role alignment, Supervisor synthesis and safety. States: NOT REVIEWED, REVIEW IN PROGRESS, REVIEWED, DISAGREEMENT, ADJUDICATED. A single completed reviewer cannot finalize quality; an unfinished review must not be counted as correct.

Missing-information semantic bindings require role/index/claim_sha256/criterion_id, explicit recommendation_requires_cause and rationale. Do not bind merely because a phrase contains timeout or logs. Read the actual proposed recommendation, registered question, available sources and retrieved IDs. Cross-specialist ownership does not imply nonmateriality. Capture concerns even where every predicate is supported. Unresolved causal narratives must remain hypotheses, not established causes.

Use `py -3.13 -m scripts.evaluate_quality review --input CASE_DIRECTORY --reviews REVIEW1.json REVIEW2.json --output NEW_DIRECTORY`. Disagreement requires an independent third reviewer and `--adjudication FILE` with reviewer, decision, rationale, packet_sha256 and review_hashes. It finalizes only the decision; disputed semantic bindings are not silently accepted. Reconciled binding analysis requires two matching reviewer submissions. All outputs use new directories; operational outcomes and historical reports stay unchanged. No real independent expert review has been conducted in this phase.''')
    doc('LIVE_EVALUATION_PROTOCOL.md','''# Controlled real-model handoff
No paid calls were authorized or made. Use the existing local environment; no key argument/file or secret inspection is needed. Native model profile is explicitly selected via --model gpt-4.1-mini-2025-04-14. Only this reviewed profile is accepted; another model needs independently reviewed schema/pricing support. Per-case model/limits are supported via --case-config JSON keyed by selected IDs. A case configuration cannot add cases or exceed previous caps.

From ResolveOS with existing DATABASE_URL and backend Python dependencies:

```powershell
py -3.13 -m scripts.run_evaluation_benchmark --track offline --output docs/evaluation/phase20/artifacts/LOCAL-offline
py -3.13 -m scripts.run_evaluation_benchmark --track rules --output docs/evaluation/phase20/artifacts/LOCAL-rules
py -3.13 -m scripts.evaluate_quality integrity --input docs/evaluation/phase20/artifacts/LOCAL-offline
py -3.13 -m scripts.evaluate_quality suite --input docs/evaluation/phase20/artifacts/LOCAL-offline --output docs/evaluation/phase20/artifacts/LOCAL-scorecard
```

All output paths must be NEW; choose a different suffix on each invocation. One explicitly authorized paid development case (NOT RUN here):

```powershell
py -3.13 -m scripts.run_evaluation_benchmark --track live --cases P19-07 --model gpt-4.1-mini-2025-04-14 --authorize-paid-cases 1 --case-max-seconds 600 --batch-max-seconds 900 --batch-max-requests 10 --batch-max-tokens 120000 --batch-max-usd 0.15
```

Separately explicitly authorized two-case development batch (NOT RUN here):

```powershell
py -3.13 -m scripts.run_evaluation_benchmark --track live --cases P19-07 P19-02 --authorize-paid-cases 2 --case-max-seconds 600 --batch-max-seconds 1800 --batch-max-requests 20 --batch-max-tokens 240000 --batch-max-usd 0.30
```

Only selected cases execute. Default remains unpaid. Native metering still wraps the real provider directly, so missing usage retains reservations and halts; deadline fencing sits outside it. No automatic retry/fallback. Runtime checks occur before requests and task stages; native socket timeout is shortened to the remaining deadline. These are cooperative investigation deadlines, not hard process kills: migrations, socket I/O edge conditions and DB cleanup may extend wall time. Ctrl+C preserves partial records and drops the owned DB via finally; the safety guard stops unrun cases. Critical safety failures, uncertain billed usage, batch budget/deadline or interruption stop further work. Per-case limits remain 10 requests,120000 accounted tokens, USD0.15 estimate,3 specialist turns,12 tools,2048 output tokens/request.

P19-07 separates slow/failed API advisory assessment from definitive cause; P19-02 tests genuinely absent authoritative receipt. Together they test completion and escalation, not an attempt to make Scenario C reach Supervisor. A meaningful improvement is source retrieval and independently reviewed proportionate decisions with uncertainty preserved, not higher completion counts. Expected outputs include native tasks/results, actual role requests, usage, frozen prompt/evaluator/configuration hashes, quality layers and review packets. Estimated caps are not actual bills. Inspect REPORT.md/results.json/quality-evaluation.json and run the quality suite command. Any quality judgement requires separate expert review.''')
    doc('HELD_OUT_EVALUATION_PLAN.md','''# Held-out preparation and consumption
Three separately authored engineering candidate families are frozen in held-out-candidates-v4.json: currency disagreement with equal amounts; slow HTTP200 above the native latency threshold; negative acknowledgement without an authoritative positive receipt. They use existing source fields and native routing only. Their source data and expert expectations differ from Scenario C; they are not randomized Scenario C IDs. All are unrun on GPT and unreviewed by independent banking experts. The `held-out` manifest split is preparation metadata, not an independence certification.

Initial v1 used generic payment event names and an in-window payment, so native detection correctly did not produce the expected exceptions. v2 added confirmation fields but did not fix the actual canonical event/window defects. Failed source-data versions and results are preserved; v3 fixes canonical event types and puts the payment outside the existing five-minute window, without changing expected operational decisions or native rules. Three native offline mechanics passed. Version v4 freezes the same source semantics with evaluator rubric 1.1, adding per-role currency predicate coverage. Versions v1/v2 are retired engineering artifacts; v4 requires external preregistration review before a generalization evaluation. Their mechanics tests do not demonstrate held-out GPT accuracy.

Target 40 externally reviewed cases across family-partitioned development/held-out sets. Add independently authored mechanisms: currency disagreement, duplicate ledger source references, simultaneous conflicting acknowledgements, out-of-order ingestion with event-time chronology, negative receipt after successful transport, late currency correction, slow success versus server failure, approval-state disagreement, explicit unavailable policy mapping, payment failure with delayed receipt, superseded stale workflow and evidence arriving at a snapshot boundary. Verify each against existing detection/tool contracts before freezing; unsupported families remain excluded rather than inventing connectors. Include complete/partial/contradictory evidence, Tx/Tech/Risk branches and safe negative controls.

Two external reviewers should preregister source authority and materiality independently before model access; retire disputed cases until adjudicated. Do not send answer rubrics to prompts. Use the existing --manifest interface and family split guard. If observed GPT outcomes tune prompts, mark that set CONSUMED/development and freeze a new independent version. No 30–50-case evaluated set or paid batch exists yet. No current generalization claim.''')
    doc('FRONTEND_HANDOFF.md','''# Phase 21 backend handoff — no frontend edits
Reuse existing API prefix/version and identity/case-scope controls. Inspected routes: GET /api/v1/workbench/cases and /cases/{case_id} provide active exceptions, priority, employee stage/context; GET /api/v1/cases/{case_id}/orchestration and /tasks expose native workflow/task history; /investigations exposes specialist outcomes, validated/rejected findings, hypotheses and missing evidence; /investigation-evidence exposes provenance; /supervisor-reviews exposes native reviews; /authorizations and /actions expose deterministic safety state; /reviews and /reviews/{review_id}/history expose human review/audit. Operational intelligence remains /api/v1/intelligence/report and incident relationship routes. These are existing routes, not newly implemented evaluation endpoints.

The Phase 20 file contract extends Phase 19: quality_evaluation.version, provenance, layers.integration/evidence/reasoning, roles.tool_quality, role missing-evidence classifications with expert-binding status, native Supervisor context, multiple failure facts and review_packet hashes. Narrative verdicts are INCONCLUSIVE until independently REVIEWED/ADJUDICATED; NOT RUN Supervisor is never rendered as PASS. Supported fields do not verify surrounding prose; hypotheses remain unverified. Execution eligibility cannot be inferred from advisory completion.

Genuine endpoint gaps: no authenticated API for research artifact discovery, quality scorecards or dual expert review/adjudication. Phase 21 must design scoped server-side artifact indexing/serialization (no arbitrary filesystem paths), enforce case/tenant access, expose provenance and versions, preserve null/NOT APPLICABLE denominators, and distinguish historical, offline, fresh live and reviewed populations. No research decision should change operational task state. Reuse case serialization before adding read-only research routes. Remaining frontend work is wiring these existing endpoints to the existing dashboard and later exposing the scoped research extension; no dashboard or evaluation UI was added here. Verify auth, stale/snapshot data and NOT RUN/INCONCLUSIVE states before display.''')
    baseline=json.loads((ROOT/'docs/hardening/artifacts/frontend-baseline-hashes.json').read_text())
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in baseline.items())
    with zipfile.ZipFile(ROOT.parent/'ResolveOS-phase19-benchmark.zip') as archive:
        protected={Path(n).as_posix():hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==hashlib.sha256(archive.read('ResolveOS/'+Path(n).as_posix())).hexdigest()
            for n in json.loads(archive.read('ResolveOS/docs/evaluation/phase19/artifacts/phase19-integrity.json'))['protected_native_source_hashes']}
    assert all(protected.values())
    (DOC/'artifacts/phase20-preservation.json').write_text(json.dumps(dict(frontend_files_preserved=len(baseline),native_matches_phase19_zip=protected,prior_zip_sha256=hashlib.sha256((ROOT.parent/'ResolveOS-phase19-benchmark.zip').read_bytes()).hexdigest()),indent=2)+'\n')
    tests=[]
    for name in ('phase20-focused.xml','phase20-final-quality.xml','phase20-final-focused.xml','phase20-quality11-final.xml','phase20-coverage.xml','phase20-reliability-final.xml','phase20-review-integrity-after.xml','phase20-full-backend.xml'):
        path=DOC/name
        if path.exists():
            root=ET.parse(path).getroot();suites=[root] if root.tag=='testsuite' else root.findall('testsuite')
            values={k:sum(float(s.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped','time']}
            tests.append(f"- [{name}]({name}): {int(values['tests']-values['failures']-values['errors']-values['skipped'])} passed, {int(values['failures'])} failed, {int(values['errors'])} errors, {int(values['skipped'])} skipped, {values['time']:.2f}s.")
    doc('PHASE20_ACCEPTANCE_REPORT.md',f'''# Phase 20 acceptance
**LIVE MODEL EVALUATION NOT RUN.** No new paid calls or credential inspection. Prior work, histories and archives are retained.

Reused Phase 19 runtime/catalog/independent source scoring; added frozen research rubrics, three separate layers, authorized role-relevant availability probes, sufficiency with explicit expert semantic bindings, inconclusive-aware calibration, dual-review/adjudication provenance, multi-failure diagnostics, historical current-contract replay, reviewed per-case profiles and deadline fencing. Native prompts, contracts, tools, validator, orchestration, Supervisor, controls and execution code are byte-identical to the Phase 19 archive. No prompt tuning or status promotion was implemented.

{layertext}

Eight historical saved runs retain specialist output; none demonstrates native live Supervisor completion. Two directories have insufficient artifacts; older A provenance is limited. Latest historical prompt 1.5 shows both roles incomplete and recurring missed Technology timeline retrieval. This supports a measured retrieval-quality weakness; unnecessary escalation materiality remains unreviewed. No current model reliability percentage follows from offline fixture counts.

Three new candidate families pass native offline mechanics in final v4 (research rubric 1.1). Earlier failed versions are preserved; root causes were fixture event semantics/window errors. Benchmark-specific diagnostic codes were also found to be collapsed by the old shared harness error constructor; a fixed allowlist extension corrects reporting without exposing exception prose or altering controls.

Review provenance regression: three intentional failures reproduced acceptance of changed truth, native records or copied observations ([before fix](phase20-review-integrity-before.xml)). Review now checks frozen source integrity, exact truth/record packet hashes and source-observation equality before accepting reviewer verdicts or bindings. Fourteen focused review/coverage/deadline checks pass after correction. This research-only fix does not affect operational outcomes. These reproduced pre-fix failures are retained evidence, not unresolved final failures.

Verification (overlapping runs, never add counts):
{chr(10).join(tests)}

Migration upgrade/downgrade/upgrade and owned-database cleanup occur in verify_backend. The full suite began before final rubric coverage, reporting and review-integrity additions; final focused tests and fresh CLI rehearsals cover those edits. A native injected interruption preserves partial task/results and bank snapshots, drops its database and stops unrun cases. Final offline/rules/candidate CLI checks cover 23 cases, 23 dropped databases, unchanged bank records, empty safety tables and 161 frozen files. All 54 frontend files match baseline; pre-existing next-env.d.ts difference is preserved. Historical/Phase 19 comparison verifies all 1266 files unchanged against the previous archive. Package receipt separately verifies full archive CRC/SHA256 and original source/history preservation.

Remaining limitations: no fresh GPT experiments, no independent expert decisions/adjudications, no measured labour savings/billing, only one reviewed model profile, cooperative deadlines rather than hard process runtime, telemetry cannot conclusively grade duplicate calls without arguments, and no independently accepted 30–50-case held-out set. Read source chronology independently but do not call free-text causal/chronological prose verified. Live commands are opt-in preparations, not approvals or executions. Scientific infrastructure and offline scope are accepted only to the extent shown above; production readiness and live intelligence remain unproven.''')

if __name__=='__main__': main()
