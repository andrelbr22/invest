from __future__ import annotations
from datetime import datetime, timezone
from .valuation.graham import graham_number
from .scoring.fundamental import quality_score,value_score,growth_score
from .quality.data_quality import data_quality

def _f(x): return float(x) if x is not None else None

def calculate_stock_intelligence(fund):
    d={k:_f(getattr(fund,k)) for k in ("price","pe","pbv","dividend_yield_pct","ev_ebitda","ebit_margin_pct","net_margin_pct","current_ratio","roe_pct","roic_pct","gross_debt_to_equity","net_debt_to_ebitda","revenue_cagr_5y_pct","earnings_cagr_5y_pct","daily_liquidity")}
    price=d.get("price"); pe=d.get("pe"); pbv=d.get("pbv")
    eps=price/pe if price is not None and pe not in (None,0) else None
    bvps=price/pbv if price is not None and pbv not in (None,0) else None
    g=graham_number(eps,bvps)
    gu=None if g is None or not price else (g/price-1)*100
    d["graham_upside_pct"]=gu
    q=quality_score(d); v=value_score(d); gr=growth_score(d)
    dq=data_quality(d,["price","pe","pbv","roe_pct","ebit_margin_pct","net_margin_pct","dividend_yield_pct","revenue_cagr_5y_pct"],as_of=fund.reference_date,valid_ranges={"dividend_yield_pct":(0,100),"roe_pct":(-200,300)})
    comps=[x for x in (q.score,v.score,gr.score) if x is not None]
    coverage=(q.coverage+v.coverage+gr.coverage)/3
    alb=None if not comps else sum(comps)/len(comps)
    return {"data":d,"graham_number":g,"graham_upside_pct":gu,"quality":q,"value":v,"growth":gr,"data_quality":dq,"alb_preliminary":None if alb is None else round(alb,2),"coverage":round(coverage,2)}
