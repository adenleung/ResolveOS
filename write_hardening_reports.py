"""Produce reviewable handoff from executed artifacts; refuses absent final evidence."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from app.domain.case_service import CaseLifecycleService, CaseState
from app.simulator.service import SCENARIO_DEFINITIONS

ROOT=Path("docs/hardening")
ART=ROOT/"artifacts"


def read(name):return json.loads((ART/name).read_text(encoding="utf-8"))
def junit(name):
    root=ET.parse(ART/name).getroot()
    cases=root.findall(".//testcase")
    return dict(total=len(cases),passed=sum(not any(case.find(tag) is not None for tag in ("failure","error","skipped")) for case in cases),
        failed=sum(case.find("failure") is not None or case.find("error") is not None for case in cases),
        skipped=sum(case.find("skipped") is not None for case in cases),seconds=sum(float(case.get("time","0")) for case in cases))
def write(name,text):(ROOT/name).write_text(text.strip()+"\n",encoding="utf-8")
def table(headers,rows):return "| "+" | ".join(headers)+" |\n|"+"|".join("---" for _ in headers)+"|\n"+"\n".join("| "+" | ".join(str(v) for v in row)+" |" for row in rows)


def main():
    baseline=junit("baseline-postgres.xml"); final=junit("final-postgres.xml"); safety=junit("critical-safety.xml")
    clean=junit("clean-postgres.xml")
    assert final["failed"]==0 and final["skipped"]==0
    assert clean["failed"]==0 and clean["skipped"]==0 and clean["passed"]==final["passed"]
    operational=read("operational.json");memory=read("memory-evaluation.json");ai=read("ai-contract-evaluation.json")
    demo=read("headless-demo.json");runtime=read("runtime-smoke.json");ablation=read("agent-ablation.json")
    assert len(operational["rows"])==300 and all(row["false_verified"]==0 for row in operational["summary"].values())
    hashes=read("frontend-baseline-hashes.json")
    changed=[name for name,value in hashes.items() if not Path(name).exists() or hashlib.sha256(Path(name).read_bytes()).hexdigest()!=value]
    current={str(p).replace("\\","/") for p in Path("frontend").rglob("*") if p.is_file() and not any(x in p.parts for x in ("node_modules",".next",".git"))}
    added=sorted(current-set(hashes));assert not changed and not added
    preservation=dict(files_checked=len(hashes),changed=changed,added=added,preexisting_difference="frontend/next-env.d.ts",comparison="byte hashes against session-start working tree")
    (ART/"frontend-preservation.json").write_text(json.dumps(preservation,indent=2)+"\n",encoding="utf-8")
    test_summary=dict(baseline=baseline,critical_safety=safety,final=final,clean_environment=clean,offline_ai=ai["summary"])
    (ART/"acceptance-summary.json").write_text(json.dumps(test_summary,indent=2)+"\n",encoding="utf-8")
    # Capture exact names/versions from the newly installed minimal environment,
    # without dumping direct URLs or unrelated global distributions.
    clean_environment=read("clean-environment.json")
    packages=clean_environment["packages"]
    Path("requirements-hardening-constraints.txt").write_text("# Observed clean Windows/Python 3.13 constraints; install with requirements.txt.\n"+"\n".join(f"{name}=={version}" for name,version in sorted(packages.items()) if name.lower() not in {"pip","setuptools"})+"\n",encoding="utf-8")
    (ART/"test-matrix.json").write_text(json.dumps({case.get("classname","unknown"):[] for case in ET.parse(ART/"final-postgres.xml").getroot().findall(".//testcase")},indent=2),encoding="utf-8")
    groups={}
    for case in ET.parse(ART/"final-postgres.xml").getroot().findall(".//testcase"):
        groups.setdefault(case.get("classname","unknown"),[]).append(dict(name=case.get("name"),seconds=float(case.get("time","0")),status="PASS"))
    (ART/"test-matrix.json").write_text(json.dumps(groups,indent=2)+"\n",encoding="utf-8")
    transitions=[]
    for source,destinations in CaseLifecycleService.valid_transitions.items():
        for destination in sorted(destinations,key=lambda state:state.value):
            authority="ExecutionEngine" if source in {CaseState.APPROVED,CaseState.EXECUTION_QUEUED,CaseState.EXECUTING,CaseState.VERIFYING} else "OrchestrationService / specialist / Supervisor / reviewer service"
            precondition="Independent source verification; discrepancy-free observed outcome" if destination==CaseState.RESOLVED else "Current case/task/evidence context, legal transition, role and lease where required"
            transitions.append([source.value,destination.value,authority,precondition,"Attributed case transition audit; retry retains identity"])
    write("01_CORE_RELIABILITY_REPORT.md",f"""# Core reliability

Fresh baseline: {baseline['passed']} passed. Targeted safety: {safety['passed']} passed. Final: {final['passed']} passed, zero failures/skips. Evidence: artifacts/baseline-postgres.xml, critical-safety.xml, final-postgres.xml.

Fixed four demonstrated problems: identity-equivalent replays with changed content now persist an ingestion conflict without replacing the original observation; exact retries increment receipts atomically across connections; partial predicate citations become insufficient rather than supported; memory cannot include a publication later than its investigation snapshot. The smoke experiment additionally discovered and fixed the critical omission of ledger balance from current authorization and independent verification snapshots. Balance change after execution now produces FAILED_VERIFICATION and ESCALATED, not RESOLVED.

