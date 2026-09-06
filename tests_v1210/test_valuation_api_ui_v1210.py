from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from investment_engine.api.app import (
    AdvancedScreenRequest,
    _authorized_valuation_row,
    _can_read_valuation_method,
    _valuation_method_permission,
)
from investment_engine.data.providers.fundamentus import FundamentusStockProvider


ROOT = Path(__file__).resolve().parents[1]


def _economic_assumptions():
    return {
        "economic_value": {
            "use_ttm_dividend": True,
            "margin_of_safety_pct": 20,
            "scenarios": {
                "conservative": {"required_return_pct": 16, "growth_pct": 1},
                "base": {"required_return_pct": 13, "growth_pct": 3},
                "optimistic": {"required_return_pct": 11, "growth_pct": 4},
            },
        },
        "relative_peers": {"minimum_peers": 5, "winsor_limits": [0.1, 0.9]},
    }


def test_api_validates_four_method_options_and_explicit_economic_scenarios():
    request = AdvancedScreenRequest(
        asset_type="stock",
        valuation_flags={
            "below_graham": True,
            "below_dividend_yield_ceiling": True,
            "below_relative_value": True,
            "below_economic_value": True,
            "valuation_logic": "all",
            "minimum_upside_pct": 10,
        },
        valuation_assumptions=_economic_assumptions(),
    )
    assert request.valuation_flags["logic"] == "all"
    assert request.valuation_assumptions["relative_peers"]["minimum_peers"] == 5
    assert set(request.valuation_assumptions["economic_value"]["scenarios"]) == {
        "conservative", "base", "optimistic",
    }

    with pytest.raises(ValidationError, match="three_explicit_scenarios_required"):
        AdvancedScreenRequest(
            valuation_assumptions={
                "economic_value": {
                    "scenarios": {
                        "base": {"required_return_pct": 13, "growth_pct": 3},
                    }
                }
            }
        )
    with pytest.raises(ValidationError, match="scenario_assumptions_invalid"):
        AdvancedScreenRequest(
            valuation_assumptions={
                "economic_value": {
                    "scenarios": {
                        "conservative": {"required_return_pct": 12, "growth_pct": 12},
                        "base": {"required_return_pct": 13, "growth_pct": 3},
                        "optimistic": {"required_return_pct": 11, "growth_pct": 4},
                    }
                }
            }
        )


def test_authorization_strips_each_valuation_family_from_flat_and_nested_payloads():
    row = {
        "ticker": "TEST3",
        "graham_number": 10,
        "graham_upside_pct": 1,
        "barsi_ceiling_price": 11,
        "barsi_upside_pct": 2,
        "relative_peers_value": 12,
        "relative_peers_upside_pct": 3,
        "economic_value": 13,
        "economic_value_upside_pct": 4,
        "valuation_methods": {
            "graham_reference": {"status": "valid"},
            "dividend_yield_ceiling": {"status": "valid"},
            "relative_peers": {"status": "valid"},
            "economic_value": {"status": "valid"},
        },
    }
    authorized = _authorized_valuation_row(
        dict(row),
        {"can_use_relative_valuation": True},
    )
    assert authorized["ticker"] == "TEST3"
    assert authorized["relative_peers_value"] == 12
    assert set(authorized["valuation_methods"]) == {"relative_peers"}
    assert "graham_number" not in authorized
    assert "barsi_ceiling_price" not in authorized
    assert "economic_value" not in authorized

    alb = _authorized_valuation_row(dict(row), {"can_use_alb_analysis": True})
    assert set(alb["valuation_methods"]) == {
        "graham_reference", "dividend_yield_ceiling", "relative_peers", "economic_value",
    }


def test_legacy_valuation_history_endpoint_cannot_bypass_new_permissions():
    assert _valuation_method_permission("graham_number") == "can_use_graham_valuation"
    assert _valuation_method_permission("bazin") == "can_use_dividend_ceiling"
    assert _valuation_method_permission("relative_valuation") == "can_use_relative_valuation"
    assert _valuation_method_permission("gordon_growth") == "can_use_economic_valuation"
    assert not _can_read_valuation_method("graham_number", {})
    assert _can_read_valuation_method("graham_number", {"can_use_graham_valuation": True})
    assert _can_read_valuation_method("unknown_old_method", {"is_owner": True})
    assert not _can_read_valuation_method("unknown_old_method", {"can_view_market": True})


def test_fundamentus_parser_maps_roic_and_roe_to_their_distinct_columns():
    cells = ["0"] * 21
    cells[0] = "TEST3"
    cells[1] = "10,00"
    cells[2] = "5,00"
    cells[3] = "1,20"
    cells[5] = "8,00%"
    cells[15] = "12,34%"
    cells[16] = "21,43%"
    html = (
        '<table id="resultado"><tr><th>Cabeçalho</th></tr><tr>'
        + "".join(f"<td>{value}</td>" for value in cells)
        + "</tr></table>"
    )

    class Response:
        text = html

    class Http:
        def get(self, _url):
            return Response()

    row = FundamentusStockProvider(http=Http()).fetch()[0]
    assert row["roic_pct"] == pytest.approx(12.34)
    assert row["roe_pct"] == pytest.approx(21.43)
    assert row["roic_pct"] != row["roe_pct"]


def test_browser_exposes_all_four_methods_permissions_parameters_and_nd_state():
    source = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    for text in (
        "Número de Graham",
        "Preço-teto por dividend yield-alvo",
        "Valuation relativo por pares comparáveis",
        "Valor econômico (Gordon com cenários explícitos)",
        "can_use_relative_valuation",
        "can_use_economic_valuation",
        "strategy_params",
        "MMS 8",
        "MME 9",
        "MMS 200",
        "Ação agora",
        "Posição",
    ):
        assert text in source
    assert "N/D" in source
    assert "Método sem dados suficientes" in source or "método sem dados suficientes" in source
    strategy_source = (ROOT / "investment_engine" / "core" / "backtesting" / "strategies.py").read_text(encoding="utf-8")
    for strategy_id in ("supertrend_atr", "dual_momentum_relative", "bollinger_squeeze_breakout"):
        assert strategy_id in strategy_source


def test_no_inline_backtest_route_is_left_unprotected_for_regular_users():
    source = (ROOT / "investment_engine" / "api" / "app.py").read_text(encoding="utf-8")
    for route in ('@app.post("/backtests/run")', '@app.post("/backtests/compare")', '@app.post("/backtests/basket")'):
        position = source.index(route)
        block = source[position : position + 900]
        assert "_require_owner_inline_backtest(access)" in block
