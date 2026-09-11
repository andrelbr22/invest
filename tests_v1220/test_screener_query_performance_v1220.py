from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.core.models.strategy import StockFilterSet
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import (
    AssetORM,
    FundamentalSnapshotORM,
    ScoreSnapshotORM,
    TechnicalSnapshotORM,
)


ROOT = Path(__file__).resolve().parents[1]


def _dt(month: int, day: int = 1):
    return datetime(2026, month, day, tzinfo=timezone.utc)


def _database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _fundamental(asset, month: int, *, price: int):
    return FundamentalSnapshotORM(
        asset_id=asset.id,
        reference_date=_dt(month),
        retrieved_at=_dt(month, 2),
        source="test",
        status="valid",
        price=price,
        pe=5,
        pbv=1,
        roe_pct=15,
        net_margin_pct=10,
        ebit_margin_pct=10,
        current_ratio=2,
        dividend_yield_pct=6,
        daily_liquidity=2_000_000,
        raw_payload={},
    )


def _technical(asset, month: int, *, timeframe="1D", liquidity=2_000_000):
    return TechnicalSnapshotORM(
        asset_id=asset.id,
        timeframe=timeframe,
        as_of=_dt(month),
        retrieved_at=_dt(month, 2),
        source="test",
        status="valid",
        daily_liquidity=liquidity,
        close=20,
        raw_payload={},
    )


def _score(asset, month: int, *, alb_score: int):
    return ScoreSnapshotORM(
        asset_id=asset.id,
        as_of=_dt(month),
        calculated_at=_dt(month, 2),
        model_version=f"test-{month}",
        alb_score=alb_score,
        details_json={},
    )


def test_stock_screener_uses_latest_rows_without_global_window_scans():
    engine = _database()
    statements = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _conn, _cursor, statement, _parameters, _context, _many: statements.append(statement),
    )
    with Session(engine) as session:
        petr = AssetORM(ticker="PETR4", name="Petrobras", asset_type="stock", is_active=True)
        vale = AssetORM(ticker="VALE3", name="Vale", asset_type="stock", is_active=True)
        session.add_all([petr, vale])
        session.flush()
        session.add_all([
            _fundamental(petr, 1, price=10),
            _fundamental(petr, 2, price=20),
            _fundamental(vale, 1, price=30),
            _technical(petr, 1, liquidity=100),
            _technical(petr, 2, liquidity=3_000_000),
            # A newer weekly snapshot must not replace the newest daily row.
            _technical(petr, 3, timeframe="1W", liquidity=1),
            _technical(vale, 1, liquidity=3_000_000),
            _score(petr, 1, alb_score=99),
            _score(petr, 2, alb_score=10),
            _score(vale, 1, alb_score=20),
        ])
        session.commit()

        statements.clear()
        rows = AssetRepository(session).screen_latest_stocks(
            StockFilterSet(daily_liquidity_min=1_000_000),
            limit=50,
        )

    assert [row[0].ticker for row in rows] == ["VALE3", "PETR4"]
    petr_row = next(row for row in rows if row[0].ticker == "PETR4")
    assert float(petr_row[1].price) == 20
    assert float(petr_row[2].alb_score) == 10
    select_sql = "\n".join(statement for statement in statements if statement.lstrip().upper().startswith("SELECT"))
    assert "row_number" not in select_sql.lower()
    assert "fundamental_snapshots.asset_id = assets.id" in select_sql
    assert "technical_snapshots.asset_id = assets.id" in select_sql
    assert "score_snapshots.asset_id = assets.id" in select_sql


def test_universe_keeps_assets_without_snapshots_and_selects_latest_available_rows():
    engine = _database()
    with Session(engine) as session:
        first = AssetORM(ticker="BOVA11", name="BOVA", asset_type="etf", is_active=True)
        empty = AssetORM(ticker="IVVB11", name="IVVB", asset_type="etf", is_active=True)
        session.add_all([first, empty])
        session.flush()
        session.add_all([
            _fundamental(first, 1, price=90),
            _fundamental(first, 2, price=100),
            _technical(first, 1),
            _technical(first, 2),
            _score(first, 1, alb_score=10),
            _score(first, 2, alb_score=20),
        ])
        session.commit()

        rows = AssetRepository(session).latest_universe("etf", limit=50)

    assert [row[0].ticker for row in rows] == ["BOVA11", "IVVB11"]
    populated = rows[0]
    assert float(populated[1].price) == 100
    assert populated[2].as_of == _dt(2).replace(tzinfo=None)
    assert float(populated[3].alb_score) == 20
    assert rows[1][1:] == (None, None, None)


def test_performance_migration_defines_lookup_indexes_in_query_order():
    path = ROOT / "alembic" / "versions" / "0023_v1_22_screener_performance.py"
    spec = spec_from_file_location("migration_0023_v1_22_screener_performance", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "0023_v1_22_screener_performance"
    assert migration.down_revision == "0022_v1_22_observability"
    assert migration.INDEXES == {
        "assets": ("ix_assets_type_active_ticker", ["asset_type", "is_active", "ticker"]),
        "fundamental_snapshots": (
            "ix_fundamental_latest_lookup",
            ["asset_id", "reference_date", "retrieved_at", "id"],
        ),
        "technical_snapshots": (
            "ix_technical_latest_lookup",
            ["asset_id", "timeframe", "as_of", "retrieved_at", "id"],
        ),
        "score_snapshots": (
            "ix_score_latest_lookup",
            ["asset_id", "as_of", "calculated_at", "id"],
        ),
    }

    metadata_indexes = {
        index.name: [column.name for column in index.columns]
        for table in Base.metadata.tables.values()
        for index in table.indexes
    }
    for _table, (name, columns) in migration.INDEXES.items():
        assert metadata_indexes[name] == columns
