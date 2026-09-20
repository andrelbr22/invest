from __future__ import annotations

from datetime import datetime
import math
import pandas as pd

from .strategies import _ma, _rsi


FUNDAMENTAL_FIELDS = {
    "pe", "pbv", "dividend_yield_pct", "ev_ebitda", "ebit_margin_pct", "net_margin_pct",
    "current_ratio", "roe_pct", "roic_pct", "gross_debt_to_equity", "net_debt_to_ebitda",
    "revenue_cagr_5y_pct", "earnings_cagr_5y_pct", "ffo_yield_pct", "cap_rate_pct",
    "vacancy_pct", "financial_vacancy_pct", "ltv_pct", "wale_years", "daily_liquidity",
}


def default_filter_config() -> dict:
    return {
        "daily_trend": {"enabled": False, "direction": "up", "ma_type": "sma", "period": 21, "mode": "price_above", "slope_lookback": 5},
        "weekly_trend": {"enabled": False, "direction": "up", "ma_type": "sma", "period": 21, "mode": "price_above", "slope_lookback": 4},
        "monthly_trend": {"enabled": False, "direction": "up", "ma_type": "sma", "period": 21, "mode": "price_above", "slope_lookback": 3},
        "trend_combination": "all",
        "adx_min": None,
        "volume_ratio_min": None,
        "volume_period": 20,
        "volume_timeframe": "daily",
        "rsi_min": None,
        "rsi_max": None,
        "atr_pct_min": None,
        "atr_pct_max": None,
        "macd_condition": "any",
        "bollinger_percent_b_min": None,
        "bollinger_percent_b_max": None,
        "bollinger_bandwidth_min": None,
        "bollinger_bandwidth_max": None,
        "relative_strength_min": None,
        "relative_strength_lookback": 126,
        "pivot_zone": "any",
        "near_pivot_level": "none",
        "pivot_tolerance_pct": 0.5,
        "daily_liquidity_min": None,
        "exit_on_filter_failure": False,
        "fundamental_entry": {},
        "fundamental_exit": {},
        "fundamental_exit_logic": "any",
        "fundamental_min_coverage_pct": 70.0,
        "fundamental_max_age_days": 45,
    }


def normalize_filter_config(config: dict | None) -> dict:
    out = default_filter_config()
    config = config or {}
    for key, value in config.items():
        if key in {"daily_trend", "weekly_trend", "monthly_trend"}:
            base = dict(out[key]); base.update(value or {})
            base["enabled"] = bool(base.get("enabled", False))
            base["direction"] = "down" if str(base.get("direction", "up")).lower() == "down" else "up"
            ma_type = "ema" if str(base.get("ma_type", "sma")).lower() == "ema" else "sma"
            period = int(base.get("period", 21))
            allowed_pairs = {("sma", 8), ("ema", 9), ("sma", 21), ("sma", 50), ("sma", 200)}
            if (ma_type, period) not in allowed_pairs:
                ma_type, period = "sma", 21
            base["ma_type"], base["period"] = ma_type, period
            mode = str(base.get("mode", "price_above")).lower()
            allowed_modes = {"price_above", "sma_rising", "price_above_or_sma_rising", "price_above_and_sma_rising"}
            base["mode"] = mode if mode in allowed_modes else "price_above"
            base["slope_lookback"] = max(1, min(100, int(base.get("slope_lookback", 5))))
            out[key] = base
        elif key in out:
            out[key] = value
    out["fundamental_entry"] = {k: v for k, v in (out.get("fundamental_entry") or {}).items() if k in FUNDAMENTAL_FIELDS and v}
    out["fundamental_exit"] = {k: v for k, v in (out.get("fundamental_exit") or {}).items() if k in FUNDAMENTAL_FIELDS and v}
    out["fundamental_exit_logic"] = "all" if str(out.get("fundamental_exit_logic")).lower() == "all" else "any"
    combination = str(out.get("trend_combination", "all")).lower()
    out["trend_combination"] = combination if combination in {"all", "any", "majority"} else "all"
    out["fundamental_min_coverage_pct"] = float(out.get("fundamental_min_coverage_pct") or 70.0)
    out["fundamental_max_age_days"] = max(1, int(out.get("fundamental_max_age_days") or 45))
    out["volume_period"] = int(out.get("volume_period") or 20)
    if out["volume_period"] not in {9, 20, 50}:
        out["volume_period"] = 20
    timeframe = str(out.get("volume_timeframe") or "daily").lower()
    out["volume_timeframe"] = timeframe if timeframe in {"daily", "weekly", "monthly"} else "daily"
    macd = str(out.get("macd_condition") or "any").lower()
    out["macd_condition"] = macd if macd in {"any", "above", "below", "cross_up", "cross_down"} else "any"
    out["relative_strength_lookback"] = max(20, min(504, int(out.get("relative_strength_lookback") or 126)))
    zone = str(out.get("pivot_zone") or "any").lower()
    out["pivot_zone"] = zone if zone in {"any", "below_s3", "s3_s2", "s2_s1", "s1_pp", "pp_r1", "r1_r2", "r2_r3", "above_r3"} else "any"
    level = str(out.get("near_pivot_level") or "none").lower()
    out["near_pivot_level"] = level if level in {"none", "s3", "s2", "s1", "pp", "r1", "r2", "r3"} else "none"
    out["pivot_tolerance_pct"] = max(0.0, min(20.0, float(out.get("pivot_tolerance_pct") or 0.5)))
    return out


