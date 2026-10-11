"""Source-only deterministic mechanics fixtures. Never a GPT reasoning evaluator.

No catalog/ground-truth/scorer import or scenario-ID branch. Live runs never use these.
"""
import json
from app.investigation.contracts import ModelTurn, Output, SupervisorOutput, ToolCall

class SourceSpecialist:
    identifier='offline-source-only-fixture:phase19-1'
    def turn(self,instructions,messages,tools,max_tokens):
        meta=json.loads(messages[0]['content']); role=meta['role']
        if len(messages)==1:
            trace=meta['traces'][0]
            if role=='TECHNOLOGY':
                calls=[('get_event_timeline',{'correlation_id':trace})]
            elif role=='TRANSACTION':
                calls=[('get_transaction_timeline',{'payment_id':meta['entities'][0]})]
            else:
                calls=[('get_transaction_state',{'payment_id':meta['entities'][0]}),
                       ('get_applicable_synthetic_policy',{'case_id':meta['case_id']})]
            return ModelTurn(calls=[ToolCall(name=n,arguments=a,call_id='fixture-'+str(i)) for i,(n,a) in enumerate(calls)])
        rows={e['id']:e for m in messages if m.get('type')=='function_call_output'
              for e in json.loads(m['output']).get('evidence',[])}
        latest={}
        for row in rows.values():
            key=(row['source_system'],row['source_record_reference'])
            if key not in latest or (row['occurred_at'],row['ingested_at'])>(latest[key]['occurred_at'],latest[key]['ingested_at']): latest[key]=row
        observations=list(latest.values())
        fields=('status_code','latency_ms','confirmation_status','workflow_status','approval_status') if role=='TECHNOLOGY' else (
            'payment_status','ledger_status','amount','currency','entry_type','balance_after','confirmation_status','is_duplicate','workflow_status','approval_status')
        findings=[dict(claim=f"{f} observed at {r['occurred_at']}",field=f,expected_value=r['payload'][f],evidence_ids=[r['id']],assessment='SUPPORTED')
                  for r in observations for f in fields if f in r['payload']]
        payments=[r for r in observations if r['source_system']=='payments']
        ledgers=[r for r in observations if r['source_system']=='ledger']
        receipt=any(r['payload'].get('confirmation_status') in {'CONFIRMED','SUCCESS','SUCCEEDED'} for r in observations)
        missing=[]; contradictions=[]
        if payments and not receipt: missing.append('Authoritative confirmation receipt is unobserved')
        if any(p['payload'].get('amount')!=l['payload'].get('amount') or p['payload'].get('currency')!=l['payload'].get('currency') for p in payments for l in ledgers):
            contradictions.append('Observed payment and ledger values disagree')
        if any(r['payload'].get('is_duplicate') for r in observations): missing.append('Duplicate monetary impact is not established by case observations')
        if any(r['payload'].get('approval_status')=='REJECTED' for r in observations): missing.append('Rejected approval requires operator review; no action eligibility established')
        hypotheses=[]
        failures=[r for r in observations if type(r['payload'].get('status_code')) is int and r['payload']['status_code']>=500]
        if failures:
            hypotheses=[dict(possible_cause='Internal cause is unknown; technical status alone cannot establish causation',
                supporting_evidence_ids=[failures[0]['id']],contradicting_evidence_ids=[],unresolved_questions=['What internal diagnostics explain the failure?'])]
        return ModelTurn(output=Output(summary='Deterministic fixture: returned source observations, diagnostic uncertainty preserved.',
            outcome='NEEDS_ADDITIONAL_EVIDENCE' if missing or contradictions or not findings else 'COMPLETED',
            findings=findings,hypotheses=hypotheses,missing_evidence=missing,contradictions=contradictions,
            suggested_next_steps=['Advisory operational review; no automatic banking action'],proposed_resolution=None,action_authorization='NOT_EVALUATED'))

class SourceSupervisor:
    identifier='offline-source-only-supervisor:phase19-1'
    def turn(self,instructions,messages,tools,max_tokens):
        snapshot=json.loads(messages[0]['content'])
        conclusions=[dict(claim=r['claim'],evidence_ids=r['evidence_ids'],assessment='SUPPORTED',field=r['field'],expected_value=r['expected_value'])
                     for r in snapshot['findings'] if r['deterministically_supported']]
        issues=snapshot['issues']
        return ModelTurn(output=SupervisorOutput(review_version='1.0',outcome='ESCALATE' if issues else 'RECOMMENDATION',
            summary='Deterministic fixture review: grounded observations; hypotheses remain unverified interpretations.',supported_conclusions=conclusions,
            rejected_conclusions=[],unresolved_issues=issues,required_additional_checks=[],targeted_specialists=[],proposed_action=None,
            evidence_ids=sorted({i for r in conclusions for i in r['evidence_ids']}),escalation_reasons=issues,action_authorization='NOT_EVALUATED'))
