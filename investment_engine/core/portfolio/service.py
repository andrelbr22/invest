from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable


ASSET_CLASS_LABELS = {
    "stock": "Ações",
    "fii": "FIIs",
    "etf": "ETFs",
    "bdr": "BDRs",
    "future": "Futuros / derivativos",
    "fixed_income": "Renda Fixa",
    "crypto": "Cripto",
    "other": "Outros",
    "cash": "Caixa",
}

STAGE_LABELS = {
    "position": "Posição atual",
    "target": "Alvo",
    "analysis": "Em análise",
}


# TradingView returns part of the Brazilian catalog in English even when the
# request language is Portuguese.  Keep the original metadata in the database
# (the scoring models use it) and translate only the user-facing classification.
CLASSIFICATION_TRANSLATIONS = {
    "basic materials": "Materiais básicos",
    "communication services": "Comunicações",
    "consumer cyclical": "Consumo cíclico",
    "consumer defensive": "Consumo não cíclico",
    "consumer durables": "Bens de consumo duráveis",
    "consumer non-durables": "Bens de consumo não duráveis",
    "consumer services": "Serviços ao consumidor",
    "commercial services": "Serviços comerciais",
    "distribution services": "Distribuição",
    "electronic technology": "Tecnologia eletrônica",
    "energy minerals": "Energia e minerais",
    "finance": "Financeiro",
    "financial services": "Serviços financeiros",
    "health services": "Serviços de saúde",
    "health technology": "Tecnologia em saúde",
    "healthcare": "Saúde",
    "industrials": "Bens industriais",
    "industrial services": "Serviços industriais",
    "miscellaneous": "Diversos",
    "non-energy minerals": "Minerais não energéticos",
    "process industries": "Indústrias de transformação",
    "producer manufacturing": "Bens de capital",
    "real estate": "Imobiliário",
    "retail trade": "Comércio varejista",
    "technology": "Tecnologia",
    "technology services": "Serviços de tecnologia",
    "transportation": "Transportes",
    "utilities": "Utilidade pública",
    "large cap": "Grande capitalização",
    "mid cap": "Média capitalização",
    "small cap": "Pequena capitalização",
    "micro cap": "Microcapitalização",
}


def localize_classification(value: str | None) -> str | None:
    """Return a Portuguese label while preserving already localized values."""
    if value is None:
        return None
    clean = str(value).strip()
    if not clean:
        return None
    return CLASSIFICATION_TRANSLATIONS.get(clean.casefold(), clean)


