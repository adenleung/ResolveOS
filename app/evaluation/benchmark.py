"""Native, read-only, disposable-case benchmark; offline by default."""
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select, func, text
from app.config import Settings
from app.evaluation.database import disposable_database
from app.evaluation.records import case_records
from app.evaluation.pilot import build, catalog, VERSION, SCORING_VERSION
from app.evaluation.fixture_providers import SourceSpecialist, SourceSupervisor
from app.evaluation.benchmark_scoring import score_case, aggregate
from app.evaluation.experiment import Experiment, DeadlineProvider
from app.evaluation.quality import evaluate as quality_evaluate, VERSION as QUALITY_VERSION, digest
from app.ingestion.service import EventIngestionService
from app.ingestion.detection import ExceptionDetectionService
from app.ingestion.models import EventRecord
from app.classification.models import AssessmentHistory
from app.investigation.contracts import HANDLERS, Output, SupervisorOutput
from app.investigation.provider import OpenAIProvider, ProviderError
from app.investigation.service import InvestigationRunner
from app.supervisor.service import SupervisorRunner, SUPERVISOR_TASK
from app.orchestration.service import OrchestrationService
from app.orchestration.models import WorkTask
from app.models.domain import Case, ExceptionRecord, Policy, PolicyVersion, ActionRecord, HumanApproval, VerificationResult
from app.simulator.models import SyntheticPayment, SyntheticLedgerEntry, SyntheticConfirmationEvent
from app.controls.models import ControlAuthorization, ActionApproval
from app.controls.service import Controls
from app.execution.models import ExecutionOperation
from run_live_ai_test import Budget, MeteredProvider, HarnessError as LiveHarnessError, safe_error_code, bank_snapshot, assert_read_only_queue, claim_read_only, MODEL

class HarnessError(LiveHarnessError):
    """Benchmark-only fixed codes; never unrestricted exception messages."""
    def __init__(self,code):
        known={'benchmark_policy_fixture_invalid','explicit_batch_authorization_required','benchmark_database_url_required',
            'benchmark_ingestion_rejected','benchmark_expected_detection_missing','experiment_runtime_exhausted',
            'baseline_attempted_investigation','ground_truth_not_frozen_before_provider','baseline_attempted_supervisor',
            'benchmark_followup_rejected','benchmark_plan_integrity_failed','benchmark_task_limit'}
        super().__init__(code)
        if code in known: self.code=code;self.args=(code,)

def write(path,data):
    path.write_text(json.dumps(data,indent=2,default=str)+'\n',encoding='utf-8')

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def freeze(directory,names):
    hashes={name:sha(directory/name) for name in names}
    write(directory/'frozen-hashes.json',hashes)
    return hashes

def intact(directory,hashes):
    try:
        return json.loads((directory/'frozen-hashes.json').read_text())==hashes and all((directory/name).is_file() and sha(directory/name)==expected for name,expected in hashes.items())
    except (ValueError,OSError): return False

class BatchBudget(Budget):
    def __init__(self,requests,tokens,cost):
        super().__init__()
        self.max_requests=requests; self.max_tokens=tokens; self.max_cost=cost
    def check(self,bound,cap):
        cost=(bound*self.input_rate+cap*self.output_rate)/1_000_000
        if self.halted or len(self.calls)>=self.max_requests or self.tokens+bound+cap>self.max_tokens or self.cost+cost>self.max_cost:
            self.halted=True
            raise ProviderError('aggregate_benchmark_budget_exhausted')

class CaseBudget(Budget):
    def __init__(self,batch=None): super().__init__(); self.batch=batch
    def reserve(self,bound,cap):
        if self.batch: self.batch.check(bound,cap)
        row=super().reserve(bound,cap)
        if self.batch:
            # Conservative batch envelope never releases reservations, including
            # uncertain usage. Actual provider usage is exported separately.
            self.batch.tokens+=bound+cap; self.batch.cost+=row['reserved_cost']; self.batch.calls.append(row)
        return row

