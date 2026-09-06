from types import SimpleNamespace
from uuid import uuid4

import pytest

from investment_engine.core.screening.advanced import (
    advanced_screen,
    row_from_orm,
    valuation_flags_pass,
)


def _asset(ticker: str, *, asset_type: str = "stock", sector: str = "energia", segment=None):
    return SimpleNamespace(
        id=uuid4(), ticker=ticker, name=ticker, asset_type=asset_type,
        sector=sector, industry=None, segment=segment,
        market_cap_category="large", metadata_json={},
    )


def _fund(*, price=100, pe=10, pbv=2, dy=8, normalized_dividend=20):
    return SimpleNamespace(
        price=price, pe=pe, pbv=pbv, dividend_yield_pct=dy,
        daily_liquidity=2_000_000,
        raw_payload={"normalized_dividend_per_share": normalized_dividend},
    )


def _assumptions():
    return {
        "economic_value": {
            "scenarios": {
                "conservative": {"required_return_pct": 15, "growth_pct": 2},
                "base": {"required_return_pct": 13, "growth_pct": 3},
                "optimistic": {"required_return_pct": 11, "growth_pct": 4},
            },
            "margin_of_safety_pct": 10,
        }
    }


def test_row_exposes_four_canonical_families_and_keeps_legacy_fields():
    row = row_from_orm(_asset("TEST3"), _fund(price=20, pe=8, pbv=1.2, dy=9), None, None)
    fundamentals = row["fundamentals"]

    assert list(fundamentals["valuation_methods"]) == [
        "graham_reference", "dividend_yield_ceiling", "relative_peers", "economic_value",
    ]
    assert fundamentals["graham_reference_status"] == "valid"
    assert fundamentals["dividend_yield_ceiling_status"] == "valid"
    assert fundamentals["relative_peers_status"] == "insufficient_data"
    assert fundamentals["economic_value_status"] == "insufficient_data"
    assert fundamentals["barsi_ceiling_price"] == pytest.approx(30)
    assert fundamentals["dividend_yield_ceiling_value"] == pytest.approx(30)
    assert fundamentals["valuation_methods"]["dividend_yield_ceiling"]["method"] == "dividend_yield_ceiling_ttm"


def test_valuation_filter_supports_legacy_aliases_all_any_and_upside_thresholds():
    fund = {
        "price": 100, "pe": 10, "pbv": 2, "dividend_yield_pct": 8,
        "valuation_methods": {
            "relative_peers": {"status": "valid", "value": 120, "upside_pct": 20},
            "economic_value": {"status": "valid", "value": 90, "upside_pct": -10},
        },
    }
    assert valuation_flags_pass(fund, {"below_graham": True}) is True
    assert valuation_flags_pass(fund, {"below_barsi_6pct": True}) is True
    assert valuation_flags_pass(fund, {"below_relative_value": True}) is True
    assert valuation_flags_pass(
        fund, {"below_relative_value": True, "below_economic_value": True, "logic": "all"},
    ) is False
    assert valuation_flags_pass(
        fund, {"below_relative_value": True, "below_economic_value": True, "logic": "any"},
    ) is True
    assert valuation_flags_pass(
        fund,
        {"below_relative_value": True, "minimum_upside_pct": {"relative_peers": 25}},
    ) is False
    fund["valuation_methods"]["relative_peers"]["status"] = "insufficient_data"
    assert valuation_flags_pass(fund, {"below_relative_value": True}) is False
    with pytest.raises(ValueError, match="invalid_valuation_logic"):
        valuation_flags_pass(fund, {"below_graham": True, "logic": "xor"})


def test_advanced_screen_calculates_relative_and_explicit_gordon_and_fails_closed_without_assumptions():
    rows = [
        (_asset(f"EMP{i}3"), _fund(pe=pe, pbv=pbv), None, None)
        for i, (pe, pbv) in enumerate([(8, 1.6), (9, 1.8), (10, 2), (11, 2.2), (12, 2.4), (13, 2.6)])
    ]

    class Repo:
        def latest_universe(self, *, asset_type, limit):
            assert asset_type == "stock"
            assert limit == 1200
            return rows

        def price_histories_batch(self, _ids):
            raise AssertionError("history must not be loaded for a valuation-only request")

    complete = advanced_screen(
        Repo(), asset_type="stock", include_technical_columns=False,
        valuation_assumptions=_assumptions(), limit=20,
    )
    assert len(complete["rows"]) == 6
    assert complete["meta"]["valuation_families"] == [
        "graham_reference", "dividend_yield_ceiling", "relative_peers", "economic_value",
    ]
    for row in complete["rows"]:
        assert row["relative_peers_status"] == "valid"
        assert row["relative_peers_value"] is not None
        assert row["economic_value_status"] == "valid"
        assert row["economic_value"] is not None
        assert row["valuation_methods"]["economic_value"]["scenarios"]["base"]["value"] > 0

    single = advanced_screen(
        Repo(), asset_type="stock", include_technical_columns=False,
        allowed_tickers=["EMP03"], valuation_assumptions=_assumptions(), limit=20,
    )
    assert len(single["rows"]) == 1
    assert single["rows"][0]["relative_peers_status"] == "valid"
    assert single["rows"][0]["valuation_methods"]["relative_peers"]["quality"]["sample_size"] == 5

    filtered = advanced_screen(
        Repo(), asset_type="stock", include_technical_columns=False,
        valuation_flags={"below_economic_value": True},
        valuation_assumptions=_assumptions(), limit=20,
    )
    assert len(filtered["rows"]) == 6

    missing_assumptions = advanced_screen(
        Repo(), asset_type="stock", include_technical_columns=False,
        valuation_flags={"below_economic_value": True}, limit=20,
    )
    assert missing_assumptions["rows"] == []
    assert missing_assumptions["meta"]["valuation_filter_active"] == ["economic_value"]
