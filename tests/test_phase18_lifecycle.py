"""Scenario C mechanics and adversarial checks. Never uses a live provider."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
import pytest
import run_live_ai_test as runner


def execute(monkeypatch,tmp_path):
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos')
    directory=tmp_path/'C'
    code=runner.execute(False,directory,'C')
    return code,json.loads((directory/'results.json').read_text()),directory


def test_c_native_detection_chronology_frozen_inputs_and_supervisor(monkeypatch,tmp_path):
    code,r,directory=execute(monkeypatch,tmp_path)
    assert code==0 and r['live_model_tests']=='NOT RUN' and r['api_requests_attempted']==0
    assert r['risk_execution']=='NOT ROUTED' and r['evaluation']['workflow_complete']
    assert all(r['evaluation']['checks'].values())
    assert [s['task_type'] for s in r['workflow_stages']]==['CLASSIFY_CASE','ROUTE_CASE','INVESTIGATE_TECHNOLOGY','INVESTIGATE_TRANSACTION','REQUEST_SUPERVISOR_REVIEW']
    audit=json.loads((directory/'evidence-sufficiency.json').read_text())
    detected=datetime.fromisoformat(audit['exception_detected_at'])
    assert audit['all_required_accessible'] and len(audit['matrix'])==8
    assert audit['exception_condition']=='LATE_EVIDENCE_RECEIVED'
    rows=json.loads((directory/'source-observations.json').read_text())
    pending=next(x for x in rows if x['payload'].get('confirmation_status')=='PENDING')
    confirmed=next(x for x in rows if x['payload'].get('confirmation_status')=='CONFIRMED')
    assert datetime.fromisoformat(pending['occurred_at'])<detected<datetime.fromisoformat(confirmed['occurred_at'])<=datetime.fromisoformat(confirmed['ingested_at'])
    assert detected<datetime.fromisoformat(confirmed['ingested_at'])
    assert len({x['id'] for x in rows})==10
    truth=json.loads((directory/'ground-truth.json').read_text())
    assert set(truth['source_record_ids'])=={x['id'] for x in rows}
    assert truth==r['ground_truth'] and truth['confirmation_status']=='CONFIRMED'
    assert float(truth['starting_balance'])-float(truth['amount'])==float(truth['balance_after'])
    for name,digest in r['frozen_input_hashes'].items():
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest
    coverage=r['evaluation']['lifecycle_evidence_coverage']
    assert len(coverage)==8 and all(x['examined'] and x['supported'] for x in coverage)
    review=r['records']['supervisor'][0]['result']
    assert review['outcome']=='ESCALATE' and review['action_authorization']=='NOT_EVALUATED'
    assert len(review['specialist_hypotheses'])==2
    assert all(x['unresolved_questions'] and x['verification']=='UNVERIFIED_INTERPRETATION' for x in review['specialist_hypotheses'])
    assert all(not r['records'][name] for name in ('controls','approvals','actions','operations','verifications'))
    assert r['database_cleanup']=='DROPPED'


@pytest.mark.parametrize('defect',['foreign_citation','wrong_value','material_gap','composite'])
def test_c_does_not_force_completion_for_bad_or_incomplete_outputs(monkeypatch,tmp_path,defect):
    class Bad(runner.LifecycleOfflineSpecialist):
        def turn(self,*args):
            turn=super().turn(*args)
            if turn.output:
                finding=turn.output.findings[0]
                if defect=='foreign_citation': finding.evidence_ids=['foreign-source']
                elif defect=='wrong_value': finding.expected_value='WRONG' if finding.field!='status_code' else 404
                elif defect=='material_gap':
                    turn.output.outcome='NEEDS_ADDITIONAL_EVIDENCE'
                    turn.output.missing_evidence=['Payment effects cannot be established']
                else: finding.field=None; finding.expected_value=None
            return turn
    monkeypatch.setattr(runner,'LifecycleOfflineSpecialist',Bad)
    code,r,_=execute(monkeypatch,tmp_path)
    assert code==1 and not r['evaluation']['automated_pass']
    assert not r['records']['supervisor']
    assert r['evaluation']['checks']['no_authorization_or_execution']
    if defect!='foreign_citation':
        assert r['stop_reason']=='human_review_required'


def test_c_frozen_truth_tampering_is_failure(monkeypatch,tmp_path):
    class Tamper(runner.LifecycleOfflineSpecialist):
        def turn(self,*args):
            (tmp_path/'C/ground-truth.json').write_text('{}')
            return super().turn(*args)
    monkeypatch.setattr(runner,'LifecycleOfflineSpecialist',Tamper)
    code,r,_=execute(monkeypatch,tmp_path)
    assert code==1 and r['evaluation']['checks']['frozen_inputs_unchanged'] is False


def test_c_sufficiency_fails_before_provider_if_receipt_absent(monkeypatch,tmp_path):
    original=runner.add_lifecycle_followup
    def remove_observation(session,case_id,output):
        original(session,case_id,output)
        from sqlalchemy import select
        from app.ingestion.models import EventRecord
        row=session.scalars(select(EventRecord)).all()
        confirmed=next(e for e in row if e.payload.get('confirmation_status')=='CONFIRMED')
        confirmed.payload={**confirmed.payload,'confirmation_status':'PENDING'}
        session.commit()
    monkeypatch.setattr(runner,'add_lifecycle_followup',remove_observation)
    code,r,_=execute(monkeypatch,tmp_path)
    assert code==1 and r['error_code']=='evidence_sufficiency_failed'
    assert not r['calls'] and not r['records']['supervisor']


def test_c_fixture_followup_cannot_hide_ledger_mutation(monkeypatch,tmp_path):
    original=runner.add_lifecycle_followup
    def mutate(session,case_id,output):
        original(session,case_id,output)
        from sqlalchemy import select
        ledger=session.scalars(select(runner.SyntheticLedgerEntry)).first()
        ledger.balance_after=800
        session.commit()
    monkeypatch.setattr(runner,'add_lifecycle_followup',mutate)
    code,r,_=execute(monkeypatch,tmp_path)
    assert code==1 and r['error_code']=='fixture_bank_state_changed'
    assert not r['calls'] and r['evaluation']['checks']['bank_records_unchanged'] is False
