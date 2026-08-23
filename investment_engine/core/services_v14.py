from __future__ import annotations

from .valuation.graham import graham_number, implied_book_value_per_share, implied_eps, add_upside
from .quality.data_quality import data_quality
from .scoring.sector_models import (
    detect_profile, stock_quality_score, stock_value_score, stock_growth_score,
    fii_quality_score, fii_value_score,
)
from .scoring.market import technical_score, risk_score, liquidity_score, weighted_alb
from .scoring.explain import explain_components


def _f(x):
    try: return float(x) if x is not None else None
    except (TypeError, ValueError): return None


def _fund_dict(fund):
    fields=("price","pe","pbv","dividend_yield_pct","ev_ebitda","ebit_margin_pct","net_margin_pct","current_ratio","roe_pct","roic_pct","gross_debt_to_equity","net_debt_to_ebitda","revenue_cagr_5y_pct","earnings_cagr_5y_pct","ffo_yield_pct","cap_rate_pct","vacancy_pct","financial_vacancy_pct","ltv_pct","wale_years","daily_liquidity")
    return {k:_f(getattr(fund,k,None)) for k in fields}


def _tech_dict(tech):
    if tech is None: return {}
    fields=("score_tv","market_cap","daily_liquidity","sma20","sma50","sma200","high","low","close","rsi14","bb_lower","bb_upper","bb_middle","macd","atr14","volatility_annual_pct","max_drawdown_1y_pct","return_1m_pct","return_3m_pct","return_12m_pct")
    return {k:_f(getattr(tech,k,None)) for k in fields}


def calculate_asset_intelligence(asset, fund, tech=None):
    d=_fund_dict(fund); t=_tech_dict(tech)
    profile=detect_profile(asset.asset_type,asset.sector,asset.industry,asset.segment)

    g_result=None; g_value=None; g_upside=None
    if asset.asset_type == "stock":
        eps=implied_eps(d.get("price"),d.get("pe")); bvps=implied_book_value_per_share(d.get("price"),d.get("pbv"))
        g_result=add_upside(graham_number(eps,bvps),d.get("price"))
        if g_result.valid:
            g_value=g_result.value; g_upside=g_result.upside_pct
        d["graham_upside_pct"]=g_upside
        q=stock_quality_score(d,profile); v=stock_value_score(d,profile); gr=stock_growth_score(d,profile)
        expected={
            "bank":["price","pe","pbv","roe_pct","net_margin_pct","dividend_yield_pct","revenue_cagr_5y_pct","earnings_cagr_5y_pct"],
            "insurance":["price","pe","pbv","roe_pct","net_margin_pct","dividend_yield_pct","revenue_cagr_5y_pct","earnings_cagr_5y_pct"],
            "utility":["price","pe","pbv","roe_pct","roic_pct","ebit_margin_pct","dividend_yield_pct","net_debt_to_ebitda"],
            "generic":["price","pe","pbv","roe_pct","roic_pct","ebit_margin_pct","net_margin_pct","dividend_yield_pct","net_debt_to_ebitda","revenue_cagr_5y_pct"],
        }[profile.key]
    else:
        q=fii_quality_score(d); v=fii_value_score(d); gr=None
        expected=["price","pbv","dividend_yield_pct","ffo_yield_pct","cap_rate_pct","vacancy_pct","daily_liquidity"]

    ts=technical_score(t)
    rs=risk_score(d,t,profile.key)
    ls=liquidity_score(d,t,asset.asset_type)
    components={"quality":q,"value":v,"technical":ts,"risk":rs,"liquidity":ls}
    if gr is not None: components["growth"]=gr
    alb,alb_coverage,contrib=weighted_alb(components,profile.alb_weights)

    dq=data_quality(d,expected,as_of=fund.reference_date,valid_ranges={"dividend_yield_pct":(0,100),"roe_pct":(-200,300),"vacancy_pct":(0,100),"ltv_pct":(0,100)})
    explanation=explain_components(components)
    explanation["contributions"]=contrib

    return {
      "profile":profile,
      "data":d,"technical_data":t,
      "graham_result":g_result,"graham_number":g_value,"graham_upside_pct":g_upside,
      "quality":q,"value":v,"growth":gr,"technical":ts,"risk":rs,"liquidity":ls,
      "alb_score":alb,"coverage":alb_coverage,"data_quality":dq,"explanation":explanation,
      "model_version":"1.4-sector-aware",
    }
