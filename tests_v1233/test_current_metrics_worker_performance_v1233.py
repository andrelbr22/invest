from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import investment_engine.core.current_metrics as current_metrics_module
from investment_engine.core.current_metrics import AssetCurrentMetricsService
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import AssetCurrentMetricsORM


UTC = timezone.utc


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as current:
        yield current


def _asset(session: Session, ticker: str, *, active: bool = True):
    return AssetRepository(session).upsert_asset(
        ticker=ticker,
        asset_type="stock",
        name=f"Ativo {ticker}",
        is_active=active,
    )


def _bar(repo: AssetRepository, asset, *, retrieved_at: datetime, close: float = 10):
    timestamp = datetime(2026, 9, 28, 18, tzinfo=UTC)
    return repo.upsert_price_bar(
        asset,
        timeframe="1D",
        timestamp=timestamp,
        source="local-test",
        retrieved_at=retrieved_at,
        data={
            "open": close - 0.2,
            "high": close + 0.4,
            "low": close - 0.5,
            "close": close,
            "adjusted_close": close,
            "volume": 1_000,
        },
    )


def test_backfill_processes_and_counts_only_active_assets(session):
    active = _asset(session, "ATIV3")
    inactive = _asset(session, "INAT3", active=False)
    # Simulate the catalog that predates the materialized table. New asset
    # writes already create their empty current row through the dual-write path.
    session.delete(session.get(AssetCurrentMetricsORM, active.id))
    session.delete(session.get(AssetCurrentMetricsORM, inactive.id))
    session.flush()

    result = AssetCurrentMetricsService(session).sync_batch(limit=10)

    assert result["requested"] == 1
    assert result["remaining"] == 0
    assert result["cycle_completed"] is True
    assert session.get(AssetCurrentMetricsORM, active.id) is not None
    assert session.get(AssetCurrentMetricsORM, inactive.id) is None
    assert session.scalar(select(func.count()).select_from(AssetCurrentMetricsORM)) == 1


def test_unchanged_sources_skip_history_and_feature_recalculation(session, monkeypatch):
    repo = AssetRepository(session)
    asset = _asset(session, "FAST3")
    _bar(repo, asset, retrieved_at=datetime(2026, 9, 28, 20, tzinfo=UTC))
    service = AssetCurrentMetricsService(session)
    first = service.sync_asset(asset)
    assert first["changed_components"] > 0

    ensure_calls = 0
    original_ensure = service.current.ensure

    def counted_ensure(asset_id):
        nonlocal ensure_calls
        ensure_calls += 1
        return original_ensure(asset_id)

    def unexpected(*_args, **_kwargs):
        raise AssertionError("unchanged metrics must not reload or recalculate price history")

    monkeypatch.setattr(service.current, "ensure", counted_ensure)
    monkeypatch.setattr(service.assets, "price_history", unexpected)
    monkeypatch.setattr(current_metrics_module, "precompute_technical_features", unexpected)

    repeated = service.sync_asset(asset)

    assert repeated["created"] is False
    assert repeated["changed_components"] == 0
    assert ensure_calls == 1


def test_batch_preloads_latest_sources_instead_of_querying_each_asset(session, monkeypatch):
    for ticker in ("BATA3", "BATB3", "BATC3"):
        _asset(session, ticker)
    service = AssetCurrentMetricsService(session)

    def unexpected(*_args, **_kwargs):
        raise AssertionError("batch must use its preloaded latest-source maps")

    for method_name in (
        "latest_fundamentals", "latest_technical", "latest_scores", "latest_price_bar",
    ):
        monkeypatch.setattr(service.assets, method_name, unexpected)

    result = service.sync_batch(limit=10)

    assert result["requested"] == 3
    assert result["errors"] == []


def test_unchanged_batch_has_a_fixed_small_select_budget(session):
    for ticker in ("QRYA3", "QRYB3", "QRYC3"):
        _asset(session, ticker)
    service = AssetCurrentMetricsService(session)
    service.sync_batch(limit=10)
    statements = []

    def capture_selects(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(session.bind, "before_cursor_execute", capture_selects)
    try:
        result = service.sync_batch(limit=10)
    finally:
        event.remove(session.bind, "before_cursor_execute", capture_selects)

    assert result["unchanged"] == 3
    # Assets, four latest-source maps, current rows and remaining count. The
    # budget stays constant as the batch grows; no per-asset SELECT is allowed.
    assert len(statements) <= 7


def test_same_bar_revision_recomputes_features_when_observation_changes(session, monkeypatch):
    repo = AssetRepository(session)
    asset = _asset(session, "REVI3")
    first_observation = datetime(2026, 9, 28, 20, tzinfo=UTC)
    revised_observation = first_observation + timedelta(hours=1)
    first_bar = _bar(repo, asset, retrieved_at=first_observation, close=10)
    service = AssetCurrentMetricsService(session)
    service.sync_asset(asset)

    revised_bar = _bar(repo, asset, retrieved_at=revised_observation, close=11)
    assert revised_bar.id == first_bar.id
    calls = 0
    original_precompute = current_metrics_module.precompute_technical_features

    def counted_precompute(rows):
        nonlocal calls
        calls += 1
        return original_precompute(rows)

    monkeypatch.setattr(current_metrics_module, "precompute_technical_features", counted_precompute)

    result = service.sync_asset(asset)
    current = session.get(AssetCurrentMetricsORM, asset.id)

    assert calls == 1
    assert result["changed_components"] >= 1
    assert current.source_refs_json["features"]["id"] == str(revised_bar.id)
    assert current.source_refs_json["features"]["observed_at"] == revised_observation.isoformat()
