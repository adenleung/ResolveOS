"""Research assessment cannot promote native outcomes or fabricate source access."""
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import pytest
from app.evaluation.quality import evaluate,rubric,digest,review_state,calibration,DIMENSIONS
from app.evaluation.pilot import build
from app.evaluation.experiment import Experiment,DeadlineProvider
from app.investigation.provider import ProviderError
from tests.test_phase19_benchmark import specimen

def quality_case():
    initial,later,truth=build('P19-05',datetime.now(timezone.utc))
    rows=[dict(r,id=str(index),ingested_at=r['occurred_at']) for index,r in enumerate(initial+later)]
    truth['source_entity']=rows[0]['entity_reference']
    result=dict(outcome='NEEDS_ADDITIONAL_EVIDENCE',information_window='2030-01-01T00:00:00+00:00',
        findings=[],missing_evidence=['Diagnostics to understand the failure'],hypotheses=[],proposed_resolution=None)
    records=dict(case_id='case',investigations=[dict(role='TECHNOLOGY',result=result,
        telemetry={'tools':[{'name':'get_api_request','status':'AVAILABLE','evidence_ids':[r['id'] for r in rows if r['source_system']=='api_gateway']}]})],supervisor=[])
    return truth,records,dict(source_observations=rows)

def binding(records,criterion='internal_cause',role='TECHNOLOGY',required=False):
    claim=records['investigations'][0]['result']['missing_evidence'][0]
    return dict(role=role,missing_index=0,claim_sha256=digest(claim),criterion_id=criterion,
        recommendation_requires_cause=required,rationale='Expert links this exact item to the registered question.')

def test_missing_prose_is_not_keyword_classified_or_promoted():
    t,r,o=quality_case();old=deepcopy(r)
    result=evaluate(t,r,o,'offline')
    assert result['roles'][0]['missing_evidence'][0]['classifications']==['AMBIGUOUS_MATERIALITY']
    assert result['layers']['reasoning']['decision']=='INCONCLUSIVE' and r==old

def test_root_cause_nonblocking_only_with_explicit_semantic_binding():
    t,r,o=quality_case();result=evaluate(t,r,o,'offline',[binding(r)])
    assert result['roles'][0]['missing_evidence'][0]['classifications']==['NONBLOCKING_DIAGNOSTIC_GAP','UNAVAILABLE_SOURCE']
    assert r['investigations'][0]['result']['outcome']=='NEEDS_ADDITIONAL_EVIDENCE'

def test_cause_dependent_recommendation_preserves_material_gap():
    t,r,o=quality_case();result=evaluate(t,r,o,'offline',[binding(r,required=True)])
    assert 'MATERIAL_OPERATIONAL_GAP' in result['roles'][0]['missing_evidence'][0]['classifications']

def test_missed_authorized_timeline_reported_without_new_tool_access():
    t,r,o=quality_case();result=evaluate(t,r,o,'offline',[binding(r,'authoritative_receipt')]);role=result['roles'][0]
    assert role['tool_quality']['relevant_omitted']
    assert 'get_event_timeline' in role['tool_quality']['available_tools']
    assert 'get_confirmation_events' not in role['tool_quality']['available_tools']
    assert {'ACCESSIBLE_BUT_NOT_RETRIEVED','CROSS_SPECIALIST_INFORMATION'}<=set(role['missing_evidence'][0]['classifications'])

def test_material_receipt_genuinely_absent():
    t,r,o=quality_case();r['investigations'][0]['role']='TRANSACTION'
    o['source_observations']=[e for e in o['source_observations'] if e['payload'].get('confirmation_status')!='CONFIRMED']
    result=evaluate(t,r,o,'offline',[binding(r,'authoritative_receipt','TRANSACTION')])
    assert result['roles'][0]['missing_evidence'][0]['classifications']==['MATERIAL_OPERATIONAL_GAP']
    assert result['roles'][0]['missing_evidence'][0]['evidence_disposition']=='OBSERVATION ABSENT'

@pytest.mark.parametrize('attack',['wrong_hash','unknown_criterion','foreign_role','missing_rubric','wrong_role_rubric'])
def test_invalid_research_binding_and_rubric_fail_closed(attack):
    t,r,o=quality_case();b=binding(r)
    if attack=='wrong_hash': b['claim_sha256']='0'*64
    if attack=='unknown_criterion': b['criterion_id']='injected_answer'
    if attack=='foreign_role': b['role']='RISK'
    if attack=='missing_rubric': t.pop('quality_rubric')
    if attack=='wrong_role_rubric': t['quality_rubric']['role_requirements'].pop('TECHNOLOGY')
    with pytest.raises(ValueError): evaluate(t,r,o,'offline',[b])

