"""Reviewed experiment profile and deadline fence; no credentials or API calls."""
from dataclasses import dataclass, asdict
import math
import time
from app.investigation.provider import ProviderError

MODEL='gpt-4.1-mini-2025-04-14'
@dataclass(frozen=True)
class Experiment:
    model: str=MODEL
    requests: int=10
    tokens: int=120000
    usd: float=.15
    seconds: int=600
    def __post_init__(self):
        if self.model!=MODEL: raise ValueError('unreviewed_model_profile')
        if not 1<=self.requests<=10 or not 1<=self.tokens<=120000 or not math.isfinite(self.usd) or not 0<self.usd<=.15 or not 1<=self.seconds<=900: raise ValueError('invalid_case_limits')
    def export(self): return asdict(self)

class DeadlineProvider:
    def __init__(self,provider,deadline,clock=time.monotonic):
        self.provider=provider;self.deadline=deadline;self.clock=clock;self.identifier=provider.identifier
    def turn(self,*args,**kwargs):
        remaining=self.deadline-self.clock()
        if remaining<=0: raise ProviderError('experiment_runtime_exhausted')
        # Native requests have bounded socket timeout and no retries. Deadline
        # fencing is cooperative; migration/DB cleanup time is reported separately.
        native=getattr(self.provider,'provider',self.provider)
        settings=getattr(native,'settings',None)
        if settings:
            native.settings=settings.model_copy(update={'investigator_timeout_seconds':min(settings.investigator_timeout_seconds,remaining)})
        result=self.provider.turn(*args,**kwargs)
        if self.clock()>self.deadline: raise ProviderError('experiment_runtime_exhausted')
        return result
