from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import math
from typing import Iterable

import pandas as pd

from investment_engine.core.portfolio.service import classification_for, localize_classification
from investment_engine.core.screening.universe import COMPANY_SIZE_LABELS, company_size_category
from investment_engine.core.valuation.catalog import (
    VALUATION_FAMILIES,
    valuation_applicability,
    valuation_method_metadata,
)
from investment_engine.core.valuation.gordon import gordon_growth_scenarios
from investment_engine.core.valuation.relative import relative_valuation


FUNDAMENTAL_FIELDS = {
    "price", "pe", "pbv", "dividend_yield_pct", "ev_ebitda", "ebit_margin_pct", "net_margin_pct",
    "current_ratio", "roe_pct", "roic_pct", "gross_debt_to_equity", "net_debt_to_ebitda",
    "revenue_cagr_5y_pct", "earnings_cagr_5y_pct", "ffo_yield_pct", "cap_rate_pct", "vacancy_pct",
    "financial_vacancy_pct", "ltv_pct", "wale_years", "daily_liquidity",
    # Optional normalized inputs for the new valuation families. They remain
    # None with the current schema and can be supplied by future providers.
    "dividend_per_share_ttm", "normalized_dividend_per_share",
}

SCORE_FIELDS = {
    "quality_score", "value_score", "growth_score", "technical_score", "risk_score", "liquidity_score",
    "alb_score", "data_quality_score",
}

PIVOT_ZONES = {
    "below_s3", "s3_s2", "s2_s1", "s1_pp", "pp_r1", "r1_r2", "r2_r3", "above_r3",
}
PIVOT_LEVELS = {"s3", "s2", "s1", "pp", "r1", "r2", "r3"}

VALUATION_FLAG_ALIASES = {
    "graham_reference": ("below_graham", "below_graham_number"),
    "dividend_yield_ceiling": (
        "below_dividend_yield_ceiling", "below_dividend_target", "below_barsi_6pct",
    ),
    "relative_peers": ("below_relative_value", "below_relative_peers"),
    "economic_value": ("below_economic_value", "below_gordon_ddm"),
}

VALUATION_FLAT_FIELDS = {
    "graham_reference": ("graham_number", "graham_upside_pct"),
    "dividend_yield_ceiling": ("dividend_yield_ceiling_value", "dividend_yield_ceiling_upside_pct"),
    "relative_peers": ("relative_peers_value", "relative_peers_upside_pct"),
    "economic_value": ("economic_value", "economic_value_upside_pct"),
}


def _f(value):
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def pivot_points(high: float | None, low: float | None, close: float | None) -> dict[str, float | None]:
    """Classic floor pivot points using the user's requested formulas."""
    h, l, c = _f(high), _f(low), _f(close)
    if h is None or l is None or c is None or h < l:
        return {k: None for k in ("pp", "r1", "s1", "r2", "s2", "r3", "s3")}
    pp = (h + l + c) / 3.0
    r1 = 2.0 * pp - l
    s1 = 2.0 * pp - h
    r2 = pp + (h - l)
    s2 = pp - (h - l)
    r3 = h + 2.0 * (pp - l)
    s3 = l - 2.0 * (h - pp)
    return {"pp": pp, "r1": r1, "s1": s1, "r2": r2, "s2": s2, "r3": r3, "s3": s3}