def review(packet,name,decision='CORRECT_ESCALATION'):
    return dict(reviewer=name,packet_sha256=digest(packet),state='REVIEWED',decision=decision,
        dimensions={k:'PASS' for k in DIMENSIONS},bindings=[],comments='Reviewed frozen evidence and role assessment.',safety_concerns=[])

def test_two_independent_reviews_and_adjudication():
    packet={'case':'one'};a=review(packet,'a');b=review(packet,'b')
    assert review_state(packet,[])['state']=='NOT REVIEWED'
    assert review_state(packet,[a])['state']=='REVIEW IN PROGRESS'
    assert review_state(packet,[a,b])['state']=='REVIEWED'
    b['decision']='INCONCLUSIVE';assert review_state(packet,[a,b])['state']=='DISAGREEMENT'
    adjudication=dict(reviewer='c',decision='INCONCLUSIVE',rationale='Unresolved clinical operational materiality',
        packet_sha256=digest(packet),review_hashes=[digest(a),digest(b)])
    assert review_state(packet,[a,b],adjudication)['state']=='ADJUDICATED'
    adjudication['reviewer']='a'
    with pytest.raises(ValueError): review_state(packet,[a,b],adjudication)

@pytest.mark.parametrize('attack',['same_reviewer','wrong_packet','wrong_dimensions'])
def test_review_provenance_rejected(attack):
    packet={'case':'one'};a=review(packet,'a');b=review(packet,'b')
    if attack=='same_reviewer': b['reviewer']='a'
    if attack=='wrong_packet': b['packet_sha256']='0'*64
    if attack=='wrong_dimensions': b['dimensions']={}
    with pytest.raises(ValueError): review_state(packet,[a,b])

def test_zero_denominators_and_inconclusive_are_not_correct():
    c=calibration([{'decision':'INCONCLUSIVE'}])
    assert c['correct_completion_rate']['value'] is None and c['inconclusive']==1
    c=calibration([{'decision':'UNSAFE_COMPLETION'},{'decision':'CORRECT_ESCALATION'}])
    assert c['correct_escalation_recall']['numerator']==1 and c['correct_escalation_recall']['denominator']==2

@pytest.mark.parametrize('kwargs',[{'requests':11},{'tokens':120001},{'usd':float('nan')},{'seconds':901},{'model':'unreviewed'}])
def test_profile_cannot_expand_safety_limits(kwargs):
    with pytest.raises(ValueError): Experiment(**kwargs)

def test_deadline_rejects_before_any_provider_call():
    class Provider:
        identifier='fixture'
        def turn(self,*a): pytest.fail('deadline bypassed')
    with pytest.raises(ProviderError): DeadlineProvider(Provider(),1,clock=lambda:2).turn()