def observations(session):
    return [dict(id=r.id,event_id=r.event_id,source_system=r.source_system,source_record_reference=r.source_record_reference,
        entity_reference=r.entity_reference,correlation_id=r.correlation_id,occurred_at=r.occurred_at.isoformat(),
        ingested_at=r.ingested_at.isoformat(),payload=r.payload) for r in session.scalars(select(EventRecord).order_by(EventRecord.occurred_at,EventRecord.id))]

def bank_fingerprint(session):
    # Compare every column, not merely status/amount; hidden simulator labels are
    # hashed internally and never exported to investigators.
    state={model.__tablename__:[list(r) for r in session.execute(select(*model.__table__.columns).order_by(model.id))]
           for model in (SyntheticPayment,SyntheticLedgerEntry,SyntheticConfirmationEvent)}
    return hashlib.sha256(json.dumps(state,sort_keys=True,default=str).encode()).hexdigest()

def seed_bank(session,initial,later,primary_entity):
    # Only synthetic fixture state, never updated during agent execution. Existing
    # simulator tables describe the declared final state; historical observations
    # are independently represented by normalized source events.
    combined=initial+later
    # A failed secondary instruction sharing the accepted instruction's unique key
    # is an observed duplicate-risk signal, not a second accepted bank payment.
    payments={r['entity_reference']:r for r in combined if r['source_system']=='payments' and r['entity_reference']==primary_entity}
    for entity,row in payments.items():
        p=row['payload']; payment=SyntheticPayment(id=uuid4().hex,payment_id=entity,idempotency_key=p['idempotency_key'],
            amount=p['amount'],currency=p['currency'],beneficiary='Synthetic benchmark fixture',status=p['payment_status'],
            correlation_id=row['correlation_id'],scenario_name='SYNTHETIC_FIXTURE')
        session.add(payment);session.flush()
        latest={}
        for event in combined:
            if event['entity_reference']==entity and event['source_system']=='ledger': latest[event['source_record_reference']]=event
        for event in latest.values():
            l=event['payload'];session.add(SyntheticLedgerEntry(id=uuid4().hex,payment_id=payment.id,
                ledger_transaction_id=l['ledger_transaction_id'],entry_type=l['entry_type'],amount=l['amount'],currency=l['currency'],balance_after=l['balance_after'],status=l['ledger_status']))
        for event in combined:
            if event['entity_reference']==entity and event['source_system']=='confirmations':
                session.add(SyntheticConfirmationEvent(id=uuid4().hex,payment_id=payment.id,event_id=event['event_id'],
                    status=event['payload']['confirmation_status'],occurred_at=datetime.fromisoformat(event['occurred_at']),correlation_id=event['correlation_id']))
    session.commit()

def install_policy(session,now):
    policy=Policy(id=uuid4().hex,name='synthetic-benchmark-control-policy',active_version='1')
    session.add(policy);session.flush()
    content=dict(policy_schema='synthetic-controls-1.0',action_allowlist=['REPLAY_CONFIRMATION'],worker_roles=['WORKER'],
        approval_role='OPERATIONS_REVIEWER',max_amount='200',currency='SGD',max_affected_cases=1,max_blast_radius=1,
        human_approval_required=True,automatic_amount_limit='0',approval_ttl_seconds=600,authorization_ttl_seconds=600,
        effective_to=(now+timedelta(days=1)).isoformat(),compensation='NONE_CONFIRMATION_ONLY')
    version=PolicyVersion(id=uuid4().hex,policy_id=policy.id,version='1',content=content,effective_from=now-timedelta(minutes=1),is_active=True)
    session.add(version);session.commit()
    _,rules,issues=Controls(session,read_only=True).policy(version.id)
    if issues or str(rules.max_amount)!='200': raise HarnessError('benchmark_policy_fixture_invalid')
    return dict(version_id=version.id,content=content,read_only_policy_issues=issues,
                action_authorization='NOT_EVALUATED',applicability_tool_status='UNAVAILABLE')

