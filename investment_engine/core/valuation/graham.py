from __future__ import annotations

import math
from ..models.valuation import ValuationResult


def implied_book_value_per_share(price: float | None, pbv: float | None) -> float | None:
    if price is None or pbv is None or pbv <= 0:
        return None
    return price / pbv


def implied_eps(price: float | None, pe: float | None) -> float | None:
    # A negative P/E carries information (loss); it must not be turned into EPS=0.
    if price is None or pe is None or pe == 0:
        return None
    return price / pe


def graham_number(eps: float | None, bvps: float | None, constant: float = 22.5) -> ValuationResult:
    if eps is None or bvps is None:
        return ValuationResult(method="graham_number", value=None, valid=False, reason="missing_inputs")
    if eps <= 0 or bvps <= 0:
        return ValuationResult(method="graham_number", value=None, valid=False, reason="requires_positive_eps_and_bvps")
    return ValuationResult(method="graham_number", value=math.sqrt(constant * eps * bvps))


def add_upside(result: ValuationResult, market_price: float | None) -> ValuationResult:
    if result.value is None or market_price is None or market_price <= 0:
        return result.model_copy(update={"upside_pct": None})
    upside = (result.value / market_price - 1.0) * 100.0
    return result.model_copy(update={"upside_pct": upside})