def _f(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator * 100.0


def classification_for(
    asset_type: str | None,
    sector: str | None,
    segment: str | None,
    override: str | None = None,
    industry: str | None = None,
    category: str | None = None,
) -> str:
    """Classification used for the within-class allocation view.

    For FIIs, segment is economically more useful than a generic Real Estate sector.
    """
    if override:
        return localize_classification(override) or "Não classificado"
    if (asset_type or "").lower() == "fii":
        raw = segment or sector or industry or category
    else:
        raw = sector or segment or industry or category
    return localize_classification(raw) or "Não classificado"


def build_portfolio_snapshot(positions: Iterable[dict], *, cash_balance: float = 0.0, target_cash_pct: float = 0.0) -> dict:
    """Calculate portfolio allocation, target gaps and sector/class composition.

    Current weights are only considered complete when every held position with quantity > 0
    has a valid market price. Missing quotations remain ``None`` instead of being interpreted
    as zero, preserving the engine's N/D semantics.
    """
    rows = []
    cash = max(_f(cash_balance), 0.0)
    held_market_value_known = 0.0
    held_cost_known = 0.0
    held_count = 0
    missing_price_count = 0
    missing_average_price_count = 0

    for p in positions:
        quantity = max(_f(p.get("quantity")), 0.0)
        avg_price = p.get("average_price")
        avg_price_f = _f(avg_price) if avg_price is not None else None
        current_price = p.get("current_price")
        current_price_f = _f(current_price) if current_price is not None else None
        stage = p.get("stage") or "position"
        target = max(_f(p.get("target_weight_pct")), 0.0)
        # "Em análise" is a research/watchlist state. It must not silently change the strategic allocation.
        effective_target = target if stage in {"position", "target"} else 0.0
        is_held = stage == "position" and quantity > 0

        if is_held:
            held_count += 1
            if current_price_f is None or current_price_f <= 0:
                missing_price_count += 1
            else:
                held_market_value_known += quantity * current_price_f
            if avg_price_f is None or avg_price_f <= 0:
                missing_average_price_count += 1
            else:
                held_cost_known += quantity * avg_price_f

        # N/D stays N/D: a held security without a quotation does not become a zero-valued asset.
        market_value = (
            quantity * current_price_f
            if is_held and current_price_f is not None and current_price_f > 0
            else (None if is_held else 0.0)
        )
        cost_value = (
            quantity * avg_price_f
            if is_held and avg_price_f is not None and avg_price_f > 0
            else (None if is_held else 0.0)
        )
        pnl_value = (
            market_value - cost_value
            if is_held and market_value is not None and cost_value is not None
            else None
        )
        pnl_pct = (
            ((current_price_f / avg_price_f) - 1.0) * 100.0
            if is_held and avg_price_f and current_price_f is not None and current_price_f > 0
            else None
        )

        asset_type = (p.get("asset_type") or "other").lower()
        rows.append({
            **p,
            "stage": stage,
            "stage_label": STAGE_LABELS.get(stage, stage),
            "asset_class": asset_type,
            "asset_class_label": ASSET_CLASS_LABELS.get(asset_type, asset_type.upper()),
            "classification": classification_for(
                asset_type,
                p.get("sector"),
                p.get("segment"),
                p.get("classification_override"),
                p.get("industry"),
                p.get("market_cap_category"),
            ),
            "quantity": quantity,
            "average_price": avg_price_f,
            "current_price": current_price_f,
            "target_weight_pct": target,
            "effective_target_weight_pct": effective_target,
            "market_value": market_value,
            "cost_value": cost_value,
            "pnl_value": pnl_value,
            "pnl_pct": pnl_pct,
            "has_current_price": current_price_f is not None and current_price_f > 0,
        })

    allocation_complete = missing_price_count == 0
    pnl_complete = missing_price_count == 0 and missing_average_price_count == 0
    total_market_value = held_market_value_known + cash if allocation_complete else None
    total_pnl = held_market_value_known - held_cost_known if pnl_complete and held_cost_known > 0 else None
    total_pnl_pct = (
        ((held_market_value_known / held_cost_known) - 1.0) * 100.0
        if pnl_complete and held_cost_known > 0 else None
    )

    class_current_values = defaultdict(float)
    class_target_weights = defaultdict(float)
    class_missing_prices = defaultdict(int)
    classification_current = defaultdict(lambda: defaultdict(float))
    classification_missing = defaultdict(lambda: defaultdict(int))
    classification_target = defaultdict(lambda: defaultdict(float))

    for r in rows:
        cls = r["asset_class"]
        class_target_weights[cls] += r["effective_target_weight_pct"]
        classification_target[cls][r["classification"]] += r["effective_target_weight_pct"]
        if r["stage"] == "position" and r["quantity"] > 0:
            if r["market_value"] is None:
                class_missing_prices[cls] += 1
                classification_missing[cls][r["classification"]] += 1
            else:
                class_current_values[cls] += r["market_value"]
                classification_current[cls][r["classification"]] += r["market_value"]

    if cash > 0 or target_cash_pct > 0:
        class_current_values["cash"] += cash
        class_target_weights["cash"] += max(_f(target_cash_pct), 0.0)

    for r in rows:
        class_value = class_current_values.get(r["asset_class"], 0.0)
        class_target = class_target_weights.get(r["asset_class"], 0.0)
        class_complete = class_missing_prices.get(r["asset_class"], 0) == 0
        current_value = r["market_value"]
        r["current_weight_pct"] = (
            _pct(current_value, total_market_value)
            if allocation_complete and total_market_value is not None and current_value is not None else None
        )
        r["within_class_current_pct"] = (
            _pct(current_value, class_value)
            if class_complete and current_value is not None else None
        )
        r["within_class_target_pct"] = _pct(r["effective_target_weight_pct"], class_target) if class_target > 0 else None
        r["target_value"] = (
            total_market_value * r["effective_target_weight_pct"] / 100.0
            if total_market_value is not None and total_market_value > 0 else None
        )
        if r["target_value"] is not None and current_value is not None:
            r["rebalance_value"] = r["target_value"] - current_value
            r["rebalance_quantity"] = (
                r["rebalance_value"] / r["current_price"]
                if r["current_price"] and r["current_price"] > 0 else None
            )
        else:
            r["rebalance_value"] = None
            r["rebalance_quantity"] = None
        r["weight_gap_pct"] = (
            r["effective_target_weight_pct"] - r["current_weight_pct"]
            if r["current_weight_pct"] is not None else None
        )

    class_rows = []
    all_classes = sorted(set(class_current_values) | set(class_target_weights) | set(class_missing_prices))
    for cls in all_classes:
        current_value_known = class_current_values.get(cls, 0.0)
        complete = class_missing_prices.get(cls, 0) == 0
        current_value = current_value_known if complete else None
        current_weight = (
            _pct(current_value_known, total_market_value)
            if allocation_complete and total_market_value is not None else None
        )
        target_weight = class_target_weights.get(cls, 0.0)
        class_rows.append({
            "asset_class": cls,
            "asset_class_label": ASSET_CLASS_LABELS.get(cls, cls.upper()),
            "current_value": current_value,
            "known_current_value": current_value_known,
            "current_weight_pct": current_weight,
            "target_weight_pct": target_weight,
            "gap_pct": target_weight - current_weight if current_weight is not None else None,
            "missing_price_positions": class_missing_prices.get(cls, 0),
        })

    sector_rows = []
    all_sector_classes = sorted(set(classification_current) | set(classification_target) | set(classification_missing))
    for cls in all_sector_classes:
        class_value = class_current_values.get(cls, 0.0)
        class_target = class_target_weights.get(cls, 0.0)
        class_complete = class_missing_prices.get(cls, 0) == 0
        names = sorted(set(classification_current[cls]) | set(classification_target[cls]) | set(classification_missing[cls]))
        for name in names:
            value_known = classification_current[cls].get(name, 0.0)
            subgroup_complete = classification_missing[cls].get(name, 0) == 0
            target_global = classification_target[cls].get(name, 0.0)
            sector_rows.append({
                "asset_class": cls,
                "asset_class_label": ASSET_CLASS_LABELS.get(cls, cls.upper()),
                "classification": name,
                "current_value": value_known if subgroup_complete else None,
                "known_current_value": value_known,
                "within_class_current_pct": _pct(value_known, class_value) if class_complete else None,
                "global_current_pct": _pct(value_known, total_market_value) if allocation_complete and total_market_value is not None else None,
                "target_global_pct": target_global,
                "within_class_target_pct": _pct(target_global, class_target) if class_target > 0 else None,
                "missing_price_positions": classification_missing[cls].get(name, 0),
            })

    total_target = sum(r["effective_target_weight_pct"] for r in rows) + max(_f(target_cash_pct), 0.0)
    priced_held_count = held_count - missing_price_count
    price_coverage_pct = _pct(priced_held_count, held_count) if held_count else 100.0
    return {
        "summary": {
            "market_value": None if total_market_value is None else round(total_market_value, 2),
            "known_market_value": round(held_market_value_known + cash, 2),
            "invested_market_value": None if not allocation_complete else round(held_market_value_known, 2),
            "known_invested_market_value": round(held_market_value_known, 2),
            "cash_balance": round(cash, 2),
            "cost_basis": None if missing_average_price_count else round(held_cost_known, 2),
            "known_cost_basis": round(held_cost_known, 2),
            "unrealized_pnl": None if total_pnl is None else round(total_pnl, 2),
            "unrealized_pnl_pct": None if total_pnl_pct is None else round(total_pnl_pct, 4),
            "held_positions": held_count,
            "missing_price_positions": missing_price_count,
            "missing_average_price_positions": missing_average_price_count,
            "price_coverage_pct": None if price_coverage_pct is None else round(price_coverage_pct, 2),
            "allocation_complete": allocation_complete,
            "pnl_complete": pnl_complete,
            "target_total_pct": round(total_target, 4),
            "target_is_balanced": abs(total_target - 100.0) <= 0.05,
        },
        "positions": rows,
        "class_allocation": class_rows,
        "sector_allocation": sector_rows,
    }
