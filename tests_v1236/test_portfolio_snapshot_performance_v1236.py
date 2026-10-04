from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.core.jobs.schedules import REFRESH_SCHEDULES
from investment_engine.core.repositories.portfolio import PortfolioRepository
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import (
    AssetORM,
    FundamentalSnapshotORM,
    PriceBarORM,
    SharedSnapshotORM,
)


UTC = timezone.utc
NOW = datetime(2026, 10, 1, 18, tzinfo=UTC)


def _database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _asset(session: Session, ticker: str) -> AssetORM:
    asset = AssetORM(ticker=ticker, name=ticker, asset_type="stock")
    session.add(asset)
    session.flush()
    return asset


def _bar(
    session: Session,
    asset: AssetORM,
    *,
    age_days: int,
    close,
    adjusted_close,
    source: str,
    timeframe: str = "1D",
) -> None:
    session.add(PriceBarORM(
        asset_id=asset.id,
        timeframe=timeframe,
        timestamp=NOW - timedelta(days=age_days),
        close=close,
        adjusted_close=adjusted_close,
        source=source,
    ))


def _fundamental(
    session: Session,
    asset: AssetORM,
    *,
    age_days: int,
    retrieved_age_hours: int,
    price,
    source: str,
) -> None:
    session.add(FundamentalSnapshotORM(
        asset_id=asset.id,
        reference_date=NOW - timedelta(days=age_days),
        retrieved_at=NOW - timedelta(hours=retrieved_age_hours),
        source=source,
        price=price,
        raw_payload={},
    ))


def _seed_price_cases(session: Session) -> list[AssetORM]:
    adjusted = _asset(session, "PETR4")
    raw_close = _asset(session, "VALE3")
    fundamental = _asset(session, "ITUB4")
    latest_null = _asset(session, "BBDC4")
    missing = _asset(session, "WEGE3")

    _bar(
        session, adjusted, age_days=2, close=8, adjusted_close=9,
        source="daily-old",
    )
    _bar(
        session, adjusted, age_days=1, close=10, adjusted_close=11,
        source="daily-adjusted",
    )
    _bar(
        session, adjusted, age_days=0, close=999, adjusted_close=999,
        source="weekly-ignored", timeframe="1W",
    )
    _bar(
        session, raw_close, age_days=1, close=20, adjusted_close=None,
        source="daily-close",
    )

    # A null latest daily bar must trigger the fundamental fallback instead
    # of reviving the older valid daily close.
    _bar(
        session, fundamental, age_days=2, close=29, adjusted_close=29,
        source="stale-daily",
    )
    _bar(
        session, fundamental, age_days=1, close=None, adjusted_close=None,
        source="latest-daily-null",
    )
    _fundamental(
        session, fundamental, age_days=3, retrieved_age_hours=48,
        price=30, source="fundamental-old-date",
    )
    _fundamental(
        session, fundamental, age_days=2, retrieved_age_hours=2,
        price=31, source="fundamental-old-retrieval",
    )
    _fundamental(
        session, fundamental, age_days=2, retrieved_age_hours=1,
        price=32, source="fundamental-latest",
    )

    # The scalar method does not skip a newer null fundamental in search of
    # an older populated one; the batch method must retain that N/D result.
    _fundamental(
        session, latest_null, age_days=3, retrieved_age_hours=24,
        price=40, source="fundamental-populated-old",
    )
    _fundamental(
        session, latest_null, age_days=1, retrieved_age_hours=1,
        price=None, source="fundamental-null-latest",
    )
    _bar(
        session, missing, age_days=0, close=70, adjusted_close=71,
        source="weekly-only", timeframe="1W",
    )
    session.flush()
    return [adjusted, raw_close, fundamental, latest_null, missing]


