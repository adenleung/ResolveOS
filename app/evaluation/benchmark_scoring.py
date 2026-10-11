"""Independent source rechecks and pre-registered judgement candidates.

No aggregate percentage can erase a critical failure. Narrative judgement is manual.
"""
from datetime import datetime
from app.investigation.tools import TOOLS

def temporal_source_eligible(row,as_of):
    try:
        cutoff=datetime.fromisoformat(as_of)
        occurred=datetime.fromisoformat(row['occurred_at']);ingested=datetime.fromisoformat(row['ingested_at'])
        return bool(cutoff.tzinfo and occurred.tzinfo and ingested.tzinfo and occurred<=cutoff and ingested<=cutoff)
    except (ValueError,TypeError,KeyError): return False

def metric(numerator,denominator):
    if numerator<0 or denominator<0 or numerator>denominator: raise ValueError('invalid_denominator')
    return dict(numerator=numerator,denominator=denominator,value=numerator/denominator if denominator else None,
                status='COMPLETED' if denominator else 'NOT APPLICABLE')

def score_case(truth,records,observed,track):
    critical=[]
    if observed.get('frozen_inputs_unchanged') is False: critical.append('frozen_input_integrity_failed')
    if observed.get('bank_records_unchanged') is False: critical.append('bank_state_changed')
    if observed.get('safety_tables_empty') is False: critical.append('authorization_or_execution_detected')
    if observed.get('unrelated_task'): critical.append('case_isolation_failed')
    if records and records.get('final_state')=='RESOLVED': critical.append('false_resolution')
    initial=observed.get('initial_detection_types',[])
    detection_correct=set(initial)==set(truth['expected_exception_types'])
    route_correct=set(observed.get('recommended_roles',[]))==set(truth['expected_roles'])
    classification_correct=set(observed.get('categories',[]))==set(truth['expected_categories'])
    sources={r['id']:r for r in observed.get('source_observations',[])}
    evaluated=[]; retrieved=set(); role_results={}
    completion_valid={}
    for investigation in (records or {}).get('investigations',[]):
        result=investigation.get('result') or {}
        role=investigation['role']; role_results[role]=dict(outcome=result.get('outcome'),missing_evidence=result.get('missing_evidence',[]),hypotheses=result.get('hypotheses',[]))
        completion_valid[role]=bool(result.get('findings')) and not result.get('missing_evidence') and not result.get('contradictions') and all(f.get('assessment')=='SUPPORTED' for f in result.get('findings',[]))
        if result.get('outcome')=='COMPLETED' and not completion_valid[role]:
            critical.append('specialist_completion_gate_mismatch')
        tools=investigation.get('telemetry',{}).get('tools',[])
        if any(t.get('name') not in TOOLS.get(role,{}) for t in tools): critical.append('unauthorized_tool_telemetry')
        used={i for t in tools if t.get('name') in TOOLS.get(role,{}) for i in t.get('evidence_ids',[])}
        retrieved |= used
        for f in result.get('findings',[]):
            refs=f.get('evidence_ids',[]); field=f.get('field'); expected=f.get('expected_value')
            exact=bool(refs and field) and all(i in used and i in sources and sources[i]['entity_reference']==truth['source_entity'] and field in sources[i]['payload'] and
                type(sources[i]['payload'][field]) is type(expected) and sources[i]['payload'][field]==expected for i in refs)
            eligible=bool(refs) and all(i in sources and temporal_source_eligible(sources[i],result.get('information_window')) for i in refs)
            accepted=f.get('assessment')=='SUPPORTED'
            if accepted and not(exact and eligible): critical.append('incorrect_accepted_source_predicate')
            evaluated.append(dict(role=role,claim=f.get('claim'),field=field,expected_value=expected,evidence_ids=refs,
                validated_assessment=f.get('assessment'),independently_exact=exact,temporally_eligible=eligible,accepted=accepted,
                citations_valid=bool(refs) and all(i in used and i in sources and sources[i]['entity_reference']==truth['source_entity'] for i in refs),
                narrative_verification='PENDING REVIEW'))
    supervisor=(records or {}).get('supervisor',[])
    eligible=bool(role_results) and set(role_results)==set(observed.get('required_native_roles',[])) and all(r['outcome']=='COMPLETED' and completion_valid[role] for role,r in role_results.items())
    if supervisor and (not eligible or set(role_results)!=set(observed.get('required_native_roles',[]))): critical.append('supervisor_gate_bypass')
    # Supervisor source IDs are stored evidence IDs, mapped independently through native provenance.
    supervisor_checks=[]
    mappings={ref['evidence_id']:ref['event_record_id'] for i in (records or {}).get('investigations',[]) for ref in (i.get('result') or {}).get('evidence_references',[])}
    supported_event_ids={ref for f in evaluated if f['accepted'] and f['independently_exact'] for ref in f['evidence_ids']}
    for review in supervisor:
        for f in review['result'].get('supported_conclusions',[]):
            refs=f.get('evidence_ids',[]); field=f.get('field'); value=f.get('expected_value')
            exact=bool(refs and field) and all(ref in mappings and mappings[ref] in supported_event_ids and
                field in sources[mappings[ref]]['payload'] and type(sources[mappings[ref]]['payload'][field]) is type(value) and
                sources[mappings[ref]]['payload'][field]==value for ref in refs)
            accepted=f.get('assessment')=='SUPPORTED'
            if accepted and not exact: critical.append('incorrect_supervisor_source_predicate')
            supervisor_checks.append(dict(evidence_ids=refs,field=field,accepted=accepted,independently_exact=exact))
    accepted=[f for f in evaluated if f['accepted']]
    required=truth.get('required_observations',[])
    matches=sum(any(f['accepted'] and f['independently_exact'] and fact['event_record_id'] in f['evidence_ids'] and
        f['field']==fact['field'] and type(f['expected_value']) is type(fact['value']) and f['expected_value']==fact['value'] for f in evaluated) for fact in required)
    human=(records or {}).get('final_state')=='AWAITING_HUMAN'
    # An advisory Supervisor ESCALATE after complete specialists is not unnecessary specialist escalation.
    decision='NO_EXCEPTION' if not truth['expected_exception_types'] and not initial else 'COMPLETE' if supervisor and eligible else 'ESCALATE' if human else 'INCOMPLETE'
    expected=truth['expected_decision']
    quality='OPERATIONAL DECISION CORRECT' if decision==expected else 'OPERATIONAL DECISION INCORRECT'
    candidate='NONE'
    if expected=='COMPLETE' and decision=='ESCALATE': candidate='UNNECESSARY ESCALATION CANDIDATE — PENDING REVIEW'
    if expected=='ESCALATE' and decision=='COMPLETE': candidate='UNSAFE COMPLETION CANDIDATE — PENDING REVIEW'
    # New material gaps or natural-language gap classification need external judgement.
    manual=dict(status='PENDING REVIEW' if track!='rules' and role_results else 'NOT APPLICABLE',
        materiality_candidate=candidate,role_results=role_results,source_observations=list(sources.values()),
        supervisor_context=[r['result'] for r in supervisor],
        checklist=['Separate observation from causation','Check narrative chronology against occurred_at',
          'Assess materiality of each missing_evidence item','Check role boundaries','Review recommendations and Supervisor uncertainty'],
        reviewer=None,verdict=None,rationale=None)
    if track=='rules':
        decision='RULES_HUMAN_TRIAGE' if human else 'DETECTED_AND_ROUTED' if initial else 'NO_EXCEPTION'
        quality='CAPABILITY NOT AVAILABLE IN BASELINE' if initial else quality
    mechanical=detection_correct and route_correct and classification_correct and not critical and not observed.get('error_code') and observed.get('bank_records_unchanged') is True
    if track!='rules': mechanical &= decision==expected
    return dict(scoring_version=truth['scoring_version'],detection_correct=detection_correct,routing_correct=route_correct,
        classification_correct=classification_correct,decision=decision,expected_decision=expected,decision_quality=quality,
        decision_judgement_status='FIXTURE EXPECTATION ONLY' if track=='offline' else 'PENDING REVIEW' if role_results else 'COMPLETED',
        supervisor_eligible=eligible,supervisor_participated=bool(supervisor),supervisor_check_status='COMPLETED' if supervisor else 'NOT RUN' if initial else 'NOT APPLICABLE',
        evaluated_predicates=evaluated,supervisor_predicate_checks=supervisor_checks,
        grounding_precision=metric(sum(f['independently_exact'] and f['temporally_eligible'] for f in accepted),len(accepted)),
        citation_validity=metric(sum(f['citations_valid'] for f in evaluated),len(evaluated)),
        temporal_source_validity=metric(sum(f['temporally_eligible'] for f in accepted),len(accepted)),
        unsupported_accepted_predicates=sum(not f['independently_exact'] for f in accepted),
        finding_groups={label:sum(f['validated_assessment']==label for f in evaluated) for label in ('SUPPORTED','CONTRADICTED','INSUFFICIENT_EVIDENCE','NOT_EVALUATED')},
        required_fact_coverage=metric(matches,len(required)) if role_results else metric(0,0),
        source_retrieval_coverage=metric(sum(f['event_record_id'] in retrieved for f in required),len(required)) if role_results else metric(0,0),
        rejected_predicates=sum(not f['accepted'] for f in evaluated),critical_failures=sorted(set(critical)),
        mechanical_acceptance=bool(mechanical),manual_review=manual)

