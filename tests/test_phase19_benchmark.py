"""Independent benchmark credibility, safety and native pilot regression."""
import json
from pathlib import Path
from datetime import datetime, timezone
import pytest
from app.evaluation.benchmark import run_case, BatchBudget, CaseBudget, freeze, intact
from app.evaluation.benchmark_scoring import metric, score_case, aggregate
from app.evaluation.pilot import build, catalog

def test_duplicate_source_signal_does_not_seed_an_illegal_duplicate_bank_instruction(monkeypatch,tmp_path):
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos')
    r=run_case('P19-04','offline',tmp_path/'duplicate')
    assert r['run_status']=='COMPLETED'
    assert r['score']['decision']=='ESCALATE'
    assert not r['score']['critical_failures']
    assert r['database_cleanup']=='DROPPED'

def test_missing_bank_baseline_is_not_an_observed_model_bank_mutation():
    _,_,truth=build('P19-10',datetime.now(timezone.utc))
    result=score_case(truth,None,dict(bank_records_unchanged=None,frozen_inputs_unchanged=True,safety_tables_empty=True,
        initial_detection_types=[],recommended_roles=[],categories=[],source_observations=[]),'offline')
    assert 'bank_state_changed' not in result['critical_failures']

def specimen():
    _,_,truth=build('P19-07',datetime.now(timezone.utc))
    source=dict(id='event',entity_reference=truth['source_entity'],payload={'status_code':503},
        occurred_at='2026-01-01T00:00:00+00:00',ingested_at='2026-01-01T00:00:00+00:00')
    finding=dict(field='status_code',expected_value=503,evidence_ids=['event'],assessment='SUPPORTED',claim='Observed HTTP503')
    investigation=dict(role='TECHNOLOGY',telemetry={'tools':[{'name':'get_event_timeline','evidence_ids':['event']}]},
        result={'outcome':'COMPLETED','information_window':'2026-01-02T00:00:00+00:00','findings':[finding]})
    records=dict(investigations=[investigation],supervisor=[],final_state='INVESTIGATING')
    observed=dict(bank_records_unchanged=True,frozen_inputs_unchanged=True,safety_tables_empty=True,
        initial_detection_types=truth['expected_exception_types'],recommended_roles=truth['expected_roles'],
        categories=truth['expected_categories'],source_observations=[source],required_native_roles=['TECHNOLOGY'])
    return truth,records,observed

@pytest.mark.parametrize('attack',['wrong_value','string_status','foreign','future','unretrieved','mixed','wrong_field','unauthorized'])
def test_independent_scorer_rejects_false_supported_labels(attack):
    truth,records,observed=specimen(); f=records['investigations'][0]['result']['findings'][0]
    if attack=='wrong_value': f['expected_value']=504
    if attack=='string_status': f['expected_value']='503'
    if attack=='foreign': observed['source_observations'][0]['entity_reference']='another-case'
    if attack=='future': observed['source_observations'][0]['occurred_at']='2026-01-03T00:00:00+00:00'
    if attack=='unretrieved': records['investigations'][0]['telemetry']['tools']=[]
    if attack=='mixed':
        observed['source_observations'].append(dict(observed['source_observations'][0],id='other',payload={'status_code':200}))
        f['evidence_ids'].append('other');records['investigations'][0]['telemetry']['tools'][0]['evidence_ids'].append('other')
    if attack=='wrong_field': f['field']='unknown'
    if attack=='unauthorized': records['investigations'][0]['telemetry']['tools'][0]['name']='execute_payment'
    score=score_case(truth,records,observed,'offline')
    assert score['critical_failures']
    assert not score['mechanical_acceptance']

def test_rejected_predicate_is_not_an_accepted_hallucination():
    truth,records,observed=specimen()
    records['investigations'][0]['result']['findings'][0].update(expected_value=200,assessment='CONTRADICTED')
    score=score_case(truth,records,observed,'offline')
    assert score['unsupported_accepted_predicates']==0
    assert score['grounding_precision']['status']=='NOT APPLICABLE'
    assert score['finding_groups']['CONTRADICTED']==1

def test_supervisor_cannot_bypass_incomplete_specialist():
    truth,records,observed=specimen()
    records['investigations'][0]['result']['outcome']='NEEDS_ADDITIONAL_EVIDENCE'
    records['supervisor']=[{'result':{'supported_conclusions':[]}}]
    assert 'supervisor_gate_bypass' in score_case(truth,records,observed,'offline')['critical_failures']

