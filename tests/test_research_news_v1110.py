from datetime import datetime, timezone
from pathlib import Path

from investment_engine.core.backtesting.study import build_strategy_study
from investment_engine.core.repositories.access import full_owner_policy
from investment_engine.data.providers.news import MarketNewsService


def _record(ticker, strategy, score, *, status="adequate", win_rate=50):
    return {
        "ticker": ticker,
        "strategy_id": strategy,
        "strategy_name": strategy.upper(),
        "ranking_score": score,
        "sample_status": status,
        "metrics": {"win_rate_pct": win_rate},
    }


def test_strategy_study_prioritizes_repeated_top_three_results():
    records = []
    for ticker in ("AAAA3", "BBBB3", "CCCC3", "DDDD3"):
        records.extend([
            _record(ticker, "consistent", 82),
            _record(ticker, "runner_up", 76),
            _record(ticker, "third", 70),
            _record(ticker, "weak", 40),
        ])
    # One exceptional result must not beat a strategy that is consistently good.
    records.append(_record("AAAA3", "one_hit", 99))
    result = build_strategy_study(records, top_limit=5)
    assert result["eligible_assets"] == 4
    assert result["ranking"][0]["strategy_id"] == "consistent"
    assert result["ranking"][0]["top3_count"] == 4
    assert all(row["strategy_id"] != "one_hit" for row in result["ranking"])


def test_strategy_study_excludes_insufficient_samples():
    records = [
        _record("AAAA3", "a", 90), _record("AAAA3", "b", 80), _record("AAAA3", "c", 70),
        _record("BBBB3", "a", 95, status="insufficient"),
        _record("BBBB3", "b", 80), _record("BBBB3", "c", 70), _record("BBBB3", "d", 60),
    ]
    result = build_strategy_study(records)
    assert result["excluded_insufficient_runs"] == 1
    assert result["eligible_assets"] == 2


class _Response:
    def __init__(self, articles):
        self.articles = articles

    def raise_for_status(self):
        return None

    def json(self):
        return {"articles": self.articles}


def test_news_provider_sanitizes_deduplicates_and_prioritizes_impact():
    articles = [
        {
            "title": "PETR4 anuncia dividendos e novo guidance",
            "url": "https://example.com/petr4-dividendos",
            "domain": "example.com",
            "seendate": "20260824T120000Z",
        },
        {
            "title": "PETR4 anuncia dividendos e novo guidance",
            "url": "https://duplicate.example.com/petr4-dividendos",
            "domain": "duplicate.example.com",
            "seendate": "20260824T120000Z",
        },
        {
            "title": "Mercado abre em alta nesta manhã",
            "url": "javascript:alert(1)",
            "domain": "unsafe.example",
            "seendate": "20260824T130000Z",
        },
    ]
    service = MarketNewsService(http_get=lambda *args, **kwargs: _Response(articles))
    result = service.asset_news("PETR4", "Petrobras", limit=3)
    assert len(result["items"]) == 1
    assert result["items"][0]["title"].startswith("PETR4")
    assert result["items"][0]["importance_score"] > 0

    portfolio = service.portfolio_news([
        {"ticker": "PETR4", "name": "Petrobras"},
        {"ticker": "BBAS3", "name": "Banco do Brasil"},
        {"ticker": "PETR4", "name": "Petrobras"},
    ])
    assert portfolio["asset_count"] == 2
    assert [item["ticker"] for item in portfolio["assets"]] == ["PETR4", "BBAS3"]


def test_research_features_are_owner_permissions_and_ui_is_wired():
    policy = full_owner_policy("owner@example.com")
    assert policy["can_view_backtest_studies"] is True
    assert policy["can_view_news_insights"] is True
    root = Path(__file__).resolve().parents[1]
    source = (root / "examples" / "streamlit_v15_integrated.py").read_text(encoding="utf-8")
    assert '"research":' not in source
    assert 'portfolio_tab_labels.append("📰 Notícias")' in source
    assert '_render_market_news(selected_portfolio_id=pid,selected_portfolio_detail=snap)' in source
    assert 'backtest_tab_labels.append("🏆 Estudo dos Backtests")' in source
    assert "with study_tab:" in source
    assert 'runs=sorted(runs,key=lambda item:_datetime_sort_value(item.get("created_at")),reverse=True)' in source
    assert 'sort_values("_analysis_order",ascending=False' in source
    assert "Ver estudo e ranking dos backtests" in source
    assert "Ver notícias da carteira e recomendações de bancos" in source
    assert 'api_get(f"/insights/news/cache/portfolios/{portfolio_id}"' in source
    assert 'api_post("/insights/news/refresh-daily"' in source
    assert '@st.fragment(run_every="10s")' in source
