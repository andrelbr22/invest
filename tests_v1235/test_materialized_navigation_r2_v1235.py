from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from importlib import import_module
import json

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

app_module = import_module("investment_engine.api.app")
from investment_engine.api.app import (
    _enrich_listing_valuations,
    asset_detail,
    backtest_leaderboard,
)
from investment_engine.core.current_metrics import AssetCurrentMetricsService
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.core.repositories.backtests import BacktestRepository
from investment_engine.core.repositories.current_metrics import AssetCurrentMetricsRepository
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import (
    AssetCurrentMetricsORM,
    BacktestRunORM,
)


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


def _asset(session: Session, ticker: str):
    return AssetRepository(session).upsert_asset(
        ticker=ticker,
        name=f"Ativo {ticker}",
        asset_type="stock",
        is_active=True,
    )


def _official_run(asset_id, strategy_id: str, ranking: int):
    now = datetime(2026, 10, 2, 12, tzinfo=UTC)
    return BacktestRunORM(
        asset_id=asset_id,
        owner_email="official-catalog@system.local",
        scope="official",
        config_hash=f"{strategy_id}-config",
        market_date=date(2026, 10, 2),
        engine_version="1.23.5",
        strategy_id=strategy_id,
        strategy_name=f"Estratégia {strategy_id}",
        requested_start=datetime(2021, 1, 1, tzinfo=UTC),
        requested_end=now,
        initial_capital=Decimal("10000"),
        fee_pct=Decimal("0.03"),
        slippage_pct=Decimal("0.05"),
        risk_free_rate_pct=Decimal("0"),
        parameters_json={"strategy": {"id": strategy_id}},
        metrics_json={"total_return_pct": ranking},
        equity_curve_json=[],
        result_json={},
        ranking_score=Decimal(str(ranking)),
        sample_status="adequate",
        current_signal="buy",
        signal_as_of=now,
        status="valid",
        created_at=now,
    )


def _complete_stock(session: Session, ticker: str = "TEST3"):
    repository = AssetRepository(session)
    asset = _asset(session, ticker)
    now = datetime(2026, 10, 2, 12, tzinfo=UTC)
    repository.upsert_fundamentals(
        asset,
        source="test",
        reference_date=now,
        retrieved_at=now,
        status="valid",
        quality_score=100,
        data={
            "price": 20,
            "pe": 8,
            "pbv": 1.1,
            "roe_pct": 18,
            "net_margin_pct": 12,
            "dividend_yield_pct": 6.5,
            "daily_liquidity": 5_000_000,
        },
        raw_payload={"audited": True},
    )
    AssetCurrentMetricsService(session).sync_asset(asset)
    return asset


def _projected_leader(ticker: str, strategy_id: str, ranking: float = 80.0):
    return {
        "id": f"run-{strategy_id}",
        "ticker": ticker,
        "strategy_id": strategy_id,
        "strategy_name": f"Estratégia {strategy_id}",
        "ranking_score": ranking,
        "current_signal": "buy",
        "market_date": date(2026, 10, 2),
        "created_at": datetime(2026, 10, 2, 12, tzinfo=UTC),
    }


def test_read_model_is_json_safe_and_preserves_last_known_good(session):
    asset = _asset(session, "SAFE3")
    repository = AssetCurrentMetricsRepository(session)
    valuation = {
        "relative_peers_value": Decimal("25.50"),
        "relative_peers_status": "valid",
        "valuation_methods": {
            "relative_peers": {"status": "valid", "as_of": date(2026, 10, 2)},
        },
    }
    assert repository.sync_valuation(asset.id, valuation) is True
    first_valuation = dict(session.get(AssetCurrentMetricsORM, asset.id).valuation_json)
    assert repository.sync_valuation(asset.id, {}) is False

    leaders = [_projected_leader("SAFE3", "alpha")]
    assert repository.sync_backtest_leaders(asset.id, leaders) is True
    first_leaders = list(session.get(AssetCurrentMetricsORM, asset.id).backtest_leaders_json)
    assert repository.sync_backtest_leaders(asset.id, []) is False

    current = session.get(AssetCurrentMetricsORM, asset.id)
    assert current.valuation_json == first_valuation
    assert current.backtest_leaders_json == first_leaders
    json.dumps(current.valuation_json)
    json.dumps(current.backtest_leaders_json)


