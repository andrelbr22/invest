import pytest

from investment_engine import __version__
from investment_engine.core.valuation import (
    VALUATION_FAMILIES,
    gordon_growth_scenarios,
    normalize_valuation_method,
    relative_valuation,
    valuation_applicability,
    valuation_method_metadata,
)
from investment_engine.core.valuation.dividend_target import dividend_yield_target_price
from investment_engine.core.valuation.graham import graham_number


def test_release_is_exactly_v1210_and_new_suite_is_discoverable():
    assert __version__ == "1.21.0"


def test_four_families_and_legacy_method_names_are_canonicalized():
    assert list(VALUATION_FAMILIES) == [
        "graham_reference", "dividend_yield_ceiling", "relative_peers", "economic_value",
    ]
    assert normalize_valuation_method("graham_number") == "graham_number"
    assert normalize_valuation_method("barsi_ceiling_price") == "dividend_yield_ceiling_ttm"
    assert normalize_valuation_method("dividend_yield_target") == "dividend_yield_ceiling_ttm"
    assert valuation_method_metadata("bazin").label == "Preço-teto por dividend yield-alvo (proventos de 12 meses)"
    # Existing result ids remain unchanged for API/database compatibility.
    assert graham_number(2, 10).method == "graham_number"
    assert dividend_yield_target_price(1.2, 6).method == "dividend_yield_target"


def test_applicability_fails_closed_and_never_values_futures_like_companies():
    bank = valuation_applicability("stock", "bank")
    assert bank["relative_peers"].method == "pbv_peers"
    assert bank["economic_value"].method == "fcfe_ddm"
    brick = valuation_applicability("fii", "brick")
    assert brick["graham_reference"].status == "not_applicable"
    assert brick["economic_value"].method == "nav_noi_cap_rate"
    future = valuation_applicability("future")
    assert all(rule.status == "not_applicable" for rule in future.values())
    assert future["economic_value"].method == "fair_value_cost_of_carry"
    assert all(rule.status == "not_applicable" for rule in valuation_applicability("crypto").values())


def _stock_peers():
    return [
        {"ticker": f"P{i}", "asset_type": "stock", "sector": "energia", "pe": pe, "pbv": pbv}
        for i, (pe, pbv) in enumerate([
            (8, 1.6), (9, 1.8), (10, 2.0), (11, 2.2), (12, 2.4), (1000, 99),
        ])
    ]


def test_stock_relative_valuation_uses_strict_peers_winsorization_and_scenarios():
    target = {
        "ticker": "ALVO3", "asset_type": "stock", "sector": "energia",
        "price": 100, "pe": 10, "pbv": 2,
    }
    peers = _stock_peers() + [
        {"ticker": "OUTRO3", "asset_type": "stock", "sector": "bancos", "pe": 2, "pbv": 0.2},
        {"ticker": "NEG3", "asset_type": "stock", "sector": "energia", "pe": -5, "pbv": -1},
    ]
    result = relative_valuation(target, peers)
    assert result.status == "valid"
    assert result.quality.metrics_used == ["pbv", "pe"]
    assert result.quality.metric_sample_sizes == {"pe": 6, "pbv": 6}
    assert result.metadata["comparable_peers"] == 7
    assert result.metadata["metrics"]["pe"]["winsorized_bounds"][1] < 1000
    assert result.scenarios["conservative"].value == pytest.approx(92.5)
    assert result.scenarios["base"].value == pytest.approx(105.0)
    assert result.scenarios["optimistic"].value == pytest.approx(117.5)
    assert result.scenarios["base"].upside_pct == pytest.approx(5.0)


def test_bank_relative_valuation_uses_only_bank_pbv_peers():
    target = {
        "ticker": "BANCO3", "asset_type": "stock", "asset_class": "bank",
        "sector": "financeiro", "price": 20, "pbv": 1.0, "pe": 5,
    }
    banks = [
        {
            "ticker": f"BAN{i}", "asset_type": "stock", "asset_class": "bank",
            "sector": "financeiro", "pbv": value, "pe": 20,
        }
        for i, value in enumerate((0.8, 0.9, 1.0, 1.1, 1.2))
    ]
    insurers = [
        {
            "ticker": f"SEG{i}", "asset_type": "stock", "asset_class": "insurance",
            "sector": "financeiro", "pbv": 4.0, "pe": 2,
        }
        for i in range(5)
    ]
    result = relative_valuation(target, [*banks, *insurers], asset_class="bank")

    assert result.status == "valid"
    assert result.quality.metrics_used == ["pbv"]
    assert result.metadata["comparable_peers"] == 5
    assert result.scenarios["base"].value == pytest.approx(20.0)


