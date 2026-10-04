from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.core.current_metrics import AssetCurrentMetricsService
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.core.screening.advanced import advanced_screen
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import (
    AssetCurrentMetricsORM,
    AssetORM,
    TechnicalSnapshotORM,
)


UTC = timezone.utc
TICKERS = {
    "etf": "BOVA11",
    "bdr": "AAPL34",
    "future": "WIN1!",
}
NAVIGATION_TECHNICAL_FIELDS = (
    "close", "daily_liquidity", "signal_tv", "rsi14", "sma20", "sma50", "sma200",
)
NAVIGATION_SCORE_FIELDS = (
    "alb_score", "quality_score", "value_score", "growth_score",
    "technical_score", "risk_score", "liquidity_score", "data_quality_score",
)
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def session(database):
    with Session(database, expire_on_commit=False) as current:
        yield current


def _complete_asset(session: Session, asset_type: str):
    repository = AssetRepository(session)
    ticker = TICKERS[asset_type]
    now = datetime(2026, 10, 3, 12, tzinfo=UTC)
    raw_payload = {
        "provider_trace": "x" * 4_000,
        "valuation_source": "test-provider",
        "valuation_inputs_as_of": now.isoformat(),
    }
    if asset_type == "etf":
        raw_payload.update({
            "nav_per_share": 98,
            "nav_discount_premium_pct": 2.040816,
            "fundamental_currency_code": "BRL",
        })
    elif asset_type == "bdr":
        raw_payload.update({
            "price_book_fq": 8,
            "underlying_price": 200,
            "fx_brl_per_underlying_currency": 5,
            "bdr_underlying_share_ratio": 10,
        })
    else:
        raw_payload.update({
            "front_contract_price": 100,
            "underlying_spot_price": 98,
            "days_to_expiry": 30,
            "carry_rate_pct": 12,
            "front_contract": ticker,
        })

    asset = repository.upsert_asset(
        ticker=ticker,
        asset_type=asset_type,
        name=f"Ativo {ticker}",
        sector="Mercado",
        industry="Instrumentos",
        segment="Listados",
        market_cap_category="large_cap",
        metadata_json={"last_market_cap": 1_000_000_000},
        is_active=True,
    )
    repository.upsert_technical(
        asset,
        source="test",
        timeframe="1D",
        as_of=now,
        retrieved_at=now,
        status="valid",
        quality_score=100,
        data={
            "close": 100,
            "daily_liquidity": 5_000_000,
            "signal_tv": "buy",
            "rsi14": 55,
            "sma20": 99,
            "sma50": 97,
            "sma200": 90,
            "market_cap": 1_000_000_000,
        },
        raw_payload=raw_payload,
    )
    repository.upsert_scores(
        asset,
        as_of=now,
        model_version="test",
        scores={
            "quality_score": 71,
            "value_score": 72,
            "growth_score": 73,
            "technical_score": 74,
            "risk_score": 75,
            "liquidity_score": 76,
            "alb_score": 77,
        },
        coverage_pct=88,
        data_quality_score=89,
        details={"provider_trace": "y" * 4_000},
    )
    # Deliberately newer than the TradingView snapshot.  The established
    # universe tuple still exposes the technical close when that snapshot is
    # present; the compact projection must preserve that exact precedence.
    repository.upsert_price_bar(
        asset,
        timeframe="1D",
        timestamp=now + timedelta(minutes=5),
        source="prices",
        data={"close": 101, "adjusted_close": 101, "volume": 10_000},
        retrieved_at=now + timedelta(minutes=5),
    )
    session.flush()
    return asset


def _navigation_signature(row):
    asset, fundamental, technical, score = row
    return {
        "asset": {
            "ticker": asset.ticker,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "sector": asset.sector,
            "industry": asset.industry,
            "segment": asset.segment,
            "market_cap_category": asset.market_cap_category,
            "metadata_json": asset.metadata_json,
        },
        "fundamental": fundamental,
        "technical": None if technical is None else {
            field: getattr(technical, field, None)
            for field in NAVIGATION_TECHNICAL_FIELDS
        },
        "score": None if score is None else {
            field: getattr(score, field, None)
            for field in NAVIGATION_SCORE_FIELDS
        },
    }


