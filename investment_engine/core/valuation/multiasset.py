"""Class-specific valuation references for ETFs, BDRs and futures.

These calculations intentionally fail closed.  They only return a reference
when the provider supplied the economic input required by that asset class;
no company multiple is silently reused for a fund or derivative.
"""

from __future__ import annotations

import math
from datetime import date
from statistics import median
from typing import Iterable, Mapping

from .catalog import valuation_method_metadata
from .results import ScenarioValuationResult, ValuationQuality, ValuationScenario, upside_pct


SCENARIOS = ("conservative", "base", "optimistic")


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive(value) -> float | None:
    number = _finite(value)
    return number if number is not None and number > 0 else None


def _key(value) -> str:
    return str(value or "").strip().casefold()


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _winsorized(values: list[float], limits: tuple[float, float]) -> tuple[list[float], tuple[float, float]]:
    low_probability, high_probability = limits
    if not 0 <= low_probability < high_probability <= 1:
        raise ValueError("invalid_winsor_limits")
    low, high = _quantile(values, low_probability), _quantile(values, high_probability)
    return [min(max(value, low), high) for value in values], (low, high)


def _empty(
    method: str,
    *,
    asset_type: str,
    market_price: float | None,
    reason: str,
    metadata: dict | None = None,
    warnings: list[str] | None = None,
) -> ScenarioValuationResult:
    definition = valuation_method_metadata(method)
    return ScenarioValuationResult(
        family_id=definition.family_id,
        method=definition.canonical_id,
        label=definition.label,
        status="insufficient_data",
        asset_type=asset_type,
        market_price=market_price,
        reason=reason,
        quality=ValuationQuality(warnings=warnings or []),
        metadata=metadata or {},
    )


def _single_reference(
    method: str,
    *,
    asset_type: str,
    market_price: float,
    value: float,
    assumptions: dict,
    metadata: dict,
    warnings: list[str] | None = None,
) -> ScenarioValuationResult:
    definition = valuation_method_metadata(method)
    return ScenarioValuationResult(
        family_id=definition.family_id,
        method=definition.canonical_id,
        label=definition.label,
        status="valid",
        asset_type=asset_type,
        market_price=market_price,
        scenarios={
            "base": ValuationScenario(
                value=value,
                upside_pct=upside_pct(value, market_price),
                assumptions=assumptions,
            ),
        },
        quality=ValuationQuality(
            score=100.0,
            coverage_pct=100.0,
            sample_size=1,
            metrics_used=[definition.canonical_id],
            warnings=warnings or [],
        ),
        metadata=metadata,
    )


def etf_nav_reference(target: Mapping) -> ScenarioValuationResult:
    """Recover the ETF NAV per share from the reported premium/discount.

    The provider reports ``100 * (price / NAV - 1)``.  Reversing that
    identity yields the reference NAV without inventing portfolio holdings.
    """
    method = "etf_nav_reference"
    price = _positive(target.get("price"))
    if price is None:
        return _empty(method, asset_type="etf", market_price=None, reason="market_price_required")
    direct_nav = _positive(target.get("nav_per_share"))
    premium = _finite(target.get("nav_discount_premium_pct"))
    if direct_nav is not None:
        nav, source = direct_nav, "provider_nav_per_share"
    elif premium is not None and premium > -100:
        nav, source = price / (1.0 + premium / 100.0), "provider_nav_discount_premium"
    else:
        return _empty(
            method,
            asset_type="etf",
            market_price=price,
            reason="etf_nav_or_premium_required",
            metadata={"source": target.get("valuation_source")},
        )
    return _single_reference(
        method,
        asset_type="etf",
        market_price=price,
        value=nav,
        assumptions={"reported_premium_discount_pct": premium},
        metadata={
            "formula": "NAV = market_price / (1 + premium_discount_pct / 100)",
            "input_source": source,
            "source": target.get("valuation_source"),
            "as_of": target.get("valuation_inputs_as_of"),
        },
    )


