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
        "daily_trend": {"enabled": False, "direction": "up", "period": 21, "mode": "price_above", "slope_lookback": 5},
        "weekly_trend": {"enabled": False, "direction": "up", "period": 21, "mode": "price_above", "slope_lookback": 4},
        "monthly_trend": {"enabled": False, "direction": "up", "period": 21, "mode": "price_above", "slope_lookback": 3},
        "trend_combination": "all",
        "adx_min": None,
        "volume_ratio_min": None,
        "rsi_min": None,
        "rsi_max": None,
        "atr_pct_min": None,
        "atr_pct_max": None,
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
            period = int(base.get("period", 21))
            base["period"] = 50 if period == 50 else 21
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
    return out


def filters_active(config: dict | None) -> bool:
    cfg = normalize_filter_config(config)
    if any(cfg[x]["enabled"] for x in ("daily_trend", "weekly_trend", "monthly_trend")):
        return True
    if any(cfg.get(x) is not None for x in ("adx_min", "volume_ratio_min", "rsi_min", "rsi_max", "atr_pct_min", "atr_pct_max")):
        return True
    return bool(cfg["fundamental_entry"] or cfg["fundamental_exit"])


def _completed_period_sma(price: pd.Series, period: int, kind: str) -> pd.Series:
    if kind == "daily":
        return price.rolling(period, min_periods=period).mean()
    naive_index = price.index.tz_convert(None) if getattr(price.index, "tz", None) is not None else price.index
    labels = naive_index.to_period("W-FRI" if kind == "weekly" else "M")
    grouped = price.groupby(labels)
    closes = grouped.last()
    last_dates = grouped.apply(lambda s: s.index.max())
    sma = closes.rolling(period, min_periods=period).mean()
    anchors = pd.Series(sma.to_numpy(), index=pd.DatetimeIndex(list(last_dates)))
    union = price.index.union(anchors.index).sort_values()
    return anchors.reindex(union).ffill().reindex(price.index)


def _completed_period_sma_previous(price: pd.Series, period: int, kind: str, lookback: int) -> pd.Series:
    if kind == "daily":
        return _completed_period_sma(price, period, kind).shift(lookback)
    naive_index = price.index.tz_convert(None) if getattr(price.index, "tz", None) is not None else price.index
    labels = naive_index.to_period("W-FRI" if kind == "weekly" else "M")
    grouped = price.groupby(labels)
    closes = grouped.last()
    last_dates = grouped.apply(lambda s: s.index.max())
    previous = closes.rolling(period, min_periods=period).mean().shift(lookback)
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
        ma = _completed_period_sma(price, int(rule["period"]), kind)
        previous_ma = _completed_period_sma_previous(price, int(rule["period"]), kind, int(rule["slope_lookback"]))
        col = f"Filtro SMA {rule['period']} {kind}"
        indicators[col] = ma
        passed, valid, slope = _trend_condition(
            price, ma, previous_ma, mode=rule["mode"], direction=rule["direction"]
        )
        indicators[f"{col} inclinação"] = slope
        trend_conditions.append(passed)
        trend_labels.append(label)
        diagnostics["conditions"][label] = {
            "period": int(rule["period"]), "direction": rule["direction"], "mode": rule["mode"],
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
        avg = volume.rolling(20, min_periods=20).mean()
        ratio = volume / avg.mask(lambda x: x == 0)
        indicators["Filtro volume / média20"] = ratio
        passed = ratio.notna() & (ratio >= float(cfg["volume_ratio_min"]))
        gate &= passed
        diagnostics["conditions"]["Volume"] = {"min_ratio": float(cfg["volume_ratio_min"]), "bars_pass": int(passed.sum()), "bars_valid": int(ratio.notna().sum())}

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
    if any(cfg.get(x) is not None for x in ("adx_min", "volume_ratio_min", "rsi_min", "rsi_max", "atr_pct_min", "atr_pct_max")):
        days = max(days, 90)
    return days
