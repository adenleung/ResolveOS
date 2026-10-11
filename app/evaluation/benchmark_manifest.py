"""External versioned suite templates for expansion without runner changes."""
import json
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.ingestion.schemas import EventEnvelope
from app.investigation.tools import PAYLOAD_FIELDS

class ManifestCase(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id: str=Field(pattern=r'^[A-Za-z0-9_-]{1,50}$')
    family: str=Field(min_length=1,max_length=100)
    split: str=Field(pattern=r'^(development|held-out)$')
    ground_truth: dict
    initial_sources: list[dict]=Field(min_length=1,max_length=100)
    subsequent_sources: list[dict]=Field(default_factory=list,max_length=100)
    @model_validator(mode='after')
    def validate_contract(self):
        required={'expected_target_type','expected_exception_types','expected_categories','expected_roles','expected_decision',
            'material_missing_evidence','known_unknowns','nonblocking_diagnostic_uncertainty','acceptable_advisory_outcomes',
            'authorization_restrictions','expert_judgement','rubric','scoring_version','ground_truth_version'}
        if not required<=self.ground_truth.keys(): raise ValueError('incomplete_pre_registered_ground_truth')
        for key in ('expected_exception_types','expected_categories','expected_roles','material_missing_evidence',
                    'known_unknowns','nonblocking_diagnostic_uncertainty','acceptable_advisory_outcomes','authorization_restrictions'):
            if not isinstance(self.ground_truth[key],list) or not all(isinstance(v,str) for v in self.ground_truth[key]):
                raise ValueError('invalid_ground_truth_list')
        if not all(isinstance(self.ground_truth[key],dict) for key in ('expert_judgement','rubric')):
            raise ValueError('invalid_review_rubric')
        if self.ground_truth['expected_decision'] not in {'COMPLETE','ESCALATE','NO_EXCEPTION'}: raise ValueError('invalid_decision_rubric')
        for r in self.initial_sources+self.subsequent_sources:
            if not set(r.get('payload',{}))<=PAYLOAD_FIELDS: raise ValueError('unapproved_source_field')
            if 'minutes_before' not in r or type(r['minutes_before']) not in {int,float} or not 0<=r['minutes_before']<=10080: raise ValueError('invalid_relative_time')
            sample={k:v for k,v in r.items() if k!='minutes_before'}
            sample['occurred_at']='2026-01-01T00:00:00+00:00'
            EventEnvelope.model_validate(sample)
        return self

def load_manifest(path):
    raw=json.loads(path.read_text(encoding='utf-8'))
    if set(raw)!={'manifest_version','benchmark_version','cases'} or raw['manifest_version']!='phase19-suite-manifest-1.0': raise ValueError('invalid_suite_manifest')
    cases=[ManifestCase.model_validate(c) for c in raw['cases']]
    if not cases or len(cases)>50 or len({c.id for c in cases})!=len(cases): raise ValueError('invalid_suite_size_or_identity')
    # Families may not occur in both partitions: identity changes are not holdout independence.
    for family in {c.family for c in cases}:
        if len({c.split for c in cases if c.family==family})!=1: raise ValueError('family_split_leakage')
    return raw['benchmark_version'],{c.id:c for c in cases}

def instantiate(spec,now,benchmark_version):
    replacements={'$ENTITY':'synthetic-p19-'+uuid4().hex,'$TRACE':'trace-'+uuid4().hex,'$KEY':'key-'+uuid4().hex}
    def replace(value):
        if isinstance(value,str):
            if value.startswith('$REF_'): return replacements.setdefault(value,uuid4().hex)
            return replacements.get(value,value)
        if isinstance(value,dict): return {k:replace(v) for k,v in value.items()}
        if isinstance(value,list): return [replace(v) for v in value]
        return value
    def sources(rows):
        result=[]
        for original in rows:
            row=replace(deepcopy(original));minutes=row.pop('minutes_before')
            row['occurred_at']=(now-timedelta(minutes=minutes)).isoformat()
            EventEnvelope.model_validate(row);result.append(row)
        return result
    initial=sources(spec.initial_sources);later=sources(spec.subsequent_sources)
    truth=deepcopy(spec.ground_truth)
    truth.update(scenario_id=spec.id,family=spec.family,split=spec.split,description=spec.family,benchmark_version=benchmark_version,
        source_entity=replacements['$ENTITY'],initial_sources=initial,planned_subsequent_sources=later)
    return initial,later,truth