def etf_relative_nav_premium(
    target: Mapping,
    peers: Iterable[Mapping],
    *,
    min_peers: int = 5,
    winsor_limits: tuple[float, float] = (0.10, 0.90),
) -> ScenarioValuationResult:
    """Value an ETF at the peer distribution of premiums/discounts to NAV."""
    method = "etf_peer_nav_premium"
    price = _positive(target.get("price"))
    nav_result = etf_nav_reference(target)
    base = nav_result.scenarios.get("base")
    if price is None or nav_result.status != "valid" or base is None:
        return _empty(
            method,
            asset_type="etf",
            market_price=price,
            reason="etf_nav_or_premium_required",
        )
    if min_peers < 3:
        return _empty(method, asset_type="etf", market_price=price, reason="min_peers_must_be_at_least_three")
    ticker = _key(target.get("ticker"))
    currency = _key(target.get("fundamental_currency_code") or target.get("currency"))
    values: list[float] = []
    for peer in peers or ():
        if not isinstance(peer, Mapping) or _key(peer.get("asset_type")) != "etf":
            continue
        if ticker and _key(peer.get("ticker")) == ticker:
            continue
        peer_currency = _key(peer.get("fundamental_currency_code") or peer.get("currency"))
        if currency and peer_currency and peer_currency != currency:
            continue
        premium = _finite(peer.get("nav_discount_premium_pct"))
        if premium is not None and -95 < premium < 500:
            values.append(premium)
    if len(values) < min_peers:
        return _empty(
            method,
            asset_type="etf",
            market_price=price,
            reason="insufficient_etf_nav_peers",
            metadata={"minimum_peers": min_peers, "comparable_peers": len(values)},
        )
    try:
        clean, bounds = _winsorized(values, winsor_limits)
    except ValueError as exc:
        return _empty(method, asset_type="etf", market_price=price, reason=str(exc))
    nav = base.value
    scenario_premiums = {
        name: _quantile(clean, probability)
        for name, probability in zip(SCENARIOS, (0.25, 0.50, 0.75))
    }
    scenarios = {
        name: ValuationScenario(
            value=nav * (1.0 + premium / 100.0),
            upside_pct=upside_pct(nav * (1.0 + premium / 100.0), price),
            assumptions={"peer_premium_discount_pct": premium},
        )
        for name, premium in scenario_premiums.items()
    }
    definition = valuation_method_metadata(method)
    return ScenarioValuationResult(
        family_id=definition.family_id,
        method=definition.canonical_id,
        label=definition.label,
        status="valid",
        asset_type="etf",
        market_price=price,
        scenarios=scenarios,
        quality=ValuationQuality(
            score=min(100.0, 70.0 + 30.0 * len(values) / max(min_peers * 2, 1)),
            coverage_pct=100.0,
            sample_size=len(values),
            metric_sample_sizes={"nav_discount_premium_pct": len(values)},
            metrics_used=["nav_discount_premium_pct"],
        ),
        metadata={
            "minimum_peers": min_peers,
            "comparable_peers": len(values),
            "currency_group": currency or None,
            "winsorized_bounds": bounds,
            "formula": "peer_reference = target_NAV * (1 + peer_premium_discount_pct / 100)",
            "source": target.get("valuation_source"),
            "as_of": target.get("valuation_inputs_as_of"),
        },
    )


def bdr_pbv_relative(
    target: Mapping,
    peers: Iterable[Mapping],
    *,
    min_peers: int = 5,
    winsor_limits: tuple[float, float] = (0.10, 0.90),
) -> ScenarioValuationResult:
    """Compare a BDR's reported P/VP with BDRs in the same industry/sector."""
    method = "bdr_pbv_peers"
    price = _positive(target.get("price"))
    pbv = _positive(target.get("pbv"))
    book_value = _positive(target.get("book_value_per_share"))
    if price is None:
        return _empty(method, asset_type="bdr", market_price=None, reason="market_price_required")
    if book_value is None and pbv is not None:
        book_value = price / pbv
    if book_value is None:
        return _empty(method, asset_type="bdr", market_price=price, reason="bdr_book_value_or_pbv_required")
    if min_peers < 3:
        return _empty(method, asset_type="bdr", market_price=price, reason="min_peers_must_be_at_least_three")
    ticker = _key(target.get("ticker"))
    target_industry, target_sector = _key(target.get("industry")), _key(target.get("sector"))
    candidates = [
        peer for peer in peers or ()
        if isinstance(peer, Mapping)
        and _key(peer.get("asset_type")) == "bdr"
        and (not ticker or _key(peer.get("ticker")) != ticker)
        and _positive(peer.get("pbv")) is not None
    ]
    group_name = None
    selected: list[Mapping] = []
    if target_industry:
        selected = [peer for peer in candidates if _key(peer.get("industry")) == target_industry]
        group_name = "industry"
    if len(selected) < min_peers and target_sector:
        selected = [peer for peer in candidates if _key(peer.get("sector")) == target_sector]
        group_name = "sector"
    multiples = [float(peer["pbv"]) for peer in selected]
    if len(multiples) < min_peers:
        return _empty(
            method,
            asset_type="bdr",
            market_price=price,
            reason="insufficient_bdr_pbv_peers" if target_industry or target_sector else "bdr_peer_classification_required",
            metadata={"minimum_peers": min_peers, "comparable_peers": len(multiples)},
        )
    try:
        clean, bounds = _winsorized(multiples, winsor_limits)
    except ValueError as exc:
        return _empty(method, asset_type="bdr", market_price=price, reason=str(exc))
    scenario_multiples = {
        name: _quantile(clean, probability)
        for name, probability in zip(SCENARIOS, (0.25, 0.50, 0.75))
    }
    scenarios = {
        name: ValuationScenario(
            value=book_value * multiple,
            upside_pct=upside_pct(book_value * multiple, price),
            assumptions={"peer_pbv": multiple},
        )
        for name, multiple in scenario_multiples.items()
    }
    definition = valuation_method_metadata(method)
    return ScenarioValuationResult(
        family_id=definition.family_id,
        method=definition.canonical_id,
        label=definition.label,
        status="valid",
        asset_type="bdr",
        market_price=price,
        scenarios=scenarios,
        quality=ValuationQuality(
            score=min(100.0, 70.0 + 30.0 * len(multiples) / max(min_peers * 2, 1)),
            coverage_pct=100.0,
            sample_size=len(multiples),
            metric_sample_sizes={"pbv": len(multiples)},
            metrics_used=["pbv"],
        ),
        metadata={
            "minimum_peers": min_peers,
            "comparable_peers": len(multiples),
            "peer_group": {group_name: target.get(group_name) if group_name else None},
            "winsorized_bounds": bounds,
            "book_value_per_bdr": book_value,
            "formula": "reference = book_value_per_BDR * peer_PBV",
            "source": target.get("valuation_source"),
            "as_of": target.get("valuation_inputs_as_of"),
        },
    )