No queue, lifecycle, database or approval architecture was replaced. Existing tests exercise independent PostgreSQL claims, SKIP LOCKED, separate worker processes, lease expiry/recovery, stale fencing, retry exhaustion, ambiguous retries, precommit rollback and concurrent single effects. Dedicated hardening regression uses six independent receipt connections. New balance, source-type and temporal regressions are in tests/test_hardening_postgres.py.

Intentional compatibility effect: authorizations with the old incomplete ledger snapshot are stale when rechecked and must be reevaluated. Historic authorizations, verified outcomes and audit rows are not rewritten. This is an additive backend source observation, with unchanged API fields and action allowlist.

## Invariants

Stable event/case identity: unique source/event and detector keys. Evidence authority: scoped immutable observations with provenance, source recheck and typed field equality. Lifecycle: explicit transition service below. AI separation: advisory schemas and read-only tools. Fresh authorization: source/policy/action fingerprint and expiry. Idempotency: unique logical confirmation operation/event. Ownership: PostgreSQL clock, token and post-effect fence. Verification: source reread and unchanged monetary fields including balance. Audit: caller-owned protected transactions and attributed transitions. Historical integrity: snapshot cutoff and retained versioned records. Evidence spans lifecycle, Phase 6–11 tests and new hardening tests; this is finite prototype validation, not a universal failure-probability guarantee.

## Implemented transition matrix

{table(['From','To','Authority','Required condition','Audit / retry'],transitions)}

Terminal states have no outgoing transitions. Scheduling, simulation, HTTP success and worker completion cannot establish RESOLVED. Failure destinations and recovery paths are recorded in the Phase 6/10 tests and headless verification-failure/interruption traces. Detailed trigger-specific evidence is in each trace's audit and task events; the matrix is the allowed service graph, not an invented replacement lifecycle.
""")
    journey_rows=[[name,record['final_state'],len(record['tasks']),len(record['evidence']),sum(bool(v['success']) for v in record['verifications'])] for name,record in demo['records'].items()]
    write("02_BACKEND_E2E_ACCEPTANCE.md",f"""# Headless backend acceptance

`py -3.13 run_headless_demo.py --scenario all` freshly migrates an owned disposable PostgreSQL database, uses app/demo and the actual ingestion, detection, classification, incident correlation, orchestration, specialist, Supervisor, controls, reviewer, execution and verification services, and removes the database on exit. No second engine or frontend is introduced. Source generation is deterministic synthetic seeding; record IDs/timestamps are observed, not fabricated. The recorded correlation run examines three cases/two pairs and correctly leaves all three ungrouped; shared endpoints alone do not establish a common incident. Its opt-in demo hook preserves the original default, and the four Phase 15 demo/API compatibility tests were rerun afterward.

{table(['Scenario','Observed case state','Tasks','Evidence records','Successful independent verifications'],journey_rows)}

Named CLI scenarios: verified-resolution, contradictory-evidence, stale-authorization, duplicate-request, worker-interruption, verification-failure and missing-handler. JSON exports source IDs/timestamps, task events, specialist findings, Supervisor conclusions, controls, approvals, operation/effect identity, verification detail and audit transitions. Intelligence is calculated by the existing service. Unsupported workflow/document handlers remain WAITING_HANDLER even with available specialist providers. Case state INVESTIGATING is distinct from the unsupported task's waiting status.

The interruption scenario expires a real durable claim and recovers it. Full regression additionally kills ownership through failure injection, proves stale commits roll back, and runs separate worker processes. This runner does not claim a mid-effect OS process kill; that remaining recovery experiment is in the gap register.

`py -3.13 verify_hardening_runtime.py` also starts a real Uvicorn process, checks /health and /ready over loopback HTTP, starts the real one-shot worker subprocess, and runs read-only diagnostics on another empty migrated database. Output: artifacts/runtime-smoke.json. API role/contract checks are in the final regression, including Phase 15. Full frontend-to-PostgreSQL browser acceptance remains unperformed; the frontend was frozen.
""")
    bench_rows=[]
    for mode,summary in operational['summary'].items():
        bench_rows.append([mode,summary['cases'],summary['independently_verified'],summary['eligible_cases'],summary['false_verified'],summary['simulated_review_decisions'],round(summary['end_to_end']['median_seconds'],4),round(summary['end_to_end']['p95_seconds'],4)])
    write("03_OPERATIONAL_VALUE_BENCHMARK.md",f"""# Operational comparison — offline synthetic study

{table(['Mode','Cases','Verified','Automatically eligible cohort','False verified','Scripted review decisions','Completed median seconds','Completed p95 seconds'],bench_rows)}

Mode A is deterministic evidence predicates through existing contracts. Mode B uses the same offline predicates and requires an additional scripted reviewer workflow decision before current action controls. Mode C uses the same offline predicates with automatic execution only where current policy allows it. All modes have equivalent source definitions, current policy limits, action allowlist, action-specific approvals where required, and independent verification. A is as capable as C on these rule-covered cases. **This experiment establishes no live-AI quality or resolution advantage over A.**

100 held-out cases per mode, across twelve families: eligible confirmation loss, exact duplicate delivery, human amount threshold, inactive policy, missing ledger, duplicate debit, unsettled payment, contradictory payment observation, balance-change verification failure, lease recovery, technology timeout and temporarily unavailable provider. Development data has 24 cases; held-out input/labels are frozen separately in datasets/operational-v1 with seed 20261010. Labels are evaluator-only and never passed to investigators or retrieval tools. Root causes requiring expert adjudication are not claimed. The permanently unsupported workflow-handler scenario is separately demonstrated by the headless runner.

