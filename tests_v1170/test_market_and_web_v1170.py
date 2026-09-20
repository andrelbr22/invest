from datetime import datetime, timedelta, timezone
from pathlib import Path

from investment_engine.data.providers.market_dashboard import MarketDashboardService


ROOT = Path(__file__).resolve().parents[1]


def test_ifix_falls_back_to_xfix_and_keeps_all_standard_windows():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    bars = [
        {"timestamp": start + timedelta(days=index), "adjusted_close": 100 + index, "close": 100 + index}
        for index in range(300)
    ]

    class Prices:
        def fetch(self, symbol, **_kwargs):
            return bars if symbol == "XFIX11" else []

    result = MarketDashboardService(prices=Prices())._yahoo_metric(
        "IFIX", ["^IFIX", "IFIX.SA", "XFIX11"]
    )
    assert result["ticker"] == "XFIX11"
    assert result["proxy"] is True
    assert all(result["variations"][period] is not None for period in ("1d", "1w", "1m", "1y"))


def test_asset_dialog_and_analysis_controls_are_complete():
    index = (ROOT / "investment_engine" / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "investment_engine" / "web" / "static" / "app.css").read_text(encoding="utf-8")
    assert 'id="asset-dialog-content" class="asset-dialog-content"' in index
    assert "94dvh" in styles
    for text in (
        "below-barsi", "ibov-membership", "company-sizes",
        "volume-daily-ma9", "column-picker", "backtest_leaders",
        'name="strategy_ids"',
    ):
        assert text in script


def test_staging_is_isolated_and_production_requires_promotion():
    compose = (ROOT / "docker-compose.oracle-web.yml").read_text(encoding="utf-8")
    caddy = (ROOT / "deployment" / "Caddyfile.oracle-micro.example").read_text(encoding="utf-8")
    update = (ROOT / "deployment" / "update-staging-from-github.sh").read_text(encoding="utf-8")
    promote = (ROOT / "deployment" / "promote-staging-to-production.sh").read_text(encoding="utf-8")
    assert "DATABASE_NAME_OVERRIDE: investment_engine_staging" in compose
    assert "handle_path /testefdi/*" in caddy
    assert "build staging" in update
    assert "up -d --no-deps --force-recreate staging" in update
    assert "docker tag \"${STAGING_IMAGE}\" \"${PRODUCTION_IMAGE}\"" in promote
    assert "up -d --no-deps --force-recreate app" in promote
