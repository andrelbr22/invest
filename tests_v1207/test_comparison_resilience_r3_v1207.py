from pathlib import Path

from investment_engine.core.jobs.handlers import _json_safe
from investment_engine.data.providers.market_dashboard import HISTORICAL_COMPARISON_ORDER


ROOT = Path(__file__).resolve().parents[1]


def test_non_finite_provider_values_are_safe_for_postgresql_json():
    assert _json_safe({"nan": float("nan"), "inf": float("inf"), "ok": 2.5}) == {
        "nan": None,
        "inf": None,
        "ok": 2.5,
    }


def test_comparison_refresh_keeps_snapshot_and_polls_without_blanking_panel():
    script = (ROOT / "investment_engine/web/static/app.js").read_text(encoding="utf-8")
    backend = (ROOT / "investment_engine/api/app.py").read_text(encoding="utf-8")

    assert 'if(comparisonRefresh){loadComparison(true);}' in script
    assert 'state.comparison=null;loadComparison(true)' not in script
    assert 'attempt<120' in script
    assert '"data": dict(snapshot.payload_json or {})' in backend
    assert '"refreshing": update["status"] in {"queued", "running"}' in backend


def test_crypto_selectors_remain_in_the_authoritative_comparison_catalog():
    assert "BTC" in HISTORICAL_COMPARISON_ORDER
    assert "ETH" in HISTORICAL_COMPARISON_ORDER