Results: artifacts/operational.json/.csv/.jsonl. Metadata includes dataset SHA-256, assumptions, mode definitions and limitations. Every row links actual source/case/task/evidence/control/action/verification/audit IDs and retains failures. Original smoke errors are retained, including the balance false-closure experiment and the 192-observation incomplete runner-claim failure; they are not accepted final results. The corrected runner handles unrelated claimed work through normal services until the intended action ID is claimed, rather than assuming queue order.

`py -3.13 run_stage_metrics.py` derives persisted stage samples in artifacts/stage-metrics.json: ingestion-to-case detection, immediate-task first eligible claim waiting, investigation attempts, Supervisor processing, scripted action approval waiting, fenced effect processing and independent verification latency. Definitions and completed/censored sample counts are explicit. PostgreSQL task-event timestamps anchor worker stages; recorded timestamps precede final commits, subsequent retry waiting is excluded, and approval audit/application clock mismatch can produce unknown intervals. These are processing/recorded stage metrics, not measured employee waiting or complete provider-only latency.

End-to-end starts immediately before synthetic source creation/ingestion and ends after worker draining and observed independent verification. It includes database setup for the case, not database provisioning. Eligible unresolved cases are censored (null), never zero-duration completed samples. Processing-observation time is separately available for all rows. States are snapshots at each case observation end; temporarily unavailable providers may be reactivated by later trusted worker runs in that mode database. Mode databases are separate. Cases share a worker/database within a mode, so cache/load and later pending work can affect latency.

Verified coverage = independently verified / all cases. Verified automation = eligible verified cases with zero scripted review decisions / automatically eligible cohort. Human route = AWAITING_HUMAN, ESCALATED, or blocked controls requiring operator handling; this differs from terminal escalation alone. Precision/recall use the explicitly labelled human-route cohort. A blocked case may stay APPROVED in mode B: workflow approval does not authorize a protected action. False closure compares independent observed success with frozen permitted outcomes.

Human active time is **modelled**: 60 seconds per simulated meaningful review and 300 seconds per unresolved human route; hourly cost SGD 30. Reviewer assignment is not double-counted as a decision. No employees participated, no actual review/handling durations were observed, and no wait-time savings are asserted. Infrastructure cost, live token usage and measured total cost per verified resolution are null. A complete manual SOP baseline is in the banking catalogue: open case, locate payment/ledger/API evidence, compare sources, identify gaps, check policy, select action/escalation, obtain approval, execute, reread independent sources, record outcome. These assumptions need a real timed operator study.

One run per mode; fixed mode order A/B/C; template-based cases are not statistically independent banking incidents. No confidence interval, significance, employee productivity or financial-savings claim is made. End-to-end stage timing (queue, Supervisor, approval and verification subcomponents) is available only where persisted timestamps support it; not all requested cost/latency metrics were established. Actual timing variation is reported, not optimized away. The matched comparison demonstrates preserved safety and a modelled review-overhead tradeoff, not a complete business-value acceptance.
""")
    write("04_AI_RELIABILITY_EVALUATION.md",f"""# AI reliability — offline evaluation

`py -3.13 run_ai_contract_evaluation.py`: {ai['summary']['passed']}/{ai['summary']['checks']} checks passed. Three observed fixture runs cover Transaction, Technology and Risk; remaining checks exercise fabricated/unretrieved references, contradicted fields, absent fields, unverified prose, denied write/cross-case tools and invalid self-authorization schemas. Source equality verifies only the explicit predicate, not surrounding narrative. Supported/contradicted/insufficient/not-evaluated states remain distinct.

Artifacts: ai-contract-evaluation.json, final-postgres.xml (Phase 7/8 contract/timeout/disagreement/stale-source/Supervisor tests), grounding-before.xml and grounding-after.xml. Supervisor actual workflow behavior is established by PostgreSQL tests and recorded headless journeys; no separate live Supervisor accuracy estimate exists.

Transaction reads case-scoped payment/ledger/confirmation observations. Technology reads permitted traces/service observations and cannot query arbitrary infrastructure. Risk alone exposes reviewed historical lookup; memory IDs cannot become current evidence. Supervisor has no executable tools and cross-checks accepted specialist/source context. Output contracts cap findings, hypotheses, missing-evidence lists and require NOT_EVALUATED authority. Runner bounds iterations, tool calls, timeout, byte-based token preflight, reported usage and estimated cost; queue leases fence accepted effects. Current configured bounds and versions are in app/config.py, investigation/contracts.py and Supervisor service.

Live-provider status: NOT RUN. No model was enabled or credentials provisioned/reused; no API calls occurred. The provider implementation was not changed. Offline provider identifiers, checks and timing cannot measure actual model accuracy, unsupported-claim incidence, model error-detection recall, token efficiency or live cost. Live model evaluation requires a separately explicit credential/model decision and reliable price/usage configuration. This is a remaining P0 evidence gap.
""")
    memory_rows=[[algorithm,*[round(summary[key],4) if summary[key] is not None else 'unknown' for key in ('precision_at_1','precision_at_3','recall_at_3','reciprocal_rank','ndcg_at_3')]] for algorithm,summary in memory['summary'].items()]
    write("05_MEMORY_RETRIEVAL_EVALUATION.md",f"""# Memory Option B experiment