def test_latest_price_infos_matches_scalar_priority_and_fallback():
    engine = _database()
    with Session(engine) as session:
        assets = _seed_price_cases(session)
        repository = PortfolioRepository(session)

        expected = {
            asset.id: repository.latest_price_info(asset.id)
            for asset in assets
        }
        actual = repository.latest_price_infos(asset.id for asset in assets)

        assert actual == expected
        assert actual[assets[0].id]["price"] == 11.0
        assert actual[assets[0].id]["source"] == "daily-adjusted"
        assert actual[assets[1].id]["price"] == 20.0
        assert actual[assets[1].id]["source"] == "daily-close"
        assert actual[assets[2].id]["price"] == 32.0
        assert actual[assets[2].id]["source"] == "fundamental-latest"
        assert actual[assets[3].id] == {
            "price": None, "as_of": None, "source": None,
        }
        assert actual[assets[4].id] == {
            "price": None, "as_of": None, "source": None,
        }


def test_latest_price_infos_query_count_is_constant_for_many_assets():
    engine = _database()
    with Session(engine) as session:
        assets = _seed_price_cases(session)
        repository = PortfolioRepository(session)
        statements: list[str] = []

        def capture(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lower())

        event.listen(engine, "before_cursor_execute", capture)
        try:
            prices = repository.latest_price_infos(asset.id for asset in assets)
        finally:
            event.remove(engine, "before_cursor_execute", capture)

        assert len(prices) == len(assets)
        assert len(statements) == 2
        assert sum("price_bars" in statement for statement in statements) == 1
        assert sum("fundamental_snapshots" in statement for statement in statements) == 1
        assert all("row_number() over" in statement for statement in statements)


def test_portfolio_snapshot_payload_matches_scalar_reads_and_keeps_live_override(monkeypatch):
    engine = _database()
    api_module = importlib.import_module("investment_engine.api.app")
    fixed_refresh_status = {"status": "test", "snapshot_key": "test"}

    with Session(engine) as session:
        assets = _seed_price_cases(session)
        repository = PortfolioRepository(session)
        portfolio = repository.create_portfolio(
            owner_email="owner@example.com",
            name="Carteira",
            cash_balance=100,
            target_cash_pct=10,
        )
        for asset in assets:
            repository.upsert_position(
                portfolio,
                asset,
                quantity=2,
                average_price=5,
                target_weight_pct=18,
            )

        session.add(SharedSnapshotORM(
            snapshot_key=REFRESH_SCHEDULES["technical_intraday"].snapshot_key,
            snapshot_kind="market_intraday",
            payload_json={
                "quotes": {
                    "PETR4": {
                        "price": 99.5,
                        "quote_at": "2026-10-01T17:59:00-03:00",
                        "source": "live-test",
                    },
                },
            },
            as_of=NOW,
        ))
        session.flush()

        def scalar_price_infos(self, asset_ids):
            return {
                asset_id: self.latest_price_info(asset_id)
                for asset_id in asset_ids
            }

        with monkeypatch.context() as patch:
            patch.setattr(api_module, "refresh_status", lambda *_args: fixed_refresh_status)
            patch.setattr(PortfolioRepository, "latest_price_infos", scalar_price_infos)
            expected = api_module._portfolio_snapshot(session, portfolio)

        def fail_scalar_read(*_args, **_kwargs):
            raise AssertionError("portfolio snapshot performed a per-position price read")

        with monkeypatch.context() as patch:
            patch.setattr(api_module, "refresh_status", lambda *_args: fixed_refresh_status)
            patch.setattr(PortfolioRepository, "latest_price_info", fail_scalar_read)
            actual = api_module._portfolio_snapshot(session, portfolio)

        assert actual == expected
        positions = {row["ticker"]: row for row in actual["positions"]}
        assert positions["PETR4"]["current_price"] == 99.5
        assert positions["PETR4"]["current_price_as_of"] == "2026-10-01T17:59:00-03:00"
        assert positions["PETR4"]["price_source"] == "live-test"
        assert positions["VALE3"]["current_price"] == 20.0
        assert positions["ITUB4"]["current_price"] == 32.0
        assert positions["BBDC4"]["current_price"] is None
        assert positions["WEGE3"]["current_price"] is None
