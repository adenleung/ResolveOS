"""Temporal source predicates remain distinct from unverified narrative chronology."""
from copy import deepcopy
import pytest
from app.investigation.contracts import Finding
from app.investigation.service import INSTRUCTIONS
from app.investigation.validation import EvidenceRejected, validate_output
from tests.test_completion_semantics import observation
from test_phase6_postgres import postgres_engine, session, settings


def events():
    return [dict(id='pending', occurred_at='2026-10-10T23:06:09+00:00', payload={'confirmation_status':'PENDING'}),
            dict(id='confirmed', occurred_at='2026-10-10T23:20:10+00:00', payload={'confirmation_status':'CONFIRMED'})]


def predicate(value, refs, claim=None):
    return dict(claim=claim or value, evidence_ids=refs, assessment='SUPPORTED',
                field='confirmation_status', expected_value=value)


def check(findings, rows=None, retrieved=None, **updates):
    rows=rows or events()
    return validate_output(observation(findings=findings, hypotheses=[], **updates),
        {'events':rows,'truncated':False}, retrieved if retrieved is not None else {e['id'] for e in rows})


def test_separately_cited_lifecycle_observations_complete_without_authorization():
    r=check([predicate('PENDING',['pending']),predicate('CONFIRMED',['confirmed'])],
            summary='PENDING then CONFIRMED; internal cause unknown.')
    assert r['outcome']=='COMPLETED'
    assert all(f['assessment']=='SUPPORTED' for f in r['findings'])
    assert r['action_authorization']=='NOT_EVALUATED'


@pytest.mark.parametrize('same_time',[False,True])
def test_mixed_states_are_not_split_rewritten_or_upgraded(same_time):
    rows=events()
    if same_time: rows[1]['occurred_at']=rows[0]['occurred_at']
    finding=predicate('CONFIRMED',['pending','confirmed'],'Initially PENDING, later CONFIRMED')
    original=deepcopy(finding)
    r=check([finding],rows)
    assert finding==original
    assert len(r['findings'])==1
    assert r['findings'][0]['assessment']=='CONTRADICTED'
    assert r['findings'][0]['evidence_ids']==original['evidence_ids']
    assert r['outcome']=='NEEDS_ADDITIONAL_EVIDENCE'


def test_same_time_material_conflict_still_blocks_separate_supported_observations():
    rows=events(); rows[1]['occurred_at']=rows[0]['occurred_at']
    r=check([predicate('PENDING',['pending']),predicate('CONFIRMED',['confirmed'])],rows,
            contradictions=['Conflicting simultaneous confirmation observations require review'])
    assert all(f['assessment']=='SUPPORTED' for f in r['findings'])
    assert r['outcome']=='NEEDS_ADDITIONAL_EVIDENCE'


def test_incorrect_chronology_is_not_certified_by_field_equality():
    rows=events()
    assert rows[0]['occurred_at'] < rows[1]['occurred_at']
    r=check([predicate('CONFIRMED',['confirmed'],'CONFIRMED occurred before PENDING')],rows)
    # No temporal NLP validator: independently supported field equality must not
    # be advertised as verification of this deliberately incorrect model prose.
    assert r['findings'][0]['verification']=='OBSERVED_FIELD_EQUALITY'
    assert set(r['findings'][0]['verified_observation'])=={'field','expected_value','observed_values'}


@pytest.mark.parametrize('ref',['foreign','future-outside-snapshot','stale-snapshot-reference'])
def test_ineligible_temporal_references_fail_closed(ref):
    with pytest.raises(EvidenceRejected,match='fabricated_or_unretrieved_evidence'):
        check([predicate('CONFIRMED',[ref])])


def test_real_but_unretrieved_reference_is_rejected():
    with pytest.raises(EvidenceRejected):
        check([predicate('CONFIRMED',['confirmed'])],retrieved={'pending'})


def test_wrong_source_reference_contradicts_even_when_target_value_exists_elsewhere():
    assert check([predicate('CONFIRMED',['pending'])])['findings'][0]['assessment']=='CONTRADICTED'


