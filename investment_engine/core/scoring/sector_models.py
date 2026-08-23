from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fundamental import ComponentScore, _higher, _lower, _combine


FINANCIAL_SECTORS = {"finance", "financial", "financeiro", "financial services"}
BANK_INDUSTRIES = {"major banks", "regional banks", "banks", "commercial banks", "investment banks/brokers"}
INSURANCE_INDUSTRIES = {"insurance brokers/services", "multi-line insurance", "life/health insurance", "property/casualty insurance", "specialty insurers"}
UTILITY_SECTORS = {"utilities", "utility", "serviços públicos", "servicos publicos"}


@dataclass(frozen=True)
class ScoreProfile:
    key: str
    label: str
    notes: str
    alb_weights: dict[str, float]


PROFILES = {
    "bank": ScoreProfile(
        "bank",
        "Bancos",
        "Usa rentabilidade, valuation, crescimento, risco de mercado e liquidez; não usa EBIT, ROIC nem dívida/EBITDA como se fossem empresas industriais.",
        {"quality": .30, "value": .25, "growth": .10, "technical": .10, "risk": .15, "liquidity": .10},
    ),
    "insurance": ScoreProfile(
        "insurance",
        "Seguradoras",
        "Evita métricas industriais pouco comparáveis e dá maior peso a ROE, crescimento, valuation, risco e liquidez.",
        {"quality": .28, "value": .24, "growth": .13, "technical": .10, "risk": .15, "liquidity": .10},
    ),
    "utility": ScoreProfile(
        "utility",
        "Utilities / Concessionárias",
        "Aceita estrutura de capital mais alavancada e dá maior peso a estabilidade, valuation e risco.",
        {"quality": .25, "value": .25, "growth": .10, "technical": .10, "risk": .20, "liquidity": .10},
    ),
    "generic": ScoreProfile(
        "generic",
        "Empresas não financeiras",
        "Modelo geral para empresas operacionais não financeiras.",
        {"quality": .25, "value": .25, "growth": .15, "technical": .10, "risk": .15, "liquidity": .10},
    ),
    "fii": ScoreProfile(
        "fii",
        "Fundos Imobiliários",
        "Modelo próprio de FIIs baseado em P/VP, renda, FFO, Cap Rate, vacância, LTV, risco técnico e liquidez.",
        {"quality": .25, "value": .30, "technical": .10, "risk": .20, "liquidity": .15},
    ),
}


def detect_profile(asset_type: str | None, sector: str | None = None, industry: str | None = None, segment: str | None = None) -> ScoreProfile:
    if (asset_type or "").lower() == "fii":
        return PROFILES["fii"]
    s = (sector or "").strip().lower()
    i = (industry or "").strip().lower()
    if i in BANK_INDUSTRIES or "bank" in i or (s in FINANCIAL_SECTORS and "bank" in i):
        return PROFILES["bank"]
    if i in INSURANCE_INDUSTRIES or "insurance" in i or "segur" in i:
        return PROFILES["insurance"]
    if s in UTILITY_SECTORS or "utilit" in s or "electric" in i or "water" in i:
        return PROFILES["utility"]
    return PROFILES["generic"]


def stock_quality_score(d: dict[str, Any], profile: ScoreProfile) -> ComponentScore:
    if profile.key == "bank":
        parts = {
            "roe": _higher(d.get("roe_pct"), 8, 22),
            "net_margin": _higher(d.get("net_margin_pct"), 8, 28),
            "earnings_growth": _higher(d.get("earnings_cagr_5y_pct"), 0, 15),
            "revenue_growth": _higher(d.get("revenue_cagr_5y_pct"), 0, 12),
        }
        return _combine(parts, {"roe": .45, "net_margin": .25, "earnings_growth": .20, "revenue_growth": .10})
    if profile.key == "insurance":
        parts = {
            "roe": _higher(d.get("roe_pct"), 8, 22),
            "net_margin": _higher(d.get("net_margin_pct"), 5, 20),
            "earnings_growth": _higher(d.get("earnings_cagr_5y_pct"), 0, 15),
            "revenue_growth": _higher(d.get("revenue_cagr_5y_pct"), 0, 12),
        }
        return _combine(parts, {"roe": .40, "net_margin": .25, "earnings_growth": .20, "revenue_growth": .15})
    if profile.key == "utility":
        parts = {
            "roe": _higher(d.get("roe_pct"), 7, 18),
            "roic": _higher(d.get("roic_pct"), 5, 14),
            "ebit_margin": _higher(d.get("ebit_margin_pct"), 8, 25),
            "net_margin": _higher(d.get("net_margin_pct"), 4, 15),
            "debt": _lower(d.get("net_debt_to_ebitda"), 1.5, 5.0),
        }
        return _combine(parts, {"roe": .22, "roic": .23, "ebit_margin": .20, "net_margin": .15, "debt": .20})
    parts = {
        "roe": _higher(d.get("roe_pct"), 5, 20),
        "roic": _higher(d.get("roic_pct"), 5, 18),
        "ebit_margin": _higher(d.get("ebit_margin_pct"), 5, 20),
        "net_margin": _higher(d.get("net_margin_pct"), 3, 15),
        "debt": _lower(d.get("net_debt_to_ebitda"), 1, 4),
        "current_ratio": _higher(d.get("current_ratio"), .8, 1.8),
    }
    return _combine(parts, {"roe": .22, "roic": .25, "ebit_margin": .16, "net_margin": .12, "debt": .15, "current_ratio": .10})