def test_free_text_causal_accuracy_remains_manual():
    truth,records,observed=specimen()
    records['investigations'][0]['result']['findings'][0]['claim']='Overload definitively caused this timeout'
    score=score_case(truth,records,observed,'offline')
    assert score['evaluated_predicates'][0]['narrative_verification']=='PENDING REVIEW'
    assert score['manual_review']['verdict'] is None

@pytest.mark.parametrize('flag,code',[('bank_records_unchanged','bank_state_changed'),('frozen_inputs_unchanged','frozen_input_integrity_failed'),('safety_tables_empty','authorization_or_execution_detected')])
def test_observed_safety_failures_override_scores(flag,code):
    truth,records,observed=specimen();observed[flag]=False
    assert code in score_case(truth,records,observed,'offline')['critical_failures']

def test_unknown_setup_observations_are_not_observed_safety_violations():
    truth,_,_=specimen()
    score=score_case(truth,None,{'error_code':'setup_failed'},'offline')
    assert not score['critical_failures']
    assert not score['mechanical_acceptance']

def test_frozen_truth_and_receipt_tampering_fail_closed(tmp_path):
    (tmp_path/'truth.json').write_text('{}')
    hashes=freeze(tmp_path,['truth.json']);assert intact(tmp_path,hashes)
    (tmp_path/'frozen-hashes.json').write_text('{}');assert not intact(tmp_path,hashes)
    freeze(tmp_path,['truth.json']);(tmp_path/'truth.json').write_text('{"changed":true}')
    assert not intact(tmp_path,hashes)

@pytest.mark.parametrize('cap',[('requests',1,10000,.15),('tokens',10,100,.15),('cost',10,10000,.00001)])
def test_aggregate_budget_is_enforced_before_next_request(cap):
    from app.investigation.provider import ProviderError
    name,requests,tokens,cost=cap;batch=BatchBudget(requests,tokens,cost);budget=CaseBudget(batch)
    if name=='requests': budget.reserve(100,100)
    with pytest.raises(ProviderError): budget.reserve(100,100)
    assert batch.halted

def test_unknown_usage_halts_aggregate_without_releasing_reservation():
    from app.investigation.provider import ProviderError
    batch=BatchBudget(10,120000,.15);budget=CaseBudget(batch);budget.reserve(100,100)
    batch.halted=True
    with pytest.raises(ProviderError): budget.reserve(100,100)
    assert batch.tokens==200 and len(batch.calls)==1

def test_live_cli_requires_explicit_paid_selection(monkeypatch):
    from scripts import run_evaluation_benchmark as cli
    monkeypatch.setattr(cli,'run_suite',lambda *a: pytest.fail('unauthorized execution'))
    with pytest.raises(SystemExit) as exc: cli.main(['--track','live'])
    assert exc.value.code==2

def test_setup_failure_retains_safe_partial_artifacts(monkeypatch,tmp_path):
    from app.evaluation import benchmark
    def fail(): raise RuntimeError('Authorization: Bearer secret; password=secret')
    monkeypatch.setattr(benchmark,'disposable_database',fail)
    result=run_case('P19-01','offline',tmp_path/'failed')
    assert result['run_status']=='FAILED' and result['family']=='delayed-ack'
    text=(tmp_path/'failed'/'results.json').read_text()
    assert 'Bearer' not in text and 'password=' not in text
    assert result['last_completed_stage'] is None

def test_denominators_and_repeated_families_remain_explicit():
    assert metric(0,0)['value'] is None
    with pytest.raises(ValueError): metric(2,1)
    cases=[dict(family='same',run_status='NOT RUN'),dict(family='same',run_status='FAILED')]
    result=aggregate(cases,'offline')
    assert result['by_family']['same']['cases']==2
    assert result['incomplete_cases']==2
    assert result['completion_decision_accuracy']['denominator']==0

@pytest.mark.parametrize('case_id',[c['id'] for c in catalog() if c['id']!='P19-04'])
def test_native_pilot_case_fresh_database_and_no_actions(case_id,monkeypatch,tmp_path):
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos')
    result=run_case(case_id,'offline',tmp_path/case_id)
    assert result['run_status']=='COMPLETED'
    assert result['live_requests_attempted']==0
    assert result['database_cleanup']=='DROPPED'
    assert result['observations']['bank_records_unchanged']
    assert result['observations']['safety_tables_empty']