def _bars_frame(bars: Iterable) -> pd.DataFrame:
    rows = []
    for b in bars:
        if isinstance(b, dict):
            get = b.get
        else:
            get = lambda k, _b=b: getattr(_b, k, None)
        rows.append({
            "timestamp": get("timestamp"),
            "open": _f(get("open")), "high": _f(get("high")), "low": _f(get("low")),
            "close": _f(get("close")), "adjusted_close": _f(get("adjusted_close")),
            "volume": _f(get("volume")),
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    if df.empty:
        return df
    df = df.set_index("timestamp")
    df["price"] = df["adjusted_close"].where(df["adjusted_close"].notna(), df["close"])
    df = df[df["price"].notna() & (df["price"] > 0)].copy()
    # Keep OHLC and the analysis price on the same corporate-action-adjusted
    # basis.  Comparing adjusted close with raw highs/lows can create false
    # pivot/support/resistance levels around splits and reverse splits.
    factor = df["price"] / pd.to_numeric(df["close"], errors="coerce").replace(0, pd.NA)
    for field in ("open", "high", "low", "close"):
        raw = pd.to_numeric(df[field], errors="coerce")
        df[field] = (raw * factor).where(factor.notna(), raw)
    return df


def _completed_resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    aggregations = {"open": "first", "high": "max", "low": "min", "close": "last", "price": "last"}
    if "volume" in df.columns:
        aggregations["volume"] = "sum"
    agg = df.resample(rule).agg(aggregations).dropna(subset=["price"])
    # The final bucket may represent the week/month currently in formation. Always excluding it is conservative
    # and guarantees that weekly/monthly filters only depend on completed periods.
    return agg.iloc[:-1].copy() if len(agg) >= 2 else agg.iloc[0:0].copy()


def _simple_sma(series: pd.Series, period: int) -> float | None:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < period:
        return None
    return float(s.iloc[-period:].mean())


def _rsi(series: pd.Series, period: int = 14) -> float | None:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) <= period:
        return None
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    last_g = _f(avg_gain.iloc[-1]); last_l = _f(avg_loss.iloc[-1])
    if last_g is None or last_l is None:
        return None
    if last_g == 0 and last_l == 0:
        # Wilder's ratio is indeterminate in a perfectly flat market. There is
        # neither buying nor selling pressure, therefore the neutral RSI is 50.
        return 50.0
    if last_l == 0:
        return 100.0
    rs = last_g / last_l
    return 100.0 - 100.0 / (1.0 + rs)


def technical_features(bars: Iterable, *, trend_period: int = 21, pivot_timeframe: str = "daily") -> dict:
    if trend_period not in {20, 21}:
        raise ValueError("trend_period_must_be_20_or_21")
    if pivot_timeframe not in {"daily", "weekly", "monthly"}:
        raise ValueError("invalid_pivot_timeframe")
    df = _bars_frame(bars)
    if df.empty:
        return {
            "current_price": None, "trend_period": trend_period,
            "sma_daily": None, "sma_weekly": None, "sma_monthly": None,
            "trend_daily": None, "trend_weekly": None, "trend_monthly": None,
            "rsi14": None, "pivot_timeframe": pivot_timeframe,
            "volume_daily": None, "volume_daily_ma9": None, "volume_daily_ratio": None,
            "volume_monthly": None, "volume_monthly_ma9": None, "volume_monthly_ratio": None,
            **{k: None for k in ("pp", "r1", "s1", "r2", "s2", "r3", "s3")},
        }
    current = float(df["price"].iloc[-1])
    daily_sma = _simple_sma(df["price"], trend_period)
    weekly = _completed_resample(df, "W-FRI")
    monthly = _completed_resample(df, "ME")
    weekly_sma = _simple_sma(weekly["price"], trend_period) if not weekly.empty else None
    monthly_sma = _simple_sma(monthly["price"], trend_period) if not monthly.empty else None

    def trend(sma):
        if sma is None:
            return None
        return "up" if current > sma else "down"

    if pivot_timeframe == "daily":
        ref = df.iloc[-2] if len(df) >= 2 else None
    elif pivot_timeframe == "weekly":
        ref = weekly.iloc[-1] if len(weekly) >= 1 else None
    else:
        ref = monthly.iloc[-1] if len(monthly) >= 1 else None
    piv = pivot_points(ref["high"], ref["low"], ref["close"]) if ref is not None else pivot_points(None, None, None)
    ref_ts = None if ref is None else ref.name.isoformat()
    daily_volume = _f(df["volume"].iloc[-1]) if "volume" in df.columns else None
    daily_volume_ma9 = _simple_sma(df["volume"].iloc[:-1], 9) if "volume" in df.columns else None
    monthly_volume = _f(monthly["volume"].iloc[-1]) if "volume" in monthly.columns and not monthly.empty else None
    monthly_volume_ma9 = _simple_sma(monthly["volume"].iloc[:-1], 9) if "volume" in monthly.columns else None
    return {
        "current_price": current, "trend_period": trend_period,
        "sma_daily": daily_sma, "sma_weekly": weekly_sma, "sma_monthly": monthly_sma,
        "trend_daily": trend(daily_sma), "trend_weekly": trend(weekly_sma), "trend_monthly": trend(monthly_sma),
        "rsi14": _rsi(df["price"], 14), "pivot_timeframe": pivot_timeframe, "pivot_reference": ref_ts,
        "volume_daily": daily_volume,
        "volume_daily_ma9": daily_volume_ma9,
        "volume_daily_ratio": daily_volume / daily_volume_ma9 if daily_volume is not None and daily_volume_ma9 else None,
        "volume_monthly": monthly_volume,
        "volume_monthly_ma9": monthly_volume_ma9,
        "volume_monthly_ratio": monthly_volume / monthly_volume_ma9 if monthly_volume is not None and monthly_volume_ma9 else None,
        **piv,
    }


def _range_pass(value, spec: dict | None) -> bool:
    if not spec:
        return True
    lo, hi = spec.get("min"), spec.get("max")
    if lo is None and hi is None:
        return True
    v = _f(value)
    if v is None:
        return False
    if lo is not None and v < float(lo):
        return False
    if hi is not None and v > float(hi):
        return False
    return True


def _trend_pass(actual: str | None, requested: str | None) -> bool:
    return requested in (None, "any") or actual == requested


def _pivot_zone(price: float | None, piv: dict) -> str | None:
    p = _f(price)
    if p is None or any(_f(piv.get(k)) is None for k in PIVOT_LEVELS):
        return None
    s3, s2, s1, pp, r1, r2, r3 = [float(piv[k]) for k in ("s3", "s2", "s1", "pp", "r1", "r2", "r3")]
    if p < s3: return "below_s3"
    if p < s2: return "s3_s2"
    if p < s1: return "s2_s1"
    if p < pp: return "s1_pp"
    if p < r1: return "pp_r1"
    if p < r2: return "r1_r2"
    if p < r3: return "r2_r3"
    return "above_r3"


def technical_filters_pass(features: dict, spec: dict | None) -> bool:
    spec = spec or {}
    if not _trend_pass(features.get("trend_daily"), spec.get("daily_trend")): return False
    if not _trend_pass(features.get("trend_weekly"), spec.get("weekly_trend")): return False
    if not _trend_pass(features.get("trend_monthly"), spec.get("monthly_trend")): return False
    if not _range_pass(features.get("rsi14"), spec.get("rsi14")): return False
    if spec.get("volume_daily_above_ma9") and (_f(features.get("volume_daily_ratio")) or 0) <= 1:
        return False
    if spec.get("volume_monthly_above_ma9") and (_f(features.get("volume_monthly_ratio")) or 0) <= 1:
        return False

    zone = spec.get("pivot_zone")
    if zone and zone != "any":
        if zone not in PIVOT_ZONES or _pivot_zone(features.get("current_price"), features) != zone:
            return False
    near = spec.get("near_pivot_level")
    if near and near != "none":
        if near not in PIVOT_LEVELS:
            return False
        level = _f(features.get(near)); price = _f(features.get("current_price"))
        if level is None or price is None or level == 0:
            return False
        tol = max(float(spec.get("pivot_tolerance_pct") or 0.5), 0.0) / 100.0
        if abs(price / level - 1.0) > tol:
            return False
    return True


def _valuation_result(
    family_id: str,
    *,
    method: str,
    status: str,
    value: float | None = None,
    upside_pct: float | None = None,
    reason: str | None = None,
    scenarios: dict | None = None,
    quality: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    """Return one stable payload shape for every valuation family."""
    family = VALUATION_FAMILIES[family_id]
    return {
        "family_id": family_id,
        "method": method,
        "label": family.label,
        "status": status,
        "value": _f(value),
        "upside_pct": _f(upside_pct),
        "reason": reason,
        "scenarios": scenarios or {},
        "quality": quality or {
            "score": 100.0 if status == "valid" else 0.0,
            "coverage_pct": 100.0 if status == "valid" else 0.0,
            "sample_size": 0,
            "metric_sample_sizes": {},
            "metrics_used": [],
            "warnings": [],
        },
        "metadata": metadata or {},
    }


def _unavailable_valuation(family_id: str, asset_type: str, asset_class: str = "default") -> dict:
    rule = valuation_applicability(asset_type, asset_class)[family_id]
    status = "not_applicable" if rule.status == "not_applicable" else "insufficient_data"
    return _valuation_result(
        family_id,
        method=rule.method or family_id,
        status=status,
        reason=rule.note,
        metadata={"applicability": rule.status, "asset_class": asset_class},
    )


def _set_valuation_result(fund: dict, family_id: str, result: dict) -> None:
    """Store canonical nested data and convenient flat fields together."""
    fund.setdefault("valuation_methods", {})[family_id] = result
    value_field, upside_field = VALUATION_FLAT_FIELDS[family_id]
    fund[value_field] = _f(result.get("value"))
    fund[upside_field] = _f(result.get("upside_pct"))
    fund[f"{family_id}_status"] = result.get("status")


def _active_valuation_families(flags: Mapping | None) -> list[str]:
    values = flags or {}
    return [
        family_id
        for family_id, aliases in VALUATION_FLAG_ALIASES.items()
        if any(bool(values.get(alias)) for alias in aliases)
    ]


def _valuation_family_passes(fund: dict, family_id: str, flags: Mapping) -> bool:
    nested = fund.get("valuation_methods") if isinstance(fund.get("valuation_methods"), dict) else {}
    result = nested.get(family_id) if isinstance(nested.get(family_id), dict) else {}
    if result and result.get("status") not in {None, "valid"}:
        return False
    value_field, upside_field = VALUATION_FLAT_FIELDS[family_id]
    value = _f(result.get("value")) if result else _f(fund.get(value_field))
    upside = _f(result.get("upside_pct")) if result else _f(fund.get(upside_field))

    # Preserve compatibility with rows constructed by older clients/tests.
    if family_id == "graham_reference" and value is None:
        price, pe, pbv = _f(fund.get("price")), _f(fund.get("pe")), _f(fund.get("pbv"))
        if price is not None and price > 0 and pe is not None and pe > 0 and pbv is not None and pbv > 0:
            value = price * math.sqrt(22.5 / (pe * pbv))
            upside = (value / price - 1.0) * 100.0
    elif family_id == "dividend_yield_ceiling" and value is None:
        price, dy = _f(fund.get("price")), _f(fund.get("dividend_yield_pct"))
        if price is not None and price > 0 and dy is not None and dy >= 0:
            value = price * dy / 6.0
            upside = (value / price - 1.0) * 100.0

    price = _f(fund.get("price"))
    if value is None or price is None or price <= 0:
        return False

    thresholds = flags.get("minimum_upside_pct")
    threshold = None
    if isinstance(thresholds, Mapping):
        threshold = _f(thresholds.get(family_id))
    elif thresholds is not None:
        threshold = _f(thresholds)
    if threshold is not None:
        return upside is not None and upside >= threshold
    return price < value


def valuation_flags_pass(fund: dict, flags: dict | None) -> bool:
    """Evaluate any combination of the four families, failing closed on N/D.

    ``all`` is the default and therefore preserves the historical behavior.
    ``any`` lets an authorized caller select several methodologies as
    alternatives. Legacy flag names remain accepted.
    """
    flags = flags or {}
    logic = str(flags.get("logic") or flags.get("valuation_logic") or "all").strip().casefold()
    if logic not in {"all", "any"}:
        raise ValueError("invalid_valuation_logic")
    active = _active_valuation_families(flags)
    if not active:
        return True
    checks = [_valuation_family_passes(fund, family_id, flags) for family_id in active]
    return all(checks) if logic == "all" else any(checks)


def filter_row(fund: dict, scores: dict, *, fundamental_filters: dict | None = None,
               score_filters: dict | None = None, valuation_flags: dict | None = None) -> bool:
    for field, spec in (fundamental_filters or {}).items():
        if field not in FUNDAMENTAL_FIELDS or not _range_pass(fund.get(field), spec):
            return False
    for field, spec in (score_filters or {}).items():
        if field not in SCORE_FIELDS or not _range_pass(scores.get(field), spec):
            return False
    return valuation_flags_pass(fund, valuation_flags)


def row_from_orm(asset, fund, tech, score) -> dict:
    def g(obj, name): return _f(getattr(obj, name, None)) if obj is not None else None
    fund_dict = {field: g(fund, field) for field in FUNDAMENTAL_FIELDS}
    if fund_dict.get("price") is None:
        fund_dict["price"] = g(tech, "close")
    if fund_dict.get("daily_liquidity") is None:
        fund_dict["daily_liquidity"] = g(tech, "daily_liquidity")
    score_dict = {field: g(score, field) for field in SCORE_FIELDS}
    graham_number = None
    graham_upside_pct = None
    barsi_ceiling_price = None
    barsi_upside_pct = None
    price = fund_dict.get("price")
    pe = fund_dict.get("pe")
    pbv = fund_dict.get("pbv")
    if asset.asset_type == "stock" and price is not None and price > 0 and pe is not None and pe > 0 and pbv is not None and pbv > 0:
        # P/L = preço/LPA e P/VP = preço/VPA; esta forma é equivalente
        # ao número de Graham e evita depender de campos derivados ausentes.
        graham_number = price * math.sqrt(22.5 / (pe * pbv))
        graham_upside_pct = ((graham_number / price) - 1.0) * 100.0
    dy = fund_dict.get("dividend_yield_pct")
    if asset.asset_type in {"stock", "fii"} and price is not None and price > 0 and dy is not None and dy >= 0:
        # Preço-teto de dividendos: provento anual estimado dividido pela
        # rentabilidade mínima desejada de 6% ao ano.
        barsi_ceiling_price = price * dy / 6.0
        barsi_upside_pct = (barsi_ceiling_price / price - 1.0) * 100.0
    raw_payload = getattr(fund, "raw_payload", None) if fund is not None else None
    if isinstance(raw_payload, dict):
        fund_dict["dividend_per_share_ttm"] = _f(raw_payload.get("dividend_per_share_ttm"))
        fund_dict["normalized_dividend_per_share"] = _f(raw_payload.get("normalized_dividend_per_share"))
    if (
        fund_dict.get("dividend_per_share_ttm") is None
        and price is not None and price > 0 and dy is not None and dy >= 0
    ):
        # Fundamentus publishes DY on the same price basis. Recovering D0 from
        # price * DY is an exact unit conversion, not a growth assumption.
        fund_dict["dividend_per_share_ttm"] = price * dy / 100.0

    valuation_methods = {
        family_id: _unavailable_valuation(family_id, asset.asset_type)
        for family_id in VALUATION_FAMILIES
    }
    graham_meta = valuation_method_metadata("graham_number")
    if asset.asset_type == "stock":
        valuation_methods["graham_reference"] = _valuation_result(
            "graham_reference",
            method=graham_meta.canonical_id,
            status="valid" if graham_number is not None else "insufficient_data",
            value=graham_number,
            upside_pct=graham_upside_pct,
            reason=None if graham_number is not None else "requires_positive_eps_and_bvps",
            metadata={"formula": graham_meta.formula},
        )
    dividend_meta = valuation_method_metadata("dividend_yield_ceiling_ttm")
    if asset.asset_type in {"stock", "fii"}:
        valuation_methods["dividend_yield_ceiling"] = _valuation_result(
            "dividend_yield_ceiling",
            method=dividend_meta.canonical_id,
            status="valid" if barsi_ceiling_price is not None else "insufficient_data",
            value=barsi_ceiling_price,
            upside_pct=barsi_upside_pct,
            reason=None if barsi_ceiling_price is not None else "dividend_per_share_ttm_required",
            metadata={"target_yield_pct": 6.0, "formula": dividend_meta.formula},
        )
    size = company_size_category({
        "market_cap_category": asset.market_cap_category,
        "metadata_json": asset.metadata_json if isinstance(asset.metadata_json, dict) else {},
        "market_cap": g(tech, "market_cap"),
    })
    return {
        "asset": {
            "id": str(asset.id), "ticker": asset.ticker, "name": asset.name, "asset_type": asset.asset_type,
            "asset_type_label": {"stock": "Ação", "fii": "FII", "etf": "ETF", "bdr": "BDR", "future": "Futuro / derivativo"}.get(asset.asset_type, "Outro"),
            "sector": asset.sector, "industry": asset.industry, "segment": asset.segment,
            "classification": classification_for(
                asset.asset_type, asset.sector, asset.segment,
                industry=asset.industry, category=asset.market_cap_category,
            ),
            "sector_label": localize_classification(asset.sector),
            "industry_label": localize_classification(asset.industry),
            "segment_label": localize_classification(asset.segment),
            "company_size": size,
            "company_size_label": COMPANY_SIZE_LABELS.get(size),
            "market_cap_category_label": COMPANY_SIZE_LABELS.get(size) or localize_classification(asset.market_cap_category),
        },
        "fundamentals": {
            **fund_dict,
            "graham_number": graham_number,
            "graham_upside_pct": graham_upside_pct,
            # Legacy fields are retained until every API/UI client has moved
            # to the canonical nested representation.
            "barsi_ceiling_price": barsi_ceiling_price,
            "barsi_upside_pct": barsi_upside_pct,
            "dividend_yield_ceiling_value": barsi_ceiling_price,
            "dividend_yield_ceiling_upside_pct": barsi_upside_pct,
            "relative_peers_value": None,
            "relative_peers_upside_pct": None,
            "economic_value": None,
            "economic_value_upside_pct": None,
            "valuation_methods": valuation_methods,
            **{f"{family_id}_status": valuation_methods[family_id]["status"] for family_id in VALUATION_FAMILIES},
        },
        "scores": score_dict,
        "snapshot_technical": {
            "rsi14": g(tech, "rsi14"), "sma20": g(tech, "sma20"), "sma20_1w": g(tech, "sma20_1w"),
            "sma20_1m": g(tech, "sma20_1m"), "daily_liquidity": g(tech, "daily_liquidity"),
        },
    }


def _asset_valuation_class(asset) -> str:
    metadata = asset.metadata_json if isinstance(getattr(asset, "metadata_json", None), dict) else {}
    explicit = str(metadata.get("valuation_class") or metadata.get("asset_class") or "").strip().casefold()
    if explicit:
        return explicit
    sector = str(getattr(asset, "sector", None) or "").casefold()
    industry = str(getattr(asset, "industry", None) or "").casefold()
    segment = str(getattr(asset, "segment", None) or "").casefold()
    if asset.asset_type == "stock":
        if any(token in f"{sector} {industry}" for token in ("bank", "banco", "financial services")):
            return "bank"
        if any(token in f"{sector} {industry}" for token in ("insurance", "segur")):
            return "insurance"
    if asset.asset_type == "fii":
        if any(token in segment for token in ("papel", "receb", "cri", "mortgage")):
            return "paper"
        if any(token in segment for token in ("fof", "fundo de fundos")):
            return "fof"
        if segment:
            return "brick"
    return "default"


def _scenario_family_result(result) -> dict:
    payload = result.model_dump(mode="python")
    base = payload.get("scenarios", {}).get("base") or {}
    metadata = {
        **(payload.get("metadata") or {}),
        "asset_type": payload.get("asset_type"),
        "asset_class": payload.get("asset_class"),
    }
    return _valuation_result(
        result.family_id,
        method=result.method,
        status=result.status,
        value=base.get("value"),
        upside_pct=base.get("upside_pct"),
        reason=result.reason,
        scenarios=payload.get("scenarios"),
        quality=payload.get("quality"),
        metadata=metadata,
    )


def _valuation_options(options: Mapping | None) -> tuple[dict, dict]:
    values = options if isinstance(options, Mapping) else {}
    relative = values.get("relative_peers")
    relative = dict(relative) if isinstance(relative, Mapping) else {}
    economic = values.get("economic_value") or values.get("gordon_growth_ddm")
    economic = dict(economic) if isinstance(economic, Mapping) else {}
    return relative, economic


def _enrich_valuation_rows(
    entries: list[tuple[object, dict]],
    *,
    peer_entries: list[tuple[object, dict]],
    valuation_assumptions: Mapping | None,
) -> None:
    """Add relative/Gordon results after the peer universe is known."""
    relative_options, economic_options = _valuation_options(valuation_assumptions)
    try:
        min_peers = int(relative_options.get("minimum_peers", 5))
    except (TypeError, ValueError):
        min_peers = 5
    raw_limits = relative_options.get("winsor_limits", (0.10, 0.90))
    try:
        winsor_limits = (
            float(raw_limits[0]), float(raw_limits[1])
        ) if isinstance(raw_limits, (list, tuple)) and len(raw_limits) == 2 else (0.10, 0.90)
    except (TypeError, ValueError):
        winsor_limits = (0.10, 0.90)

    peers = [
        {
            **row["asset"], **row["fundamentals"],
            "asset_class": _asset_valuation_class(peer_asset),
        }
        for peer_asset, row in peer_entries
    ]
    economic_scenarios = economic_options.get("scenarios")
    if economic_scenarios is None and any(name in economic_options for name in ("conservative", "base", "optimistic")):
        economic_scenarios = {
            name: economic_options.get(name)
            for name in ("conservative", "base", "optimistic")
            if name in economic_options
        }
    dividend_by_ticker = economic_options.get("normalized_dividend_per_share_by_ticker")
    dividend_by_ticker = dividend_by_ticker if isinstance(dividend_by_ticker, Mapping) else {}

    for asset, row in entries:
        fund = row["fundamentals"]
        asset_class = _asset_valuation_class(asset)
        target = {**row["asset"], **fund, "asset_class": asset_class}
        # Only stocks and FIIs currently have the accounting inputs and peer
        # taxonomy required by this engine.  For ETFs, BDRs and futures keep
        # the more informative class-specific data requirement or
        # ``not_applicable`` result
        # produced by the applicability catalog instead of overwriting it
        # with a generic unsupported-type response.
        if asset.asset_type in {"stock", "fii"}:
            relative = relative_valuation(
                target,
                peers,
                asset_type=asset.asset_type,
                asset_class=asset_class,
                min_peers=min_peers,
                winsor_limits=winsor_limits,
            )
            _set_valuation_result(fund, "relative_peers", _scenario_family_result(relative))

        if asset.asset_type == "stock":
            use_ttm = bool(economic_options.get("use_ttm_dividend"))
            dividend = None
            dividend_source = None
            # This is an explicit opt-in.  When selected, the TTM amount must
            # actually be used rather than silently falling back behind a
            # different provider field.
            if use_ttm:
                dividend = _f(fund.get("dividend_per_share_ttm"))
                dividend_source = "trailing_12_month_dividend" if dividend is not None else None
            if dividend is None and not use_ttm:
                dividend = _f(dividend_by_ticker.get(str(asset.ticker).upper()))
                dividend_source = "user_normalized_dividend" if dividend is not None else None
            if dividend is None and not use_ttm:
                dividend = _f(fund.get("normalized_dividend_per_share"))
                dividend_source = "normalized_provider_dividend" if dividend is not None else None
            economic = gordon_growth_scenarios(
                dividend,
                assumptions=economic_scenarios,
                market_price=fund.get("price"),
                margin_of_safety_pct=economic_options.get("margin_of_safety_pct"),
                asset_type=asset.asset_type,
                asset_class=asset_class,
            )
            economic_payload = _scenario_family_result(economic)
            economic_payload.setdefault("metadata", {})["dividend_source"] = dividend_source
            if dividend_source == "trailing_12_month_dividend":
                economic_payload.setdefault("quality", {}).setdefault("warnings", []).append(
                    "ttm_dividend_is_not_normalized"
                )
        else:
            economic_payload = _unavailable_valuation("economic_value", asset.asset_type, asset_class)
        _set_valuation_result(fund, "economic_value", economic_payload)


def advanced_screen(repo, *, asset_type: str, fundamental_filters: dict | None = None,
                    score_filters: dict | None = None, valuation_flags: dict | None = None,
                    valuation_assumptions: dict | None = None,
                    technical_filters: dict | None = None, trend_period: int = 21,
                    pivot_timeframe: str = "daily", include_technical_columns: bool = True,
                    limit: int = 100, allowed_tickers: Iterable[str] | None = None,
                    company_sizes: Iterable[str] | None = None,
                    ibov_membership: str = "any", ibov_tickers: Iterable[str] | None = None) -> dict:
    full_universe = list(repo.latest_universe(asset_type=asset_type, limit=1200))
    universe = list(full_universe)
    if allowed_tickers is not None:
        allowed = {str(ticker).strip().upper() for ticker in allowed_tickers if str(ticker).strip()}
        universe = [row for row in universe if str(row[0].ticker).upper() in allowed]
    requested_sizes = {str(value) for value in (company_sizes or []) if str(value)}
    if requested_sizes:
        invalid_sizes = requested_sizes.difference(COMPANY_SIZE_LABELS)
        if invalid_sizes:
            raise ValueError("invalid_company_size")
        universe = [row for row in universe if company_size_category({
            "market_cap_category": row[0].market_cap_category,
            "metadata_json": row[0].metadata_json if isinstance(row[0].metadata_json, dict) else {},
            "market_cap": getattr(row[2], "market_cap", None),
        }) in requested_sizes]
    ibov = {str(value).strip().upper() for value in (ibov_tickers or []) if str(value).strip()}
    if ibov_membership not in {"any", "inside", "outside"}:
        raise ValueError("invalid_ibov_membership")
    if ibov_membership != "any":
        if not ibov:
            raise ValueError("ibov_membership_unavailable")
        should_be_inside = ibov_membership == "inside"
        universe = [row for row in universe if ((str(row[0].ticker).upper() in ibov) == should_be_inside)]
    peer_rows = []
    rows_by_asset_id = {}
    for asset, fund, tech, score in full_universe:
        if fund is None and asset_type in {"stock", "fii"}:
            continue
        row = row_from_orm(asset, fund, tech, score)
        peer_rows.append((asset, row))
        rows_by_asset_id[asset.id] = row

    # Screen restrictions select targets, not the reference peer group. This
    # keeps a one-ticker search comparable with the same full market cohort.
    base_rows = [
        (asset, rows_by_asset_id[asset.id])
        for asset, _fund, _tech, _score in universe
        if asset.id in rows_by_asset_id
    ]

    preliminary = []
    for asset, row in base_rows:
        if filter_row(row["fundamentals"], row["scores"], fundamental_filters=fundamental_filters,
                      score_filters=score_filters, valuation_flags=None):
            preliminary.append((asset, row))

    _enrich_valuation_rows(
        preliminary,
        peer_entries=peer_rows,
        valuation_assumptions=valuation_assumptions,
    )
    preliminary = [
        (asset, row)
        for asset, row in preliminary
        if valuation_flags_pass(row["fundamentals"], valuation_flags)
    ]

    tech_spec = technical_filters or {}
    technical_active = any([
        tech_spec.get("daily_trend") not in (None, "any"), tech_spec.get("weekly_trend") not in (None, "any"),
        tech_spec.get("monthly_trend") not in (None, "any"), bool(tech_spec.get("rsi14")),
        tech_spec.get("pivot_zone") not in (None, "any"), tech_spec.get("near_pivot_level") not in (None, "none"),
        bool(tech_spec.get("volume_daily_above_ma9")), bool(tech_spec.get("volume_monthly_above_ma9")),
    ])
    need_history = technical_active or include_technical_columns
    histories = repo.price_histories_batch([a.id for a, _ in preliminary]) if need_history and preliminary else {}

    results = []
    missing_history = 0
    for asset, row in preliminary:
        features = technical_features(histories.get(asset.id, []), trend_period=trend_period, pivot_timeframe=pivot_timeframe) if need_history else {}
        # Wide-universe fallback: when period 20 is requested and local history is missing, use the existing TradingView
        # 20-period snapshots for trend only. Pivot levels intentionally never use this fallback because their period semantics
        # are not guaranteed by that snapshot.
        if need_history and features.get("current_price") is None:
            missing_history += 1
            snap = row["snapshot_technical"]
            price = row["fundamentals"].get("price")
            features.update({"current_price": price, "rsi14": snap.get("rsi14")})
            if trend_period == 20 and price is not None:
                for label, key in (("daily", "sma20"), ("weekly", "sma20_1w"), ("monthly", "sma20_1m")):
                    sma = snap.get(key)
                    features[f"sma_{label}"] = sma
                    features[f"trend_{label}"] = None if sma is None else ("up" if price > sma else "down")
        if technical_active and not technical_filters_pass(features, tech_spec):
            continue
        flat = {
            **row["asset"], **row["fundamentals"], **row["scores"],
            **({
                "trend_period": features.get("trend_period", trend_period),
                "trend_daily": features.get("trend_daily"), "trend_weekly": features.get("trend_weekly"), "trend_monthly": features.get("trend_monthly"),
                "sma_daily": features.get("sma_daily"), "sma_weekly": features.get("sma_weekly"), "sma_monthly": features.get("sma_monthly"),
                "rsi14_screen": features.get("rsi14"), "pivot_timeframe": pivot_timeframe, "pivot_reference": features.get("pivot_reference"),
                "pp": features.get("pp"), "r1": features.get("r1"), "s1": features.get("s1"), "r2": features.get("r2"), "s2": features.get("s2"), "r3": features.get("r3"), "s3": features.get("s3"),
                "pivot_zone": _pivot_zone(features.get("current_price"), features),
                "volume_daily": features.get("volume_daily"), "volume_daily_ma9": features.get("volume_daily_ma9"),
                "volume_daily_ratio": features.get("volume_daily_ratio"),
                "volume_monthly": features.get("volume_monthly"), "volume_monthly_ma9": features.get("volume_monthly_ma9"),
                "volume_monthly_ratio": features.get("volume_monthly_ratio"),
                "in_ibov": str(asset.ticker).upper() in ibov if ibov else None,
            } if need_history else {}),
        }
        results.append(flat)
    if asset_type == "stock":
        # Rank the complete approved universe before applying the display limit.
        # Otherwise the first database rows, rather than the best Graham upside,
        # would determine which assets are eligible to appear.
        results.sort(
            key=lambda item: _f(item.get("graham_upside_pct"))
            if _f(item.get("graham_upside_pct")) is not None else float("-inf"),
            reverse=True,
        )
    results = results[:limit]
    return {
        "rows": results,
        "meta": {
            "universe_count": len(universe), "fundamental_candidates": len(preliminary), "returned": len(results),
            "technical_history_missing": missing_history, "trend_period": trend_period, "pivot_timeframe": pivot_timeframe,
            "technical_filter_active": technical_active,
            "valuation_families": list(VALUATION_FAMILIES),
            "valuation_filter_active": _active_valuation_families(valuation_flags),
            "valuation_logic": str((valuation_flags or {}).get("logic") or (valuation_flags or {}).get("valuation_logic") or "all").casefold(),
        },
    }
