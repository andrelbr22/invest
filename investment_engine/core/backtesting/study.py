from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from typing import Iterable


POSITION_POINTS = {1: 10.0, 2: 7.0, 3: 5.0, 4: 2.0, 5: 1.0}
ELIGIBLE_SAMPLE_STATUS = {"adequate", "limited"}


def _number(value, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _metrics(record: dict) -> dict:
    value = record.get("metrics")
    return value if isinstance(value, dict) else {}


def _mapping(value) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _configuration_payload(record: dict) -> dict:
    stored = _mapping(record.get("parameters"))
    if any(key in stored for key in ("strategy", "filters", "financial")):
        strategy = _mapping(stored.get("strategy"))
        filters = _mapping(stored.get("filters"))
        financial = _mapping(stored.get("financial"))
    else:
        # Backtests created before the structured parameter map stored only the
        # strategy parameters. Keeping this fallback makes their details useful.
        strategy, filters, financial = stored, {}, {}
    assumptions = _mapping(record.get("assumptions"))
    return {
        "strategy": strategy,
        "filters": filters,
        "financial": financial,
        "assumptions": assumptions,
    }


def build_strategy_configuration_catalog(
    records: Iterable[dict], *, strategy_id: str | None = None,
) -> dict:
    """Group effective backtest configurations without repeating them per asset.

    Dates, tickers and results are intentionally excluded from the identity. Two
    runs therefore belong to the same configuration when their strategy
    parameters, entry filters and financial assumptions are equal.
    """

    groups: dict[str, dict] = {}
    received_runs = 0
    selected_strategy_name = None
    for raw in records:
        record = dict(raw or {})
        current_strategy_id = str(record.get("strategy_id") or "").strip()
        if strategy_id and current_strategy_id != strategy_id:
            continue
        if not current_strategy_id:
            continue
        received_runs += 1
        selected_strategy_name = selected_strategy_name or record.get("strategy_name") or current_strategy_id
        payload = _configuration_payload(record)
        identity = {"strategy_id": current_strategy_id, **payload}
        encoded = json.dumps(identity, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        current = groups.setdefault(digest, {
            "configuration_id": digest[:12],
            "strategy_id": current_strategy_id,
            "strategy_name": record.get("strategy_name") or current_strategy_id,
            "strategy_parameters": payload["strategy"],
            "filters": payload["filters"],
            "financial": payload["financial"],
            "assumptions": payload["assumptions"],
            "tickers": set(),
            "run_count": 0,
            "ranking_scores": [],
            "metric_values": defaultdict(list),
            "sample_status_counts": defaultdict(int),
            "signal_counts": defaultdict(int),
            "latest_analysis_at": None,
            "requested_start": None,
            "requested_end": None,
        })
        ticker = str(record.get("ticker") or "").strip().upper()
        if ticker:
            current["tickers"].add(ticker)
        current["run_count"] += 1
        if record.get("ranking_score") is not None:
            current["ranking_scores"].append(_number(record.get("ranking_score")))
        metrics = _metrics(record)
        for key in (
            "total_return_pct", "cagr_pct", "sharpe_ratio", "max_drawdown_pct",
            "profit_factor", "win_rate_pct", "closed_trades",
        ):
            if metrics.get(key) is not None:
                current["metric_values"][key].append(_number(metrics.get(key)))
        current["sample_status_counts"][str(record.get("sample_status") or "unknown")] += 1
        current["signal_counts"][str(record.get("current_signal") or "neutral")] += 1
        created_at = record.get("created_at")
        if created_at is not None and (
            current["latest_analysis_at"] is None or str(created_at) > str(current["latest_analysis_at"])
        ):
            current["latest_analysis_at"] = created_at
            current["requested_start"] = record.get("requested_start")
            current["requested_end"] = record.get("requested_end")

    items = []
    for current in groups.values():
        metrics = {
            f"mean_{key}": _mean(values)
            for key, values in current.pop("metric_values").items()
        }
        current["tickers"] = sorted(current["tickers"])
        current["assets_tested"] = len(current["tickers"])
        current["mean_ranking_score"] = _mean(current.pop("ranking_scores"))
        current["mean_metrics"] = metrics
        current["sample_status_counts"] = dict(sorted(current["sample_status_counts"].items()))
        current["signal_counts"] = dict(sorted(current["signal_counts"].items()))
        items.append(current)
    items.sort(key=lambda item: (
        -(item.get("mean_ranking_score") or 0.0),
        -item.get("assets_tested", 0),
        item["configuration_id"],
    ))
    for position, item in enumerate(items, start=1):
        item["configuration_number"] = position
    return {
        "strategy_id": strategy_id or (items[0]["strategy_id"] if items else None),
        "strategy_name": selected_strategy_name,
        "configuration_count": len(items),
        "run_count": received_runs,
        "items": items,
    }


def build_strategy_study(records: Iterable[dict], *, top_limit: int = 5) -> dict:
    """Aggregate official backtests without letting parameter grids crowd the podium.

    Each asset contributes at most one result per strategy: its best eligible
    configuration. Strategies are then ranked inside each asset. The final score
    favours repeated top-three appearances, while placement, robust backtest
    quality and catalog coverage keep the comparison fair.
    """

    best_by_asset_strategy: dict[tuple[str, str], dict] = {}
    received = 0
    excluded_insufficient = 0
    for raw in records:
        received += 1
        record = dict(raw or {})
        ticker = str(record.get("ticker") or "").strip().upper()
        strategy_id = str(record.get("strategy_id") or "").strip()
        sample_status = str(record.get("sample_status") or "insufficient").strip().lower()
        if not ticker or not strategy_id or sample_status not in ELIGIBLE_SAMPLE_STATUS:
            excluded_insufficient += 1
            continue
        score = _number(record.get("ranking_score"), -1.0)
        if score < 0:
            excluded_insufficient += 1
            continue
        record["ticker"] = ticker
        record["strategy_id"] = strategy_id
        record["ranking_score"] = score
        key = (ticker, strategy_id)
        previous = best_by_asset_strategy.get(key)
        if previous is None or score > _number(previous.get("ranking_score"), -1.0):
            best_by_asset_strategy[key] = record

    per_asset: dict[str, list[dict]] = defaultdict(list)
    for record in best_by_asset_strategy.values():
        per_asset[record["ticker"]].append(record)

    # A podium only has statistical meaning when at least three strategies competed.
    comparable_assets = {
        ticker: sorted(
            rows,
            key=lambda item: (-_number(item.get("ranking_score")), item.get("strategy_id", "")),
        )
        for ticker, rows in per_asset.items()
        if len(rows) >= 3
    }
    total_assets = len(comparable_assets)
    stats: dict[str, dict] = {}

    for ticker, ranked in comparable_assets.items():
        for record in ranked:
            strategy_id = record["strategy_id"]
            current = stats.setdefault(strategy_id, {
                "strategy_id": strategy_id,
                "strategy_name": record.get("strategy_name") or strategy_id,
                "assets_tested": 0,
                "first_places": 0,
                "second_places": 0,
                "third_places": 0,
                "top3_count": 0,
                "top5_count": 0,
                "position_points": 0.0,
                "quality_scores": [],
                "win_rates": [],
            })
            current["assets_tested"] += 1
            current["quality_scores"].append(_number(record.get("ranking_score")))
            win_rate = _metrics(record).get("win_rate_pct")
            if win_rate is not None:
                current["win_rates"].append(_number(win_rate))

        for position, record in enumerate(ranked[:5], start=1):
            current = stats[record["strategy_id"]]
            current["position_points"] += POSITION_POINTS[position]
            current["top5_count"] += 1
            if position <= 3:
                current["top3_count"] += 1
            if position == 1:
                current["first_places"] += 1
            elif position == 2:
                current["second_places"] += 1
            elif position == 3:
                current["third_places"] += 1

    minimum_assets = min(total_assets, max(3, math.ceil(total_assets * 0.20))) if total_assets else 0
    ranking = []
    for current in stats.values():
        assets_tested = current["assets_tested"]
        if assets_tested < minimum_assets:
            continue
        top3_frequency = (current["top3_count"] / total_assets * 100.0) if total_assets else 0.0
        placement_quality = current["position_points"] / (10.0 * assets_tested) * 100.0
        robust_quality = sum(current["quality_scores"]) / len(current["quality_scores"])
        coverage = assets_tested / total_assets * 100.0 if total_assets else 0.0
        final_score = (
            0.55 * top3_frequency
            + 0.25 * placement_quality
            + 0.15 * robust_quality
            + 0.05 * coverage
        )
        ranking.append({
            "strategy_id": current["strategy_id"],
            "strategy_name": current["strategy_name"],
            "study_score": round(final_score, 2),
            "assets_tested": assets_tested,
            "coverage_pct": round(coverage, 1),
            "top3_count": current["top3_count"],
            "top3_frequency_pct": round(top3_frequency, 1),
            "first_places": current["first_places"],
            "second_places": current["second_places"],
            "third_places": current["third_places"],
            "top5_count": current["top5_count"],
            "position_points": round(current["position_points"], 1),
            "mean_robust_score": round(robust_quality, 2),
            "mean_win_rate_pct": (
                round(sum(current["win_rates"]) / len(current["win_rates"]), 1)
                if current["win_rates"] else None
            ),
        })

    ranking.sort(key=lambda item: (
        -item["study_score"], -item["top3_count"], -item["first_places"], item["strategy_name"],
    ))
    for position, item in enumerate(ranking[: max(1, top_limit)], start=1):
        item["position"] = position

    return {
        "ranking": ranking[: max(1, top_limit)],
        "eligible_assets": total_assets,
        "eligible_strategy_asset_pairs": len(best_by_asset_strategy),
        "received_runs": received,
        "excluded_insufficient_runs": excluded_insufficient,
        "minimum_assets_per_strategy": minimum_assets,
        "methodology": {
            "position_points": {str(key): value for key, value in POSITION_POINTS.items()},
            "weights_pct": {
                "top3_recurrence": 55,
                "placement_quality": 25,
                "robust_backtest_quality": 15,
                "catalog_coverage": 5,
            },
            "rules": [
                "Somente resultados oficiais válidos com amostra adequada ou limitada.",
                "Em cada ativo, somente a melhor configuração de cada estratégia disputa posições.",
                "Um ativo só participa quando ao menos três estratégias puderam ser comparadas.",
                "A recorrência entre os três primeiros é o fator dominante da nota final.",
            ],
        },
    }