def test_coverage_probe_uses_not_exists_and_keeps_catalog_semantics(session, database):
    covered = _complete_asset(session, "etf")
    # Unsupported legacy noise remains outside coverage, as before.
    session.add(AssetORM(ticker="INVALID", asset_type="etf", is_active=True))
    session.flush()
    repository = AssetRepository(session)
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lower())

    event.listen(database, "before_cursor_execute", capture)
    try:
        assert repository._current_coverage_complete(
            {"etf"}, component="technical",
        ) is True
    finally:
        event.remove(database, "before_cursor_execute", capture)

    coverage_sql = " ".join(statements[-1].split())
    assert "exists" in coverage_sql
    assert "count(" not in coverage_sql
    assert "limit" in coverage_sql

    session.delete(session.get(AssetCurrentMetricsORM, covered.id))
    session.flush()
    assert repository._current_coverage_complete(
        {"etf"}, component="technical",
    ) is False


@pytest.mark.parametrize("asset_type", ["etf", "bdr", "future"])
def test_compact_navigation_projection_is_payload_equivalent(session, asset_type):
    _complete_asset(session, asset_type)
    repository = AssetRepository(session)

    broad = repository.latest_universe(asset_type=asset_type, limit=50)
    compact = repository.latest_navigation_universe(
        asset_type=asset_type, limit=50,
    )

    assert [_navigation_signature(row) for row in compact] == [
        _navigation_signature(row) for row in broad
    ]
    assert compact[0][2].close == 100
    assert broad[0][2].raw_payload["provider_trace"] == "x" * 4_000
    assert compact[0][2].raw_payload == {}


def test_navigation_query_does_not_select_wide_current_documents(session, database):
    _complete_asset(session, "etf")
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(database, "before_cursor_execute", capture)
    try:
        rows = AssetRepository(session).latest_navigation_universe(
            asset_type="etf", limit=50,
        )
    finally:
        event.remove(database, "before_cursor_execute", capture)

    assert [row[0].ticker for row in rows] == ["BOVA11"]
    projection_sql = next(
        statement.lower() for statement in statements
        if "cm_nav_asset_id" in statement.lower()
    )
    # One scalar close extraction preserves parity.  None of the full current
    # JSON mirrors or historical snapshot rows is transferred by navigation.
    assert projection_sql.count("technical_json") == 1
    for wide_column in (
        "fundamental_json", "score_json", "technical_features_json",
        "valuation_json", "backtest_leaders_json", "source_refs_json",
        "fallback_json", "parity_json",
    ):
        assert wide_column not in projection_sql
    assert "technical_snapshots" not in projection_sql
    assert "score_snapshots" not in projection_sql


def test_universe_route_uses_compact_loader_with_legacy_repository_fallback():
    source = (ROOT / "investment_engine" / "api" / "app.py").read_text(
        encoding="utf-8",
    )
    route = source.split(
        'def screen_db_universe(', 1,
    )[1].split('@app.get("/screen/db/custom/{filter_id}")', 1)[0]

    assert '"latest_navigation_universe"' in route
    assert "repo.latest_universe" in route


def test_navigation_falls_back_to_historical_rows_until_coverage_is_complete(
    session, database,
):
    asset = _complete_asset(session, "etf")
    session.delete(session.get(AssetCurrentMetricsORM, asset.id))
    session.flush()
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lower())

    event.listen(database, "before_cursor_execute", capture)
    try:
        rows = AssetRepository(session).latest_navigation_universe(
            asset_type="etf", limit=50,
        )
    finally:
        event.remove(database, "before_cursor_execute", capture)

    assert len(rows) == 1
    assert isinstance(rows[0][2], TechnicalSnapshotORM)
    assert rows[0][2].raw_payload["provider_trace"] == "x" * 4_000
    assert any("technical_snapshots" in statement for statement in statements)
    assert any("score_snapshots" in statement for statement in statements)


def test_advanced_and_worker_paths_keep_full_class_specific_inputs(session):
    asset = _complete_asset(session, "etf")
    repository = AssetRepository(session)

    advanced = advanced_screen(
        repository,
        asset_type="etf",
        allowed_tickers=[asset.ticker],
        include_technical_columns=False,
        limit=1,
    )
    assert advanced["rows"][0]["economic_value_status"] == "valid"
    assert advanced["rows"][0]["economic_value"] == pytest.approx(98)

    materialized = AssetCurrentMetricsService(session).sync_navigation_metrics(
        [asset], include_backtests=False,
    )
    current = session.get(AssetCurrentMetricsORM, asset.id)
    assert materialized["errors"] == []
    assert current.valuation_json["economic_value_status"] == "valid"
    assert current.valuation_json["economic_value"] == pytest.approx(98)

