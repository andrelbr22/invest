from __future__ import annotations

from ..models.valuation import ValuationResult


def implied_dividend_per_share(price: float | None, dividend_yield_pct: float | None) -> float | None:
    if price is None or dividend_yield_pct is None or price < 0:
        return None
    return price * dividend_yield_pct / 100.0


def dividend_yield_target_price(
    dividend_per_share: float | None,
    target_yield_pct: float = 6.0,
) -> ValuationResult:
    """Price ceiling from annual dividend and an explicit target yield.

    The historical method id is retained for stored snapshots and clients.
    Presentation should use the canonical metadata from ``catalog.py`` rather
    than attributing this one-period calculation to Barsi or Bazin.
    """
    if dividend_per_share is None:
        return ValuationResult(method="dividend_yield_target", value=None, valid=False, reason="missing_dividend")
    if target_yield_pct <= 0:
        return ValuationResult(method="dividend_yield_target", value=None, valid=False, reason="invalid_target_yield")
    return ValuationResult(method="dividend_yield_target", value=dividend_per_share / (target_yield_pct / 100.0))