def test_navigation_leaderboard_falls_back_only_for_uncovered_ticker(session, monkeypatch):
    projected_asset = _asset(session, "MAT3")
    gap_asset = _asset(session, "GAP3")
    current = AssetCurrentMetricsRepository(session)
    current.sync_backtest_leaders(
        projected_asset.id,
        [_projected_leader("MAT3", "materialized")],
    )
    session.add(_official_run(gap_asset.id, "historical", 70))
    session.flush()

    repository = BacktestRepository(session)
    original = repository.leaderboard
    legacy_calls = []

    def counted_legacy(**kwargs):
        legacy_calls.append(list(kwargs.get("tickers") or []))
        return original(**kwargs)

    monkeypatch.setattr(repository, "leaderboard", counted_legacy)
    result = repository.navigation_leaderboard(
        tickers=["MAT3", "GAP3"],
        per_asset=3,
    )

    assert legacy_calls == [["GAP3"]]
    assert result["MAT3"][0]["strategy_id"] == "materialized"
    assert result["GAP3"][0]["strategy_id"] == "historical"


def test_materialized_leaderboard_keeps_tuple_contract_for_blank_tickers(session):
    grouped, covered = BacktestRepository(session)._materialized_leaderboard_state(
        tickers=["", "   "],
    )

    assert grouped == {}
    assert covered == set()


def test_worker_materializes_default_valuation_and_three_distinct_backtests(session):
    asset = _complete_stock(session, "WORK3")
    session.add_all([
        _official_run(asset.id, "alpha", 90),
        _official_run(asset.id, "beta", 80),
        _official_run(asset.id, "gamma", 70),
    ])
    session.flush()
    historical_count = session.scalar(select(func.count()).select_from(BacktestRunORM))

    result = AssetCurrentMetricsService(session).sync_navigation_metrics([asset])
    current = session.get(AssetCurrentMetricsORM, asset.id)

    assert result["errors"] == []
    assert result["valuations_updated"] == 1
    assert result["backtest_podiums_updated"] == 1
    assert current.valuation_calculated_at is not None
    assert isinstance(current.valuation_json.get("valuation_methods"), dict)
    assert [item["strategy_id"] for item in current.backtest_leaders_json] == [
        "alpha", "beta", "gamma",
    ]
    assert session.scalar(select(func.count()).select_from(BacktestRunORM)) == historical_count
    json.dumps(current.valuation_json)
    json.dumps(current.backtest_leaders_json)


def test_worker_marks_missing_valuation_inputs_as_explicit_nd_coverage(session):
    asset = _asset(session, "NODA3")

    result = AssetCurrentMetricsService(session).sync_navigation_metrics(
        [asset], include_backtests=False,
    )
    current = session.get(AssetCurrentMetricsORM, asset.id)

    assert result["errors"] == []
    assert current.valuation_calculated_at is not None
    methods = current.valuation_json["valuation_methods"]
    assert methods["graham_reference"]["status"] == "insufficient_data"
    assert methods["relative_peers"]["status"] in {
        "insufficient_data", "unavailable",
    }


def test_lists_and_asset_detail_do_not_recalculate_after_projection_coverage(session, monkeypatch):
    asset = _complete_stock(session, "FAST3")
    current = AssetCurrentMetricsRepository(session)
    current.sync_valuation(asset.id, {
        "relative_peers_value": 31.5,
        "relative_peers_upside_pct": 57.5,
        "relative_peers_status": "valid",
        "valuation_methods": {
            "relative_peers": {"status": "valid", "value": 31.5},
        },
    })
    current.sync_backtest_leaders(
        asset.id,
        [_projected_leader("FAST3", "projected")],
    )
    session.flush()

    def unexpected(*_args, **_kwargs):
        raise AssertionError("covered navigation must not rebuild historical projections")

    monkeypatch.setattr(app_module, "advanced_screen", unexpected)
    monkeypatch.setattr(BacktestRepository, "leaderboard", unexpected)

    enriched = _enrich_listing_valuations(
        AssetRepository(session),
        [{"ticker": "FAST3", "price": 20}],
        asset_type="stock",
        access={"can_use_relative_valuation": True},
    )
    detail = asset_detail(
        "FAST3",
        access={
            "can_view_backtests": True,
            "can_use_relative_valuation": True,
        },
        db=session,
    )
    leaderboard = backtest_leaderboard(
        tickers="FAST3",
        per_asset=3,
        _access={"can_view_backtests": True},
        db=session,
    )

    assert enriched[0]["relative_peers_value"] == 31.5
    assert detail["derived"]["relative_peers_value"] == 31.5
    assert detail["backtests"][0]["strategy_id"] == "projected"
    assert leaderboard["items"]["FAST3"][0]["strategy_id"] == "projected"

