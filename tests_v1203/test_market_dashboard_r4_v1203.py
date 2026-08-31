from datetime import datetime, timedelta, timezone
from pathlib import Path

from investment_engine.data.providers.market_dashboard import (
    HISTORICAL_COMPARISON_ORDER,
    MarketDashboardService,
)


ROOT = Path(__file__).resolve().parents[1]


class _OfflinePrices:
    def fetch(self, ticker, *, start, end):
        return [
            {
                "timestamp": end - timedelta(days=30 * offset),
                "adjusted_close": 100 + offset,
                "close": 100 + offset,
            }
            for offset in reversed(range(8))
        ]


def test_comparison_has_the_approved_order_without_duplicates(monkeypatch):
    service = MarketDashboardService(
        prices=_OfflinePrices(),
        now=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        service,
        "_sgs_between",
        lambda _series, start, _end: [
            (start + timedelta(days=30 * offset), 0.5) for offset in range(8)
        ],
    )

    payload = service.historical_comparison(years=1)
    codes = [item["code"] for item in payload["series"]]

    assert codes == HISTORICAL_COMPARISON_ORDER
    assert len(codes) == len(set(codes)) == 28
    by_code = {item["code"]: item for item in payload["series"]}
    assert by_code["IMAB"]["proxy"] is True
    assert "IMAB11" in by_code["IMAB"]["note"]
    assert by_code["IRFM"]["proxy"] is True
    assert "IRF-M P2" in by_code["IRFM"]["note"]


def test_market_dashboard_r4_packages_the_approved_layout_and_defaults():
    script = (ROOT / "investment_engine/web/static/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "investment_engine/web/static/app.css").read_text(encoding="utf-8")
    html = (ROOT / "investment_engine/web/index.html").read_text(encoding="utf-8")

    assert 'comparisonSelected: ["CDI","IBOV","IFIX"]' in script
    assert "global-market-layout" in script
    assert "global-market-stack" in script
    assert "grid-template-rows: repeat(2,minmax(0,1fr))" in styles
    assert "grid-template-columns: repeat(4,minmax(0,1fr))" in styles
    assert 'aria-label="Indicadores para comparação"' in script
    assert '>Criptos e Câmbio</button>' in html
    assert ">Câmbio e cripto</button>" not in html
