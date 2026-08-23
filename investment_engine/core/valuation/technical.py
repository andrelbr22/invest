from __future__ import annotations

from ..models.common import Signal, Trend
from ..models.valuation import PivotLevels


def tradingview_signal(score: float | None) -> Signal:
    if score is None:
        return Signal.NO_DATA
    if score > 0.5:
        return Signal.STRONG_BUY
    if score > 0.1:
        return Signal.BUY
    if score < -0.5:
        return Signal.STRONG_SELL
    if score < -0.1:
        return Signal.SELL
    return Signal.NEUTRAL


def position_vs_sma(price: float | None, sma: float | None) -> Trend:
    if price is None or sma is None or price <= 0 or sma <= 0:
        return Trend.NO_DATA
    return Trend.ABOVE if price > sma else Trend.BELOW


def distance_pct(price: float | None, reference: float | None) -> float | None:
    if price is None or reference is None or reference <= 0:
        return None
    return (price / reference - 1.0) * 100.0


def classic_pivots(high: float | None, low: float | None, close: float | None) -> PivotLevels | None:
    if high is None or low is None or close is None:
        return None
    if high < low:
        return None
    pp = (high + low + close) / 3.0
    return PivotLevels(
        pp=pp,
        r1=2 * pp - low,
        s1=2 * pp - high,
        r2=pp + (high - low),
        s2=pp - (high - low),
        r3=high + 2 * (pp - low),
        s3=low - 2 * (high - pp),
    )
