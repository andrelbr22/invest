from __future__ import annotations
from typing import Any
from .fundamental import ComponentScore, _higher, _lower, _combine


def _band(v, low_bad, low_good, high_good, high_bad):
    if v is None: return None
    if low_good <= v <= high_good: return 100.0
    if v <= low_bad or v >= high_bad: return 0.0
    if v < low_good: return 100*(v-low_bad)/(low_good-low_bad)
    return 100*(high_bad-v)/(high_bad-high_good)


def technical_score(tech: dict[str, Any] | None) -> ComponentScore:
    tech = tech or {}
    close=tech.get("close"); s20=tech.get("sma20"); s50=tech.get("sma50"); s200=tech.get("sma200")
    trend20 = None if close is None or s20 is None else (100.0 if close > s20 else 0.0)
    trend50 = None if close is None or s50 is None else (100.0 if close > s50 else 0.0)
    trend200 = None if close is None or s200 is None else (100.0 if close > s200 else 0.0)
    alignment = None if s20 is None or s50 is None or s200 is None else (100.0 if s20 > s50 > s200 else 50.0 if s20 > s50 else 0.0)
    macd = tech.get("macd")
    parts={
      "price_vs_sma20": trend20,
      "price_vs_sma50": trend50,
      "price_vs_sma200": trend200,
      "ma_alignment": alignment,
      "rsi": _band(tech.get("rsi14"),25,40,65,80),
      "macd": None if macd is None else (100.0 if macd > 0 else 0.0),
      "momentum_3m": _higher(tech.get("return_3m_pct"),-10,15),
    }
    return _combine(parts,{"price_vs_sma20":.12,"price_vs_sma50":.13,"price_vs_sma200":.20,"ma_alignment":.20,"rsi":.10,"macd":.10,"momentum_3m":.15})


def risk_score(fund: dict[str, Any], tech: dict[str, Any] | None, profile_key: str) -> ComponentScore:
    tech=tech or {}
    vol=_lower(tech.get("volatility_annual_pct"),18,55)
    drawdown=None
    if tech.get("max_drawdown_1y_pct") is not None:
        drawdown=_higher(tech.get("max_drawdown_1y_pct"),-45,-12)
    if profile_key in {"bank","insurance"}:
        parts={"volatility":vol,"drawdown":drawdown}
        return _combine(parts,{"volatility":.55,"drawdown":.45})
    if profile_key == "fii":
        parts={
          "volatility":vol,
          "drawdown":drawdown,
          "vacancy":_lower(fund.get("vacancy_pct"),4,20),
          "ltv":_lower(fund.get("ltv_pct"),15,50),
        }
        return _combine(parts,{"volatility":.25,"drawdown":.25,"vacancy":.30,"ltv":.20})
    debt_good,debt_bad=(1.5,5.0) if profile_key=="utility" else (1.0,4.0)
    parts={
      "volatility":vol,
      "drawdown":drawdown,
      "net_debt_ebitda":_lower(fund.get("net_debt_to_ebitda"),debt_good,debt_bad),
    }
    return _combine(parts,{"volatility":.30,"drawdown":.30,"net_debt_ebitda":.40})


def liquidity_score(fund: dict[str, Any], tech: dict[str, Any] | None, asset_type: str) -> ComponentScore:
    tech=tech or {}
    liq=tech.get("daily_liquidity")
    if liq is None: liq=fund.get("daily_liquidity")
    if asset_type == "fii": score=_higher(liq,100_000,5_000_000)
    else: score=_higher(liq,500_000,20_000_000)
    return _combine({"daily_liquidity":score},{"daily_liquidity":1.0})


def weighted_alb(components: dict[str, ComponentScore], weights: dict[str,float]):
    usable={k:v for k,v in components.items() if v.score is not None and k in weights}
    total=sum(weights[k] for k in usable)
    full=sum(weights.values())
    coverage=0.0 if full==0 else 100*total/full
    score=None if total==0 else sum(usable[k].score*weights[k] for k in usable)/total
    contributions={k: round(v.score*weights[k]/total,2) if total else None for k,v in usable.items()}
    return (None if score is None else round(score,2),round(coverage,2),contributions)
