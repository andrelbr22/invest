from __future__ import annotations

from itertools import product

from .strategies import STRATEGIES


OFFICIAL_GRID_VERSION = "1.0"
DEFAULT_MAX_COMBINATIONS = 200


def _trend(enabled=False, period=21, mode="sma_rising", slope_lookback=5):
    return {"enabled": enabled, "period": period, "mode": mode, "slope_lookback": slope_lookback}


def official_filter_presets() -> list[dict]:
    empty = {
        "daily_trend": _trend(), "weekly_trend": _trend(slope_lookback=4),
        "monthly_trend": _trend(slope_lookback=3), "trend_combination": "all",
    }
    return [
        empty,
        {**empty, "daily_trend": _trend(True, 21, "sma_rising", 5)},
        {**empty, "weekly_trend": _trend(True, 21, "sma_rising", 4)},
        {**empty, "monthly_trend": _trend(True, 21, "sma_rising", 3)},
        {**empty, "weekly_trend": _trend(True, 21, "sma_rising", 4), "monthly_trend": _trend(True, 21, "sma_rising", 3), "trend_combination": "all"},
        {**empty, "weekly_trend": _trend(True, 21, "sma_rising", 4), "monthly_trend": _trend(True, 21, "sma_rising", 3), "trend_combination": "any"},
        {**empty, "daily_trend": _trend(True, 21, "sma_rising", 5), "weekly_trend": _trend(True, 21, "sma_rising", 4), "monthly_trend": _trend(True, 21, "sma_rising", 3), "trend_combination": "majority"},
        {**empty, "daily_trend": _trend(True, 50, "price_above_or_sma_rising", 10)},
        {**empty, "weekly_trend": _trend(True, 50, "price_above_and_sma_rising", 4)},
        {**empty, "adx_min": 25.0},
        {**empty, "volume_ratio_min": 1.0},
    ]


def strategy_parameter_variants() -> dict[str, list[dict]]:
    variants = {sid: [dict(definition.default_params)] for sid, definition in STRATEGIES.items()}
    variants["custom_ma_cross"] = [
        {"fast_period": fast, "slow_period": slow, "fast_type": fast_type, "slow_type": "sma"}
        for fast, slow, fast_type in product((5, 9, 20), (21, 40, 50, 100, 200), ("ema", "sma"))
        if fast < slow
    ]
    variants["bollinger_rsi_trend"] = [
        {
            "period": 20, "stddev": stddev, "rsi_period": 14, "entry_rsi": entry,
            "exit_rsi": exit_rsi, "trend_period": 200, "trend_filter_mode": mode,
            "trend_slope_lookback": 20, "band_trigger": trigger,
        }
        for stddev, entry, exit_rsi, mode, trigger in product(
            (1.5, 2.0, 2.5), (30, 35), (50, 55),
            ("none", "price_above", "sma_rising", "price_above_or_sma_rising", "price_above_and_sma_rising"),
            ("close", "low_touch", "close_reentry"),
        )
    ]
    return variants


def official_grid(limit: int = DEFAULT_MAX_COMBINATIONS) -> list[dict]:
    """Return a deterministic, balanced finite grid across every strategy family."""
    maximum = max(1, min(int(limit), DEFAULT_MAX_COMBINATIONS))
    variants = strategy_parameter_variants()
    filters = official_filter_presets()
    candidates: dict[str, list[dict]] = {}
    for sid, parameter_rows in variants.items():
        candidates[sid] = [
            {"strategy_id": sid, "params": params, "filters": filter_config, "grid_version": OFFICIAL_GRID_VERSION}
            for filter_config in filters for params in parameter_rows
        ]
    result = []
    strategy_ids = list(STRATEGIES)
    cursor = 0
    while len(result) < maximum:
        added = False
        for sid in strategy_ids:
            rows = candidates[sid]
            if cursor < len(rows):
                result.append(rows[cursor])
                added = True
                if len(result) >= maximum:
                    break
        if not added:
            break
        cursor += 1
    return result
