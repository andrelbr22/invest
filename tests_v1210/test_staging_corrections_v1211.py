from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import importlib

from investment_engine.api.app import (
    SavedScreeningFilterCreateRequest,
    screen_db_universe,
    screening_presets,
)
from investment_engine.core.repositories.access import PERMISSION_FIELDS, full_owner_policy
from investment_engine.core.screening.advanced import advanced_screen


ROOT = Path(__file__).resolve().parents[1]
api_module = importlib.import_module("investment_engine.api.app")


def _asset(asset_type: str):
    return SimpleNamespace(
        id=uuid4(), ticker="TEST11", name="Teste", asset_type=asset_type,
        sector=None, industry=None, segment=None, market_cap_category=None,
        metadata_json={},
    )


def test_owner_email_policy_always_contains_every_granular_permission():
    policy = full_owner_policy("ANDRELBR22@GMAIL.COM")
    assert policy["email"] == "andrelbr22@gmail.com"
    assert policy["is_owner"] is True
    assert all(policy[field] is True for field in PERMISSION_FIELDS)


def test_etf_bdr_and_future_have_three_honest_technical_presets():
    for asset_type in ("etf", "bdr", "future"):
        payload = screening_presets(asset_type=asset_type, _access={"can_view_market": True})
        assert payload["basis"] == "technical"
        items = {item["id"]: item for item in payload["items"]}
        assert set(items) == {"default", "cnpi", "alb"}
        assert items["default"]["configuration"]["asset_type"] == asset_type
        assert items["cnpi"]["configuration"]["technical_filters"]["daily_trend"] == "up"
        assert items["alb"]["configuration"]["technical_filters"]["weekly_trend"] == "up"
        assert all(item["configuration"]["fundamental_filters"] == {} for item in items.values())


def test_custom_analysis_request_accepts_every_visible_asset_tab():
    for asset_type in ("stock", "fii", "etf", "bdr", "future"):
        request = SavedScreeningFilterCreateRequest(
            asset_type=asset_type,
            name="Minha análise",
            filters={"schema_version": 2, "configuration": {"asset_type": asset_type}},
        )
        assert request.asset_type == asset_type


def test_specific_universe_endpoint_does_not_load_all_other_b3(monkeypatch):
    calls = []

    class Repository:
        def __init__(self, _db):
            pass

        def latest_universe(self, *, asset_type, limit):
            calls.append((asset_type, limit))
            return []

    monkeypatch.setattr(api_module, "AssetRepository", Repository)
    assert screen_db_universe("bdr", limit=50, access={"can_view_market": True}, db=object()) == []
    assert calls == [("bdr", 50)]


def test_non_company_valuation_fails_closed_without_class_specific_inputs():
    asset = _asset("etf")

    class Repository:
        def latest_universe(self, *, asset_type, limit):
            assert asset_type == "etf"
            return [(asset, None, None, None)]

        def price_histories_batch(self, _ids):
            raise AssertionError("history is unnecessary when technical columns are disabled")

    row = advanced_screen(
        Repository(), asset_type="etf", include_technical_columns=False, limit=1,
    )["rows"][0]
    result = row["valuation_methods"]["relative_peers"]
    assert result["status"] == "insufficient_data"
    assert result["reason"] == "etf_nav_or_premium_required"
    assert row["valuation_methods"]["economic_value"]["status"] == "insufficient_data"


def test_browser_makes_scenarios_help_and_fast_class_queries_discoverable():
    source = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="economic-assumptions" class="filter-subgroup" open' in source
    assert "Cenários do valor econômico: Conservador, Base e Otimista" in source
    assert "100 × (valor de referência ÷ preço atual − 1)" in source
    assert "valuation-mini-scenarios" in source
    assert "/screen/db/universe/${type}?limit=${state.analysisLimit}" in source
    assert "analysisResultCache" in source
    assert "state.analysisEnsureSentAt>300000" in source
    assert 'node.disabled=!supportsTechnical||Boolean(permission&&!access[permission])' in source
