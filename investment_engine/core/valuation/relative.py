"""Robust relative valuation for stocks and Brazilian real-estate funds."""

from __future__ import annotations

import math
from statistics import median
from typing import Iterable, Mapping

from .catalog import valuation_method_metadata
from .results import ScenarioValuationResult, ValuationQuality, ValuationScenario, upside_pct


SCENARIOS = ("conservative", "base", "optimistic")


def _positive(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _finite(value, *, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _winsorize(values: list[float], lower: float, upper: float) -> tuple[list[float], tuple[float, float]]:
    if not 0 <= lower < upper <= 1:
        raise ValueError("invalid_winsor_limits")
    low, high = _quantile(values, lower), _quantile(values, upper)
    return [min(max(value, low), high) for value in values], (low, high)


def _key(value) -> str:
    return str(value or "").strip().casefold()


def _comparable_peers(
    target: Mapping,
    peers: Iterable[Mapping],
    *,
    asset_type: str,
) -> tuple[list[Mapping], list[str]]:
    warnings: list[str] = []
    classification_field = "sector" if asset_type == "stock" else "segment"
    classification = _key(target.get(classification_field))
    target_class = _key(target.get("asset_class"))
    ticker = _key(target.get("ticker"))
    if not classification:
        warnings.append(f"target_{classification_field}_missing")
    selected: list[Mapping] = []
    for peer in peers:
        if not isinstance(peer, Mapping):
            warnings.append("invalid_peer_ignored")
            continue
        peer_type = _key(peer.get("asset_type") or asset_type)
        if peer_type != asset_type:
            continue
        if ticker and _key(peer.get("ticker")) == ticker:
            continue
        if classification and _key(peer.get(classification_field)) != classification:
            continue
        if target_class and target_class != "default" and _key(peer.get("asset_class")) != target_class:
            continue
        selected.append(peer)
    return selected, warnings


def _per_share(target: Mapping, direct: str, multiple: str, price: float) -> tuple[float | None, str | None]:
    value = _positive(target.get(direct))
    if value is not None:
        return value, None
    current_multiple = _positive(target.get(multiple))
    if current_multiple is None:
        return None, None
    return price / current_multiple, f"{direct}_implied_from_{multiple}"


def _per_share_from_yield(
    target: Mapping,
    direct: str,
    yield_field: str,
    price: float,
) -> tuple[float | None, str | None]:
    """Return a per-share flow from a percentage yield.

    A yield is ``flow / price`` rather than ``price / flow``.  Keeping this
    separate from :func:`_per_share` prevents treating FFO yield as if it were
    a P/FFO multiple.
    """
    value = _positive(target.get(direct))
    if value is not None:
        return value, None
    percentage = _positive(target.get(yield_field))
    if percentage is None:
        return None, None
    return price * percentage / 100.0, f"{direct}_implied_from_{yield_field}"


def _multiple_estimates(
    peers: list[Mapping],
    *,
    field: str,
    base_value: float,
    min_peers: int,
    winsor_limits: tuple[float, float],
    inverse: bool = False,
    subtract: float = 0.0,
) -> tuple[dict[str, float] | None, dict]:
    raw = [value for peer in peers if (value := _positive(peer.get(field))) is not None]
    details = {"sample_size": len(raw)}
    if len(raw) < min_peers:
        return None, details
    clean, bounds = _winsorize(raw, *winsor_limits)
    probabilities = (0.75, 0.5, 0.25) if inverse else (0.25, 0.5, 0.75)
    multiples = dict(zip(SCENARIOS, (_quantile(clean, probability) for probability in probabilities)))
    if inverse:
        values = {name: base_value / (multiple / 100.0) - subtract for name, multiple in multiples.items()}
    else:
        values = {name: base_value * multiple - subtract for name, multiple in multiples.items()}
    if any(not math.isfinite(value) or value <= 0 for value in values.values()):
        return None, {**details, "winsorized_bounds": bounds, "scenario_multiples": multiples}
    return values, {
        **details,
        "winsorized_bounds": bounds,
        "scenario_multiples": multiples,
    }


def relative_valuation(
    target: Mapping,
    peers: Iterable[Mapping],
    *,
    asset_type: str | None = None,
    asset_class: str = "default",
    min_peers: int = 5,
    winsor_limits: tuple[float, float] = (0.10, 0.90),
) -> ScenarioValuationResult:
    """Estimate a valuation range from comparable peers.

    Peer medians and quartiles are computed only after strict type and
    sector/segment matching. Negative, zero and non-finite multiples are
    rejected. Outliers are winsorized before scenarios are estimated.
    """
    metadata = valuation_method_metadata("relative_peers")
    type_key = _key(asset_type or target.get("asset_type"))
    price = _positive(target.get("price"))
    empty_quality = ValuationQuality(warnings=[])
    if type_key not in {"stock", "fii"}:
        return ScenarioValuationResult(
            family_id=metadata.family_id, method=metadata.canonical_id, label=metadata.label,
            status="not_applicable", asset_type=type_key or "unknown", asset_class=asset_class,
            market_price=price, quality=empty_quality, reason="relative_valuation_asset_type_not_supported",
        )
    if price is None:
        return ScenarioValuationResult(
            family_id=metadata.family_id, method=metadata.canonical_id, label=metadata.label,
            status="insufficient_data", asset_type=type_key, asset_class=asset_class,
            quality=empty_quality, reason="market_price_required",
        )
    if min_peers < 3:
        return ScenarioValuationResult(
            family_id=metadata.family_id, method=metadata.canonical_id, label=metadata.label,
            status="invalid_input", asset_type=type_key, asset_class=asset_class,
            market_price=price, quality=empty_quality, reason="min_peers_must_be_at_least_three",
        )
    try:
        comparable, warnings = _comparable_peers(target, list(peers or ()), asset_type=type_key)
        # Validate limits even when every metric later proves unavailable.
        _winsorize([1.0], *winsor_limits)
    except ValueError as exc:
        return ScenarioValuationResult(
            family_id=metadata.family_id, method=metadata.canonical_id, label=metadata.label,
            status="invalid_input", asset_type=type_key, asset_class=asset_class,
            market_price=price, quality=empty_quality, reason=str(exc),
        )
    classification_field = "sector" if type_key == "stock" else "segment"
    if not _key(target.get(classification_field)):
        return ScenarioValuationResult(
            family_id=metadata.family_id, method=metadata.canonical_id, label=metadata.label,
            status="insufficient_data", asset_type=type_key, asset_class=asset_class,
            market_price=price,
            quality=ValuationQuality(warnings=sorted(set(warnings))),
            reason=f"target_{classification_field}_required",
            metadata={"minimum_peers": min_peers, "comparable_peers": 0},
        )

    metric_values: dict[str, dict[str, float]] = {}
    metric_details: dict[str, dict] = {}
    financial_equity = type_key == "stock" and _key(asset_class) in {"bank", "insurance"}
    expected_metrics = (
        ("pbv",) if financial_equity else ("pe", "pbv")
    ) if type_key == "stock" else ("pbv", "ffo_yield_pct")

    if type_key == "stock":
        eps, warning = _per_share(target, "earnings_per_share", "pe", price)
        if warning:
            warnings.append(warning)
        bvps, warning = _per_share(target, "book_value_per_share", "pbv", price)
        if warning:
            warnings.append(warning)
        stock_bases = (("pbv", bvps),) if financial_equity else (("pe", eps), ("pbv", bvps))
        for field, base_value in stock_bases:
            if base_value is None:
                metric_details[field] = {"sample_size": 0, "target_input_missing": True}
                continue
            values, details = _multiple_estimates(
                comparable, field=field, base_value=base_value, min_peers=min_peers,
                winsor_limits=winsor_limits,
            )
            metric_details[field] = details
            if values is not None:
                metric_values[field] = values

        ebitda_per_share = _positive(target.get("ebitda_per_share"))
        net_debt_per_share = _finite(target.get("net_debt_per_share"), default=0.0)
        if ebitda_per_share is not None and net_debt_per_share is not None:
            values, details = _multiple_estimates(
                comparable, field="ev_ebitda", base_value=ebitda_per_share,
                subtract=net_debt_per_share, min_peers=min_peers, winsor_limits=winsor_limits,
            )
            metric_details["ev_ebitda"] = details
            if values is not None:
                metric_values["ev_ebitda"] = values
    else:
        nav, warning = _per_share(target, "nav_per_share", "pbv", price)
        if warning:
            warnings.append(warning)
        ffo, warning = _per_share_from_yield(
            target, "ffo_per_share", "ffo_yield_pct", price,
        )
        if warning:
            warnings.append(warning)
        if nav is not None:
            values, details = _multiple_estimates(
                comparable, field="pbv", base_value=nav, min_peers=min_peers,
                winsor_limits=winsor_limits,
            )
            metric_details["pbv"] = details
            if values is not None:
                metric_values["pbv"] = values
        else:
            metric_details["pbv"] = {"sample_size": 0, "target_input_missing": True}
        if ffo is not None:
            values, details = _multiple_estimates(
                comparable, field="ffo_yield_pct", base_value=ffo, inverse=True,
                min_peers=min_peers, winsor_limits=winsor_limits,
            )
            metric_details["ffo_yield_pct"] = details
            if values is not None:
                metric_values["ffo_yield_pct"] = values
        else:
            metric_details["ffo_yield_pct"] = {"sample_size": 0, "target_input_missing": True}

    metric_counts = {field: int(details.get("sample_size") or 0) for field, details in metric_details.items()}
    metrics_used = sorted(metric_values)
    coverage = 100.0 * len(set(metrics_used).intersection(expected_metrics)) / len(expected_metrics)
    qualifying_counts = [metric_counts[field] for field in metrics_used]
    sample_size = min(qualifying_counts) if qualifying_counts else len(comparable)
    sample_factor = min(1.0, sample_size / max(min_peers * 2, 1))
    quality_score = round(60.0 * (coverage / 100.0) + 40.0 * sample_factor, 2)
    if not metric_values:
        warnings.append("no_metric_reached_minimum_peer_sample")
        return ScenarioValuationResult(
            family_id=metadata.family_id, method=metadata.canonical_id, label=metadata.label,
            status="insufficient_data", asset_type=type_key, asset_class=asset_class,
            market_price=price,
            quality=ValuationQuality(
                score=quality_score, coverage_pct=coverage, sample_size=len(comparable),
                metric_sample_sizes=metric_counts, metrics_used=[], warnings=sorted(set(warnings)),
            ),
            reason="insufficient_comparable_peers",
            metadata={"minimum_peers": min_peers, "comparable_peers": len(comparable), "metrics": metric_details},
        )

    scenarios: dict[str, ValuationScenario] = {}
    for scenario in SCENARIOS:
        estimates = [values[scenario] for values in metric_values.values()]
        value = float(median(estimates))
        scenarios[scenario] = ValuationScenario(
            value=value,
            upside_pct=upside_pct(value, price),
            assumptions={"metric_values": {field: values[scenario] for field, values in metric_values.items()}},
        )

    ordered = [scenarios[name].value for name in SCENARIOS]
    if ordered != sorted(ordered):
        warnings.append("combined_scenarios_not_monotonic")
        ordered = sorted(ordered)
        for name, value in zip(SCENARIOS, ordered):
            scenarios[name] = ValuationScenario(value=value, upside_pct=upside_pct(value, price))

    return ScenarioValuationResult(
        family_id=metadata.family_id, method=metadata.canonical_id, label=metadata.label,
        status="valid", asset_type=type_key, asset_class=asset_class, market_price=price,
        scenarios=scenarios,
        quality=ValuationQuality(
            score=quality_score, coverage_pct=coverage, sample_size=sample_size,
            metric_sample_sizes=metric_counts, metrics_used=metrics_used,
            warnings=sorted(set(warnings)),
        ),
        metadata={
            "minimum_peers": min_peers,
            "comparable_peers": len(comparable),
            "peer_group": {"sector": target.get("sector"), "segment": target.get("segment")},
            "winsor_limits": winsor_limits,
            "metrics": metric_details,
        },
    )