def test_relative_valuation_requires_minimum_comparable_sample():
    target = {"asset_type": "stock", "sector": "energia", "price": 100, "pe": 10, "pbv": 2}
    result = relative_valuation(target, _stock_peers()[:4])
    assert result.status == "insufficient_data"
    assert result.reason == "insufficient_comparable_peers"
    assert result.scenarios == {}


def test_relative_valuation_fails_closed_without_peer_classification_and_ignores_bad_optional_numbers():
    unclassified = relative_valuation(
        {"asset_type": "stock", "price": 100, "pe": 10, "pbv": 2},
        _stock_peers(),
    )
    assert unclassified.status == "insufficient_data"
    assert unclassified.reason == "target_sector_required"

    target = {
        "asset_type": "stock", "sector": "energia", "price": 100,
        "pe": 10, "pbv": 2, "ebitda_per_share": 5,
        "net_debt_per_share": "indisponível",
    }
    result = relative_valuation(target, [*_stock_peers(), None])
    assert result.status == "valid"
    assert "invalid_peer_ignored" in result.quality.warnings


def test_fii_relative_valuation_combines_pnav_and_ffo_yield_without_graham():
    target = {
        "ticker": "ALVO11", "asset_type": "fii", "segment": "logística",
        "price": 100, "pbv": 0.9, "ffo_yield_pct": 10,
    }
    peers = [
        {"ticker": f"F{i}11", "asset_type": "fii", "segment": "logística", "pbv": pbv, "ffo_yield_pct": ffo}
        for i, (pbv, ffo) in enumerate([(0.8, 8), (0.85, 9), (0.9, 10), (0.95, 11), (1.0, 12), (4, 50)])
    ]
    result = relative_valuation(target, peers)
    assert result.status == "valid"
    assert result.quality.metrics_used == ["ffo_yield_pct", "pbv"]
    assert result.scenarios["conservative"].value < result.scenarios["base"].value
    assert result.scenarios["base"].value < result.scenarios["optimistic"].value
    assert result.family_id == "relative_peers"


def test_fii_ffo_yield_is_converted_to_flow_per_share_not_inverted_as_multiple():
    target = {
        "ticker": "ALVO11", "asset_type": "fii", "segment": "logística",
        "price": 100, "ffo_yield_pct": 8,
    }
    peers = [
        {
            "ticker": f"F{i}11", "asset_type": "fii", "segment": "logística",
            "ffo_yield_pct": value,
        }
        for i, value in enumerate((8, 9, 10, 11, 12))
    ]
    result = relative_valuation(target, peers)

    assert result.status == "valid"
    # FFO/cota implícito = R$ 100 * 8% = R$ 8; ao yield mediano de
    # pares de 10%, o valor-base é R$ 80.
    assert result.scenarios["base"].value == pytest.approx(80.0)


def test_gordon_requires_explicit_complete_scenarios_and_never_uses_globals():
    missing = gordon_growth_scenarios(2.0, assumptions=None, market_price=20)
    assert missing.status == "insufficient_data"
    assert missing.reason == "three_explicit_scenarios_required"
    assert missing.scenarios == {}

    incomplete = gordon_growth_scenarios(
        2.0,
        assumptions={
            "conservative": {"required_return_pct": 15, "growth_pct": 2},
            "base": {"required_return_pct": 13, "growth_pct": 3},
        },
    )
    assert incomplete.status == "insufficient_data"

    invalid = gordon_growth_scenarios(
        "indisponível",
        assumptions={
            "conservative": {"required_return_pct": 15, "growth_pct": 2},
            "base": {"required_return_pct": 13, "growth_pct": 3},
            "optimistic": {"required_return_pct": 11, "growth_pct": 4},
        },
    )
    assert invalid.status == "insufficient_data"
    assert invalid.reason == "normalized_dividend_per_share_required"


def test_gordon_scenarios_are_ordered_auditable_and_support_explicit_margin():
    result = gordon_growth_scenarios(
        2.0,
        assumptions={
            "conservative": {"required_return_pct": 15, "growth_pct": 2},
            "base": {"required_return_pct": 13, "growth_pct": 3},
            "optimistic": {"required_return_pct": 11, "growth_pct": 4},
        },
        market_price=20,
        margin_of_safety_pct=10,
        asset_class="bank",
    )
    assert result.status == "valid"
    assert result.metadata["uses_global_defaults"] is False
    assert result.scenarios["conservative"].value < result.scenarios["base"].value
    assert result.scenarios["base"].value < result.scenarios["optimistic"].value
    assert result.scenarios["base"].value == pytest.approx((2 * 1.03 / 0.10) * 0.9)
    assert result.scenarios["base"].assumptions["required_return_pct"] == 13
