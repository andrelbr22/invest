from pathlib import Path
import inspect

from fastapi.testclient import TestClient

from investment_engine.api.app import (
    _request_email,
    app,
    market_dashboard_comparison,
    market_dashboard_headlines,
    official_investor_calendar,
    portfolio_dividend_calendar,
    relevant_facts_feed,
)
from investment_engine.core.observability import ROUTE_LATENCIES
from investment_engine.infrastructure.config import settings


ROOT = Path(__file__).resolve().parents[1]


def test_navigation_get_routes_do_not_enqueue_or_commit():
    for endpoint in (
        market_dashboard_headlines,
        market_dashboard_comparison,
        official_investor_calendar,
        relevant_facts_feed,
        portfolio_dividend_calendar,
    ):
        source = inspect.getsource(endpoint)
        assert "enqueue_refresh(" not in source
        assert ".commit()" not in source


def test_navigation_caches_cover_normal_tab_switching():
    assert settings.access_policy_cache_ttl_seconds >= 60
    assert settings.analysis_preset_cache_ttl_seconds >= 60
    assert settings.shared_response_cache_ttl_seconds >= 60
    assert settings.screener_response_cache_ttl_seconds >= 120


def test_browser_reports_real_panel_time_without_database_write():
    app.dependency_overrides[_request_email] = lambda: "owner@example.com"
    try:
        response = TestClient(app).post(
            "/operations/client-performance",
            json={
                "panel": "analysis",
                "duration_ms": 842.5,
                "success": True,
                "cache_state": "cold",
            },
        )
        assert response.status_code == 204
        metrics = {item["key"]: item for item in ROUTE_LATENCIES.snapshot()["categories"]}
        assert metrics["panel_analysis"]["count"] >= 1
    finally:
        app.dependency_overrides.pop(_request_email, None)


def test_browser_parallelizes_catalog_and_preserves_stale_data():
    javascript = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "const [presetPayload,custom]=await Promise.all" in javascript
    assert "reportPanelPerformance(\"analysis\"" in javascript
    assert 'cacheTtlMs:120000' in javascript
    assert 'cacheTtlMs:60000,bypassCache:true' not in javascript

