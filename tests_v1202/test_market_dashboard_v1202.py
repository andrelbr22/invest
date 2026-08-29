from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from investment_engine import __version__
from investment_engine.api.app import app
from investment_engine.data.providers.market_dashboard import MarketDashboardService


def test_release_line_and_routes_keep_v1202_capabilities():
    assert __version__.startswith("1.20.")
    paths = {route.path for route in app.routes}
    assert "/market-dashboard/comparison" in paths
    assert "/market-dashboard/comparison/refresh" in paths


def test_monthly_rate_points_use_compound_interest():
    rows = [
        (datetime(2026, 1, 2).date(), 1.0),
        (datetime(2026, 1, 3).date(), 2.0),
        (datetime(2026, 2, 2).date(), 1.0),
    ]
    points = MarketDashboardService._monthly_rate_points(rows)
    assert points[0]["value"] == pytest.approx(103.02)
    assert points[1]["value"] == pytest.approx(104.0502)


def test_di_contract_expiry_and_252_day_axis():
    service = MarketDashboardService(now=datetime(2026, 8, 28, tzinfo=timezone.utc))
    expiry = service._di_expiry("DI1F27")
    assert expiry.isoformat() == "2027-01-04"
    assert service._business_days(service.now.date(), expiry) > 0


def test_calendar_includes_brazil_and_us_elections():
    class OfflineCalendar(MarketDashboardService):
        def _bls_calendar(self):
            return []

    events = OfflineCalendar(now=datetime(2026, 8, 28, tzinfo=timezone.utc)).calendar()
    dates = {(item["region"], item["date"]) for item in events if item["category"] == "Eleições"}
    assert ("Brasil", "2026-10-04") in dates
    assert ("Estados Unidos", "2026-11-03") in dates


def test_market_ui_replaces_sp500_card_and_exposes_comparison():
    root = Path(__file__).resolve().parents[1]
    javascript = (root / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    html = (root / "investment_engine" / "web" / "index.html").read_text(encoding="utf-8")
    summary = javascript[javascript.index("function renderMarketSummary"):javascript.index("function marketTable")]
    assert 'metricCard("IPCA • 12 meses"' in summary
    assert 'metricCard("S&P 500"' not in summary
    assert 'data-tab="comparison"' in html
    assert 'curve.title || "Curva de juros brasileira"' in javascript


def test_price_history_rebases_first_observation_to_100():
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    bars = [
        {"timestamp": now - timedelta(days=31), "close": 20},
        {"timestamp": now, "close": 25},
    ]
    points = MarketDashboardService._monthly_price_points(bars)
    assert points[0]["value"] == 100
    assert points[-1]["value"] == 125
