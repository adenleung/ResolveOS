"""Explicitly authorized live batches only; offline is the default."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from app.evaluation.pilot import catalog
from app.evaluation.benchmark import run_suite, BatchBudget
from app.evaluation.experiment import Experiment, MODEL
import json

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--track',choices=['offline','rules','live'],default='offline')
    parser.add_argument('--suite',choices=['pilot10'],default='pilot10')
    parser.add_argument('--cases',nargs='+')
    parser.add_argument('--manifest',type=Path,help='Versioned external suite; maximum 50 family-partitioned cases')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--authorize-paid-cases',type=int)
    parser.add_argument('--batch-max-requests',type=int)
    parser.add_argument('--batch-max-tokens',type=int)
    parser.add_argument('--batch-max-usd',type=float)
    parser.add_argument('--model',choices=[MODEL],default=MODEL)
    parser.add_argument('--case-config',type=Path,help='Selected case ID to reviewed Experiment limits mapping')
    parser.add_argument('--case-max-requests',type=int,default=10)
    parser.add_argument('--case-max-tokens',type=int,default=120000)
    parser.add_argument('--case-max-usd',type=float,default=.15)
    parser.add_argument('--case-max-seconds',type=int,default=600)
    parser.add_argument('--batch-max-seconds',type=int,default=1800)
    args=parser.parse_args(argv)
    specs=None;version='phase19-pilot-1.0'
    if args.manifest:
        from app.evaluation.benchmark_manifest import load_manifest
        try: version,specs=load_manifest(args.manifest)
        except Exception: parser.error('Invalid external manifest; inspect the documented contract without exposing raw exceptions')
    available=list(specs) if specs else [c['id'] for c in catalog()]
    selected=args.cases or available
    if any(c not in available for c in selected): parser.error('Unknown selected case')
    if len(set(selected))!=len(selected): parser.error('Duplicate case selection is prohibited')
    if not 1<=args.batch_max_seconds<=7200: parser.error('Invalid batch runtime cap')
    try:
        defaults=Experiment(args.model,args.case_max_requests,args.case_max_tokens,args.case_max_usd,args.case_max_seconds)
        custom=json.loads(args.case_config.read_text()) if args.case_config else {}
        if not isinstance(custom,dict) or not set(custom)<=set(selected): raise ValueError('config_outside_selection')
        experiments={case:Experiment(**(defaults.export()|custom.get(case,{}))) for case in selected}
    except Exception: parser.error('Invalid reviewed case configuration')
    batch=None
    if args.track=='live':
        if not args.cases or args.authorize_paid_cases!=len(selected): parser.error('Live execution requires explicit --cases and matching --authorize-paid-cases; no implicit paid suite')
        n=len(selected)
        if not args.batch_max_requests or not 1<=args.batch_max_requests<=10*n or not args.batch_max_tokens or not 1<=args.batch_max_tokens<=120000*n or args.batch_max_usd is None or not 0<args.batch_max_usd<=.15*n:
            parser.error('Supply positive batch request/token/USD caps bounded by selected-case limits')
        batch=BatchBudget(args.batch_max_requests,args.batch_max_tokens,args.batch_max_usd)
    output=args.output or Path('docs/evaluation/phase19/artifacts')/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+args.track+'-'+uuid4().hex[:6])
    return run_suite(args.track,selected,output,batch,specs,version,experiments,args.batch_max_seconds)

if __name__=='__main__': raise SystemExit(main())
