from copy import deepcopy
from pathlib import Path

import pytest

from investment_engine.core.portfolio.service import (
    build_consolidated_allocation_hierarchy,
    build_portfolio_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]


def position(ticker, asset_type, value, *, sector=None, segment=None, current_price=10):
    return {
        "ticker": ticker,
        "asset_type": asset_type,
        "stage": "position",
        "quantity": value / current_price,
        "average_price": current_price,
        "current_price": current_price,
        "target_weight_pct": 0,
        "sector": sector,
        "segment": segment,
    }


def test_hierarchy_preserves_snapshot_and_builds_two_exclusive_levels():
    snapshot = build_portfolio_snapshot([
        position("BANC3", "stock", 600, sector="Financeiro", segment="Bancos"),
        position("VARE3", "stock", 400, sector="Consumo cíclico", segment="Varejo"),
        position("SHOP11", "fii", 500, sector="Imobiliário", segment="Shoppings"),
    ], cash_balance=100)
    original = deepcopy(snapshot)

    hierarchy = build_consolidated_allocation_hierarchy(snapshot)

    assert snapshot == original
    assert hierarchy["known_total_value"] == 1600
    assert hierarchy["allocation_complete"] is True
    assert sum(item["value"] for item in hierarchy["types"]) == 1600

    stocks = next(item for item in hierarchy["types"] if item["id"] == "stock")
    assert stocks["value"] == 1000
    assert {item["label"] for item in stocks["breakdown"]} == {"Financeiro", "Consumo cíclico"}
    assert {item["dimension"] for item in stocks["breakdown"]} == {"sector"}
    assert sum(item["value"] for item in stocks["breakdown"]) == stocks["value"]
    assert sum(item["within_type_weight_pct"] for item in stocks["breakdown"]) == pytest.approx(100)

    fiis = next(item for item in hierarchy["types"] if item["id"] == "fii")
    assert fiis["breakdown"][0]["label"] == "Shoppings"
    assert fiis["breakdown"][0]["dimension"] == "segment"

    cash = next(item for item in hierarchy["types"] if item["id"] == "cash")
    assert cash["breakdown"][0]["label"] == "Disponível"


def test_custom_investments_merge_canonical_types_and_prefer_segment():
    snapshot = build_portfolio_snapshot([
        position("RFIX11", "fixed_income", 200, sector="Crédito privado"),
    ])
    custom = [
        {
            "allocation_group": "  RENDA   FIXA ",
            "category_label": "CDB",
            "sector": "Bancário",
            "segment": "Pós-fixado",
            "current_value": 300,
        },
        {
            "allocation_group": "Fundos",
            "category_label": "Fundo multimercado",
            "sector": "Fundos",
            "segment": None,
            "current_value": 250,
        },
        {
            "allocation_group": "Previdência",
            "category_label": "Previdência privada",
            "sector": None,
            "segment": None,
            "current_value": 150,
        },
    ]

    hierarchy = build_consolidated_allocation_hierarchy(snapshot, custom)

    fixed_income = next(item for item in hierarchy["types"] if item["id"] == "fixed_income")
    assert fixed_income["value"] == 500
    assert {item["label"] for item in fixed_income["breakdown"]} == {
        "Crédito privado", "Pós-fixado",
    }
    post_fixed = next(item for item in fixed_income["breakdown"] if item["label"] == "Pós-fixado")
    assert post_fixed["dimension"] == "segment"
    assert post_fixed["sector"] == "Bancário"
    assert post_fixed["segment"] == "Pós-fixado"
    assert next(item for item in hierarchy["types"] if item["id"] == "funds")["value"] == 250
    pension = next(item for item in hierarchy["types"] if item["id"] == "pension")
    assert pension["breakdown"][0]["dimension"] == "category"


def test_missing_quote_stays_explicit_and_is_not_counted_as_zero_value_slice():
    missing = position("MISS34", "bdr", 100, sector="Tecnologia")
    missing["current_price"] = None
    snapshot = build_portfolio_snapshot([
        position("GOOD3", "stock", 100, sector="Financeiro"),
        missing,
    ])

    hierarchy = build_consolidated_allocation_hierarchy(snapshot)

    assert hierarchy["allocation_complete"] is False
    assert hierarchy["missing_price_positions"] == 1
    assert hierarchy["known_total_value"] == 100
    bdr = next(item for item in hierarchy["types"] if item["id"] == "bdr")
    assert bdr["value"] == 0
    assert bdr["weight_pct"] == 0
    assert bdr["missing_price_positions"] == 1
    assert bdr["breakdown"][0]["value"] == 0
    assert bdr["breakdown"][0]["within_type_weight_pct"] is None


def test_labels_are_normalized_without_duplicate_breakdown_slices():
    snapshot = build_portfolio_snapshot([
        position("ONE3", "stock", 100, sector=" Financeiro "),
        position("TWO3", "stock", 100, sector="financeiro"),
    ])

    hierarchy = build_consolidated_allocation_hierarchy(snapshot)
    stocks = next(item for item in hierarchy["types"] if item["id"] == "stock")

    assert len(stocks["breakdown"]) == 1
    assert stocks["breakdown"][0]["label"] == "Financeiro"
    assert stocks["breakdown"][0]["value"] == 200


def test_portfolio_api_keeps_legacy_payload_and_adds_hierarchy():
    source = (ROOT / "investment_engine" / "api" / "app.py").read_text(encoding="utf-8")

    assert 'snap["consolidated_allocation"] = consolidated_allocation' in source
    assert 'snap["consolidated_allocation_hierarchy"] = build_consolidated_allocation_hierarchy(snap, custom)' in source