def final_truth(truth,rows):
    latest={}
    for r in rows:
        key=(r['source_system'],r['source_record_reference'])
        if key not in latest or (r['occurred_at'],r['ingested_at'])>(latest[key]['occurred_at'],latest[key]['ingested_at']): latest[key]=r
    fields={'payments':['payment_status','amount'],'ledger':['ledger_status','amount'],
            'confirmations':['confirmation_status','is_duplicate'],'api_gateway':['status_code'],
            'workflow':['workflow_status','approval_status']}
    truth['required_observations']=[dict(event_record_id=r['id'],source_system=r['source_system'],source_record_reference=r['source_record_reference'],
        field=f,value=r['payload'][f],occurred_at=r['occurred_at']) for r in latest.values() if r['entity_reference']==truth['source_entity']
        for f in fields.get(r['source_system'],[]) if f in r['payload']]
    truth['independently_observed_facts']=truth['required_observations']
    truth['chronology']=[dict(id=r['id'],occurred_at=r['occurred_at'],ingested_at=r['ingested_at']) for r in rows]
    return truth

def run_case(case_id,track,directory,batch=None,manifest_spec=None,benchmark_version=VERSION,experiment=None,batch_deadline=None):
    directory.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();budget=CaseBudget(batch if track=='live' else None)
    experiment=experiment or Experiment()
    deadline=min(started+experiment.seconds,batch_deadline or float('inf'))
    budget.max_requests=experiment.requests;budget.max_tokens=experiment.tokens;budget.max_cost=experiment.usd
    family=manifest_spec.family if manifest_spec else next(c['family'] for c in catalog() if c['id']==case_id)
    row=dict(scenario_id=case_id,family=family,track=track,benchmark_version=benchmark_version,scoring_version=SCORING_VERSION,
        run_status='ATTEMPTED',live_model_tests='NOT RUN',model=MODEL if track=='live' else 'DETERMINISTIC FIXTURE' if track=='offline' else None,
        current_stage='setup',last_completed_stage=None,task_history=[],manual_review_status='PENDING REVIEW',
        actual_billed_cost=None,usage_basis='real provider telemetry' if track=='live' else 'no paid model usage',
        comparison_scope='matched detection/classification/routing; advisory reasoning unavailable in rules baseline')
    row['experiment_configuration']=experiment.export()
    records=None;truth=None;frozen={}; before=None;observed={}
    try:
        # Explicit live authorization is checked by CLI before entering this function.
        if track=='live' and batch is None: raise HarnessError('explicit_batch_authorization_required')
        if not Settings(openai_api_key=None).database_url:
            raise HarnessError('benchmark_database_url_required')
        with disposable_database() as (database,settings):
            row['disposable_database']=database.engine.url.database
            settings=settings.model_copy(update=dict(openai_api_key=None if track!='live' else settings.openai_api_key,
                investigator_live_enabled=track=='live',investigator_model=experiment.model,investigator_model_version='2025-04-14',
                investigator_max_iterations=3,investigator_max_tool_calls=12,investigator_token_budget=40000,
                investigator_cost_budget=.06,investigator_input_cost_per_million=Budget.input_rate,
                investigator_output_cost_per_million=Budget.output_rate,orchestration_max_attempts=1,database_echo=False))
            provider=OpenAIProvider(settings) if track=='live' else SourceSpecialist()
            supervisor=OpenAIProvider(settings,output_model=SupervisorOutput) if track=='live' else SourceSupervisor()
            investigator=InvestigationRunner(database,settings,DeadlineProvider(MeteredProvider(provider,budget,Output),deadline))
            reviewer=SupervisorRunner(database,settings,DeadlineProvider(MeteredProvider(supervisor,budget,SupervisorOutput),deadline))
            case_id_native=None
            try:
                with database.get_session() as session:
                    if session.scalar(select(func.count()).select_from(Case)): raise HarnessError('test_database_not_empty')
                    now=session.scalar(select(func.clock_timestamp()))
                    if manifest_spec:
                        from app.evaluation.benchmark_manifest import instantiate
                        initial,later,truth=instantiate(manifest_spec,now,benchmark_version)
                    else: initial,later,truth=build(case_id,now)
                    from app.investigation.service import instructions_for_role, PROMPT_VERSION
                    from app.supervisor.service import INSTRUCTIONS as SUPERVISOR_INSTRUCTIONS
                    from app.evaluation.quality import rubric
                    if 'quality_rubric' not in truth: truth['quality_rubric']=rubric(truth)
                    configuration=dict(experiment=experiment.export(),evaluator_version=QUALITY_VERSION,
                        evaluator_source_sha256=sha(Path(__file__).with_name('quality.py')),experiment_source_sha256=sha(Path(__file__).with_name('experiment.py')),
                        specialist_prompt_version=PROMPT_VERSION,
                        specialist_prompt_hashes={role:digest(instructions_for_role(role)) for role in truth['expected_roles']},
                        supervisor_prompt_hash=digest(SUPERVISOR_INSTRUCTIONS))
                    write(directory/'experiment-configuration.json',configuration)
                    row['family']=truth['family'];row['benchmark_version']=truth['benchmark_version'];row['scoring_version']=truth['scoring_version']
                    write(directory/'ground-truth-plan.json',truth);write(directory/'initial-sources.json',initial)
                    write(directory/'planned-followup.json',later)
                    plan_hash=freeze(directory,['ground-truth-plan.json','initial-sources.json','planned-followup.json','experiment-configuration.json'])
                    seed_bank(session,initial,later,truth['source_entity'])
                    if case_id=='P19-09': write(directory/'policy-observation.json',install_policy(session,now))
                    stats=EventIngestionService(session).ingest(initial)
                    row['initial_ingestion']=stats
                    if stats['rejected']: raise HarnessError('benchmark_ingestion_rejected')
                    ExceptionDetectionService(session,clock=lambda:now).run()
                    exceptions=session.scalars(select(ExceptionRecord)).all()
                    observed['initial_detection_types']=sorted(e.exception_type for e in exceptions)
                    if truth['expected_target_type']:
                        target=next((e for e in exceptions if e.exception_type==truth['expected_target_type'] and e.source_reference==truth['source_entity']),None)
                        if target is None: raise HarnessError('benchmark_expected_detection_missing')
                        case_id_native=target.case_id
                        OrchestrationService(session,settings).schedule_case(case_id_native)
                    before=bank_fingerprint(session)
                owner='phase19-read-only';followup_done=False;source_hash=None
                for _ in range(16):
                    if time.monotonic()>=deadline: raise HarnessError('experiment_runtime_exhausted')
                    with database.get_session() as session:
                        if case_id_native is None: break
                        human=assert_read_only_queue(session,case_id_native)
                        if human: row['stop_reason']='native_human_review';break
                        if track!='rules': investigator.activate(session);reviewer.activate(session)
                        claim=claim_read_only(session,settings,case_id_native,owner)
                    if not claim: row['stop_reason']='no_eligible_task';break
                    kind=claim['task_type'];row['current_stage']=kind;stage=time.monotonic()
                    if kind in HANDLERS:
                        if track=='rules': raise HarnessError('baseline_attempted_investigation')
                        if not frozen: raise HarnessError('ground_truth_not_frozen_before_provider')
                        investigator.run(claim['id'],owner,claim['lease_token'])
                    elif kind==SUPERVISOR_TASK:
                        if track=='rules': raise HarnessError('baseline_attempted_supervisor')
                        reviewer.run(claim['id'],owner,claim['lease_token'])
                    else:
                        with database.get_session() as session: OrchestrationService(session,settings).execute(claim['id'],owner,claim['lease_token'])
                    row['task_history'].append(dict(task_type=kind,latency_seconds=time.monotonic()-stage))
                    with database.get_session() as session:
                        task=session.get(WorkTask,claim['id'])
                        if task.status!='COMPLETED':
                            row['error_code']='native_task_failed';row['stop_reason']='task_failed';break
                        row['last_completed_stage']=kind
                        if kind=='ROUTE_CASE':
                            # Matched-capability baseline is captured before any
                            # model turn, on the exact same source bytes/database.
                            assessments=session.scalars(select(AssessmentHistory).where(AssessmentHistory.case_id==case_id_native)).all()
                            row['rules_only_observations']=dict(initial_detection_types=observed['initial_detection_types'],
                                assessments=[a.assessment for a in assessments],
                                native_records=case_records(session,case_id_native),
                                latency_seconds=sum(s['latency_seconds'] for s in row['task_history']),
                                advisory_investigation='CAPABILITY NOT AVAILABLE IN BASELINE',provider_calls=0)
                            write(directory/'rules-baseline.json',row['rules_only_observations'])
                            if later:
                                for event in later:
                                    event['occurred_at']=session.scalar(select(func.clock_timestamp())).isoformat()
                                    stats=EventIngestionService(session).ingest([event])
                                    row.setdefault('followup_ingestion',[]).append(stats)
                                    if stats['rejected']: raise HarnessError('benchmark_followup_rejected')
                                ExceptionDetectionService(session).run(entity_reference=truth['source_entity'])
                            followup_done=True
                            rows=observations(session);final_truth(truth,rows)
                            write(directory/'source-observations.json',rows);write(directory/'subsequent-sources.json',later)
                            truth['frozen_artifact_hashes']={name:sha(directory/name) for name in ['initial-sources.json','source-observations.json','subsequent-sources.json']}
                            write(directory/'ground-truth.json',truth)
                            if not intact(directory,plan_hash): raise HarnessError('benchmark_plan_integrity_failed')
                            names=list(plan_hash)+['source-observations.json','subsequent-sources.json','ground-truth.json']
                            if case_id=='P19-09': names.append('policy-observation.json')
                            frozen=freeze(directory,names);source_hash=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
                            if bank_fingerprint(session)!=before: raise HarnessError('fixture_bank_state_changed')
                    if kind==SUPERVISOR_TASK: row['stop_reason']='first_native_supervisor_review';break
                    if track=='rules' and kind=='ROUTE_CASE': row['stop_reason']='rules_capability_boundary';break
                else: raise HarnessError('benchmark_task_limit')
            finally:
                # Preserve diagnostics before owned database cleanup on every path.
                with database.get_session() as session:
                    rows=observations(session)
                    if truth and not frozen:
                        final_truth(truth,rows);write(directory/'source-observations.json',rows);write(directory/'ground-truth.json',truth)
                        frozen=freeze(directory,['ground-truth-plan.json','initial-sources.json','planned-followup.json','experiment-configuration.json','source-observations.json','ground-truth.json'])
                        source_hash=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
                    records=case_records(session,case_id_native) if case_id_native else None
                    if case_id_native is None:
                        row['rules_only_observations']=dict(initial_detection_types=observed.get('initial_detection_types',[]),
                            assessments=[],native_records=None,provider_calls=0,
                            advisory_investigation='CAPABILITY NOT AVAILABLE IN BASELINE')
                        write(directory/'rules-baseline.json',row['rules_only_observations'])
                    assessments=session.scalars(select(AssessmentHistory).where(AssessmentHistory.case_id==case_id_native)).all() if case_id_native else []
                    if 'rules_only_observations' not in row:
                        row['rules_only_observations']=dict(initial_detection_types=observed.get('initial_detection_types',[]),
                            assessments=[a.assessment for a in assessments],native_records=records,provider_calls=0,
                            advisory_investigation='CAPABILITY NOT AVAILABLE IN BASELINE')
                        write(directory/'rules-baseline.json',row['rules_only_observations'])
                    observed.update(source_observations=rows,bank_records_unchanged=bank_fingerprint(session)==before if before is not None else None,
                        frozen_inputs_unchanged=intact(directory,frozen) and hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()==source_hash,
                        safety_tables_empty=all(session.scalar(select(func.count()).select_from(model))==0 for model in
                          (ActionRecord,HumanApproval,VerificationResult,ControlAuthorization,ActionApproval,ExecutionOperation)),
                        recommended_roles=sorted({r for a in assessments for r in a.assessment.get('routing',{}).get('recommended_specialists',[])}),
                        categories=sorted({c['category'] for a in assessments for c in a.assessment.get('classification',{}).get('categories',[])}),
                        required_native_roles=sorted({t['task_type'].removeprefix('INVESTIGATE_') for t in (records or {}).get('tasks',[]) if t['task_type'] in HANDLERS}))
            row['database_cleanup']='DROPPED'
    except BaseException as exc:
        if not isinstance(exc,(Exception,KeyboardInterrupt)): raise
        row['error_code']='interrupted' if isinstance(exc,KeyboardInterrupt) else safe_error_code(exc)
        if row['error_code']=='unrelated_queue_task': observed['unrelated_task']=True
        row['run_status']='STOPPED' if isinstance(exc,KeyboardInterrupt) else 'FAILED'
        row['database_cleanup']='ATTEMPTED — inspect owned-database lifecycle'
    finally:
        observed['error_code']=row.get('error_code')
        row['observations']=observed;row['records']=records;row['frozen_hashes']=frozen
        row['provider_calls']=budget.calls
        row['live_model_tests']='ATTEMPTED' if track=='live' and budget.calls else 'NOT RUN'
        row['live_requests_attempted']=len(budget.calls) if track=='live' else 0
        row['fixture_turns']=len(budget.calls) if track=='offline' else 0
        row['input_tokens']=sum(c.get('input_tokens',0) for c in budget.calls) if track=='live' else 0
        row['output_tokens']=sum(c.get('output_tokens',0) for c in budget.calls) if track=='live' else 0
        row['accounted_tokens']=budget.tokens if track=='live' else 0
        row['estimated_usd']=budget.cost if track=='live' else 0
        row['latency_seconds']=time.monotonic()-started
        if budget.halted and batch: batch.halted=True
        if truth:
            try:
                row['quality_evaluation']=quality_evaluate(truth,records,observed,track)
                write(directory/'quality-evaluation.json',row['quality_evaluation'])
                write(directory/'review-packet.json',row['quality_evaluation']['review_packet'])
                from app.evaluation.quality import DIMENSIONS
                write(directory/'review-template.json',dict(reviewer='ANONYMOUS_REVIEWER_CODE',state='NOT REVIEWED',decision='INCONCLUSIVE',
                    packet_sha256=digest(row['quality_evaluation']['review_packet']),dimensions={k:'INCONCLUSIVE' for k in DIMENSIONS},
                    bindings=[],safety_concerns=[],comments='Replace with independent evidence-based reviewer comments.'))
            except Exception:
                row['quality_error_code']='quality_evaluation_failed';row['run_status']='FAILED'
            try:
                row['score']=score_case(truth,records,observed,track)
            except Exception:
                # A grader failure must preserve raw evidence, not lose the case
                # report or expose arbitrary exception text.
                row['error_code']='independent_scoring_failed';row['run_status']='FAILED'
                row['manual_review_status']='NOT RUN'
                write(directory/'results.json',row)
                (directory/'requests.jsonl').write_text(''.join(json.dumps(c,default=str)+'\n' for c in budget.calls),encoding='utf-8')
                return row
            if row.get('quality_evaluation'):
                layers=row['quality_evaluation']['layers']
                layers['integration'].update(checks={k:row['score'][k] for k in ('detection_correct','classification_correct','routing_correct')},
                    status='PASS' if all(row['score'][k] for k in ('detection_correct','classification_correct','routing_correct')) and
                      not row['score']['critical_failures'] and not observed.get('error_code') and observed.get('bank_records_unchanged') is True else 'FAIL')
                layers['evidence'].update(metrics={k:row['score'][k] for k in ('grounding_precision','citation_validity','required_fact_coverage','finding_groups')})
                write(directory/'quality-evaluation.json',row['quality_evaluation'])
            if row['run_status']=='ATTEMPTED':
                row['run_status']='COMPLETED' if row['score']['mechanical_acceptance'] else 'INCOMPLETE'
            write(directory/'manual-review.json',row['score']['manual_review'])
            row['manual_review_status']=row['score']['manual_review']['status']
        row['rules_only_advisory_capability']='CAPABILITY NOT AVAILABLE IN BASELINE'
        write(directory/'results.json',row)
        (directory/'requests.jsonl').write_text(''.join(json.dumps(c,default=str)+'\n' for c in budget.calls),encoding='utf-8')
    return row

