from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

@dataclass
class DataQualityResult:
    score: float
    completeness: float
    freshness: float
    validity: float
    status: str
    issues: list[str]
    def as_dict(self): return asdict(self)

def data_quality(data: dict, expected_fields: list[str], *, as_of: datetime|None=None, max_age_days: int=120, valid_ranges: dict|None=None):
    expected=list(expected_fields); issues=[]
    present=sum(data.get(k) is not None for k in expected)
    completeness=100*present/len(expected) if expected else 100.0
    freshness=100.0
    if as_of is not None:
        now=datetime.now(timezone.utc)
        if as_of.tzinfo is None: as_of=as_of.replace(tzinfo=timezone.utc)
        age=max((now-as_of).total_seconds()/86400,0)
        freshness=max(0.0,100*(1-age/max_age_days))
        if age>max_age_days: issues.append("stale_data")
    checks=0; bad=0
    for field,bounds in (valid_ranges or {}).items():
        val=data.get(field)
        if val is None: continue
        checks+=1; lo,hi=bounds
        if (lo is not None and val<lo) or (hi is not None and val>hi):
            bad+=1; issues.append(f"{field}_out_of_range")
    validity=100.0 if checks==0 else 100*(checks-bad)/checks
    score=round(0.60*completeness+0.25*freshness+0.15*validity,2)
    status="valid" if score>=80 else "partial" if score>=50 else "poor"
    return DataQualityResult(score,round(completeness,2),round(freshness,2),round(validity,2),status,issues)