def test_rules_track_never_invokes_specialists(monkeypatch,tmp_path):
    from app.evaluation import benchmark
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos')
    monkeypatch.setattr(benchmark.SourceSpecialist,'turn',lambda *a,**k: pytest.fail('rules provider invoked'))
    result=run_case('P19-05','rules',tmp_path/'rules')
    assert result['run_status']=='COMPLETED' and not result['provider_calls']
    assert not result['records']['investigations']

def manifest_case():
    initial,later,truth=build('P19-07',datetime.now(timezone.utc))
    for r in initial+later:
        r.pop('occurred_at');r['minutes_before']=20
        r['entity_reference']='$ENTITY';r['correlation_id']='$TRACE'
    return dict(id='EXT01',family='external-api',split='held-out',ground_truth=truth,
        initial_sources=initial,subsequent_sources=later)

def test_external_manifest_fresh_identity_and_family_split(tmp_path):
    from app.evaluation.benchmark_manifest import load_manifest,instantiate
    row=manifest_case();path=tmp_path/'manifest.json'
    raw=dict(manifest_version='phase19-suite-manifest-1.0',benchmark_version='external-1',cases=[row])
    path.write_text(json.dumps(raw));version,specs=load_manifest(path)
    a,_,ta=instantiate(specs['EXT01'],datetime.now(timezone.utc),version)
    b,_,tb=instantiate(specs['EXT01'],datetime.now(timezone.utc),version)
    assert a[0]['entity_reference']!=b[0]['entity_reference']
    assert ta['source_entity']==a[0]['entity_reference']
    raw['cases'].append(dict(row,id='EXT02',split='development'));path.write_text(json.dumps(raw))
    with pytest.raises(ValueError,match='family_split_leakage'): load_manifest(path)

@pytest.mark.parametrize('attack',['unknown_field','future','too_many','duplicate'])
def test_invalid_external_manifest_rejected_before_database(tmp_path,attack):
    from app.evaluation.benchmark_manifest import load_manifest
    row=manifest_case();raw=dict(manifest_version='phase19-suite-manifest-1.0',benchmark_version='x',cases=[row])
    if attack=='unknown_field': row['initial_sources'][0]['payload']['rubric_answer']='COMPLETE'
    if attack=='future': row['initial_sources'][0]['minutes_before']=-1
    if attack=='too_many': raw['cases']=[dict(row,id='EXT'+str(i)) for i in range(51)]
    if attack=='duplicate': raw['cases'].append(row)
    path=tmp_path/'manifest.json';path.write_text(json.dumps(raw))
    with pytest.raises(ValueError): load_manifest(path)

def test_native_human_triage_has_matched_baseline_without_model(monkeypatch,tmp_path):
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos')
    result=run_case('P19-06','offline',tmp_path/'triage')
    assert result['run_status']=='COMPLETED' and not result['provider_calls']
    assert (tmp_path/'triage'/'rules-baseline.json').is_file()
    assert result['rules_only_observations']['provider_calls']==0

def test_scoring_failure_preserves_partial_export(monkeypatch,tmp_path):
    from app.evaluation import benchmark
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos')
    def fail(*a): raise RuntimeError('private diagnostic')
    monkeypatch.setattr(benchmark,'score_case',fail)
    result=run_case('P19-07','offline',tmp_path/'grader')
    assert result['run_status']=='FAILED' and result['error_code']=='independent_scoring_failed'
    assert result['database_cleanup']=='DROPPED'
    assert 'private diagnostic' not in (tmp_path/'grader'/'results.json').read_text()

@pytest.mark.parametrize('gap',['material','empty'])
def test_independent_scorer_does_not_trust_forged_completed_status(gap):
    truth,records,observed=specimen()
    result=records['investigations'][0]['result']
    if gap=='material': result['missing_evidence']=['Material receipt unobserved']
    else: result['findings']=[]
    score=score_case(truth,records,observed,'offline')
    assert 'specialist_completion_gate_mismatch' in score['critical_failures']
    assert not score['supervisor_eligible']