`py -3.13 run_memory_evaluation.py` builds four actual independently verified, reviewed PostgreSQL histories and 12 correlated retrieval queries. One history has stale policy; one is withdrawn. No revoked history is returned. Current eligibility/role/case/source/verified-source/content integrity checks occur before either algorithm's ranking. Temporal tests additionally exclude reviews after the investigator snapshot and reject naive/future cutoffs.

{table(['Algorithm','Precision@1','Precision@3','Recall@3 (positive queries)','MRR','nDCG@3 (positive queries)'],memory_rows)}

Relevance is explicitly current-policy guidance with matching observed endpoint. No subjective root-cause accuracy is inferred. Precision@3 uses denominator 3, even when fewer results exist; recall/nDCG omit no-relevant queries as undefined and MRR includes them as zero. Byte usage and measured per-query latency are in artifacts/memory-evaluation.json. Both algorithms still return same-category irrelevant histories on no-match queries, and identical Precision@3/Recall@3 show the limit of this ordering experiment.

Option B `structured-policy-2.0`: current policy +100, shared permitted source system +2 each, exact endpoint +20/mismatch -20, error type +30/mismatch -30, service name +5/mismatch -5, status code +5/mismatch -5; missing features contribute zero. Stable recency breaks equal-score ties within the existing 50-candidate window. Category, review, withdrawal, permissions and integrity remain hard filters. The score is neither confidence nor cause. Only approved observed payload fields are used; summaries and hidden labels are excluded. Contributions are inspectable in returned similarity metadata and ranking version is audited in retrieval limits. Rollback is choosing the original `overlap-recency-1.0`.

Decision: retain the original operational default. Option B is explicitly selectable by trusted Python callers for further evaluation; APIs and investigator runtime defaults do not change. Sample size and repeated templates cannot establish significance or investigation/time benefit. Broad older-case recall, root-cause discrimination, robust business-process taxonomy and production retrieval load remain unverified. No pgvector, graph database, autonomous memory learning or extra agent was added.
""")
    coverage=[]
    for name in SCENARIO_DEFINITIONS:
        coverage.append([name,"Existing synthetic generation/detection/classification test coverage", "Evidence-dependent / supported specialists or explicit waiting", "REPLAY_CONFIRMATION only if settled payment, one posted debit, absent confirmation and current controls", "Independent synthetic confirmation reread if replay eligible; otherwise unresolved/review"])
    write("06_RESOLUTION_COVERAGE_MATRIX.md",f"""# Resolution coverage and candidate decision

{table(['Existing scenario','Detection/classification','Investigation / routing','Permitted resolution','Verification / escalation'],coverage)}

This is a source-backed eligibility matrix, not a claim that every scenario has an observed successful remediation. Exact generation/detection cases are in foundational/Phase 2/3 tests; supported workflow paths in Phase 6–10 tests; final hardening has the seven headless journeys and matched operational families. Existing simulator missing_confirmation uses a PENDING payment: it is detectable but not replay-eligible until current authoritative sources establish SETTLED. Duplicate_event denotes a repeated business confirmation, distinct from duplicate transport delivery. Historical ML families do not imply operational action support.

Additional action considered: synthetic workflow-step retry. Rejected for this release: no independent step-result source or supported Workflow Investigator exists; retrying a durable task would duplicate existing worker recovery rather than demonstrate a distinct banking remediation. Ledger reconciliation correction was rejected because it changes monetary state and lacks authoritative accounting rules. Document-status correction lacks a genuine approved document source. These fail the required evidence/authorization/independent-verification tests for useful expansion. Preserve the narrow existing action allowlist; broader action coverage is deferred, not implemented or claimed.
""")
    catalogue=[]
    cases=[('Missing payment confirmation','Payments, ledger, confirmation, API','Settled or pending payment exceeds confirmation window','Transaction; Technology; Risk when evidence requires','Check settlement, one posted debit, absent confirmation, ambiguity and current action policy','Replay only when settled and authorized; otherwise investigate/review','Independent confirmation processed and all protected monetary fields unchanged'),
        ('Reconciliation mismatch','Payments and ledger','Amount or currency disagreement','Transaction; Risk / human accounting reviewer','Compare ledger transaction reference, amount/currency and event freshness','Escalate; do not alter balances','Reconcile authoritative source agreement; no automated correction exists'),
        ('Duplicate business event','Confirmation source and payment/ledger','Source marks duplicate or replayed logical confirmation','Transaction; Risk','Distinguish transport retry, source business duplicate and actual second debit','Review; no blind payment or confirmation replay','Check unique effect identity and absence of duplicate monetary effect'),
        ('API processing failure','API gateway, related payment observations','5xx or latency threshold exceeded','Technology; Transaction when payment affected','Determine ambiguous success, evidence gap and affected scope','Investigate/escalate; infrastructure restart not allowlisted','Independent source observations; HTTP 200 alone is insufficient'),
        ('Missing supporting document','Workflow; proposed approved document observation','DOCUMENT_REQUIRED workflow; no approved document-source execution exists','Document/Workflow handlers unsupported: waiting/review','Establish genuine document provenance and reviewer competence','Human obtains/reviews evidence; no fabricated document','Approved source confirmation would be needed; currently deferred'),
        ('Overdue workflow','Workflow events and timestamps','Incomplete workflow exceeds deadline','Workflow handler unsupported: explicit waiting/review','Current step, deadline, earlier approvals and missing evidence','Human triage; existing durable retry only for eligible supported tasks','Observed workflow progression would be required; no invented completion'),
        ('Contradictory evidence','Payment, confirmation, ledger and API','Incompatible current source states','Transaction; Technology; Risk when relevant','Identify superseded records and uncertainty, do not infer cause from similarity','Reinvestigate or escalate; controls block inconsistent replay','Fresh independent source agreement required before any later action')]
    for name,sources,trigger,roles,questions,action,verification in cases:
        catalogue.append(dict(name=name,business_context='Synthetic operations exception; no customer data',normal_process='Record payment and ledger, confirm outcome, advance workflow and retain audit',
            triggering_exception=trigger,source_systems=sources,synthetic_data='Stable source/event/entity/trace references, typed monetary fields, occurred/ingested timestamps',
            evidence_requirements=questions,detection_conditions=trigger,investigation_questions=questions,possible_causes='Missing or delayed observation, ambiguity, source disagreement or unsupported processing; causes are hypotheses until established',
            uncertainty='Absent, conflicting, stale, superseded or unsupported evidence',specialists=roles,human_responsibility='Review uncertainty and action-specific requests; never approve outside current role/policy',
            controls='Current source/action/policy fingerprint, limits, expiry, allowlist and independent verification',permitted_actions=action,prohibited_actions='Real money transfer, ledger correction, fabricated evidence, policy override and unsupported execution',
            independent_verification=verification,failure_outcomes='Unresolved, waiting handler, blocked control, human review, dead letter or escalation',audit='Source/evidence links, classification history, task attempts, findings, Supervisor, controls, reviewer decisions, effects and verification',
            benchmark_ground_truth='Explicit per-family synthetic outcome labels where evaluated; no assumed root-cause truth',expected_benefit='Potentially reduce search/review effort; employee savings unmeasured'))
    (ROOT/"datasets/banking-exception-catalogue.json").write_text(json.dumps(catalogue,indent=2)+"\n",encoding='utf-8')
    write("07_BANKING_EXCEPTION_CATALOGUE.md",f"""# Banking exception catalogue

