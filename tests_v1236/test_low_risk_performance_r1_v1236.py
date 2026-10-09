from __future__ import annotations
from frontend_test_support import browser_source

import importlib
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from investment_engine.core.repositories.news_cache import NewsCacheRepository


ROOT = Path(__file__).resolve().parents[1]
VISIBLE_GROUPS = (
    "selic_current",
    "selic_focus",
    "macro",
    "global_markets",
    "rates_calendar",
    "crypto",
    "fx",
)


def _updates():
    return {
        key: {"status": "fresh", "last_updated_at": "2026-10-04T00:00:00Z"}
        for key in VISIBLE_GROUPS
    }


def test_dashboard_skips_legacy_json_after_independent_snapshots_are_complete(monkeypatch):
    module = importlib.import_module("investment_engine.api.app")
    schedules = {
        key: SimpleNamespace(snapshot_key=f"snapshot:{key}")
        for key in VISIBLE_GROUPS
    }
    rows = {
        f"snapshot:{key}": SimpleNamespace(
            payload_json={key: {"value": key}},
            as_of=datetime(2026, 10, 4, tzinfo=timezone.utc),
        )
        for key in VISIBLE_GROUPS
    }

    class SnapshotRepository:
        def __init__(self, _session):
            pass

        def get_many(self, _keys):
            return rows

    class LegacyRepositoryMustNotBeUsed:
        def __init__(self, _session):
            raise AssertionError("the complete dashboard must not read legacy JSON")

    monkeypatch.setattr(module, "REFRESH_SCHEDULES", schedules)
    monkeypatch.setattr(module, "SharedSnapshotRepository", SnapshotRepository)
    monkeypatch.setattr(module, "NewsCacheRepository", LegacyRepositoryMustNotBeUsed)
    monkeypatch.setattr(module, "all_refresh_statuses", lambda *_args, **_kwargs: _updates())

    payload = module._build_market_dashboard_payload(object())

    assert payload["status"] == "completed"
    assert payload["has_data"] is True
    assert payload["data"]["crypto"] == {"value": "crypto"}
    assert payload["data"]["fx"] == {"value": "fx"}


def test_dashboard_preserves_legacy_fallback_when_one_snapshot_is_missing(monkeypatch):
    module = importlib.import_module("investment_engine.api.app")
    schedules = {
        key: SimpleNamespace(snapshot_key=f"snapshot:{key}")
        for key in VISIBLE_GROUPS
    }
    rows = {
        f"snapshot:{key}": SimpleNamespace(
            payload_json={key: {"value": key}},
            as_of=datetime(2026, 10, 4, tzinfo=timezone.utc),
        )
        for key in VISIBLE_GROUPS
        if key != "fx"
    }
    legacy_row = SimpleNamespace(
        id="legacy",
        status="completed",
        result_json={"fx": {"value": "preserved"}, "legacy_only": True},
        cache_kind="market_dashboard",
        cache_key="shared",
        market_date=date(2026, 10, 4),
        trigger="automatic",
        error_message=None,
        requested_at=None,
        started_at=None,
        finished_at=None,
    )

    class SnapshotRepository:
        def __init__(self, _session):
            pass

        def get_many(self, _keys):
            return rows

    class LegacyRepository:
        def __init__(self, _session):
            pass

        def get(self, **_kwargs):
            return None

        def latest_completed(self, **_kwargs):
            return legacy_row

    monkeypatch.setattr(module, "REFRESH_SCHEDULES", schedules)
    monkeypatch.setattr(module, "SharedSnapshotRepository", SnapshotRepository)
    monkeypatch.setattr(module, "NewsCacheRepository", LegacyRepository)
    monkeypatch.setattr(module, "all_refresh_statuses", lambda *_args, **_kwargs: _updates())

    payload = module._build_market_dashboard_payload(object())

    assert payload["data"]["fx"] == {"value": "preserved"}
    assert payload["data"]["legacy_only"] is True
    assert payload["data"]["crypto"] == {"value": "crypto"}


def test_news_latest_queries_are_bounded_to_one_database_row():
    statements = []

    class Session:
        def scalar(self, statement):
            statements.append(statement)
            return None

    repository = NewsCacheRepository(Session())
    repository.latest(owner_email="owner@example.com", cache_kind="news", cache_key="main")
    repository.latest_completed(owner_email="owner@example.com", cache_kind="news", cache_key="main")

    assert len(statements) == 2
    assert all("LIMIT" in str(statement).upper() for statement in statements)


def test_backtest_enrichment_patches_only_secondary_cells_with_safe_fallback():
    source = browser_source(Path(__file__).resolve().parents[1])

    assert 'data-column-id="${esc(c.id)}"' in source
    assert "function patchAnalysisBacktestCells(rows)" in source
    assert 'element.querySelector(`td[data-column-id="${columnId}"]`)' in source
    assert "if(!patchAnalysisBacktestCells(enrichedRows))renderAnalysisRows(enrichedRows);" in source
    assert "cell.innerHTML=backtestLeaderCell(row,index)" in source


def test_real_browser_metrics_cover_the_remaining_heavy_panels():
    source = browser_source(Path(__file__).resolve().parents[1])

    for panel in ("backtests", "finances", "admin"):
        assert f'reportPanelPerformance("{panel}",panelStarted' in source
    # Dashboard, Análises and Carteira already measured their starts inside
    # combined declarations; R1 adds three explicit starts for the remaining
    # heavy areas.
    assert source.count("const panelStarted=performance.now();") >= 3


def test_operator_benchmark_can_measure_cold_and_extended_user_journeys():
    source = (ROOT / "scripts" / "benchmark_application_routes.py").read_text(encoding="utf-8")

    assert '"--cold"' in source
    assert '"--extended"' in source
    assert "_SCREENER_RESPONSE_CACHE.invalidate()" in source
    assert '"universe_etf_100"' in source
    assert '"advanced_stock_50"' in source