def filters_active(config: dict | None) -> bool:
    cfg = normalize_filter_config(config)
    if any(cfg[x]["enabled"] for x in ("daily_trend", "weekly_trend", "monthly_trend")):
        return True
    if any(cfg.get(x) is not None for x in (
        "adx_min", "volume_ratio_min", "rsi_min", "rsi_max", "atr_pct_min", "atr_pct_max",
        "bollinger_percent_b_min", "bollinger_percent_b_max", "bollinger_bandwidth_min",
        "bollinger_bandwidth_max", "relative_strength_min", "daily_liquidity_min",
    )):
        return True
    if cfg.get("macd_condition") != "any" or cfg.get("pivot_zone") != "any" or cfg.get("near_pivot_level") != "none":
        return True
    return bool(cfg["fundamental_entry"] or cfg["fundamental_exit"])


def _moving_average(price: pd.Series, period: int, ma_type: str) -> pd.Series:
    if ma_type == "ema":
        return price.ewm(span=period, adjust=False, min_periods=period).mean()
    return price.rolling(period, min_periods=period).mean()


def _completed_period_ma(price: pd.Series, period: int, kind: str, ma_type: str) -> pd.Series:
    if kind == "daily":
        return _moving_average(price, period, ma_type)
    naive_index = price.index.tz_convert(None) if getattr(price.index, "tz", None) is not None else price.index
    labels = naive_index.to_period("W-FRI" if kind == "weekly" else "M")
    grouped = price.groupby(labels)
    closes = grouped.last()
    last_dates = grouped.apply(lambda s: s.index.max())
    average = _moving_average(closes, period, ma_type)
    anchors = pd.Series(average.to_numpy(), index=pd.DatetimeIndex(list(last_dates)))
    union = price.index.union(anchors.index).sort_values()
    return anchors.reindex(union).ffill().reindex(price.index)


def _completed_period_ma_previous(price: pd.Series, period: int, kind: str, lookback: int, ma_type: str) -> pd.Series:
    if kind == "daily":
        return _completed_period_ma(price, period, kind, ma_type).shift(lookback)
    naive_index = price.index.tz_convert(None) if getattr(price.index, "tz", None) is not None else price.index
    labels = naive_index.to_period("W-FRI" if kind == "weekly" else "M")
    grouped = price.groupby(labels)
    closes = grouped.last()
    last_dates = grouped.apply(lambda s: s.index.max())
    previous = _moving_average(closes, period, ma_type).shift(lookback)
    anchors = pd.Series(previous.to_numpy(), index=pd.DatetimeIndex(list(last_dates)))
    union = price.index.union(anchors.index).sort_values()
    return anchors.reindex(union).ffill().reindex(price.index)


