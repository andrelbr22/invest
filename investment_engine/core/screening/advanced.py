from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math
from typing import Iterable

import pandas as pd

from investment_engine.core.portfolio.service import classification_for, localize_classification
from investment_engine.core.screening.universe import COMPANY_SIZE_LABELS, company_size_category


FUNDAMENTAL_FIELDS = {
    "price", "pe", "pbv", "dividend_yield_pct", "ev_ebitda", "ebit_margin_pct", "net_margin_pct",
    "current_ratio", "roe_pct", "roic_pct", "gross_debt_to_equity", "net_debt_to_ebitda",
    "revenue_cagr_5y_pct", "earnings_cagr_5y_pct", "ffo_yield_pct", "cap_rate_pct", "vacancy_pct",
    "financial_vacancy_pct", "ltv_pct", "wale_years", "daily_liquidity",
}

SCORE_FIELDS = {
    "quality_score", "value_score", "growth_score", "technical_score", "risk_score", "liquidity_score",
    "alb_score", "data_quality_score",
}

PIVOT_ZONES = {
    "below_s3", "s3_s2", "s2_s1", "s1_pp", "pp_r1", "r1_r2", "r2_r3", "above_r3",
}
PIVOT_LEVELS = {"s3", "s2", "s1", "pp", "r1", "r2", "r3"}


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
    return df[df["price"].notna() & (df["price"] > 0)].copy()


def _completed_resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    agg = df.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "price": "last"}).dropna(subset=["price"])
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
    return {
        "current_price": current, "trend_period": trend_period,
        "sma_daily": daily_sma, "sma_weekly": weekly_sma, "sma_monthly": monthly_sma,
        "trend_daily": trend(daily_sma), "trend_weekly": trend(weekly_sma), "trend_monthly": trend(monthly_sma),
        "rsi14": _rsi(df["price"], 14), "pivot_timeframe": pivot_timeframe, "pivot_reference": ref_ts,
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


def valuation_flags_pass(fund: dict, flags: dict | None) -> bool:
    flags = flags or {}
    if flags.get("below_graham"):
        pe, pbv = _f(fund.get("pe")), _f(fund.get("pbv"))
        if pe is None or pbv is None or pe <= 0 or pbv <= 0 or pe * pbv >= 22.5:
            return False
    if flags.get("below_barsi_6pct"):
        dy = _f(fund.get("dividend_yield_pct"))
        if dy is None or dy <= 6.0:
            return False
    return True


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
    score_dict = {field: g(score, field) for field in SCORE_FIELDS}
    size = company_size_category({
        "market_cap_category": asset.market_cap_category,
        "metadata_json": asset.metadata_json if isinstance(asset.metadata_json, dict) else {},
        "market_cap": g(tech, "market_cap"),
    })
    return {
        "asset": {
            "id": str(asset.id), "ticker": asset.ticker, "name": asset.name, "asset_type": asset.asset_type,
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
        "fundamentals": fund_dict,
        "scores": score_dict,
        "snapshot_technical": {
            "rsi14": g(tech, "rsi14"), "sma20": g(tech, "sma20"), "sma20_1w": g(tech, "sma20_1w"),
            "sma20_1m": g(tech, "sma20_1m"), "daily_liquidity": g(tech, "daily_liquidity"),
        },
    }


def advanced_screen(repo, *, asset_type: str, fundamental_filters: dict | None = None,
                    score_filters: dict | None = None, valuation_flags: dict | None = None,
                    technical_filters: dict | None = None, trend_period: int = 21,
                    pivot_timeframe: str = "daily", include_technical_columns: bool = True,
                    limit: int = 100, allowed_tickers: Iterable[str] | None = None) -> dict:
    universe = repo.latest_universe(asset_type=asset_type, limit=1200)
    if allowed_tickers is not None:
        allowed = {str(ticker).strip().upper() for ticker in allowed_tickers if str(ticker).strip()}
        universe = [row for row in universe if str(row[0].ticker).upper() in allowed]
    preliminary = []
    for asset, fund, tech, score in universe:
        if fund is None:
            continue
        row = row_from_orm(asset, fund, tech, score)
        if filter_row(row["fundamentals"], row["scores"], fundamental_filters=fundamental_filters,
                      score_filters=score_filters, valuation_flags=valuation_flags):
            preliminary.append((asset, row))

    tech_spec = technical_filters or {}
    technical_active = any([
        tech_spec.get("daily_trend") not in (None, "any"), tech_spec.get("weekly_trend") not in (None, "any"),
        tech_spec.get("monthly_trend") not in (None, "any"), bool(tech_spec.get("rsi14")),
        tech_spec.get("pivot_zone") not in (None, "any"), tech_spec.get("near_pivot_level") not in (None, "none"),
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
            } if need_history else {}),
        }
        results.append(flat)
        if len(results) >= limit:
            break
    return {
        "rows": results,
        "meta": {
            "universe_count": len(universe), "fundamental_candidates": len(preliminary), "returned": len(results),
            "technical_history_missing": missing_history, "trend_period": trend_period, "pivot_timeframe": pivot_timeframe,
            "technical_filter_active": technical_active,
        },
    }