def stock_value_score(d: dict[str, Any], profile: ScoreProfile) -> ComponentScore:
    pe = d.get("pe")
    pbv = d.get("pbv")
    ev = d.get("ev_ebitda")
    dy = d.get("dividend_yield_pct")
    graham = d.get("graham_upside_pct")
    if profile.key in {"bank", "insurance"}:
        parts = {
            "pe": _lower(pe, 6, 18) if pe is not None and pe > 0 else None,
            "pbv": _lower(pbv, .8, 2.5) if pbv is not None and pbv > 0 else None,
            "dy": _higher(dy, 2, 8),
            "graham_upside": _higher(graham, -10, 35),
        }
        return _combine(parts, {"pe": .30, "pbv": .35, "dy": .20, "graham_upside": .15})
    if profile.key == "utility":
        parts = {
            "pe": _lower(pe, 8, 22) if pe is not None and pe > 0 else None,
            "pbv": _lower(pbv, 1, 3.5) if pbv is not None and pbv > 0 else None,
            "ev_ebitda": _lower(ev, 6, 15) if ev is not None and ev > 0 else None,
            "dy": _higher(dy, 3, 9),
            "graham_upside": _higher(graham, -10, 35),
        }
        return _combine(parts, {"pe": .20, "pbv": .15, "ev_ebitda": .25, "dy": .25, "graham_upside": .15})
    parts = {
        "pe": _lower(pe, 8, 25) if pe is not None and pe > 0 else None,
        "pbv": _lower(pbv, 1, 4) if pbv is not None and pbv > 0 else None,
        "ev_ebitda": _lower(ev, 6, 18) if ev is not None and ev > 0 else None,
        "dy": _higher(dy, 2, 8),
        "graham_upside": _higher(graham, -10, 35),
    }
    return _combine(parts, {"pe": .25, "pbv": .20, "ev_ebitda": .25, "dy": .15, "graham_upside": .15})


def stock_growth_score(d: dict[str, Any], profile: ScoreProfile) -> ComponentScore:
    parts = {
        "revenue_cagr_5y": _higher(d.get("revenue_cagr_5y_pct"), 0, 15 if profile.key == "generic" else 12),
        "earnings_cagr_5y": _higher(d.get("earnings_cagr_5y_pct"), 0, 18 if profile.key == "generic" else 15),
    }
    return _combine(parts, {"revenue_cagr_5y": .45, "earnings_cagr_5y": .55})


def fii_quality_score(d: dict[str, Any]) -> ComponentScore:
    parts = {
        "ffo_yield": _higher(d.get("ffo_yield_pct"), 4, 11),
        "cap_rate": _higher(d.get("cap_rate_pct"), 4, 10),
        "vacancy": _lower(d.get("vacancy_pct"), 4, 18),
        "ltv": _lower(d.get("ltv_pct"), 15, 45),
        "wale": _higher(d.get("wale_years"), 2, 7),
    }
    return _combine(parts, {"ffo_yield": .25, "cap_rate": .20, "vacancy": .25, "ltv": .20, "wale": .10})


def fii_value_score(d: dict[str, Any]) -> ComponentScore:
    parts = {
        "pbv": _lower(d.get("pbv"), .85, 1.20) if d.get("pbv") is not None and d.get("pbv") > 0 else None,
        "dy": _higher(d.get("dividend_yield_pct"), 6, 12),
        "ffo_yield": _higher(d.get("ffo_yield_pct"), 5, 12),
        "cap_rate": _higher(d.get("cap_rate_pct"), 5, 11),
    }
    return _combine(parts, {"pbv": .30, "dy": .30, "ffo_yield": .25, "cap_rate": .15})
