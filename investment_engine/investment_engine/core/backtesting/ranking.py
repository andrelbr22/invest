from __future__ import annotations

import math
from typing import Any

import pandas as pd


MINIMUM_CLOSED_TRADES = 5
VALIDATION_FRACTION = 0.30


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def validation_metrics(equity_curve: list[dict], fraction: float = VALIDATION_FRACTION) -> dict:
    """Calculate a transparent final-period holdout without rerunning the strategy."""
    if not equity_curve:
        return {"validation_bars": 0}
    frame = pd.DataFrame(equity_curve)
    if len(frame) < 20 or "equity" not in frame or "timestamp" not in frame:
        return {"validation_bars": 0}
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame["equity"] = pd.to_numeric(frame["equity"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "equity"]).sort_values("timestamp")
    size = max(20, int(round(len(frame) * fraction)))
    sample = frame.tail(min(size, len(frame))).copy()
    if len(sample) < 2 or float(sample.iloc[0]["equity"]) <= 0:
        return {"validation_bars": int(len(sample))}
    daily = sample["equity"].pct_change().fillna(0.0)
    total = float(sample.iloc[-1]["equity"] / sample.iloc[0]["equity"] - 1.0)
    years = max((sample.iloc[-1]["timestamp"] - sample.iloc[0]["timestamp"]).days / 365.25, 1 / 365.25)
    cagr = (1.0 + total) ** (1.0 / years) - 1.0 if total > -1 else -1.0
    volatility = float(daily.std(ddof=0))
    sharpe = float(daily.mean() / volatility * math.sqrt(252)) if volatility > 0 else None
    drawdown = sample["equity"] / sample["equity"].cummax() - 1.0
    return {
        "validation_bars": int(len(sample)),
        "validation_start": sample.iloc[0]["timestamp"].isoformat(),
        "validation_end": sample.iloc[-1]["timestamp"].isoformat(),
        "validation_total_return_pct": total * 100.0,
        "validation_cagr_pct": cagr * 100.0,
        "validation_sharpe_ratio": sharpe,
        "validation_max_drawdown_pct": float(drawdown.min()) * 100.0,
    }


def robust_ranking(metrics: dict) -> tuple[float, str]:
    """Rank return and risk together; small samples remain visible but penalized."""
    trades = int(metrics.get("closed_trades", metrics.get("trades", 0)) or 0)
    bars = int(metrics.get("bars") or 0)
    cagr = _number(metrics.get("validation_cagr_pct"), _number(metrics.get("cagr_pct")))
    sharpe = _number(metrics.get("validation_sharpe_ratio"), _number(metrics.get("sharpe_ratio")))
    drawdown = _number(metrics.get("validation_max_drawdown_pct"), _number(metrics.get("max_drawdown_pct"), -100.0))
    sortino = _number(metrics.get("sortino_ratio"))
    profit_factor = _clamp(_number(metrics.get("profit_factor")), 0.0, 5.0)

    score = (
        20.0 * _clamp((cagr + 20.0) / 60.0, 0.0, 1.0)
        + 25.0 * _clamp((sharpe + 1.0) / 3.0, 0.0, 1.0)
        + 10.0 * _clamp((sortino + 1.0) / 4.0, 0.0, 1.0)
        + 20.0 * _clamp((40.0 + drawdown) / 40.0, 0.0, 1.0)
        + 15.0 * _clamp(profit_factor / 3.0, 0.0, 1.0)
        + 10.0 * _clamp(trades / 12.0, 0.0, 1.0)
    )
    if trades < 2:
        sample_status, score = "insufficient", score * 0.35
    elif trades < MINIMUM_CLOSED_TRADES or bars < 252:
        sample_status, score = "limited", score * 0.65
    else:
        sample_status = "adequate"
    return round(score, 4), sample_status


def enrich_result(result: dict) -> dict:
    metrics = dict(result.get("metrics") or {})
    metrics.update(validation_metrics(result.get("equity_curve") or []))
    ranking_score, sample_status = robust_ranking(metrics)
    result["metrics"] = metrics
    result["ranking_score"] = ranking_score
    result["sample_status"] = sample_status
    return result
