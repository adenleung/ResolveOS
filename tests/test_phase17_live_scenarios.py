"""Native disposable-database rehearsals; no OpenAI calls."""
import json
from datetime import datetime
import run_live_ai_test as runner


def test_scenario_b_native_supervisor_and_dataset(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos')
    directory=tmp_path/'B'
    assert runner.execute(False, directory, 'B')==0
    r=json.loads((directory/'results.json').read_text())
    truth=json.loads((directory/'ground-truth.json').read_text())
    dataset=json.loads((directory/'synthetic-input.json').read_text())
    assert r['ground_truth']==truth and truth['scenario']=='B'
    assert r['live_model_tests']=='NOT RUN' and r['api_requests_attempted']==0
    assert r['evaluation']['workflow_complete'] and all(r['evaluation']['checks'].values())
    assert len(r['records']['supervisor'])==1
    assert r['workflow_stages'][-1]['task_type']=='REQUEST_SUPERVISOR_REVIEW'
    assert r['risk_execution']=='NOT ROUTED'
    categories={item['category'] for assessment in r['routing_assessments'] for item in assessment['classification']['categories']}
    assert categories==set(truth['expected_categories'])
    assert len({x['entity_reference'] for x in dataset})==len({x['correlation_id'] for x in dataset})==1
    assert {x['id'] for x in r['records']['source_events']}==set(truth['source_record_ids'])
    sources={x['source_system']:x['payload'] for x in dataset}
    assert sources['payments']['amount']==sources['ledger']['amount']==sources['confirmations']['amount']=='100'
    assert sources['ledger']['ledger_status']=='POSTED' and sources['confirmations']['confirmation_status']=='PENDING'
    assert sources['ledger']['balance_after']=='900'
    for investigation in r['records']['investigations']:
        window=datetime.fromisoformat(investigation['result']['information_window'])
        assert all(datetime.fromisoformat(x['occurred_at'])<=window and datetime.fromisoformat(x['ingested_at'])<=window for x in r['records']['source_events'])
    assert all(x['task_type'] in runner.ALLOWLIST or x['task_type']=='REQUEST_HUMAN_REVIEW' for x in r['queue_snapshot'])
    assert all(x['attempt_count']==0 for x in r['queue_snapshot'] if x['task_type']=='REQUEST_HUMAN_REVIEW')
    assert r['database_cleanup']=='DROPPED'


def test_scenario_b_uncertainty_cannot_force_supervisor(monkeypatch, tmp_path):
    class Incomplete(runner.CorroboratedOfflineSpecialist):
        def turn(self,*args):
            turn=super().turn(*args)
            if turn.output:
                turn.output.outcome='NEEDS_ADDITIONAL_EVIDENCE'
                turn.output.missing_evidence=['Underlying cause remains unknown']
            return turn
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos')
    monkeypatch.setattr(runner,'CorroboratedOfflineSpecialist',Incomplete)
    directory=tmp_path/'uncertain'
    assert runner.execute(False,directory,'B')==1
    r=json.loads((directory/'results.json').read_text())
    assert r['stop_reason']=='human_review_required'
    assert not r['records']['supervisor']
    assert r['evaluation']['check_statuses']['supervisor_completed']=='NOT RUN'
    assert r['evaluation']['checks']['no_authorization_or_execution']


def test_truth_isolation_and_invalid_selector(tmp_path):
    a,b=runner.scenario_truth('A'),runner.scenario_truth('B')
    b['required_predicates']['status_code']=200
    assert a['required_predicates']['status_code']==runner.GROUND_TRUTH['status_code']==504
    import pytest
    with pytest.raises(ValueError,match='invalid_scenario'):
        runner.execute(False,tmp_path/'invalid','INVALID')
