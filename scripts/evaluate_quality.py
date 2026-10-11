"""Offline quality reports, immutable historical replay, integrity and expert review."""
import argparse
import json
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
from app.evaluation.quality import evaluate,rubric,digest,review_state,calibration,DIMENSIONS
from app.investigation.validation import validate_output

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value): path.write_text(json.dumps(value,indent=2,default=str)+'\n',encoding='utf-8')

def check_integrity(directory):
    files=list(directory.rglob('frozen-hashes.json'))
    if not files: raise ValueError('no_frozen_artifacts')
    count=0
    for receipt in files:
        hashes=json.loads(receipt.read_text())
        if not hashes: raise ValueError('empty_frozen_receipt')
        for name,expected in hashes.items():
            target=(receipt.parent/name).resolve()
            if not target.is_relative_to(receipt.parent.resolve()) or not target.is_file() or sha(target)!=expected:
                raise ValueError('frozen_artifact_integrity_failed')
            count+=1
    return dict(status='PASS',receipts=len(files),frozen_files=count,
        limitation='Local hash receipts are not external signatures; archive receipt or separately trusted hashes anchor provenance.')

def historical(directory):
    files={p.name:sha(p) for p in directory.iterdir() if p.is_file()}
    r=json.loads((directory/'results.json').read_text());records=r.get('records')
    if not records: return dict(source=str(directory),provenance='HISTORICAL SAVED GPT',status='INSUFFICIENT SAVED ARTIFACTS',source_hashes=files)
    original=json.loads((directory/'synthetic-input.json').read_text()) if (directory/'synthetic-input.json').exists() else []
    sources={e['event_id']:e for e in original}
    events=[sources.get(e['event_id'],{})|e for e in records['source_events']]
    old_truth=json.loads((directory/'ground-truth.json').read_text()) if (directory/'ground-truth.json').exists() else r.get('ground_truth',{})
    truth=dict(scenario_id=directory.name,source_entity=events[0].get('entity_reference'),expected_roles=[i['role'] for i in records['investigations']],
        expected_decision='INCONCLUSIVE',initial_sources=original,planned_subsequent_sources=[],historical_truth=old_truth)
    truth['quality_rubric']=rubric(truth)
    # Historical rubric is a new retrospective research artifact, not a preregistered live truth.
    result=evaluate(truth,records,dict(source_observations=events),'historical') if original else dict(status='SOURCE AUTHORIZATION CONTEXT NOT SAVED',roles=[])
    replays=[]
    for i in records['investigations']:
        raw=[c.get('model_output') for c in r.get('calls',[]) if c.get('role')==i['role'] and c.get('model_output')]
        if not raw: replays.append(dict(role=i['role'],status='NO SAVED MODEL OUTPUT'));continue
        used={ref for t in i['telemetry'].get('tools',[]) for ref in t.get('evidence_ids',[])}
        eligible=[e for e in events if e['occurred_at']<=i['result']['information_window'] and e['ingested_at']<=i['result']['information_window']]
        try:
            replay=validate_output(raw[-1],{'events':eligible,'truncated':False},used)
            replays.append(dict(role=i['role'],status='CURRENT CONTRACT REVALIDATION',original_sha256=digest(raw[-1]),
                original=raw[-1],revalidated=replay,historical_outcome=i['result']['outcome']))
        except Exception as exc:
            replays.append(dict(role=i['role'],status='REJECTED',safe_error_type=type(exc).__name__,original_sha256=digest(raw[-1])))
    if files!={p.name:sha(p) for p in directory.iterdir() if p.is_file()}: raise ValueError('historical_artifact_changed')
    return dict(source=str(directory),provenance='HISTORICAL SAVED GPT',source_hashes=files,immutable_verified=True,
        retrospective_rubric=truth['quality_rubric'],original_ground_truth_sha256=digest(old_truth),quality=result,replays=replays,
        requests_historically_attempted=r.get('api_requests_attempted'),input_tokens=r.get('provider_input_tokens'),output_tokens=r.get('provider_output_tokens'),
        new_requests=0,supervisor_historically_ran=bool(records.get('supervisor')))

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['integrity','suite','history','review'])
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--reviews',type=Path,nargs='*',default=[])
    parser.add_argument('--adjudication',type=Path)
    args=parser.parse_args(argv)
    if args.mode=='integrity':
        try: print(json.dumps(check_integrity(args.input),indent=2));return 0
        except Exception: print('frozen_artifact_integrity_failed');return 1
    output=args.output or Path('docs/evaluation/phase20/artifacts')/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+args.mode+'-'+uuid4().hex[:6])
    output.mkdir(parents=True,exist_ok=False)
    if args.mode=='history':
        results=[]
        for p in sorted(args.input.glob('*-live-*')):
            if not (p/'results.json').exists(): continue
            try: results.append(historical(p))
            except Exception as exc: results.append(dict(source=str(p),status='REPLAY FAILED',safe_error_type=type(exc).__name__,new_requests=0))
        write(output/'historical-results.json',results)
        write(output/'status.json',dict(new_live_model_evaluation='NOT RUN',new_paid_requests=0,saved_runs=len(results)))
    elif args.mode=='review':
        check_integrity(args.input)
        packet=json.loads((args.input/'review-packet.json').read_text());reviews=[json.loads(p.read_text()) for p in args.reviews]
        truth=json.loads((args.input/'ground-truth.json').read_text())
        raw=json.loads((args.input/'results.json').read_text())
        sources=json.loads((args.input/'source-observations.json').read_text())
        if (digest(truth)!=packet.get('truth_sha256') or digest(raw.get('records'))!=packet.get('records_sha256') or
                digest(raw.get('observations',{}).get('source_observations'))!=digest(sources)):
            raise ValueError('review_source_provenance_mismatch')
        adjudication=json.loads(args.adjudication.read_text()) if args.adjudication else None
        status=review_state(packet,reviews,adjudication)
        write(output/'review-results.json',dict(status=status,packet_sha256=digest(packet),reviews=reviews,adjudication=adjudication))
        # Semantic binding is never implicitly accepted from an unfinished/disputed review.
        if status['state']=='REVIEWED':
            bindings=reviews[0].get('bindings',[])
            write(output/'bound-quality-evaluation.json',evaluate(truth,raw.get('records'),raw['observations'],raw['track'],bindings))
        write(output/'calibration.json',calibration([status]))
    else:
        check_integrity(args.input);suite=json.loads((args.input/'results.json').read_text())
        results=[]
        for c in suite['cases']:
            if c.get('quality_evaluation'): results.append(c['quality_evaluation'])
        write(output/'quality-scorecard.json',dict(version='phase20-scorecard-1.0',provenance=suite['track'],
            integration_metrics={k:v for k,v in suite['metrics'].items() if k in {'detection_accuracy','classification_accuracy','routing_accuracy','critical_failures'}},
            evidence_metrics={k:v for k,v in suite['metrics'].items() if k in {'grounding_precision','citation_validity','required_fact_coverage','temporal_source_validity'}},
            reasoning=calibration([{'decision':'INCONCLUSIVE'} for c in suite['cases']]),
            case_diagnostics=results,live_model_evaluation='NOT RUN' if suite['track']!='live' else suite['live_model_tests'],
            timing_seconds=suite['latency_seconds'],usage=[dict(case=c['scenario_id'],requests=c.get('live_requests_attempted'),input=c.get('input_tokens'),output=c.get('output_tokens'),estimated_usd=c.get('estimated_usd')) for c in suite['cases']]))
    print('Quality artifacts:',output.resolve());return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print('quality_command_failed:'+type(exc).__name__)
        raise SystemExit(1) from None