Seven detailed specifications with all 20 requested dimensions are in datasets/banking-exception-catalogue.json. These are simplified synthetic operating assumptions, not bank-approved SOPs or ISO 20022 interoperability. They use stable payment/event/trace/ledger references, currency and amounts, event time versus ingestion time, settlement versus confirmation and action-specific review. No real account/customer records exist.

{table(['Exception','Observed source / trigger','Investigation','Permitted handling','Verification requirement'],[[r[0],r[1]+': '+r[2],r[4],r[5],r[6]] for r in cases])}

Manual operating baseline: open exception; identify payment/workflow references; retrieve ledger/confirmation/API observations; compare authoritative states and timestamps; establish missing or contradictory evidence; consult current policy and roles; prepare permitted action or escalation; obtain required action approval; perform the supported synthetic step; independently reread sources; record outcome and unresolved uncertainty. Human active effort and queue waiting must be timed separately in a future participant study. The benchmark's explicit time assumptions are modelling, not observed banking productivity.

Supported and proposed capabilities remain separate: document/workflow handlers and monetary correction are absent. Confirmation replay does not resend payment funds. Transport duplicates do not by themselves prove duplicate business effects. Similarity, recent incidents and historical summaries are not proof of causation.
""")
    threats=[('Prompt injection / misleading summary','Permitted source text or reviewed memory','Read-only role tools; sanitized payloads; NOT_EVALUATED authority; independent controls','Phase 7/11, hardening grounding and AI contracts','Real-model adversarial robustness unmeasured','AI/backend'),
        ('False citation / absent predicate','Specialist and Supervisor output','Reference scope and explicit field-presence/type equality','Grounding before/after and Phase 7/8','Narrative meaning is unverified','AI/backend'),
        ('Stale worker / duplicate effect','Durable worker retries','Database claim locks, lease token, post-effect fence and unique logical effect','Phase 6/10 concurrent/process tests','Production distributed failover untested','SRE'),
        ('Stale/revoked approval or policy','Action submission/execution','Action binding, expiry, current fingerprint and role check','Phase 9/10; stale-policy headless','Enterprise identity/tenant adapter absent','Controls'),
        ('False verification','Source state after effect','Independent reread including protected ledger balance','New balance regression, Phase 10, failure headless','Finite tested synthetic field scope','Backend'),
        ('Replay identity content conflict','Ingestion retry','Immutable original, persisted conflict, atomic exact-retry counters','Hardening concurrent and conflicting replay tests','Source authenticity not cryptographically established','Data/backend'),
        ('Memory contamination / future availability','Reviewed retrieval','Verified source chain, publication integrity, grants, withdrawal and snapshot cutoff','Phase 11 and temporal hardening tests','Small ranking experiment; no historical policy reconstruction guarantee','Memory'),
        ('Hidden label leakage','Simulator/evaluation tools','Explicit source columns/payload allowlist; evaluator labels isolated','Phase 7/15 and AI sanitization','No live-model leakage study','Evaluation'),
        ('Synthetic source mutation / setup authenticity','Public simulator/ingestion/correlation routes in app/main.py','Synthetic-only scope; operational effects still require protected current controls','Foundation/Phase 2–5 and control regressions','Source/setup APIs are not enterprise-authenticated; local trusted prototype only; ORM startup create_all remains a deployment concern','Security/backend'),
        ('Credential misuse','Dev auth / provider setup','Distinct long tokens, production denial, SecretStr, disabled live inference','Config/Phase 6/15; runtime manifest','No enterprise identity or external penetration test','Security')]
    risk_table=table(['Threat / actor opportunity','Entry','Control','Test evidence','Residual limitation','Owner'],threats)
    regulatory="MAS issued AI Risk Management Guidelines on 7 October 2026 for financial institutions and all forms of AI. The stated effective date is 7 October 2027, with Sections 5–6 expectations by 7 October 2028. Oversight, lifecycle testing, human review, monitoring and third-party accountability inform this prototype's design; this is not certification or a compliance conclusion. Source checked 10 October 2026: [MAS official release](https://www.mas.gov.sg/news/media-releases/2026/mas-sets-out-supervisory-expectations-on-responsible-ai-adoption-by-financial-institutions)."
    write("08_SECURITY_THREAT_MODEL.md",f"# Security threat model\n\nSynthetic sources and model/memory text are untrusted. Trusted boundaries are PostgreSQL transactions, role-issued capabilities, deterministic services and explicit reviewer action decisions. Backend APIs retain existing protection; diagnostics require a trusted local database operator.\n\n{risk_table}\n\n{regulatory}\n\nNo credential values, provider keys or environment files are included in the handoff. Public synthetic fixture tokens and development compose defaults are test material. No regulatory or banking production acceptance is asserted.")
    write("08_RISK_CONTROL_MATRIX.md",f"# Risk/control matrix\n\n{risk_table}\n\nAll controls are prototype assertions evidenced by finite tests. Residual risks remain visible; ownership labels are proposed engineering roles, not employee assignments. See the threat model for current MAS source/date applicability and limitations.")
    write("09_OBSERVABILITY_AND_RECOVERY.md",f"""# Observability and recovery