def bdr_underlying_parity(target: Mapping) -> ScenarioValuationResult:
    """Convert a verified underlying quote using FX and the depositary ratio."""
    method = "bdr_underlying_parity"
    price = _positive(target.get("price"))
    underlying = _positive(target.get("underlying_price"))
    fx = _positive(target.get("fx_brl_per_underlying_currency"))
    ratio = _positive(target.get("bdr_underlying_share_ratio"))
    if price is None:
        return _empty(method, asset_type="bdr", market_price=None, reason="market_price_required")
    if underlying is None or fx is None or ratio is None:
        return _empty(
            method,
            asset_type="bdr",
            market_price=price,
            reason="bdr_underlying_price_fx_and_ratio_required",
            metadata={"inputs_present": {"underlying_price": underlying is not None, "fx": fx is not None, "ratio": ratio is not None}},
        )
    value = underlying * fx * ratio
    return _single_reference(
        method,
        asset_type="bdr",
        market_price=price,
        value=value,
        assumptions={"underlying_price": underlying, "fx_brl_per_unit": fx, "bdr_ratio": ratio},
        metadata={"formula": "underlying_price * BRL_FX * underlying_shares_per_BDR", "source": target.get("valuation_source"), "as_of": target.get("valuation_inputs_as_of")},
    )


def future_cost_of_carry(target: Mapping) -> ScenarioValuationResult:
    """Calculate a front-contract theoretical price from observable carry inputs."""
    method = "future_cost_of_carry"
    market_price = _positive(target.get("front_contract_price") or target.get("price"))
    spot = _positive(target.get("underlying_spot_price"))
    carry_rate = _finite(target.get("carry_rate_pct"))
    income_yield = _finite(target.get("underlying_income_yield_pct"))
    days = _finite(target.get("days_to_expiry"))
    if market_price is None:
        return _empty(method, asset_type="future", market_price=None, reason="future_market_price_required")
    present = {
        "underlying_spot_price": spot is not None,
        "carry_rate_pct": carry_rate is not None,
        "days_to_expiry": days is not None and days > 0,
    }
    if not all(present.values()):
        return _empty(
            method,
            asset_type="future",
            market_price=market_price,
            reason="future_spot_carry_and_expiry_required",
            metadata={"inputs_present": present, "front_contract": target.get("front_contract")},
        )
    income_yield = income_yield or 0.0
    if carry_rate <= -100 or income_yield <= -100:
        return _empty(method, asset_type="future", market_price=market_price, reason="future_carry_rate_invalid")
    years = days / 365.0
    value = spot * ((1.0 + carry_rate / 100.0) / (1.0 + income_yield / 100.0)) ** years
    warnings = [] if target.get("underlying_income_yield_pct") is not None else ["underlying_income_yield_unavailable_assumed_zero"]
    return _single_reference(
        method,
        asset_type="future",
        market_price=market_price,
        value=value,
        assumptions={
            "underlying_spot_price": spot,
            "annual_carry_rate_pct": carry_rate,
            "annual_income_yield_pct": income_yield,
            "days_to_expiry": days,
        },
        metadata={
            "formula": "spot * ((1 + carry_rate) / (1 + income_yield)) ** (days / 365)",
            "front_contract": target.get("front_contract"),
            "expiration_date": target.get("expiration_date"),
            "underlying_ticker": target.get("underlying_ticker"),
            "carry_rate_source": target.get("carry_rate_source"),
            "source": target.get("valuation_source"),
            "as_of": target.get("valuation_inputs_as_of"),
        },
        warnings=warnings,
    )
