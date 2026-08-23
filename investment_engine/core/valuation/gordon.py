from __future__ import annotations

from ..models.valuation import ValuationResult


def gordon_growth_value(
    dividend_per_share: float | None,
    required_return_pct: float,
    growth_pct: float,
) -> ValuationResult:
    """Stable-growth Dividend Discount Model (Gordon Growth).

    V0 = D1 / (k - g), where D1 = D0 * (1 + g).
    Rates are supplied in percentage points.
    """
    if dividend_per_share is None or dividend_per_share < 0:
        return ValuationResult(method="gordon_growth", value=None, valid=False, reason="missing_or_invalid_dividend")
    if required_return_pct <= 0:
        return ValuationResult(method="gordon_growth", value=None, valid=False, reason="invalid_required_return")
    if growth_pct < 0:
        return ValuationResult(method="gordon_growth", value=None, valid=False, reason="invalid_growth")
    if growth_pct >= required_return_pct:
        return ValuationResult(method="gordon_growth", value=None, valid=False, reason="growth_must_be_below_required_return")

    k = required_return_pct / 100.0
    g = growth_pct / 100.0
    d1 = dividend_per_share * (1.0 + g)
    return ValuationResult(method="gordon_growth", value=d1 / (k - g), version="1.0")


def price_ceiling_with_margin(value: float | None, margin_of_safety_pct: float = 20.0) -> ValuationResult:
    if value is None or value < 0:
        return ValuationResult(method="gordon_ddm_ceiling", value=None, valid=False, reason="missing_intrinsic_value")
    if margin_of_safety_pct < 0 or margin_of_safety_pct >= 100:
        return ValuationResult(method="gordon_ddm_ceiling", value=None, valid=False, reason="invalid_margin_of_safety")
    ceiling = value * (1.0 - margin_of_safety_pct / 100.0)
    return ValuationResult(method="gordon_ddm_ceiling", value=ceiling, version="1.0")
