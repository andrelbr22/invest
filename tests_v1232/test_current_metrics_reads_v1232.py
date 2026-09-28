from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.api.app import _stock_screen_result
from investment_engine.core.current_metrics import AssetCurrentMetricsService
from investment_engine.core.models.strategy import StockFilterSet
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.core.screening.advanced import advanced_screen
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import AssetCurrentMetricsORM


UTC = timezone.utc


def _database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _complete_stock(session: Session, ticker: str = "TEST3"):
    repository = AssetRepository(session)
    asset = repository.upsert_asset(ticker=ticker, asset_type="stock", is_active=True)
    now = datetime(2026, 9, 28, 18, tzinfo=UTC)
    repository.upsert_fundamentals(
        asset,
        source="test",
        reference_date=now,
        retrieved_at=now,
        status="valid",
        quality_score=100,
        data={
            "price": 20, "pe": 8, "pbv": 1.1, "roe_pct": 18,
            "net_margin_pct": 12, "ebit_margin_pct": 14,
            "dividend_yield_pct": 6.5, "current_ratio": 1.7,
            "daily_liquidity": 5_000_000,
        },
        raw_payload={"audited": True},
    )
    repository.upsert_scores(
        asset,
        as_of=now,
        model_version="test",
        scores={"quality_score": 80, "value_score": 75, "alb_score": 70},
        coverage_pct=90,
        data_quality_score=100,
    )
    rows = []
    for index in range(260):
        price = 15 + index * 0.02
        rows.append({
            "timeframe": "1D", "source": "test",
            "timestamp": now - timedelta(days=260 - index),
            "open": price - 0.1, "high": price + 0.2, "low": price - 0.2,
            "close": price, "adjusted_close": price, "volume": 1000 + index,
        })
    repository.bulk_upsert_price_bars(asset, rows, retrieved_at=now)
    AssetCurrentMetricsService(session).sync_asset(asset)
    session.commit()
    return asset


def test_standard_stock_screen_uses_current_table_after_coverage_is_complete():
    engine = _database()
    with Session(engine) as session:
        _complete_stock(session)
        statements: list[str] = []

        def capture(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lower())

        event.listen(engine, "before_cursor_execute", capture)
        try:
            rows = AssetRepository(session).screen_latest_stocks(
                StockFilterSet(pe_max=15, roe_min=10), limit=50,
            )
        finally:
            event.remove(engine, "before_cursor_execute", capture)

        assert [row[0].ticker for row in rows] == ["TEST3"]
        assert any("asset_current_metrics" in statement for statement in statements)
        assert not any("fundamental_snapshots" in statement for statement in statements)
        assert not any("score_snapshots" in statement for statement in statements)


def test_advanced_screen_uses_precomputed_features_without_loading_price_history():
    engine = _database()
    with Session(engine) as session:
        _complete_stock(session)
        statements: list[str] = []

        def capture(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lower())

        event.listen(engine, "before_cursor_execute", capture)
        try:
            result = advanced_screen(
                AssetRepository(session),
                asset_type="stock",
                technical_filters={"daily_trend": "up"},
                include_technical_columns=True,
                limit=50,
            )
        finally:
            event.remove(engine, "before_cursor_execute", capture)

        assert result["rows"][0]["ticker"] == "TEST3"
        assert result["meta"]["technical_precomputed"] == 1
        assert result["meta"]["technical_history_loaded"] == 0
        assert not any("from price_bars" in statement for statement in statements)


def test_historical_fallback_remains_available_until_backfill_covers_every_asset():
    engine = _database()
    with Session(engine) as session:
        asset = _complete_stock(session)
        session.delete(session.get(AssetCurrentMetricsORM, asset.id))
        session.commit()

        rows = AssetRepository(session).latest_universe("stock", limit=50)

        assert len(rows) == 1
        assert rows[0][0].ticker == "TEST3"
        assert float(rows[0][1].pe) == 8.0


def test_asset_without_source_data_does_not_disable_complete_materialized_catalog():
    engine = _database()
    with Session(engine) as session:
        _complete_stock(session)
        repository = AssetRepository(session)
        empty = repository.upsert_asset(
            ticker="VAZI3", asset_type="stock", is_active=True,
        )
        # The materializer deliberately creates a current row even when the
        # historical source is absent.  Standard stock screening must still
        # exclude that asset, exactly as the legacy inner join did, while the
        # populated asset can use the fast table.
        AssetCurrentMetricsService(session).sync_asset(empty)
        session.commit()

        assert repository._current_coverage_complete(
            {"stock"}, component="fundamental",
        ) is True
        rows = repository.screen_latest_stocks(
            StockFilterSet(pe_max=15, roe_min=10), limit=50,
        )
        assert [row[0].ticker for row in rows] == ["TEST3"]


def test_current_and_historical_standard_screen_payloads_are_equivalent():
    engine = _database()
    with Session(engine) as session:
        asset = _complete_stock(session)
        filters = StockFilterSet(pe_max=15, roe_min=10)
        current_payload = _stock_screen_result(
            AssetRepository(session).screen_latest_stocks(filters, limit=50),
            {"is_owner": True},
        )
        session.delete(session.get(AssetCurrentMetricsORM, asset.id))
        session.commit()
        historical_payload = _stock_screen_result(
            AssetRepository(session).screen_latest_stocks(filters, limit=50),
            {"is_owner": True},
        )

        keys = {
            "ticker", "price", "pe", "pbv", "dy", "roe", "net_margin",
            "daily_liquidity", "alb_score", "quality_score", "graham_number",
            "graham_upside_pct",
        }
        assert {
            key: current_payload[0].get(key) for key in keys
        } == {
            key: historical_payload[0].get(key) for key in keys
        }
