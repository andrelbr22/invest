from __future__ import annotations
from typing import Any
from ..models.strategy import StockFilterSet, FiiFilterSet


def _min_ok(value: float | None, threshold: float | None) -> bool:
    return True if threshold is None else value is not None and value >= threshold


def _max_ok(value: float | None, threshold: float | None) -> bool:
    return True if threshold is None else value is not None and value <= threshold


def stock_passes(data: dict[str, Any], f: StockFilterSet) -> bool:
    checks = [
        _min_ok(data.get("roe_pct"), f.roe_min),
        _min_ok(data.get("net_margin_pct"), f.net_margin_min),
        _min_ok(data.get("ebit_margin_pct"), f.ebit_margin_min),
        _min_ok(data.get("revenue_cagr_5y_pct"), f.revenue_cagr_5y_min),
        _min_ok(data.get("pe"), f.pe_min),
        _max_ok(data.get("pe"), f.pe_max),
        _max_ok(data.get("pbv"), f.pbv_max),
        _min_ok(data.get("dividend_yield_pct"), f.dividend_yield_min),
        _max_ok(data.get("ev_ebitda"), f.ev_ebitda_max),
        _max_ok(data.get("gross_debt_to_equity"), f.gross_debt_to_equity_max),
        _min_ok(data.get("current_ratio"), f.current_ratio_min),
        _min_ok(data.get("daily_liquidity"), f.daily_liquidity_min),
    ]
    if f.require_below_graham:
        price = data.get("price")
        graham = data.get("graham_number")
        checks.append(price is not None and graham is not None and price < graham)
    return all(checks)


def fii_passes(data: dict[str, Any], f: FiiFilterSet) -> bool:
    checks = [
        _max_ok(data.get("pbv"), f.pbv_max),
        _min_ok(data.get("dividend_yield_pct"), f.dividend_yield_min),
        _min_ok(data.get("ffo_yield_pct"), f.ffo_yield_min),
        _min_ok(data.get("cap_rate_pct"), f.cap_rate_min),
        _max_ok(data.get("vacancy_pct"), f.vacancy_max),
        _min_ok(data.get("daily_liquidity"), f.daily_liquidity_min),
    ]
    if f.require_below_dividend_target:
        price = data.get("price")
        ceiling = data.get("dividend_target_price")
        checks.append(price is not None and ceiling is not None and price < ceiling)
    return all(checks)