Existing TaskHistory, AuditLog, InvestigationRun telemetry, SupervisorReview, control/action IDs and VerificationResult provide traceability. Headless/benchmark records link case, task, investigation, policy, action and verification IDs with timestamps. Worker attempts and retrieval versions are auditable; no default full model/credential logging was added.

`py -3.13 run_backend_diagnostics.py --output diagnostics.json` uses a read-only PostgreSQL transaction and five-second statement timeout. It reports migration/server version, task state/type/count/oldest age boundary/max attempts, expired running leases, case states, actions and independent successes/failures. It never repairs or truncates a database. Business outcome states are separate from healthy API/worker processes. Runtime evidence: artifacts/runtime-smoke.json.

Recovery runbook: inspect task/audit IDs; confirm database/role/environment; allow expired ownership to recover through WorkQueue; inspect RETRY_WAIT scheduled time/attempt limit; use existing explicit reviewer-authorized requeue only after root cause is addressed; retain DEAD_LETTER and escalation evidence. Do not manually mark completion, bypass current controls, reuse revoked approval or delete effects. For ambiguous execution, check the unique logical operation/event and independent verification before resubmission. Old incomplete monetary snapshots require fresh control evaluation.

Fresh evidence includes actual separate worker claims/processes, rollback before effect commit, expired lease after partial effects, retry/dead-letter reconciliation, source mutation and malformed/offline provider failure. Headless interruption expires/reclaims a real durable claim. Actual PostgreSQL network-disconnect and mid-effect OS-kill experiments were not newly performed; no distributed failover or recovery-time SLA is claimed. API latency/load, database query-duration instrumentation and production alerting remain gaps. Existing bounded telemetry is preserved rather than replaced by a new monitoring platform.
""")
    ablation_rows=[[row['configuration'],row['family'],row['final_state'],row['specialist_invocations'],row['tool_calls'],row['supervisor_records'],round(row['elapsed_seconds'],4)] for row in ablation['rows']]
    write("10_AGENT_ABLATION_STUDY.md",f"""# Offline component-unavailability study

`py -3.13 run_agent_ablation.py`; ten real-service runs on owned PostgreSQL databases:

{table(['Configuration','Family','Case state','Specialist invocations','Tool calls','Supervisor records','Observed seconds'],ablation_rows)}

No action was submitted in this study. Required specialist unavailability fails explicitly and routes to review; absent Supervisor produces no review record, so action controls cannot accept a nonexistent review. Risk omission can be identical to baseline when current routing does not require Risk: this is evidence of selective routing, not proof Risk is unnecessary. Normal routing reaches advisory decision readiness, which is distinct from verified resolution. Mode A versus C in the operational benchmark supplies the rule-covered deterministic comparison.

Retain the existing specialists/Supervisor and routing. No added agent is justified. This is a failure-containment ablation, not a live-model accuracy study or comparison with an optimized single investigator. Two families/one run cannot quantify accuracy, token savings, meaningful latency advantages or broad architecture optimality. Always-all and leaner live configurations remain deferred until a nonleaking held-out accuracy/cost evaluation can support them.
""")
    cost_rows=[[mode,summary['simulated_review_decisions'],summary['modelled_human_seconds'],round(summary['modelled_human_cost_per_verified'],4) if summary['modelled_human_cost_per_verified'] is not None else 'unknown','unmeasured'] for mode,summary in operational['summary'].items()]
    write("11_COST_AND_EFFICIENCY_REPORT.md",f"""# Cost and efficiency

{table(['Mode','Scripted review decisions','Modelled human seconds','Modelled human-only SGD / verified','Measured total cost'],cost_rows)}

Human assumptions: 60 active seconds per meaningful synthetic review, 300 seconds per unresolved human-route case, SGD 30/hour. Include all cohort handling costs in the numerator and independently verified cases only in the denominator. Zero denominators return null. These are transparent assumptions; there is no observed employee study or measured financial saving.

