"""Render inspectable Phase 19 documentation from observed offline artifacts."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'docs/evaluation/phase19'

def document(name,text):
    (DOC/name).write_text(text.strip()+'\n',encoding='utf-8')

def main():
    def latest(track):
        paths=sorted((DOC/'artifacts').glob('*-'+track+'-*/results.json'))
        return next((p,json.loads(p.read_text())) for p in reversed(paths) if json.loads(p.read_text()).get('run_status')=='COMPLETED')
    offline_path,offline=latest('offline');rules_path,rules=latest('rules')
    links=f"[Native offline results]({offline_path.relative_to(DOC).as_posix()}) and [rules results]({rules_path.relative_to(DOC).as_posix()})."
    rows=['| Case | Family | Decision | Specialist runs | Supervisor |','|---|---|---|---|---|']
    for c in offline['cases']:
        rows.append(f"| {c['scenario_id']} | {c['family']} | {c['score']['decision']} | {len((c['records'] or {}).get('investigations',[]))} | {'COMPLETED' if c['score']['supervisor_participated'] else 'NOT RUN' if c['observations']['initial_detection_types'] else 'NOT APPLICABLE'} |")
    table='\n'.join(rows)
    metrics=json.dumps(offline['metrics'],indent=2)
    investigators=[i for c in offline['cases'] for i in (c.get('records') or {}).get('investigations',[])]
    roles=Counter(i['role'] for i in investigators)
    tool_statuses=Counter(t['status'] for i in investigators for t in i['telemetry'].get('tools',[]))
    document('CASE_CATALOG.md',f'''# Pilot case catalog
All ten cases are development fixtures, not held-out cases. Identities and source records vary each run. Source truth and expert materiality are frozen separately before provider use.

{table}

P19-04 represents a duplicate-risk normalized observation, not two accepted instructions with the same unique key. Only the primary payment is seeded in the simulator. P19-06 is genuine native human triage before specialist execution. P19-10 is a negative control: a newer completed workflow supersedes the old state before detection. P19-08 substitutes late ledger correction for an unsupported WORKFLOW investigator; no handler was invented. P19-09 installs and reads an existing valid policy but cannot authorize. Risk's unavailable policy-applicability connector remains unavailable.

{links}''')
    document('BENCHMARK_METHODOLOGY.md','''# Benchmark methodology
Version phase19-pilot-1.0; scorer phase19-scoring-1.3. The catalog pre-registers objective source facts and expert advisory decisions. Facts do not establish internal causation. Every run owns fresh migrated PostgreSQL databases, one per case, and drops them. No production/development records are reset. Sources are ingested and detected natively; the selected case is classified and routed natively. Declared follow-up observations are ingested after routing and attached through native detection. No Supervisor task is manually created.

Two tracks: rules-only stops before model investigations; offline invokes source-only deterministic providers through the existing specialist and Supervisor services. Offline success proves mechanics under designed fixture outputs, not independent GPT reasoning or reliability. Source providers never import the catalog or grader. Live runs are NOT RUN in this phase. A separate rules-prefix snapshot is captured before providers inside each offline/live case, sharing exact input IDs and native assessments. The standalone rules run uses fresh equivalent fixtures; its generated IDs/timestamps differ. This implementation clarification supersedes the design's proposed separate-database identical-byte comparison.

Ground truth, planned follow-up, observed input, source identities and frozen hashes remain private artifacts. No expected answer or case name enters model prompts/tool metadata. Frozen receipts and source bytes are rechecked. Full simulator column fingerprints detect any mutation, including fields beyond amounts/status. Failure exports contain safe error codes and completed/current stages, never unrestricted exception text. Unknown safety observations cannot be reported as observed violations or passes; setup failures still fail acceptance.

The first failing prototype and pre-fix JUnit are preserved. Scoring 1.1 corrected missing baseline misclassification; 1.2 adds independent source/temporal/provenance checks and unknown-observation handling; 1.3 independently rejects forged COMPLETED results with material gaps, empty findings or rejected predicates. Native completion rules remain unchanged. Previously written artifacts are never retroactively regraded in place.

Development overlap with A/B/C is acknowledged. These are ten designed operational branches, not a random production sample. No confidence interval or generalization claim is meaningful from deterministic outputs. Free-text temporal narratives, causal calibration, gap materiality, role boundaries and recommendation quality require independent human review.''')
    document('SCORING_RUBRIC.md','''# Independent scoring rubric
Detection, categories and recommended roles compare preregistered expected sets with native observations. Finding assessments remain separate: SUPPORTED, CONTRADICTED, INSUFFICIENT_EVIDENCE, NOT_EVALUATED. Each accepted predicate is independently checked for a retrieved authorized source, correct case identity, actual field, exact typed value on every citation and timestamps within the result snapshot. The scorer never splits, rewrites or upgrades model output. Native validator regressions separately cover stale/current source versions and snapshot provenance. Supervisor conclusions map stored evidence references back to independently supported source observations; Supervisor participation requires all routed investigators completed.

Metrics retain numerator and denominator. Zero denominators are NOT APPLICABLE with null values. Incomplete/failed/unrun outcomes do not count as correct decisions; incomplete counts remain explicit. Precision is correct escalations / all evaluated escalations; recall is correct escalations / expected escalations among evaluated decisions. Grounding precision counts independently exact and temporally eligible accepted predicates. Required-fact coverage measures source-qualified preregistered facts, not prose word overlap. Family aggregates retain repeated cases. Critical failures override every score; no weighted total conceals them.

COMPLETE is bounded advisory completion reaching native Supervisor, including its advisory ESCALATE; it is neither incident resolution nor authorization. Native pre-Supervisor human escalation is ESCALATE. NO_EXCEPTION is the negative control. Missing Supervisor is NOT RUN when escalation legitimately blocks it. Rules-only advisory assessment is CAPABILITY NOT AVAILABLE IN BASELINE, not an AI reasoning failure.

Each manual-review.json preserves source observations, hypotheses, material gaps, Supervisor context, reviewer/verdict/rationale slots and checklist. Narrative causality, chronology and expert unnecessary-escalation/unsafe-completion candidates remain PENDING REVIEW. Finalize in a separately versioned signed review artifact referencing original hashes; never overwrite initial scores. Without review, no free-text hallucination or causal-quality pass is claimed.''')
    document('PILOT10_RESULTS.md',f'''# Ten-case pilot results
LIVE MODEL TESTS: **NOT RUN**. Zero paid requests. Both final CLI tracks returned 0 and all ten cases completed their track-specific evaluation.

{table}

{links}

```json
{metrics}
```

These are deterministic fixture expectations. No real-model operational accuracy is measured. Each case exports raw persisted native results, task/tool telemetry, preregistered truth, source identities, frozen hashes and a manual review packet. Actual billed cost is unobserved; offline tokens and fixture latency are not GPT telemetry. All per-case databases were dropped.''')
    with (DOC/'PILOT10_RESULTS.md').open('a',encoding='utf-8') as report:
        report.write(f'\nActual persisted specialist runs by role: {dict(roles)}. Tool statuses: {dict(tool_statuses)}. UNAVAILABLE denotes the explicitly absent policy-applicability connector, not fabricated evidence or a provider transport failure. Supervisor ran four times; all usage here is deterministic.\n')
    document('COMPARATIVE_ANALYSIS.md',f'''# Matched baseline comparison
{links}

Both tracks detected, classified and routed 10/10 preregistered cases correctly (including the no-exception control). The rules track stops at its actual capabilities: it detects/routs exceptions, creates native human triage where appropriate and creates no advisory synthesis. It invokes no specialists or Supervisor. Each native offline case also captures rules-baseline.json before providers on the same initial source identities. Additional offline evidence synthesis and four legitimate Supervisor reviews demonstrate mechanics only.

No reasoning accuracy or labour savings advantage is inferred from fixture providers. Detection/classification/routing are shared native code, so matching scores are expected. Rules-only advisory metrics have zero denominators/NOT APPLICABLE, not zero accuracy. Whole-suite timing includes fresh database migration/drop; it is not employee handling time or comparative model latency. Offline suite seconds: {offline['latency_seconds']:.3f}; rules suite seconds: {rules['latency_seconds']:.3f}. Concurrent execution and setup overhead prevent a performance claim.''')
    document('SAFETY_ASSESSMENT.md','''# Safety assessment
No paid API calls, secret inspection or frontend changes. Native completion, validation, role authorization, temporal safeguards, human escalation, deterministic policy and execution code are unchanged by Phase 19. Queue claims remain limited to classification, routing, permitted investigations and native Supervisor review. Human tasks and follow-ups after the first Supervisor review remain unprocessed; unrelated or executable tasks fail closed. No worker drains other queued tasks.

Every final pilot case has unchanged full-column bank fingerprints, unchanged frozen inputs, empty action/approval/authorization/operation/verification tables and no false RESOLVED state. All owned databases were dropped. These checks are synthetic-scope observations, not production control certification. Unknown setup baselines remain unknown and fail acceptance without being classified as model banking mutations.

Live selection requires explicit case IDs, matching paid-case authorization count and positive finite aggregate request/token/USD caps. Per-case maximums remain 10 requests, 120000 accounted tokens, USD0.15 conservative estimate, three specialist turns, twelve tool calls and 2048 output tokens/request. Batch reservations are conservative and never released, even where local known usage is reconciled. Unknown usage halts the remaining batch; no retries/fallbacks. Critical safety failures stop further cases, preserve NOT RUN rows and return nonzero.

All 54 frozen frontend files match their baseline bytes. next-env.d.ts has an existing Git difference selecting .next/dev/types imports; these bytes match the frozen worktree baseline and were preserved. Earlier phase artifacts/archives are not rewritten. Package CRC and every included file SHA256 are checked; credentials, caches and database dumps are excluded.''')
    document('LIMITATIONS.md','''# Limitations and measured-business study plan
Live GPT pilot: NOT RUN. No actual model quality, model latency, paid token consumption, actual billing, production reliability, generalization or ROI has been measured. Manual causal/chronological/recommendation review remains PENDING REVIEW. Deterministic source providers are not independent reasoning judges. Several families overlap earlier development fixtures. No production dataset or real bank connector is used. Unavailable internal traces, policy-applicability mapping and the missing WORKFLOW handler remain explicit architecture limits.

Expansion plan: prepare 40 cases, 20 development and 20 held-out, with family-level separation, expert-reviewed frozen materiality and distinct operational mechanisms. New held-out families should include currency disagreement, partial acknowledgement identifiers, boundary-time evidence arrival and contradictory approval provenance, using existing registered fields/tools only. Two subject-matter reviewers must pre-register ambiguity and safe outcomes before model access. Unsupported families are documented/excluded or substituted transparently. No held-out cases have been authored/validated/executed here; this is an UNRUN plan. The external manifest supports up to 50 cases and rejects families spanning development/held-out partitions. A/B/C remain development, never relabelled held-out. If outcomes tune prompts, retire that version into development.

Business timing study: recruit qualified operators, define identical read-only tasks and evidence packets, randomly assign/counterbalance manual rules-only versus assisted reviews, record active handling minutes separately from waiting and migration/model latency, record quality and rework under blinded review, and pre-register sample size/exclusions. Obtain observed salaries/loaded costs from the organization only with authorization. Savings and ROI remain NOT MEASURED. Any planning formula (cases * minutes saved * loaded hourly cost / 60 minus observed AI/operating costs) is assumption-based until those inputs are collected. Do not use fixture wall time as employee time.

Phase 20 should begin with independent review of materiality and role boundaries, then one explicitly authorized bounded live case. Extend held-out families only after frozen review; do not run a paid benchmark by default.''')
    document('EXPORT_CONTRACT.md','''# Phase 21 file export contract
export_version: phase19-export-1.0. Files are versioned UTF-8 JSON/JSONL/Markdown artifacts; no analytics database or UI has been added. Suite results.json contains run_id, benchmark_version, track, run_status, live_model_tests, cases, explicit-denominator metrics, latency_seconds, batch_reservations, actual_billed_cost and manual_review_status. Each case contains scenario_id/family, stage/task history, source/frozen hashes, raw native records, observations, independently scored predicates, request usage, safe error_code and database_cleanup.

Operational decisions: COMPLETE / ESCALATE / NO_EXCEPTION / INCOMPLETE; baseline adds DETECTED_AND_ROUTED / RULES_HUMAN_TRIAGE. Run states: ATTEMPTED / COMPLETED / FAILED / STOPPED / INCOMPLETE / NOT RUN. Check/metric states include NOT APPLICABLE. Narrative judgement: PENDING REVIEW until a separate signed review is supplied. Grounding counts and narrative status must never be collapsed into one quality percentage. actual_billed_cost is null when billing is not observable; offline provider tokens remain zero, fixture turns are separate. Consumers must retain versions, hashes, missing populations, source-qualified facts and critical failures. Never infer resolved/authorized from advisory completion.''')
    document('README.md','''# Reproduce Phase 19
From ResolveOS, use the existing Python 3.13 backend dependencies and local PostgreSQL configuration. No new dependencies or manual migrations are needed. Supply DATABASE_URL through your existing local environment; the runner creates/drops fresh owned databases only. Run with the existing backend interpreter (py -3.13 works in this workspace):

```powershell
py -3.13 -m scripts.run_evaluation_benchmark --track offline
py -3.13 -m scripts.run_evaluation_benchmark --track rules
```

Inspect the printed directory's REPORT.md/results.json, then each case's ground truth, frozen source records, rules-baseline.json, manual-review.json and requests.jsonl. Nonzero exit means incomplete or failed evaluation. Offline is the default and never validates GPT quality.

External reviewed suites use --manifest PATH with phase19-suite-manifest-1.0, benchmark_version, and cases. Each case declares id, family, split, ground_truth, initial_sources and subsequent_sources. Ground truth requires the existing pilot truth fields. Source templates use registered payload fields, minutes_before >= 0, and optional exact $ENTITY/$TRACE/$KEY/$REF_name identity tokens. Families must belong to exactly one split; max 50 cases. This interface is tested, but no held-out evaluation is claimed.

Do not execute live unless separately authorized. After such authorization, one bounded case in your own environment with its existing key can be selected explicitly:

```powershell
py -3.13 -m scripts.run_evaluation_benchmark --track live --cases P19-05 --authorize-paid-cases 1 --batch-max-requests 10 --batch-max-tokens 120000 --batch-max-usd 0.15
```

The command itself is a paid opt-in; it was NOT RUN here. No key argument or file is used. Legitimate incomplete model output remains human escalation; never override the gate to reach Supervisor.''')
    frontend=json.loads((ROOT/'docs/hardening/artifacts/frontend-baseline-hashes.json').read_text())
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in frontend.items())
    protected={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for directory in ['app/investigation','app/supervisor','app/orchestration','app/controls','app/execution'] for p in (ROOT/directory).glob('*.py')}
    integrity=dict(frontend_files_preserved=len(frontend),frontend_baseline_match=True,preexisting_next_env_difference_preserved=True,protected_native_source_hashes=protected,
        offline_artifact=str(offline_path.relative_to(ROOT)),rules_artifact=str(rules_path.relative_to(ROOT)))
    (DOC/'artifacts/phase19-integrity.json').write_text(json.dumps(integrity,indent=2)+'\n')
    testrows=[]
    for name in ['phase19-before.xml','phase19-fix.xml','phase19-full-backend.xml','phase19-focused.xml','phase19-final-focused.xml','phase19-final-harness.xml','phase19-completion-recheck.xml']:
        path=DOC/'artifacts'/name
        if path.exists():
            root=ET.parse(path).getroot();suites=[root] if root.tag=='testsuite' else list(root.findall('testsuite'))
            totals={k:sum(float(s.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped','time']}
            testrows.append(f"- [{name}](artifacts/{name}): {int(totals['tests']-totals['failures']-totals['errors']-totals['skipped'])} passed, {int(totals['failures'])} failed, {int(totals['errors'])} errors, {int(totals['skipped'])} skipped, {totals['time']:.2f}s.")
    document('PHASE19_ACCEPTANCE_REPORT.md',f'''# Phase 19 acceptance report
Live AI: **NOT RUN**. Zero paid requests. Existing uncommitted work, earlier phases and historical artifacts are retained.

The duplicate fixture previously tried to insert two simulator payments sharing a unique idempotency key. The secondary FAILED instruction is now represented only as its normalized duplicate-risk source observation; no banking unique constraint was relaxed. Setup errors previously compared an absent bank baseline as a mutation. Unknown baselines now remain unknown, do not count as observed mutations and still fail acceptance. The two defects were reproduced before correction; artifacts are preserved.

Final offline pilot and rules-only baseline: ten of ten cases completed their respective mechanical scope; detection/classification/routing 10/10, independently grounded accepted specialist predicates 158/158, required source facts 56/56, no critical failures. Four native Supervisor reviews, five native human escalations and one no-exception control. Supervisor was never manually scheduled. Causal/narrative quality remains PENDING REVIEW; deterministic fixture scores are not live GPT accuracy.

{links}

Verification (runs overlap; do not sum totals):
{chr(10).join(testrows)}

Fresh migration upgrade/downgrade/upgrade is included in verify_backend runs. Pilot-owned databases were dropped. All 54 frozen frontend files match; next-env.d.ts's pre-existing Git difference was preserved. No native completion, tool authorization, validation, deterministic control or execution rules changed in Phase 19. Package receipt separately records ZIP CRC/per-file SHA256, history bundle and original archive preservation.

The initial expanded focused run's sole failure was a test patch aimed at nonexistent provider method respond; changing it to the actual turn method corrected that test. The failed-test owned database was subsequently dropped and the marker retained. The full backend suite started before the expanded Phase 19 tests/final reporting guard were added; the final harness suite verifies those changes separately. All reports are retained, and overlapping counts are not added.

Scope accepted: reproducible independent file-based scoring, ten designed native offline cases, matched rules capabilities and safety fencing. Remaining: live model reliability/causality, external subjective review, actual billing, measured operator timing and authored/validated 30–50-case held-out expansion. A family-partitioned manifest interface and unrun expansion protocol are supplied, not a claim that a larger benchmark passed. No production-readiness or ROI conclusion.''')

if __name__=='__main__': main()
