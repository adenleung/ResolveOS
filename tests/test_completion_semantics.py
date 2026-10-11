"""Advisory completion is distinct from causal certainty and authorization."""
import json
import pytest
from app.investigation.contracts import Output, Hypothesis
from app.investigation.validation import validate_output
import run_live_ai_test as runner


def observation(**updates):
    data=dict(summary='Observed timeout; internal cause is unconfirmed.', outcome='COMPLETED',
        findings=[dict(claim='HTTP status', field='status_code', expected_value=504, evidence_ids=['event'], assessment='SUPPORTED')],
        hypotheses=[dict(possible_cause='An internal dependency may have delayed acknowledgement', supporting_evidence_ids=['event'],
                         contradicting_evidence_ids=[], unresolved_questions=['What caused the timeout?'])],
        missing_evidence=[], contradictions=[], suggested_next_steps=['Obtain diagnostic logs; advisory review only'],
        proposed_resolution=None, action_authorization='NOT_EVALUATED')
    return {**data, **updates}


def test_unknown_cause_does_not_itself_block_supported_advisory_completion():
    result=validate_output(observation(), {'events':[dict(id='event',payload={'status_code':504})],'truncated':False}, {'event'})
    assert result['outcome']=='COMPLETED'
    assert result['hypotheses'][0]['unresolved_questions']
    assert result['action_authorization']=='NOT_EVALUATED'


@pytest.mark.parametrize('updates', [dict(missing_evidence=['Payment outcome is unknown']), dict(outcome='NEEDS_ADDITIONAL_EVIDENCE'),
    dict(findings=[dict(claim='Composite claim',field=None,expected_value=None,evidence_ids=['event'],assessment='SUPPORTED')])])
def test_material_gaps_model_uncertainty_and_unverified_claims_remain_blocking(updates):
    result=validate_output(observation(**updates), {'events':[dict(id='event',payload={'status_code':504})],'truncated':False}, {'event'})
    assert result['outcome']=='NEEDS_ADDITIONAL_EVIDENCE'


def test_completion_contract_explains_materiality():
    from app.investigation.service import INSTRUCTIONS
    assert 'causal certainty' in INSTRUCTIONS
    assert 'material' in Output.model_fields['missing_evidence'].description


def test_actual_saved_b_output_remains_incomplete_under_unchanged_validator():
    from pathlib import Path
    fixture=json.loads((Path(__file__).parent/'fixtures/scenario_b_live_completion_gap.json').read_text())
    result=validate_output(fixture['output'], {'events':fixture['events'],'truncated':False}, set(fixture['retrieved']))
    assert result['outcome']=='NEEDS_ADDITIONAL_EVIDENCE'
    assert result['missing_evidence']
    assert any(f['assessment']=='NOT_EVALUATED' for f in result['findings'])


def test_advisory_uncertainty_cannot_grant_authorization():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Output.model_validate(observation(action_authorization='APPROVED'))


def test_uncertainty_reaches_native_supervisor_and_cannot_authorize(monkeypatch,tmp_path):
    captured=[]
    class Uncertain(runner.CorroboratedOfflineSpecialist):
        def turn(self,*args):
            turn=super().turn(*args)
            if turn.output:
                finding=turn.output.findings[0]
                turn.output.hypotheses=[Hypothesis(possible_cause='Internal cause is unconfirmed',
                    supporting_evidence_ids=finding.evidence_ids,contradicting_evidence_ids=[],
                    unresolved_questions=['Internal diagnostic logs are unavailable'])]
            return turn
    class Reviewer(runner.OfflineSupervisor):
        def turn(self,instructions,messages,*args):
            snapshot=json.loads(messages[0]['content'])
            assert snapshot['specialist_hypotheses']
            assert all(h['verification']=='UNVERIFIED_INTERPRETATION' for h in snapshot['specialist_hypotheses'])
            captured.append(snapshot['specialist_hypotheses'])
            return super().turn(instructions,messages,*args)
    monkeypatch.setattr(runner,'CorroboratedOfflineSpecialist',Uncertain)
    monkeypatch.setattr(runner,'OfflineSupervisor',Reviewer)
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos')
    directory=tmp_path/'uncertain-complete'
    assert runner.execute(False,directory,'B')==0
    r=json.loads((directory/'results.json').read_text())
    review=r['records']['supervisor'][0]
    assert review['result']['specialist_hypotheses']==captured[0]
    assert review['result']['action_authorization']=='NOT_EVALUATED'
    assert all(not r['records'][name] for name in ('controls','approvals','actions','operations','verifications'))
    assert r['evaluation']['checks']['bank_records_unchanged']