def test_guidance_requires_event_specific_predicates_and_unverified_chronology():
    assert 'different temporal states' in INSTRUCTIONS
    assert 'occurred_at, not ingestion order' in INSTRUCTIONS
    assert 'Every citation' in INSTRUCTIONS
    assert 'specific source event' in Finding.model_fields['claim'].description
    assert 'Every citation' in Finding.model_fields['evidence_ids'].description


def test_temporal_guidance_reaches_both_strict_provider_output_schemas():
    from app.investigation.contracts import Output, SupervisorOutput
    from app.investigation.provider import output_schema
    for model in (Output,SupervisorOutput):
        for variant in output_schema(model)['$defs']['Finding']['anyOf']:
            assert 'specific source event' in variant['properties']['claim']['description']
            assert 'Every citation' in variant['properties']['evidence_ids']['description']
            assert variant['additionalProperties'] is False
            assert set(variant['required'])==set(variant['properties'])


def test_saved_real_c_outputs_remain_incomplete_without_rewriting():
    import json
    from pathlib import Path
    path=Path(__file__).parents[1]/'docs/live-ai/artifacts/20261010T232007-live-c0f77d/results.json'
    saved=json.loads(path.read_text())
    context={'events':saved['records']['source_events'],'truncated':False}
    for role in ('TRANSACTION','TECHNOLOGY'):
        raw=next(c['model_output'] for c in saved['calls'] if c['role']==role and c['model_output'])
        investigation=next(i for i in saved['records']['investigations'] if i['role']==role)
        retrieved={ref for tool in investigation['telemetry']['tools'] for ref in tool['evidence_ids']}
        result=validate_output(raw,context,retrieved)
        assert result['outcome']=='NEEDS_ADDITIONAL_EVIDENCE'
        if role=='TRANSACTION':
            mixed=next(f for f in result['findings'] if f['field']=='confirmation_status')
            assert mixed['assessment']=='CONTRADICTED'
            assert mixed['evidence_ids']==['4dc549f5-ad61-4503-ab87-4390b109b3f8','c89dcdef-d3b3-45f4-acd6-cb239ff156bf']
        else:
            assert result['missing_evidence']==raw['missing_evidence']
            assert result['hypotheses']==raw['hypotheses']


def test_native_snapshot_excludes_future_times_but_retains_historical_events(session, settings):
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    from sqlalchemy import select
    from app.ingestion.models import EventRecord
    from test_phase7_postgres import prepare
    case, task, runner, claim=prepare(session,settings)
    from app.models.domain import ExceptionRecord
    entity=session.scalar(select(ExceptionRecord.source_reference).where(ExceptionRecord.case_id==case.id))
    source=session.scalar(select(EventRecord).where(EventRecord.entity_reference==entity))
    now=datetime.now(timezone.utc)
    ids={}
    for label,occurred,ingested in [('historical',now-timedelta(days=1),now),
                                    ('future-occurrence',now+timedelta(days=1),now),
                                    ('future-ingestion',now,now+timedelta(days=1))]:
        ids[label]=uuid4().hex
        session.add(EventRecord(id=ids[label],event_id=uuid4().hex,source_system='confirmations',
            event_type=source.event_type,entity_reference=source.entity_reference,
            correlation_id=source.correlation_id,source_record_reference=label,
            schema_version='1.0',occurred_at=occurred,ingested_at=ingested,
            payload={'confirmation_status':'CONFIRMED'}))
    session.commit()
    _,context,_=runner.snapshot(session,task.id,'specialist',claim['lease_token'])
    eligible={row['id'] for row in context['events']}
    assert ids['historical'] in eligible
    for label in ('future-occurrence','future-ingestion'):
        assert ids[label] not in eligible
        with pytest.raises(EvidenceRejected):
            validate_output(observation(findings=[predicate('CONFIRMED',[ids[label]])],hypotheses=[]),context,{ids[label]})