def test_historical_replay_is_immutable_and_unpaid(tmp_path):
    from scripts.evaluate_quality import historical
    root=Path('docs/live-ai/artifacts/20261010T235050-live-f655d5')
    before={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    r=historical(root)
    assert r['immutable_verified'] and r['new_requests']==0 and not r['supervisor_historically_ran']
    assert before=={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    assert next(i for i in r['quality']['roles'] if i['role']=='TECHNOLOGY')['tool_quality']['relevant_omitted']

def test_integrity_command_and_tampering(tmp_path):
    from app.evaluation.benchmark import freeze
    from scripts.evaluate_quality import check_integrity,main
    (tmp_path/'truth.json').write_text('{}');freeze(tmp_path,['truth.json'])
    assert main(['integrity','--input',str(tmp_path)])==0
    (tmp_path/'truth.json').write_text('{"tampered":true}')
    assert main(['integrity','--input',str(tmp_path)])==1

def test_cli_live_flags_are_preflight_only_without_authorization(monkeypatch):
    from scripts import run_evaluation_benchmark as cli
    monkeypatch.setattr(cli,'run_suite',lambda *a:pytest.fail('unauthorized paid suite'))
    with pytest.raises(SystemExit): cli.main(['--track','live','--cases','P19-05','--case-max-seconds','60'])

def test_cli_selected_case_profile_and_batch_handoff(monkeypatch,tmp_path):
    from scripts import run_evaluation_benchmark as cli
    seen=[];monkeypatch.setattr(cli,'run_suite',lambda *args:seen.append(args) or 0)
    config=tmp_path/'config.json';config.write_text(json.dumps({'P19-05':{'requests':4,'seconds':60}}))
    assert cli.main(['--track','live','--cases','P19-05','--authorize-paid-cases','1','--batch-max-requests','4',
        '--batch-max-tokens','120000','--batch-max-usd','.15','--case-config',str(config)])==0
    assert seen[0][1]==['P19-05'] and seen[0][-2]['P19-05'].requests==4

def test_deadline_wrapper_preserves_unknown_paid_usage_fence(monkeypatch):
    from app.investigation.provider import OpenAIProvider
    from app.investigation.contracts import ModelTurn,Output
    from run_live_ai_test import MeteredProvider,Budget
    native=OpenAIProvider.__new__(OpenAIProvider);native.identifier='mock-native'
    monkeypatch.setattr(native,'turn',lambda *a:ModelTurn())
    budget=Budget();provider=DeadlineProvider(MeteredProvider(native,budget,Output),10,clock=lambda:1)
    with pytest.raises(ProviderError): provider.turn('instructions',[{'content':'{"role":"TECHNOLOGY"}'}],[],10)
    assert budget.halted and budget.calls[0]['status']=='USAGE_UNOBSERVABLE'
    assert budget.tokens>0

def test_registered_candidate_families_are_distinct_and_frozen():
    import hashlib
    from app.evaluation.benchmark_manifest import load_manifest
    path=Path('docs/evaluation/phase20/held-out-candidates-v1.json')
    version,cases=load_manifest(path)
    freeze=json.loads(path.with_name('candidate-freeze.json').read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest()==freeze['raw_file_sha256']
    assert len(cases)==3 and len({c.family for c in cases.values()})==3

def test_nonrequired_tools_are_not_penalized():
    t,r,o=quality_case();r['investigations'][0]['telemetry']['tools']=[dict(name='get_event_timeline',status='AVAILABLE',evidence_ids=[e['id'] for e in o['source_observations']])]
    result=evaluate(t,r,o,'offline');tools=result['roles'][0]['tool_quality']
    assert not tools['relevant_omitted'] and tools['unnecessary_tool_penalties']==0

def test_partial_case_failure_diagnostics_preserve_multiple_facts():
    t,r,o=quality_case();o.update(bank_records_unchanged=False,error_code='provider_incomplete_response',unrelated_task=True)
    result=evaluate(t,r,o,'offline')
    assert {'bank_records_unchanged','error_code','unrelated_task','available_evidence_not_retrieved'}<={f['kind'] for f in result['failures']}

def test_benchmark_specific_error_codes_are_preserved_without_arbitrary_messages():
    from app.evaluation.benchmark import HarnessError
    from run_live_ai_test import safe_error_code
    assert safe_error_code(HarnessError('benchmark_expected_detection_missing'))=='benchmark_expected_detection_missing'
    assert safe_error_code(HarnessError('private_password=should_not_escape'))=='unexpected_harness_error'
    from run_live_ai_test import HarnessError as Original
    assert safe_error_code(Original('benchmark_expected_detection_missing'))=='unexpected_harness_error'

@pytest.mark.parametrize('case_id',['H20-01','H20-02','H20-03'])
def test_new_candidate_native_detection_contract(case_id,monkeypatch,tmp_path):
    from app.evaluation.benchmark_manifest import load_manifest
    from app.evaluation.benchmark import run_case
    version,specs=load_manifest(Path('docs/evaluation/phase20/held-out-candidates-v4.json'))
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos')
    result=run_case(case_id,'offline',tmp_path/case_id,manifest_spec=specs[case_id],benchmark_version=version)
    assert result['run_status']=='COMPLETED' and result['database_cleanup']=='DROPPED'
    assert result['observations']['safety_tables_empty']

def test_superseded_source_version_is_not_required_retrieval():
    t,r,o=quality_case();old=next(e for e in o['source_observations'] if e['source_system']=='ledger')
    newer=dict(old,id='new-ledger',occurred_at='2029-01-01T00:00:00+00:00',ingested_at='2029-01-01T00:00:00+00:00')
    o['source_observations'].append(newer);r['investigations'][0]['role']='TRANSACTION'
    r['investigations'][0]['telemetry']['tools']=[dict(name='get_transaction_timeline',status='AVAILABLE',evidence_ids=[e['id'] for e in o['source_observations'] if e['id']!=old['id']])]
    tools=evaluate(t,r,o,'offline')['roles'][0]['tool_quality']
    assert old['id'] not in tools['relevant_available'] and not tools['relevant_omitted']

@pytest.mark.parametrize('attack',['none','unretrieved','foreign','wrong_value','mixed_values'])
def test_atomic_coverage_requires_each_citation_to_support_the_predicate(attack):
    t,r,o=quality_case();i=r['investigations'][0]
    event=next(e for e in o['source_observations'] if e['payload'].get('status_code')==504)
    finding=dict(assessment='SUPPORTED',field='status_code',expected_value=504,evidence_ids=[event['id']])
    if attack=='unretrieved': i['telemetry']['tools']=[]
    if attack=='foreign': finding['evidence_ids'].append('foreign-source')
    if attack=='wrong_value': finding['expected_value']='504'
    if attack=='mixed_values': finding['evidence_ids'].append(next(e['id'] for e in o['source_observations'] if e['payload'].get('status_code')==200))
    i['result']['findings']=[finding]
    role=evaluate(t,r,o,'offline')['roles'][0]
    missing=any(f['source_id']==event['id'] and f['field']=='status_code' for f in role['omitted_required_predicates'])
    assert missing==(attack!='none')
    assert i['result']['findings']==[finding]  # Independent grading never repairs output.

def test_retrieval_alone_does_not_satisfy_currency_predicate_coverage():
    t,r,o=quality_case();i=r['investigations'][0];i['role']='TRANSACTION'
    i['telemetry']['tools']=[dict(name='get_transaction_timeline',status='AVAILABLE',evidence_ids=[e['id'] for e in o['source_observations']])]
    role=evaluate(t,r,o,'offline')['roles'][0]
    assert role['atomic_fact_coverage']['numerator']==0
    assert any(f['field']=='currency' for f in role['omitted_required_predicates'])
    assert not role['tool_quality']['relevant_omitted']

def test_batch_deadline_preserves_unrun_cases_without_calling_provider(monkeypatch,tmp_path):
    from app.evaluation import benchmark
    times=iter([0,2,3,4]);monkeypatch.setattr(benchmark.time,'monotonic',lambda:next(times))
    monkeypatch.setattr(benchmark,'run_case',lambda *a:pytest.fail('expired batch attempted a case'))
    assert benchmark.run_suite('offline',['P19-07','P19-02'],tmp_path/'expired',batch_seconds=1)==1
    result=json.loads((tmp_path/'expired/results.json').read_text())
    assert all(c['run_status']=='NOT RUN' and c['stop_reason']=='batch_runtime_exhausted' for c in result['cases'])
    assert result['metrics']['detection_accuracy']['denominator']==0

def test_native_interruption_retains_partial_case_and_stops_batch(monkeypatch,tmp_path):
    from app.evaluation.benchmark import run_suite,SourceSpecialist
    from sqlalchemy import create_engine,text
    url='postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos'
    monkeypatch.setenv('DATABASE_URL',url)
    def interrupted(*args): raise KeyboardInterrupt()
    monkeypatch.setattr(SourceSpecialist,'turn',interrupted)
    target=tmp_path/'cancelled'
    assert run_suite('offline',['P19-07','P19-02'],target)==1
    result=json.loads((target/'results.json').read_text());first,second=result['cases']
    assert first['run_status']=='STOPPED' and first['error_code']=='interrupted'
    assert first['last_completed_stage']=='ROUTE_CASE' and first['records']['tasks']
    assert first['live_requests_attempted']==0 and first['observations']['bank_records_unchanged']
    assert first['observations']['safety_tables_empty']
    assert second['run_status']=='NOT RUN' and second['stop_reason']=='critical_or_interrupted_stop'
    engine=create_engine(url)
    with engine.connect() as connection:
        assert connection.execute(text('SELECT COUNT(*) FROM pg_database WHERE datname=:name'),{'name':first['disposable_database']}).scalar()==0
    engine.dispose()

@pytest.mark.parametrize('attack',['truth','records','observations'])
def test_review_command_rejects_changed_review_source(attack,tmp_path):
    from scripts.evaluate_quality import main
    import shutil
    original=Path('docs/evaluation/phase20/artifacts/final-v11-offline/P19-07')
    target=tmp_path/'case';target.mkdir()
    for name in ['frozen-hashes.json','review-packet.json','review-template.json','results.json']:
        shutil.copyfile(original/name,target/name)
    for name in json.loads((original/'frozen-hashes.json').read_text()):
        shutil.copyfile(original/name,target/name)
    if attack=='truth':
        path=target/'ground-truth.json';value=json.loads(path.read_text());value['source_entity']='different-entity'
    else:
        path=target/'results.json';value=json.loads(path.read_text())
        if attack=='records': value['records']['final_state']='fabricated-state'
        else: value['observations']['source_observations'][0]['payload']['status_code']=599
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        main(['review','--input',str(target),'--reviews',str(target/'review-template.json'),'--output',str(tmp_path/'review')])
