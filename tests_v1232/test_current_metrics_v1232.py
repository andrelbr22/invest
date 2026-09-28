from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.core.current_metrics import (
    AssetCurrentMetricsService,
    FEATURE_ALGORITHM,
    precompute_technical_features,
)
from investment_engine.core.jobs.handlers import DEFAULT_JOB_HANDLERS
from investment_engine.core.jobs.schedules import REFRESH_SCHEDULES
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.core.repositories.current_metrics import AssetCurrentMetricsRepository
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import (
    AssetCurrentMetricsORM,
    FundamentalSnapshotORM,
    PriceBarORM,
    ScoreSnapshotORM,
    TechnicalSnapshotORM,
)


ROOT = Path(__file__).resolve().parents[1]
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


def _asset(session: Session, ticker="TEST3"):
    return AssetRepository(session).upsert_asset(
        ticker=ticker, asset_type="stock", name=f"Ativo {ticker}", is_active=True,
    )


def _fundamental(repo, asset, when, *, pe, price=10):
    return repo.upsert_fundamentals(
        asset,
        source="test-source",
        reference_date=when,
        retrieved_at=when + timedelta(hours=1),
        status="valid",
        quality_score=95,
        data={
            "price": price, "pe": pe, "pbv": 1.2, "dividend_yield_pct": 6.5,
            "roe_pct": 18, "net_margin_pct": 12, "daily_liquidity": 2_000_000,
        },
        raw_payload={"audited": True},
    )


def test_dual_write_is_idempotent_and_never_removes_history(session):
    repo = AssetRepository(session)
    asset = _asset(session)
    newer = datetime(2026, 9, 27, 12, tzinfo=UTC)
    older = newer - timedelta(days=1)
    newest = _fundamental(repo, asset, newer, pe=8)
    _fundamental(repo, asset, older, pe=99)

    current = session.get(AssetCurrentMetricsORM, asset.id)
    assert current.fundamental_snapshot_id == newest.id
    assert float(current.pe) == 8.0
    assert current.fallback_json["price"] == "fundamental_snapshot"
    assert session.scalar(select(func.count()).select_from(FundamentalSnapshotORM)) == 2

    last_updated = current.updated_at
    changed = AssetCurrentMetricsRepository(session).sync_fundamental(newest)
    session.flush()
    assert changed is False
    assert current.updated_at == last_updated


def test_all_ingestion_writes_update_the_materialized_row(session):
    repo = AssetRepository(session)
    asset = _asset(session)
    now = datetime(2026, 9, 27, 18, tzinfo=UTC)
    fundamental = _fundamental(repo, asset, now, pe=9, price=11)
    technical = repo.upsert_technical(
        asset,
        source="internal",
        timeframe="1D",
        as_of=now,
        retrieved_at=now + timedelta(minutes=5),
        status="valid",
        data={"rsi14": 52, "sma20": 10, "daily_liquidity": 3_000_000},
        raw_payload={"source": "local-test"},
    )
    score = repo.upsert_scores(
        asset,
        as_of=now,
        model_version="test-1",
        scores={"quality_score": 80, "alb_score": 71},
        coverage_pct=90,
        data_quality_score=95,
        details={"tested": True},
    )
    bar = repo.upsert_price_bar(
        asset,
        timeframe="1D",
        timestamp=now + timedelta(hours=1),
        source="local-test",
        retrieved_at=now + timedelta(hours=2),
        data={"open": 11, "high": 13, "low": 10, "close": 12, "adjusted_close": 12.5, "volume": 1000},
    )

    current = session.get(AssetCurrentMetricsORM, asset.id)
    assert current.fundamental_snapshot_id == fundamental.id
    assert current.technical_snapshot_id == technical.id
    assert current.score_snapshot_id == score.id
    assert current.price_bar_id == bar.id
    assert float(current.price) == 12.5
    assert current.fallback_json["price"] == "local_price_bar"
    assert float(current.daily_liquidity) == 3_000_000
    assert float(current.alb_score) == 71


def test_local_feature_precompute_covers_trends_volumes_and_all_pivots(session):
    repo = AssetRepository(session)
    asset = _asset(session)
    start = datetime(2024, 1, 1, 18, tzinfo=UTC)
    rows = []
    for index in range(620):
        price = 10 + index * 0.02
        rows.append({
            "timeframe": "1D", "source": "local-history",
            "timestamp": start + timedelta(days=index),
            "open": price - 0.1, "high": price + 0.3, "low": price - 0.3,
            "close": price, "adjusted_close": price, "volume": 1000 + index,
        })
    repo.bulk_upsert_price_bars(asset, rows, retrieved_at=start + timedelta(days=621))
    history = repo.price_history(asset.id, limit=600)
    features = precompute_technical_features(history)

    assert features["algorithm"] == FEATURE_ALGORITHM
    assert features["bar_count"] == 600
    assert set(features["trend_periods"]) == {"20", "21"}
    assert features["trend_periods"]["21"]["trend_daily"] == "up"
    assert features["rsi14"] is not None
    assert set(features["pivots"]) == {"daily", "weekly", "monthly"}
    assert features["pivots"]["daily"]["pp"] is not None
    assert features["pivots"]["weekly"]["pp"] is not None
    assert features["pivots"]["monthly"]["pp"] is not None


def test_backfill_is_resumable_exact_and_idempotent(session):
    for ticker in ("AAAA3", "BBBB3", "CCCC3"):
        asset = _asset(session, ticker)
        AssetRepository(session).upsert_price_bar(
            asset,
            timeframe="1D",
            timestamp=datetime(2026, 9, 27, 18, tzinfo=UTC),
            source="local-test",
            data={"close": 10, "adjusted_close": 10, "volume": 100},
        )
    service = AssetCurrentMetricsService(session)
    first = service.sync_batch(limit=2)
    assert first["requested"] == 2
    assert first["remaining"] == 1
    assert first["cycle_completed"] is False

    second = service.sync_batch(after_ticker=first["next_cursor"], limit=2)
    assert second["requested"] == 1
    assert second["remaining"] == 0
    assert second["cycle_completed"] is True
    assert session.scalar(select(func.count()).select_from(AssetCurrentMetricsORM)) == 3

    repeat = service.sync_batch(limit=10)
    assert repeat["created"] == 0
    assert repeat["updated"] == 0
    assert repeat["unchanged"] == 3
    rows = list(session.scalars(select(AssetCurrentMetricsORM)))
    assert all(row.parity_json["state"] == "exact" for row in rows)
    assert all(row.parity_json["historical_tables_preserved"] is True for row in rows)


def test_release_wires_migration_schedule_and_worker_handler():
    migration = (ROOT / "alembic" / "versions" / "0029_v1_23_current_metrics.py").read_text(
        encoding="utf-8",
    )
    assert 'down_revision = "0028_v1_23_operational_retention"' in migration
    assert "asset_current_metrics" in migration
    assert "current_metrics" in REFRESH_SCHEDULES
    assert REFRESH_SCHEDULES["current_metrics"].job_type == "current_metrics_refresh"
    assert "current_metrics_refresh" in DEFAULT_JOB_HANDLERS


def test_current_table_has_one_row_per_asset_and_auditable_source_foreign_keys():
    table = AssetCurrentMetricsORM.__table__
    assert list(table.primary_key.columns.keys()) == ["asset_id"]
    targets = {foreign_key.target_fullname for foreign_key in table.foreign_keys}
    assert {
        "assets.id", "fundamental_snapshots.id", "technical_snapshots.id",
        "score_snapshots.id", "price_bars.id",
    }.issubset(targets)