def run_suite(track,selected,output,batch=None,manifest_specs=None,benchmark_version=VERSION,experiments=None,batch_seconds=1800):
    output.mkdir(parents=True,exist_ok=False)
    run_id=output.name;cases=[];started=time.monotonic()
    batch_deadline=started+batch_seconds
    selected_catalog=[dict(id=s.id,family=s.family,split=s.split) for s in manifest_specs.values()] if manifest_specs else catalog()
    write(output/'catalog.json',selected_catalog)
    for case_id in selected:
        if time.monotonic()>=batch_deadline:
            info=next(c for c in selected_catalog if c['id']==case_id)
            cases.append(dict(scenario_id=case_id,family=info['family'],run_status='NOT RUN',stop_reason='batch_runtime_exhausted'));continue
        if batch and batch.halted:
            info=next(c for c in selected_catalog if c['id']==case_id)
            cases.append(dict(scenario_id=case_id,family=info['family'],run_status='NOT RUN',stop_reason='aggregate_budget_halted'));continue
        print('Evaluating synthetic case:',case_id,'track:',track)
        case=run_case(case_id,track,output/case_id,batch,manifest_specs[case_id] if manifest_specs else None,benchmark_version,
            (experiments or {}).get(case_id),batch_deadline)
        cases.append(case)
        # A safety failure halts further evaluation, with unrun cases explicit.
        if case.get('score',{}).get('critical_failures') or case.get('error_code')=='interrupted':
            for remaining in selected[len(cases):]:
                info=next(c for c in selected_catalog if c['id']==remaining)
                cases.append(dict(scenario_id=remaining,family=info['family'],run_status='NOT RUN',stop_reason='critical_or_interrupted_stop'))
            break
    result=dict(export_version='phase19-export-1.0',run_id=run_id,benchmark_version=benchmark_version,track=track,
        live_model_tests='ATTEMPTED' if any(c.get('live_requests_attempted') for c in cases) else 'NOT RUN',
        cases=cases,metrics=aggregate(cases,track),latency_seconds=time.monotonic()-started,
        batch_reservations=dict(requests=len(batch.calls),tokens=batch.tokens,estimated_usd=batch.cost,halted=batch.halted) if batch else None,
        actual_billed_cost=None,manual_review_status='PENDING REVIEW' if track!='rules' else 'NOT APPLICABLE')
    success=all(c['run_status']=='COMPLETED' and c.get('score',{}).get('mechanical_acceptance') for c in cases)
    result['run_status']='COMPLETED' if success else 'INCOMPLETE'
    result['offline_integration_status']='OFFLINE INTEGRATION PASS' if track=='offline' and success else 'NOT APPLICABLE' if track!='offline' else 'OBJECTIVE INCOMPLETE'
    write(output/'results.json',result)
    lines=['# Phase 19 benchmark run', '',f'Track: {track}. Live model: **{result["live_model_tests"]}**.',
        f'Run: {result["run_status"]}. Narrative quality: {result["manual_review_status"]}.','',
        '| Case | Family | Status | Decision | Critical failures |','|---|---|---|---|---|']
    for c in cases: lines.append(f'| {c["scenario_id"]} | {c["family"]} | {c["run_status"]} | {c.get("score",{}).get("decision","NOT RUN")} | {c.get("score",{}).get("critical_failures",[])} |')
    lines+=['','Metrics retain numerator/denominator in results.json. Offline decisions are fixture expectations, not GPT accuracy.',
            'Rules-only advisory synthesis is CAPABILITY NOT AVAILABLE IN BASELINE. Missing results never count as passes.',
            'Inspect per-case manual-review.json against frozen source observations. No production reliability or ROI conclusion.']
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Benchmark artifacts:',output.resolve())
    return 0 if success else 1
