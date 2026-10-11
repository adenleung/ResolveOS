"""Author and freeze new engineering candidate families; no model evaluation."""
import json
from pathlib import Path
from app.evaluation.quality import rubric,digest

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--version',type=int,choices=[1,2,3,4],default=1)
    args=parser.parse_args();version=args.version
    root=Path('docs/evaluation/phase20');path=root/f'held-out-candidates-v{version}.json'
    if path.exists(): raise ValueError('frozen_candidate_manifest_exists')
    def event(label,source,payload,minutes=3):
        event_type={'payments':'payment.recorded','ledger':'ledger.entry_recorded','confirmations':'payment.confirmation_observed','api_gateway':'api.request_completed'}[source] if version>=3 else 'synthetic.observed'
        return dict(event_id='$REF_EVENT_'+label,source_system=source,event_type=event_type,entity_reference='$ENTITY',
            correlation_id='$TRACE',source_record_reference='$REF_RECORD_'+label,schema_version='1.0',minutes_before=10 if version>=3 and source=='payments' else minutes,payload=payload)
    def financial(currency='SGD',status='CONFIRMED',amount='75'):
        return [event('payment','payments',dict(payment_status='SETTLED',amount=amount,currency='SGD',idempotency_key='$KEY')),
            event('ledger','ledger',dict(ledger_status='POSTED',entry_type='DEBIT',amount=amount,currency=currency,
                balance_after=str(1000-int(amount)),ledger_transaction_id='$REF_LEDGER')),
            event('confirmation','confirmations',dict(confirmation_status=status,is_duplicate=False,
                **({'amount':amount,'currency':'SGD'} if version>=2 else {})),2)]
    specifications=[('H20-01','currency-disagreement',['TRANSACTION','RISK'],'RECONCILIATION_MISMATCH',['RECONCILIATION_MISMATCH'],'ESCALATE',financial('USD')),
      ('H20-02','slow-successful-endpoint',['TECHNOLOGY'],'API_PROCESSING_FAILURE',['API_PROCESSING_FAILURE'],'COMPLETE',
        [event('slow','api_gateway',dict(service_name='synthetic-statement-service',endpoint='/statements',status_code=200,latency_ms=31001))]),
      ('H20-03','negative-acknowledgement',['TRANSACTION','TECHNOLOGY'],'PAYMENT_CONFIRMATION_MISSING',['PAYMENT_CONFIRMATION_MISMATCH'],'ESCALATE',financial(status='FAILED',amount='65'))]
    cases=[]
    for case_id,family,roles,target,categories,decision,rows in specifications:
        truth=dict(scenario_id=case_id,expected_roles=roles,expected_target_type=target,expected_exception_types=[target],
            expected_categories=categories,expected_decision=decision,ground_truth_version=f'phase20-candidates-{version}.0',scoring_version='phase19-scoring-1.3',
            material_missing_evidence=[] if decision=='COMPLETE' else ['Unresolved financial discrepancy or absent authoritative positive receipt'],
            known_unknowns=['Internal technical cause and broader impact remain unknown'],nonblocking_diagnostic_uncertainty=['Internal diagnosis unless recommendation depends on it'],
            acceptable_advisory_outcomes=['ESCALATE','RECOMMENDATION','REINVESTIGATE'],authorization_restrictions=['No execution or authorization'],
            expert_judgement={'status':'ENGINEERING AUTHORED; EXTERNAL REVIEW PENDING','decision':decision},rubric={'narrative':'NOT REVIEWED'},
            initial_sources=rows,planned_subsequent_sources=[])
        truth['quality_rubric']=rubric(truth)
        if case_id=='H20-03':
            for criterion in truth['quality_rubric']['role_requirements']['TRANSACTION']:
                if criterion['id']=='authoritative_receipt': criterion['required']=True
        cases.append(dict(id=case_id,family=family,split='held-out',ground_truth=truth,initial_sources=rows,subsequent_sources=[]))
    manifest=dict(manifest_version='phase19-suite-manifest-1.0',benchmark_version=f'phase20-candidates-{version}.0',cases=cases)
    from app.evaluation.benchmark_manifest import load_manifest
    path.write_text(json.dumps(manifest,indent=2)+'\n');load_manifest(path)
    (root/('candidate-freeze.json' if version==1 else f'candidate-freeze-v{version}.json')).write_text(json.dumps(dict(sha256=digest(manifest),raw_file_sha256=__import__('hashlib').sha256(path.read_bytes()).hexdigest(),
        status='ENGINEERING CANDIDATES FROZEN; NOT INDEPENDENT EXPERT HELD-OUT ACCEPTANCE',paid_runs=0),indent=2)+'\n')
    print('Frozen candidate manifest:',path)

if __name__=='__main__': main()