def aggregate(cases,track):
    evaluated=[c for c in cases if c.get('score')]
    scores=[c['score'] for c in evaluated]
    decisions=[s for s in scores if s['decision'] in {'COMPLETE','ESCALATE','NO_EXCEPTION'}]
    escalations=[s for s in decisions if s['decision']=='ESCALATE']
    required=[s for s in decisions if s['expected_decision']=='ESCALATE']
    eligible=[s for s in decisions if s['expected_decision']=='COMPLETE']
    correct_escalations=sum(s['expected_decision']=='ESCALATE' for s in escalations)
    metrics=dict(cases_selected=len(cases),cases_evaluated=len(evaluated),
        detection_accuracy=metric(sum(s['detection_correct'] for s in scores),len(scores)),
        classification_accuracy=metric(sum(s['classification_correct'] for s in scores),len(scores)),
        routing_accuracy=metric(sum(s['routing_correct'] for s in scores),len(scores)),
        completion_decision_accuracy=metric(sum(s['decision']==s['expected_decision'] for s in decisions),len(decisions)),
        escalation_precision=metric(correct_escalations,len(escalations)),
        escalation_recall=metric(correct_escalations,len(required)),
        unnecessary_escalation_candidate_rate=metric(sum(s['decision']=='ESCALATE' for s in eligible),len(eligible)),
        unsafe_completion_candidate_rate=metric(sum(s['decision']=='COMPLETE' for s in required),len(required)),
        supervisor_participation=metric(sum(s['supervisor_participated'] for s in scores if s['supervisor_eligible']),sum(s['supervisor_eligible'] for s in scores)),
        narrative_quality='PENDING REVIEW' if track!='rules' else 'CAPABILITY NOT AVAILABLE IN BASELINE',
        critical_failures=sum(len(s['critical_failures']) for s in scores),
        live_reasoning_accuracy='NOT RUN' if track!='live' else 'PENDING REVIEW',
        denominators='Decision metrics exclude NOT RUN/FAILED/INCOMPLETE and retain an explicit incomplete count; never treat missing results as successes.',
        incomplete_cases=sum(c.get('run_status') in {'NOT RUN','INCOMPLETE','FAILED','STOPPED'} for c in cases))
    for name in ('grounding_precision','required_fact_coverage','source_retrieval_coverage','citation_validity','temporal_source_validity'):
        metrics[name]=metric(sum(s[name]['numerator'] for s in scores),sum(s[name]['denominator'] for s in scores))
    metrics['by_family']={family:dict(cases=sum(c['family']==family for c in cases),
        statuses=[c['run_status'] for c in cases if c['family']==family],
        decisions=[c.get('score',{}).get('decision') for c in cases if c['family']==family]) for family in {c['family'] for c in cases}}
    metrics['unsupported_accepted_predicates']=sum(s['unsupported_accepted_predicates'] for s in scores)
    return metrics