def _trend_condition(price: pd.Series, ma: pd.Series, previous_ma: pd.Series, *, mode: str, direction: str) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return condition, validity and SMA slope without using future observations."""
    slope = ma - previous_ma
    if direction == "down":
        price_ok = price < ma
        slope_ok = slope < 0
    else:
        price_ok = price > ma
        slope_ok = slope > 0
    if mode == "sma_rising":
        passed = slope_ok
        valid = ma.notna() & previous_ma.notna()
    elif mode == "price_above_or_sma_rising":
        passed = price_ok | slope_ok
        valid = ma.notna() & previous_ma.notna()
    elif mode == "price_above_and_sma_rising":
        passed = price_ok & slope_ok
        valid = ma.notna() & previous_ma.notna()
    else:
        passed = price_ok
        valid = ma.notna()
    return passed & valid, valid, slope


def _combine_trends(conditions: list[pd.Series], logic: str, index: pd.Index) -> pd.Series:
    if not conditions:
        return pd.Series(True, index=index, dtype=bool)
    votes = pd.concat(conditions, axis=1).fillna(False).sum(axis=1)
    count = len(conditions)
    if logic == "any":
        required = 1
    elif logic == "majority":
        required = 2 if count in {2, 3} else 1
    else:
        required = count
    return votes >= required


def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _atr_adx(df: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series]:
    high = pd.to_numeric(df.get("adj_high", df.get("high")), errors="coerce")
    low = pd.to_numeric(df.get("adj_low", df.get("low")), errors="coerce")
    close = pd.to_numeric(df["price"], errors="coerce")
    prev_close = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = _wilder(tr, period)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    smooth_tr = _wilder(tr, period)
    plus_di = 100 * _wilder(plus_dm, period) / smooth_tr.mask(lambda x: x == 0)
    minus_di = 100 * _wilder(minus_dm, period) / smooth_tr.mask(lambda x: x == 0)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).mask(lambda x: x == 0)
    adx = _wilder(dx, period)
    return atr, adx


def _volume_ratio(volume: pd.Series, *, period: int, timeframe: str) -> pd.Series:
    """Point-in-time volume relative to prior completed periods."""
    values = pd.to_numeric(volume, errors="coerce")
    if timeframe == "daily":
        average = values.rolling(period, min_periods=period).mean().shift(1)
        return values / average.mask(lambda item: item == 0)

    naive_index = values.index.tz_convert(None) if getattr(values.index, "tz", None) is not None else values.index
    labels = naive_index.to_period("W-FRI" if timeframe == "weekly" else "M")
    grouped = values.groupby(labels)
    totals = grouped.sum(min_count=1)
    last_dates = grouped.apply(lambda series: series.index.max())
    # The last week/month can still be in progress. Exclude it so the filter
    # never compares an incomplete period with completed historical periods.
    if len(totals) > 0:
        totals = totals.iloc[:-1]
        last_dates = last_dates.iloc[:-1]
    average = totals.rolling(period, min_periods=period).mean().shift(1)
    ratio = totals / average.mask(lambda item: item == 0)
    anchors = pd.Series(ratio.to_numpy(), index=pd.DatetimeIndex(list(last_dates)))
    union = values.index.union(anchors.index).sort_values()
    return anchors.reindex(union).ffill().reindex(values.index)


def _classic_pivots(df: pd.DataFrame, price: pd.Series) -> dict[str, pd.Series]:
    high = pd.to_numeric(df.get("adj_high", df.get("high", price)), errors="coerce").shift(1)
    low = pd.to_numeric(df.get("adj_low", df.get("low", price)), errors="coerce").shift(1)
    close = price.shift(1)
    pp = (high + low + close) / 3.0
    return {
        "pp": pp,
        "r1": 2.0 * pp - low,
        "s1": 2.0 * pp - high,
        "r2": pp + (high - low),
        "s2": pp - (high - low),
        "r3": high + 2.0 * (pp - low),
        "s3": low - 2.0 * (high - pp),
    }


def _pivot_zone_gate(price: pd.Series, pivots: dict[str, pd.Series], zone: str) -> pd.Series:
    p = price
    if zone == "below_s3": return p < pivots["s3"]
    if zone == "s3_s2": return (p >= pivots["s3"]) & (p < pivots["s2"])
    if zone == "s2_s1": return (p >= pivots["s2"]) & (p < pivots["s1"])
    if zone == "s1_pp": return (p >= pivots["s1"]) & (p < pivots["pp"])
    if zone == "pp_r1": return (p >= pivots["pp"]) & (p < pivots["r1"])
    if zone == "r1_r2": return (p >= pivots["r1"]) & (p < pivots["r2"])
    if zone == "r2_r3": return (p >= pivots["r2"]) & (p < pivots["r3"])
    if zone == "above_r3": return p >= pivots["r3"]
    return pd.Series(True, index=price.index, dtype=bool)


def build_fundamental_context(index: pd.DatetimeIndex, snapshots: list[dict] | None, *, max_age_days: int) -> pd.DataFrame:
    out = pd.DataFrame(index=index)
    snapshots = snapshots or []
    if not snapshots:
        return out
    rows = []
    for item in snapshots:
        ref = pd.Timestamp(item.get("reference_date"))
        if ref.tzinfo is None: ref = ref.tz_localize("UTC")
        else: ref = ref.tz_convert("UTC")
        row = {"reference_date": ref}
        for field in FUNDAMENTAL_FIELDS:
            row[field] = item.get(field)
        rows.append(row)
    snap = pd.DataFrame(rows).sort_values("reference_date").drop_duplicates("reference_date", keep="last")
    left = pd.DataFrame({"timestamp": index}).sort_values("timestamp")
    merged = pd.merge_asof(left, snap, left_on="timestamp", right_on="reference_date", direction="backward")
    age = (merged["timestamp"] - merged["reference_date"]).dt.total_seconds() / 86400.0
    stale = age > max_age_days
    for field in FUNDAMENTAL_FIELDS:
        if field in merged:
            merged.loc[stale, field] = pd.NA
    merged.index = index
    return merged


def _range_pass(series: pd.Series, rule: dict) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    ok = values.notna()
    if rule.get("min") is not None:
        ok &= values >= float(rule["min"])
    if rule.get("max") is not None:
        ok &= values <= float(rule["max"])
    return ok


def _entry_exit_state(base_signal: pd.Series, entry_gate: pd.Series, exit_trigger: pd.Series, *, exit_on_filter_failure: bool) -> pd.Series:
    state = 0
    out = []
    for base, gate, forced_exit in zip(base_signal, entry_gate.fillna(False), exit_trigger.fillna(False)):
        if pd.isna(base):
            out.append(float("nan")); continue
        base = int(float(base) > 0)
        if state == 0:
            if base == 1 and bool(gate):
                state = 1
        else:
            if base == 0 or bool(forced_exit) or (exit_on_filter_failure and not bool(gate)):
                state = 0
        out.append(float(state))
    return pd.Series(out, index=base_signal.index, dtype=float)


def apply_backtest_filters(
    df: pd.DataFrame,
    base_signal: pd.Series,
    config: dict | None,
    *,
    requested_start: datetime,
    requested_end: datetime,
    fundamental_snapshots: list[dict] | None = None,
    benchmark_price: pd.Series | None = None,
) -> tuple[pd.Series, pd.DataFrame, dict, dict]:
    cfg = normalize_filter_config(config)
    if not filters_active(cfg) and not cfg.get("exit_on_filter_failure"):
        return base_signal, pd.DataFrame(index=df.index), cfg, {"active": False}

    price = pd.to_numeric(df["price"], errors="coerce")
    indicators = pd.DataFrame(index=df.index)
    gate = pd.Series(True, index=df.index, dtype=bool)
    diagnostics = {"active": True, "conditions": {}}
    raw_prev = base_signal.fillna(0).shift(1).fillna(0)
    raw_candidates = (base_signal.fillna(0) > 0) & (raw_prev <= 0)
    trend_conditions = []
    trend_labels = []

    for key, label, kind in (
        ("daily_trend", "Tendência diária", "daily"),
        ("weekly_trend", "Tendência semanal", "weekly"),
        ("monthly_trend", "Tendência mensal", "monthly"),
    ):
        rule = cfg[key]
        if not rule["enabled"]:
            continue
        ma_type = str(rule.get("ma_type") or "sma")
        ma = _completed_period_ma(price, int(rule["period"]), kind, ma_type)
        previous_ma = _completed_period_ma_previous(price, int(rule["period"]), kind, int(rule["slope_lookback"]), ma_type)
        col = f"Filtro {ma_type.upper()} {rule['period']} {kind}"
        indicators[col] = ma
        passed, valid, slope = _trend_condition(
            price, ma, previous_ma, mode=rule["mode"], direction=rule["direction"]
        )
        indicators[f"{col} inclinação"] = slope
        trend_conditions.append(passed)
        trend_labels.append(label)
        diagnostics["conditions"][label] = {
            "ma_type": ma_type, "period": int(rule["period"]), "direction": rule["direction"], "mode": rule["mode"],
            "slope_lookback": int(rule["slope_lookback"]), "bars_pass": int(passed.sum()),
            "bars_valid": int(valid.sum()), "candidate_signals": int(raw_candidates.sum()),
            "signals_blocked": int((raw_candidates & ~passed).sum()),
        }

    if trend_conditions:
        trend_gate = _combine_trends(trend_conditions, cfg["trend_combination"], df.index)
        gate &= trend_gate
        diagnostics["trend_combination"] = {
            "logic": cfg["trend_combination"], "active_timeframes": trend_labels,
            "candidate_signals": int(raw_candidates.sum()),
            "signals_passed": int((raw_candidates & trend_gate).sum()),
            "signals_blocked": int((raw_candidates & ~trend_gate).sum()),
        }

    atr = adx = None
    if cfg.get("adx_min") is not None or cfg.get("atr_pct_min") is not None or cfg.get("atr_pct_max") is not None:
        atr, adx = _atr_adx(df, 14)
    if cfg.get("adx_min") is not None:
        indicators["Filtro ADX 14"] = adx
        passed = adx.notna() & (adx >= float(cfg["adx_min"]))
        gate &= passed
        diagnostics["conditions"]["ADX"] = {"min": float(cfg["adx_min"]), "bars_pass": int(passed.sum()), "bars_valid": int(adx.notna().sum())}

    if cfg.get("volume_ratio_min") is not None:
        volume = pd.to_numeric(df.get("volume"), errors="coerce")
        ratio = _volume_ratio(
            volume, period=int(cfg["volume_period"]), timeframe=str(cfg["volume_timeframe"]),
        )
        indicators[f"Filtro volume {cfg['volume_timeframe']} / média {cfg['volume_period']}"] = ratio
        passed = ratio.notna() & (ratio >= float(cfg["volume_ratio_min"]))
        gate &= passed
        diagnostics["conditions"]["Volume"] = {
            "min_ratio": float(cfg["volume_ratio_min"]), "period": int(cfg["volume_period"]),
            "timeframe": cfg["volume_timeframe"], "bars_pass": int(passed.sum()),
            "bars_valid": int(ratio.notna().sum()),
        }

    if cfg.get("rsi_min") is not None or cfg.get("rsi_max") is not None:
        rsi = _rsi(price, 14)
        indicators["Filtro RSI 14"] = rsi
        passed = rsi.notna()
        if cfg.get("rsi_min") is not None: passed &= rsi >= float(cfg["rsi_min"])
        if cfg.get("rsi_max") is not None: passed &= rsi <= float(cfg["rsi_max"])
        gate &= passed
        diagnostics["conditions"]["RSI"] = {"min": cfg.get("rsi_min"), "max": cfg.get("rsi_max"), "bars_pass": int(passed.sum()), "bars_valid": int(rsi.notna().sum())}

    if cfg.get("atr_pct_min") is not None or cfg.get("atr_pct_max") is not None:
        atr_pct = atr / price.mask(lambda x: x == 0) * 100.0
        indicators["Filtro ATR 14 %"] = atr_pct
        passed = atr_pct.notna()
        if cfg.get("atr_pct_min") is not None: passed &= atr_pct >= float(cfg["atr_pct_min"])
        if cfg.get("atr_pct_max") is not None: passed &= atr_pct <= float(cfg["atr_pct_max"])
        gate &= passed
        diagnostics["conditions"]["ATR %"] = {"min": cfg.get("atr_pct_min"), "max": cfg.get("atr_pct_max"), "bars_pass": int(passed.sum()), "bars_valid": int(atr_pct.notna().sum())}

    if cfg.get("macd_condition") != "any":
        ema_fast = _ma(price, 12, "ema")
        ema_slow = _ma(price, 26, "ema")
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
        difference = macd - macd_signal
        condition = cfg["macd_condition"]
        if condition == "above": passed = difference > 0
        elif condition == "below": passed = difference < 0
        elif condition == "cross_up": passed = (difference > 0) & (difference.shift(1) <= 0)
        else: passed = (difference < 0) & (difference.shift(1) >= 0)
        passed &= difference.notna()
        indicators["Filtro MACD"] = macd
        indicators["Filtro sinal MACD"] = macd_signal
        gate &= passed
        diagnostics["conditions"]["MACD"] = {
            "condition": condition, "bars_pass": int(passed.sum()), "bars_valid": int(difference.notna().sum()),
        }

    bollinger_requested = any(cfg.get(key) is not None for key in (
        "bollinger_percent_b_min", "bollinger_percent_b_max",
        "bollinger_bandwidth_min", "bollinger_bandwidth_max",
    ))
    if bollinger_requested:
        middle = price.rolling(20, min_periods=20).mean()
        deviation = price.rolling(20, min_periods=20).std(ddof=0)
        upper = middle + 2.0 * deviation
        lower = middle - 2.0 * deviation
        width = upper - lower
        percent_b = (price - lower) / width.mask(lambda value: value == 0)
        bandwidth = width / middle.mask(lambda value: value == 0) * 100.0
        passed = percent_b.notna() & bandwidth.notna()
        for key, series in (("bollinger_percent_b", percent_b), ("bollinger_bandwidth", bandwidth)):
            minimum, maximum = cfg.get(f"{key}_min"), cfg.get(f"{key}_max")
            if minimum is not None: passed &= series >= float(minimum)
            if maximum is not None: passed &= series <= float(maximum)
        indicators["Filtro Bollinger %B"] = percent_b
        indicators["Filtro Bollinger largura %"] = bandwidth
        gate &= passed
        diagnostics["conditions"]["Bollinger"] = {
            "percent_b_min": cfg.get("bollinger_percent_b_min"),
            "percent_b_max": cfg.get("bollinger_percent_b_max"),
            "bandwidth_min": cfg.get("bollinger_bandwidth_min"),
            "bandwidth_max": cfg.get("bollinger_bandwidth_max"),
            "bars_pass": int(passed.sum()),
        }

    if cfg.get("relative_strength_min") is not None:
        if benchmark_price is None:
            raise ValueError("benchmark_history_required_for_relative_strength")
        benchmark = pd.to_numeric(benchmark_price, errors="coerce").reindex(price.index).ffill()
        lookback = int(cfg["relative_strength_lookback"])
        asset_return = price / price.shift(lookback) - 1.0
        benchmark_return = benchmark / benchmark.shift(lookback) - 1.0
        relative = (asset_return - benchmark_return) * 100.0
        passed = relative.notna() & (relative >= float(cfg["relative_strength_min"]))
        indicators[f"Força relativa {lookback} pregões %"] = relative
        gate &= passed
        diagnostics["conditions"]["Força relativa"] = {
            "minimum_pct": float(cfg["relative_strength_min"]), "lookback": lookback,
            "bars_pass": int(passed.sum()), "bars_valid": int(relative.notna().sum()),
        }

    if cfg.get("daily_liquidity_min") is not None:
        volume = pd.to_numeric(df.get("volume"), errors="coerce")
        traded_value = price * volume
        average_liquidity = traded_value.rolling(20, min_periods=20).mean()
        passed = average_liquidity.notna() & (average_liquidity >= float(cfg["daily_liquidity_min"]))
        indicators["Liquidez financeira média 20"] = average_liquidity
        gate &= passed
        diagnostics["conditions"]["Liquidez"] = {
            "minimum": float(cfg["daily_liquidity_min"]), "bars_pass": int(passed.sum()),
            "bars_valid": int(average_liquidity.notna().sum()),
        }

    if cfg.get("pivot_zone") != "any" or cfg.get("near_pivot_level") != "none":
        pivots = _classic_pivots(df, price)
        for key, series in pivots.items():
            indicators[f"Pivô {key.upper()}"] = series
        passed = pd.Series(True, index=df.index, dtype=bool)
        if cfg.get("pivot_zone") != "any":
            passed &= _pivot_zone_gate(price, pivots, cfg["pivot_zone"])
        level = cfg.get("near_pivot_level")
        if level != "none":
            reference = pivots[level]
            tolerance = float(cfg.get("pivot_tolerance_pct") or 0.5) / 100.0
            passed &= reference.notna() & (reference != 0) & ((price / reference - 1.0).abs() <= tolerance)
        gate &= passed
        diagnostics["conditions"]["Pivô"] = {
            "zone": cfg.get("pivot_zone"), "near": level,
            "tolerance_pct": cfg.get("pivot_tolerance_pct"), "bars_pass": int(passed.sum()),
        }

    fundamental_entry = cfg.get("fundamental_entry") or {}
    fundamental_exit = cfg.get("fundamental_exit") or {}
    exit_trigger = pd.Series(False, index=df.index, dtype=bool)
    if fundamental_entry or fundamental_exit:
        fctx = build_fundamental_context(df.index, fundamental_snapshots, max_age_days=cfg["fundamental_max_age_days"])
        required = sorted(set(fundamental_entry) | set(fundamental_exit))
        start = pd.Timestamp(requested_start); end = pd.Timestamp(requested_end)
        if start.tzinfo is None: start = start.tz_localize("UTC")
        else: start = start.tz_convert("UTC")
        if end.tzinfo is None: end = end.tz_localize("UTC")
        else: end = end.tz_convert("UTC")
        mask = (df.index >= start) & (df.index <= end)
        coverage = {}
        for field in required:
            cov = float(fctx.loc[mask, field].notna().mean() * 100) if field in fctx and mask.sum() else 0.0
            coverage[field] = round(cov, 2)
        diagnostics["fundamental_coverage_pct"] = coverage
        diagnostics["fundamental_snapshots"] = len(fundamental_snapshots or [])
        min_cov = float(cfg["fundamental_min_coverage_pct"])
        if len(fundamental_snapshots or []) < 5 or any(v < min_cov for v in coverage.values()):
            raise ValueError(
                "insufficient_point_in_time_fundamental_history: "
                f"mínimo {min_cov:.0f}% de cobertura e 5 snapshots; cobertura={coverage}. "
                "O filtro foi recusado para evitar look-ahead bias."
            )
        for field, rule in fundamental_entry.items():
            passed = _range_pass(fctx[field], rule)
            gate &= passed
            indicators[f"Fund. {field}"] = pd.to_numeric(fctx[field], errors="coerce")
            diagnostics["conditions"][f"Fundamental entrada: {field}"] = {**rule, "bars_pass": int(passed.sum()), "bars_valid": int(fctx[field].notna().sum())}
        if fundamental_exit:
            exit_conditions = []
            for field, rule in fundamental_exit.items():
                passed = _range_pass(fctx[field], rule)
                exit_conditions.append(passed)
                indicators[f"Fund. {field}"] = pd.to_numeric(fctx[field], errors="coerce")
                diagnostics["conditions"][f"Fundamental saída: {field}"] = {**rule, "bars_trigger": int(passed.sum()), "bars_valid": int(fctx[field].notna().sum())}
            if exit_conditions:
                exit_trigger = exit_conditions[0].copy()
                for cond in exit_conditions[1:]:
                    exit_trigger = (exit_trigger & cond) if cfg["fundamental_exit_logic"] == "all" else (exit_trigger | cond)

    filtered = _entry_exit_state(base_signal, gate, exit_trigger, exit_on_filter_failure=bool(cfg.get("exit_on_filter_failure")))
    diagnostics["entry_gate_pass_bars"] = int(gate.sum())
    diagnostics["raw_long_bars"] = int((base_signal.fillna(0) > 0).sum())
    diagnostics["filtered_long_bars"] = int((filtered.fillna(0) > 0).sum())
    fil_prev = filtered.fillna(0).shift(1).fillna(0)
    diagnostics["raw_entry_signals"] = int(((base_signal.fillna(0) > 0) & (raw_prev <= 0)).sum())
    diagnostics["filtered_entry_signals"] = int(((filtered.fillna(0) > 0) & (fil_prev <= 0)).sum())
    return filtered, indicators, cfg, diagnostics


def filter_warmup_calendar_days(config: dict | None) -> int:
    """Conservative calendar-day warm-up so multi-timeframe filters are formed before requested_start."""
    cfg = normalize_filter_config(config)
    days = 60
    multipliers = {"daily_trend": 2, "weekly_trend": 9, "monthly_trend": 32}
    for key, mult in multipliers.items():
        rule = cfg[key]
        if rule["enabled"]:
            days = max(days, int(rule["period"]) * mult + 30)
    if any(cfg.get(x) is not None for x in (
        "adx_min", "volume_ratio_min", "rsi_min", "rsi_max", "atr_pct_min", "atr_pct_max",
        "bollinger_percent_b_min", "bollinger_percent_b_max", "bollinger_bandwidth_min",
        "bollinger_bandwidth_max", "relative_strength_min", "daily_liquidity_min",
    )) or cfg.get("macd_condition") != "any" or cfg.get("pivot_zone") != "any" or cfg.get("near_pivot_level") != "none":
        days = max(days, 90)
    if cfg.get("relative_strength_min") is not None:
        days = max(days, int(cfg["relative_strength_lookback"]) * 2 + 30)
    if cfg.get("volume_ratio_min") is not None:
        multiplier = {"daily": 2, "weekly": 9, "monthly": 32}[cfg["volume_timeframe"]]
        days = max(days, int(cfg["volume_period"]) * multiplier + 30)
    return days
