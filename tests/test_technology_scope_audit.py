"""Saved live evidence exposes a retrieval gap, never an outcome override."""
import json
from pathlib import Path
import pytest
from app.investigation.tools import ToolDispatcher, ToolDenied
from app.investigation.validation import validate_output, EvidenceRejected
from app.investigation.service import instructions_for_role

def saved():
    directory=Path(__file__).parents[1]/'docs/live-ai/artifacts/20261010T235050-live-f655d5'
    results=json.loads((directory/'results.json').read_text())
    sources={e['event_id']:e for e in json.loads((directory/'synthetic-input.json').read_text())}
    events=[{**sources[e['event_id']],**e} for e in results['records']['source_events']]
    return results,dict(events=events,scope=['READ_CASE_EVIDENCE'],entities=[events[0]['entity_reference']],
                       as_of='2026-10-10T23:50:53.760609+00:00',truncated=False)

def test_technology_can_retrieve_saved_confirmation_impact_without_new_access():
    r,context=saved()
    investigation=next(i for i in r['records']['investigations'] if i['role']=='TECHNOLOGY')
    assert 'get_event_timeline' not in {t['name'] for t in investigation['telemetry']['tools']}
    dispatcher=ToolDispatcher('TECHNOLOGY',context)
    timeline=dispatcher.dispatch('get_event_timeline',{'correlation_id':context['events'][0]['correlation_id']})
    assert {e['payload'].get('confirmation_status') for e in timeline['evidence']} >= {'PENDING','CONFIRMED'}
    assert {'payments','ledger','workflow','confirmations'} <= {e['source_system'] for e in timeline['evidence']}
    gateway=dispatcher.dispatch('get_api_request',{'correlation_id':context['events'][0]['correlation_id']})
    assert {e['source_system'] for e in gateway['evidence']}=={'api_gateway'}
    with pytest.raises(ToolDenied): dispatcher.dispatch('get_event_timeline',{'correlation_id':'foreign'})
    with pytest.raises(ToolDenied): dispatcher.dispatch('get_confirmation_events',{'payment_id':context['entities'][0]})

def test_saved_model_material_gaps_are_not_promoted_by_available_unretrieved_evidence():
    r,context=saved()
    raw=next(c['model_output'] for c in r['calls'] if c['role']=='TECHNOLOGY' and c['model_output'])
    investigation=next(i for i in r['records']['investigations'] if i['role']=='TECHNOLOGY')
    retrieved={ref for t in investigation['telemetry']['tools'] for ref in t['evidence_ids']}
    result=validate_output(raw,context,retrieved)
    assert result['outcome']=='NEEDS_ADDITIONAL_EVIDENCE'
    assert result['missing_evidence']==raw['missing_evidence'] and len(result['missing_evidence'])==2
    assert result['hypotheses']==raw['hypotheses']
    assert result['action_authorization']=='NOT_EVALUATED'
    assert not r['records']['supervisor']
    receipt=next(e['id'] for e in context['events'] if e['payload'].get('confirmation_status')=='CONFIRMED')
    raw['findings'].append(dict(claim='Receipt',field='confirmation_status',expected_value='CONFIRMED',evidence_ids=[receipt],assessment='SUPPORTED'))
    with pytest.raises(EvidenceRejected): validate_output(raw,context,retrieved)

def test_role_guidance_and_tool_discovery_preserve_materiality_and_division_of_work():
    _,context=saved()
    text=instructions_for_role('TECHNOLOGY')
    assert 'get_event_timeline' in text and 'Do not assume another specialist' in text
    assert 'material' in text and 'not solely because a definitive cause is unknown' in text
    descriptions={t['name']:t['description'] for t in ToolDispatcher('TECHNOLOGY',context).definitions()}
    assert 'confirmation' in descriptions['get_event_timeline']
    assert 'internal service logs and traces are not available' in descriptions['get_service_logs']
    assert 'ledger consistency' not in instructions_for_role('RISK')

def test_native_c_delivers_role_contract_without_altering_completion_or_authorization(monkeypatch,tmp_path):
    import run_live_ai_test as runner
    roles=set()
    class Capture(runner.LifecycleOfflineSpecialist):
        def turn(self,instructions,*args):
            if '\nRole: TECHNOLOGY\n' in instructions:
                assert 'get_event_timeline' in instructions
                assert 'Do not assume another specialist' in instructions
                roles.add('TECHNOLOGY')
            else:
                assert instructions.endswith('\nRole: TRANSACTION')
                roles.add('TRANSACTION')
            return super().turn(instructions,*args)
    monkeypatch.setattr(runner,'LifecycleOfflineSpecialist',Capture)
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos')
    directory=tmp_path/'native-C'
    assert runner.execute(False,directory,'C')==0
    r=json.loads((directory/'results.json').read_text())
    assert roles=={'TECHNOLOGY','TRANSACTION'}
    assert r['api_requests_attempted']==0 and r['database_cleanup']=='DROPPED'
    assert r['evaluation']['automated_pass'] and r['records']['supervisor']
    assert not any(r['records'][name] for name in ('actions','approvals','controls','operations','verifications'))
