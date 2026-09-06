from __future__ import annotations

from collections.abc import Mapping

from ..models.valuation import ValuationResult
from .catalog import valuation_method_metadata
from .results import ScenarioValuationResult, ValuationQuality, ValuationScenario, upside_pct


def _finite_number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


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


def gordon_growth_scenarios(
    dividend_per_share_d0: float | None,
    *,
    assumptions: Mapping[str, Mapping[str, float]] | None,
    market_price: float | None = None,
    margin_of_safety_pct: float | None = None,
    asset_type: str = "stock",
    asset_class: str = "default",
) -> ScenarioValuationResult:
    """Calculate explicit conservative/base/optimistic Gordon scenarios.

    No required return, growth or margin is silently supplied.  This prevents
    a single global assumption from being presented as an asset-specific fair
    value. ``dividend_per_share_d0`` is the last normalized annual dividend;
    each scenario converts it to D1 before discounting.
    """
    metadata = valuation_method_metadata("gordon_growth_ddm")
    price = _finite_number(market_price)
    if price is not None and price <= 0:
        price = None
    base = {
        "family_id": metadata.family_id,
        "method": metadata.canonical_id,
        "label": metadata.label,
        "asset_type": asset_type,
        "asset_class": asset_class,
        "market_price": price,
    }
    dividend = _finite_number(dividend_per_share_d0)
    if dividend is None or dividend <= 0:
        return ScenarioValuationResult(
            **base, status="insufficient_data", reason="normalized_dividend_per_share_required",
            quality=ValuationQuality(warnings=["no_global_dividend_assumption_used"]),
        )
    required_names = ("conservative", "base", "optimistic")
    if not isinstance(assumptions, Mapping) or any(name not in assumptions for name in required_names):
        return ScenarioValuationResult(
            **base, status="insufficient_data", reason="three_explicit_scenarios_required",
            quality=ValuationQuality(warnings=["no_global_rate_or_growth_assumption_used"]),
        )
    margin = _finite_number(margin_of_safety_pct) if margin_of_safety_pct is not None else None
    if margin_of_safety_pct is not None and (margin is None or not 0 <= margin < 100):
        return ScenarioValuationResult(
            **base, status="invalid_input", reason="invalid_margin_of_safety",
        )

    scenarios: dict[str, ValuationScenario] = {}
    for name in required_names:
        specification = assumptions[name]
        if not isinstance(specification, Mapping) or "required_return_pct" not in specification or "growth_pct" not in specification:
            return ScenarioValuationResult(
                **base, status="insufficient_data", reason=f"scenario_assumptions_missing:{name}",
                quality=ValuationQuality(warnings=["no_global_rate_or_growth_assumption_used"]),
            )
        required_return = _finite_number(specification["required_return_pct"])
        growth = _finite_number(specification["growth_pct"])
        if required_return is None or growth is None:
            return ScenarioValuationResult(
                **base, status="invalid_input", reason=f"scenario_assumptions_invalid:{name}",
            )
        result = gordon_growth_value(dividend, required_return, growth)
        if not result.valid or result.value is None:
            return ScenarioValuationResult(
                **base, status="invalid_input", reason=f"{name}:{result.reason}",
            )
        value = result.value
        if margin is not None:
            value *= 1.0 - margin / 100.0
        scenarios[name] = ValuationScenario(
            value=value,
            upside_pct=upside_pct(value, price),
            assumptions={
                "dividend_per_share_d0": dividend,
                "required_return_pct": required_return,
                "growth_pct": growth,
                "margin_of_safety_pct": margin,
            },
        )

    values = [scenarios[name].value for name in required_names]
    if values != sorted(values):
        return ScenarioValuationResult(
            **base, status="invalid_input", reason="scenario_values_must_be_ordered",
            quality=ValuationQuality(warnings=["review_scenario_rate_and_growth_order"]),
        )
    return ScenarioValuationResult(
        **base,
        status="valid",
        scenarios=scenarios,
        quality=ValuationQuality(
            score=100.0,
            coverage_pct=100.0,
            metrics_used=["normalized_dividend", "required_return", "stable_growth"],
        ),
        metadata={
            "dividend_input": "D0",
            "formula": "D1 / (required_return - stable_growth)",
            "uses_global_defaults": False,
        },
    )