Live input/output tokens, model calls, API prices and infrastructure resource cost are not measured. Offline telemetry's default zero tokens denotes no actual model usage and cannot be treated as measured model efficiency. Benchmark providers make no paid calls. Modelled human-only cost excludes infrastructure and does not equal total cost per resolution. Completed processing latency and censored observations are separate in operational.json.

Existing bounded tool result caching, selective specialists, scoped snapshots, candidate/result/byte limits, iteration/tool/time/usage/cost preflight caps remain. No prompt expansion, new AI call, neural memory or additional agent was introduced. Option B adds bounded structured source queries and measured experimental latency/bytes; runtime default remains original. Valid optimization should be guided by a live-model and operator study, not default-zero telemetry.
""")
    matrix_rows=[[group,len(cases),'PASS'] for group,cases in sorted(groups.items())]
    write("12_FULL_TEST_MATRIX.md",f"""# Fresh full test matrix

Baseline: {baseline['passed']} passed, {baseline['failed']} failed, {baseline['skipped']} skipped. Targeted control/execution/hardening gate: {safety['passed']} passed, no failures/skips. Final isolated PostgreSQL suite: **{final['passed']} passed, {final['failed']} failed, {final['skipped']} skipped**. A second full run in a newly installed isolated Python environment also passed **{clean['passed']}**, with no failures/skips, on another freshly migrated database. Exact JUnit and safe logs are in artifacts; test-matrix.json lists every collected case and observed duration. Historical reports remain separate at project root.

{table(['Test module','Collected cases','Result'],matrix_rows)}

Layers: unit, real PostgreSQL integration, migration round trip, API roles/contracts, independent connections and processes, fault/lease/retry injection, source/effect integrity, offline provider and grounding, memory governance, intelligence, ML and shadow/replay. New regressions add conflict replay, strict JSON scalar identity, six-way receipt concurrency, snapshot-time publication exclusion, invalid windows, incomplete citations, typed equality, changed ledger balance, empty denominators/censoring and inspectable ranking.

Separate executed artifacts: seven headless source-to-outcome journeys; 300 matched offline benchmark observations; 30 AI contracts; four-memory/12-query retrieval experiment; ten component-unavailability runs; real HTTP/worker runtime smoke. These are additional experiments, not added to pytest pass totals. Frontend preservation: {len(hashes)} byte-identical files; no frontend test or browser acceptance newly claimed.

Failures retained: grounding reproduction 1 failed/5 passed before fix; initial benchmark fixture-detection failure; smoke false closure on balance changes; initial diagnostics typo corrected before passing runtime validation. These were repaired without removing assertions or adjusting expected safety outcomes. New critical balance safety acceptance was rerun before benchmark acceptance. Full-suite wall-clock time varies by local load/connection conditions and is not a throughput benchmark.
""")
    gaps=[('Live investigation/Supervisor accuracy','P0','NOT RUN / not configured','Enable only after explicit credential/model/usage-budget decision; frozen adjudicated role dataset and real outputs'),
        ('Measured operator productivity / manual comparison','P0','DEFERRED','Timed participant study with matched evidence, active vs waiting time and blinded outcomes'),
        ('Business superiority over deterministic automation','P0','NOT DEMONSTRATED','A and C use equally capable offline predicates; live/complex-case value requires evidence'),
        ('Robust memory investigation benefit','P1','PARTIAL','Four histories and correlated queries improve ordering only; larger held-out corpus and no-match precision needed'),
        ('Additional distinct remediation','P1','DEFERRED — conditions unmet','Authoritative nonmonetary effect/result source and legitimate permission/verification rules'),
        ('Full per-stage timing and measured total cost','P1','PARTIAL','Seven trace-derived stage metrics; retry waits, live-provider-only latency and total token/infrastructure cost remain unmeasured'),
        ('Source/setup endpoint authentication and schema startup','P1 / deployment','KNOWN LIMITATION','Public synthetic source/setup routes and ORM create_all startup require production-facing gating/migration discipline; not changed in this synthetic release'),
        ('Recovery under DB disconnection / OS kill','P1','NOT NEWLY TESTED','Controlled disconnection/mid-effect kill in isolated process with observed recovery'),
        ('Production authentication / tenancy / failover','OUT OF PROTOTYPE','MISSING','Enterprise identity/grants, operational load and production deployment review'),
        ('Full browser-to-PostgreSQL acceptance','FROZEN FRONTEND','NOT RUN','Separate read-only acceptance with existing frontend; no source fixes in this task'),
        ('Native ML deployment','P2','DATA INADEQUATE','Realistic independent labelled dataset; retain deterministic routing'),
        ('Ideal agent architecture / token ablations','P1','PARTIAL','Current selective routing and component loss tested; no live single-vs-multi accuracy/cost study'),
        ('Populated persistent database migration','P1','NOT REQUIRED / NOT PERFORMED','No schema migration added; never migrate existing DB without backup and isolated-copy validation')]
    write("FINAL_GAP_REGISTER.md","# Remaining gaps\n\nThe request is only partially accepted. Implemented fixes and executed offline/PostgreSQL evidence are complete; the following claims remain unsupported. No failure is counted as a pass and no missing external study is invented.\n\n"+table(['Gap','Priority','Status','Acceptance needed'],gaps))
    before_after=[('Backend reliability','354 fresh baseline tests; balance omitted',f"{final['passed']} final tests; balance protected",'Final JUnit, critical-safety.xml'),
        ('End-to-end resolution','Three existing demo journeys','Seven headless recorded scenarios','headless-demo.json'),
        ('Operational value','No matched study','300 offline observations; no proven advantage over A','operational.json/.csv'),
        ('AI investigation accuracy','Live unmeasured','Live remains unmeasured; 30 offline checks','ai-contract-evaluation.json'),
        ('Escalation / human routing','Existing tests','Frozen offline cohorts with explicit precision/recall','operational.json'),
        ('Memory retrieval','Overlap/recency','Snapshot cutoff; experimental Option B, original default retained','memory-evaluation.json; temporal tests'),
        ('Remediation coverage','Confirmation replay only','Same safe action; broader actions deferred','coverage matrix'),
        ('Banking realism','Existing synthetic scenarios','Seven detailed exception specifications','banking-exception-catalogue.json'),
        ('Security','Scoped tools/controls','Conflict replay, partial predicate and temporal fixes; controls preserved','Phase 6–11 and new tests'),
        ('Worker recovery','Existing fenced queue','Fresh concurrency/process/failure tests and headless lease recovery','Final JUnit'),
        ('Token efficiency','Live unmeasured','No new AI calls; remains unmeasured','Offline provider metadata'),
        ('Cost / verified resolution','Unmeasured','Human-only assumption model; measured total unknown','operational metadata; cost report')]
    scores=[('Operational value / banking relevance',20,8,11,'Catalogue and matched offline study; no employee/live superiority evidence'),
        ('Backend integration / execution',20,18,19,'354 baseline/full final JUnit, seven headless journeys; narrow action coverage'),
        ('Reliability / security / controls',20,14,18,'Measured critical balance fix, replay/grounding/time fixes, real concurrency; production failover absent'),
        ('AI accuracy / evidence',15,5,7,'30 contracts and PostgreSQL grounding; actual model accuracy unknown'),
        ('Memory / workflow efficiency',10,6,7,'Temporal safety and small Option B comparison; no investigation benefit study'),
        ('Benchmark / demonstration',10,2,7,'300 replayable offline observations, failure records and assumptions; no live/human study'),
        ('Documentation / handoff',5,4,5,'Source-backed reports, commands, history and archive integrity verification')]
    write("FINAL_ACCEPTANCE_REPORT.md",f"""# Final backend hardening acceptance — 10 October 2026

