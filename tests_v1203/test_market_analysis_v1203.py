from pathlib import Path
from importlib import import_module

from investment_engine.api.app import (
    AdvancedScreenRequest,
    _preset_screen_configuration,
    _validated_saved_filters,
    app,
    screen_advanced,
)
from investment_engine import __version__
from investment_engine.core.strategies.presets import FII_STRATEGIES, STOCK_STRATEGIES


ROOT = Path(__file__).resolve().parents[1]
api_module = import_module("investment_engine.api.app")


def test_system_presets_expose_their_original_criteria_to_the_interface():
    cnpi = _preset_screen_configuration("stock", STOCK_STRATEGIES["cnpi"])
    assert cnpi["fundamental_filters"]["roe_pct"] == {"min": 10.0, "max": None}
    assert cnpi["fundamental_filters"]["pe"] == {"min": 0.1, "max": 20.0}
    assert cnpi["limit"] == 50

    fii = _preset_screen_configuration("fii", FII_STRATEGIES["default"])
    assert fii["fundamental_filters"]["vacancy_pct"]["max"] == 15.0
    assert fii["fundamental_filters"]["daily_liquidity"]["min"] == 500_000.0


def test_personal_analysis_preserves_fundamental_technical_and_universe_filters():
    configuration = {
        "asset_type": "stock",
        "fundamental_filters": {"pe": {"min": 1, "max": 12}},
        "score_filters": {"quality_score": {"min": 70}},
        "valuation_flags": {"below_graham": True, "below_barsi_6pct": True},
        "technical_filters": {
            "daily_trend": "up",
            "rsi14": {"min": 35, "max": 65},
            "volume_daily_above_ma9": True,
        },
        "trend_period": 20,
        "pivot_timeframe": "weekly",
        "company_sizes": ["blue_chip", "mid_cap"],
        "ibov_membership": "inside",
        "limit": 25,
    }
    saved = _validated_saved_filters("stock", configuration)
    assert saved["schema_version"] == 2
    restored = saved["configuration"]
    assert restored["technical_filters"]["rsi14"] == {"min": 35.0, "max": 65.0}
    assert restored["technical_filters"]["volume_daily_above_ma9"] is True
    assert restored["valuation_flags"]["below_barsi_6pct"] is True
    assert restored["company_sizes"] == ["large", "mid"]
    assert restored["ibov_membership"] == "inside"


def test_old_personal_filters_remain_compatible():
    saved = _validated_saved_filters("stock", {"roe_min": 12, "pe_max": 15})
    assert saved["roe_min"] == 12
    assert saved["pe_max"] == 15
    assert "schema_version" not in saved


def test_ibov_provider_failure_does_not_interrupt_the_complete_screen(monkeypatch):
    def provider_failure(_code):
        raise RuntimeError("b3 unavailable")

    captured = {}

    def fake_screen(_repo, **kwargs):
        captured.update(kwargs)
        return {"rows": [{"ticker": "TEST3"}], "meta": {}}

    monkeypatch.setattr(api_module, "_index_portfolio", provider_failure)
    monkeypatch.setattr(api_module, "advanced_screen", fake_screen)
    result = screen_advanced(
        AdvancedScreenRequest(asset_type="stock", ibov_membership="inside"),
        _access={"can_use_advanced_filters": True},
        db=object(),
    )

    assert result["rows"] == [{"ticker": "TEST3"}]
    assert captured["ibov_membership"] == "any"
    assert result["meta"]["requested_ibov_membership"] == "inside"
    assert result["meta"]["effective_ibov_membership"] == "any"
    assert "B3 não respondeu" in result["meta"]["warnings"][0]


def test_presets_endpoint_and_new_analysis_experience_are_packaged():
    assert __version__ == "1.20.3"
    paths = {route.path for route in app.routes}
    assert "/screen/presets" in paths
    html = (ROOT / "investment_engine/web/index.html").read_text(encoding="utf-8")
    script = (ROOT / "investment_engine/web/static/app.js").read_text(encoding="utf-8")
    assert "Guia dos indicadores e notas" in html
    assert "Gravar análise personalizada" in html
    assert "Salvar alterações da análise personalizada" in script
    assert "3 melhores backtests" in script
    assert "Médias de 20, 50 e 200 períodos" in script
