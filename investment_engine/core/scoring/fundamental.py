from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass
class ComponentScore:
    score: float|None
    coverage: float
    details: dict
    def as_dict(self): return asdict(self)

def _higher(v, bad, good):
    if v is None:return None
    if v<=bad:return 0.0
    if v>=good:return 100.0
    return 100*(v-bad)/(good-bad)
def _lower(v, good, bad):
    if v is None:return None
    if v<=good:return 100.0
    if v>=bad:return 0.0
    return 100*(bad-v)/(bad-good)
def _combine(parts:dict[str,float|None], weights:dict[str,float]):
    usable={k:v for k,v in parts.items() if v is not None}; total=sum(weights[k] for k in usable)
    coverage=100*total/sum(weights.values()) if weights else 100
    score=None if total==0 else sum(usable[k]*weights[k] for k in usable)/total
    return ComponentScore(None if score is None else round(score,2),round(coverage,2),parts)

def quality_score(d):
    parts={
      "roe":_higher(d.get("roe_pct"),5,20), "roic":_higher(d.get("roic_pct"),5,18),
      "ebit_margin":_higher(d.get("ebit_margin_pct"),5,20), "net_margin":_higher(d.get("net_margin_pct"),3,15),
      "debt":_lower(d.get("net_debt_to_ebitda"),1,4), "current_ratio":_higher(d.get("current_ratio"),0.8,1.8),
    }
    return _combine(parts,{"roe":.22,"roic":.25,"ebit_margin":.16,"net_margin":.12,"debt":.15,"current_ratio":.10})

def value_score(d):
    parts={
      "pe": _lower(d.get("pe"),8,25) if d.get("pe") is not None and d.get("pe")>0 else None,
      "pbv":_lower(d.get("pbv"),1,4) if d.get("pbv") is not None and d.get("pbv")>0 else None,
      "ev_ebitda":_lower(d.get("ev_ebitda"),6,18) if d.get("ev_ebitda") is not None and d.get("ev_ebitda")>0 else None,
      "dy":_higher(d.get("dividend_yield_pct"),2,8),
      "graham_upside":_higher(d.get("graham_upside_pct"),-10,35),
    }
    return _combine(parts,{"pe":.25,"pbv":.20,"ev_ebitda":.25,"dy":.15,"graham_upside":.15})

def growth_score(d):
    parts={"revenue_cagr_5y":_higher(d.get("revenue_cagr_5y_pct"),0,15),"earnings_cagr_5y":_higher(d.get("earnings_cagr_5y_pct"),0,18)}
    return _combine(parts,{"revenue_cagr_5y":.45,"earnings_cagr_5y":.55})