**Partial mission acceptance; no 95/100 or production-readiness claim.** Fixed demonstrated verification, replay-integrity, evidence-grounding and temporal-memory weaknesses. Added actual headless evidence export, fair offline A/B/C measurement, offline AI contracts, explicit Option B experiment, component-unavailability evaluation, read-only diagnostics, runtime-process smoke, pinned observed constraints and reproducible handoff. PostgreSQL, modular monolith, durable queue, current controls, action-specific review, independent verification, human-reviewed memory and all frontend files are preserved.

Fresh final regression: **{final['passed']} passed, zero failures/skips**, versus {baseline['passed']} fresh original tests. Clean isolated Python environment and another freshly migrated database also passed **{clean['passed']}**, zero failures/skips. Critical safety gate {safety['passed']} passed. Seven headless outcomes, 300 matched offline observations, 30 AI contract checks, twelve memory queries and ten component-unavailability runs are independently linked artifacts, not folded into test totals. {len(hashes)} frontend files match session-start bytes; the pre-existing next-env.d.ts difference remains untouched.

The most important discovered defect was false closure after ledger balance changed: initial smoke traces retain this failure; current snapshot and verifier compare balance and the final cohort contains zero false verified outcomes. This is a finite synthetic gate, not a real-world zero-error guarantee. No additional source action was justified. No live provider, real bank, customer data, trained operational ML, timed employee study or GitHub push was used.

{table(['Area','Baseline','Final','Evidence'],before_after)}

## Conservative internal estimate

{table(['Internal criterion','Maximum','Baseline','Current','Point rationale / evidence'],scores)}

Baseline estimate {sum(row[2] for row in scores)}/100; current estimate {sum(row[3] for row in scores)}/100. These are subjective internal engineering estimates, not official competition weights or observed probability. Each award is bounded by cited evidence and deductions for unverified areas. The official six judging headings were read from the supplied OCBC briefing; UX/presentation are not reassessed because the frontend is frozen. The target 95 is not established. Live AI quality, actual operational value, broader safe remediation, memory generalization and recovery/load evidence explain the remaining gap.

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
""")
    write("CURRENT_STATE_UPDATED.md",f"# Current state\n\nRecovered original HEAD 26871f7 on local hardening branch. Current working backend has {final['passed']} fresh passing tests with zero failures/skips. The source and benchmark changes are confined to backend/evaluation/test/documentation files; frontend byte hashes match the session start, including its pre-existing Next declaration change. No schema migration, live API call or remote push.\n\nStart normal services with existing README/RECOVERY_HANDOFF commands. New headless and evaluation commands are listed in FINAL_ACCEPTANCE_REPORT.md. The explicit current-policy balance snapshot invalidates old incomplete authorizations on reuse; reevaluate them rather than modifying history. Original memory ranking stays default; choose structured-policy-2.0 only for reviewed experiments.\n\nOffline benchmark and live-model/human evidence are separate. See FINAL_GAP_REGISTER.md before describing this as complete competitive, business-value or enterprise acceptance.")
    print("Reports generated from complete observed evidence; frontend hashes unchanged")


if __name__=="__main__":main()
