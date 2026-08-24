from datetime import datetime, timezone
from pathlib import Path

import requests

from investment_engine.core.backtesting.study import build_strategy_configuration_catalog
from investment_engine.data.providers.news import MarketNewsService


def _configuration_record(ticker, fast_period=9, *, score=80, total_return=12):
    return {
        "ticker": ticker,
        "strategy_id": "custom_ma_cross",
        "strategy_name": "Cruzamento de médias personalizado",
        "ranking_score": score,
        "sample_status": "adequate",
        "current_signal": "buy",
        "created_at": datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
        "requested_start": datetime(2021, 8, 24, tzinfo=timezone.utc),
        "requested_end": datetime(2026, 8, 24, tzinfo=timezone.utc),
        "parameters": {
            "strategy": {
                "fast_period": fast_period, "slow_period": 50,
                "fast_type": "ema", "slow_type": "sma",
            },
            "filters": {"adx_min": 25.0},
            "financial": {"apply_cash_yield": True, "cash_yield_rate_pct": 10.0},
        },
        "assumptions": {
            "initial_capital": 10000.0, "fee_pct": 0.1,
            "slippage_pct": 0.05, "risk_free_rate_pct": 10.0,
        },
        "metrics": {
            "total_return_pct": total_return, "cagr_pct": 4.0,
            "sharpe_ratio": 0.8, "max_drawdown_pct": -12.0,
            "profit_factor": 1.6, "win_rate_pct": 55.0, "closed_trades": 10,
        },
    }


def test_configuration_catalog_deduplicates_across_assets_and_aggregates_results():
    records = [
        _configuration_record("PETR4", score=80, total_return=10),
        _configuration_record("BBAS3", score=90, total_return=20),
        _configuration_record("VALE3", fast_period=20, score=70, total_return=5),
    ]
    result = build_strategy_configuration_catalog(records, strategy_id="custom_ma_cross")
    assert result["configuration_count"] == 2
    assert result["run_count"] == 3
    first = result["items"][0]
    assert first["strategy_parameters"]["fast_period"] == 9
    assert first["assets_tested"] == 2
    assert first["tickers"] == ["BBAS3", "PETR4"]
    assert first["mean_ranking_score"] == 85.0
    assert first["mean_metrics"]["mean_total_return_pct"] == 15.0
    assert first["filters"] == {"adx_min": 25.0}


class _RssResponse:
    content = b"""<?xml version='1.0' encoding='UTF-8'?>
    <rss><channel><item>
      <title>Banco do Brasil anuncia dividendos - Valor Economico</title>
      <link>https://news.google.com/articles/example</link>
      <pubDate>Mon, 24 Aug 2026 12:00:00 GMT</pubDate>
      <source>Valor Economico</source>
    </item></channel></rss>"""

    def raise_for_status(self):
        return None


def test_news_uses_rss_fallback_when_gdelt_is_unavailable():
    def http_get(url, **_kwargs):
        if "gdeltproject" in url:
            raise requests.Timeout("temporary")
        return _RssResponse()

    result = MarketNewsService(http_get=http_get).asset_news("BBAS3", "Banco do Brasil", limit=3)
    assert result["fallback_used"] is True
    assert result["provider"] == "Google News RSS"
    assert result["items"][0]["title"] == "Banco do Brasil anuncia dividendos"
    assert result["items"][0]["source"] == "Valor Economico"


def test_study_ui_has_clickable_ranking_and_configuration_endpoint():
    root = Path(__file__).resolve().parents[1]
    ui = (root / "examples" / "streamlit_v15_integrated.py").read_text(encoding="utf-8")
    api = (root / "investment_engine" / "api" / "app.py").read_text(encoding="utf-8")
    assert 'on_select="rerun",selection_mode="single-row"' in ui
    assert "Configurações usadas —" in ui
    assert 'api_get(f"/backtests/study/{strategy_id}/configurations")' in ui
    assert '@app.get("/backtests/study/{strategy_id}/configurations")' in api

