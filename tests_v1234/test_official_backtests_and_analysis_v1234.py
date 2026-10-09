from frontend_test_support import browser_source
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.api.app import app, get_db, require_owner
from investment_engine.core.analysis_settings import _expand_legacy_backtest_column
from investment_engine.core.backtesting.batch import BacktestBatchService
from investment_engine.core.repositories.backtests import BacktestRepository
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import (
    AssetORM,
    BacktestBatchJobORM,
    BacktestRunORM,
)


ROOT = Path(__file__).resolve().parents[1]


def _official_run(asset_id, *, strategy_id, config_hash, score, created_at):
    return BacktestRunORM(
        asset_id=asset_id,
        owner_email="official-catalog@system.local",
        scope="official",
        config_hash=config_hash,
        market_date=date(2026, 9, 29),
        engine_version="1.23.4",
        strategy_id=strategy_id,
        strategy_name=f"Estratégia {strategy_id}",
        requested_start=datetime(2021, 1, 1, tzinfo=timezone.utc),
        requested_end=datetime(2026, 1, 1, tzinfo=timezone.utc),
        initial_capital=Decimal("10000"),
        fee_pct=Decimal("0.03"),
        slippage_pct=Decimal("0.05"),
        risk_free_rate_pct=Decimal("0"),
        parameters_json={"strategy": {"id": strategy_id}},
        metrics_json={"total_return_pct": score},
        equity_curve_json=[],
        result_json={},
        ranking_score=Decimal(str(score)),
        sample_status="adequate",
        current_signal="buy",
        status="valid",
        created_at=created_at,
    )


def test_leaderboard_returns_three_distinct_strategies_and_keeps_every_requested_asset():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
    with Session(engine) as session:
        first = AssetORM(ticker="ABEV3", name="Ambev", asset_type="stock")
        second = AssetORM(ticker="TEST3", name="Teste", asset_type="stock")
        session.add_all([first, second])
        session.flush()
        session.add_all([
            # The stale copy has a higher score but the newest copy of the
            # same configuration is authoritative.
            _official_run(first.id, strategy_id="alpha", config_hash="alpha-a", score=95, created_at=now - timedelta(days=1)),
            _official_run(first.id, strategy_id="alpha", config_hash="alpha-a", score=30, created_at=now),
            # A second alpha configuration may win within alpha, but alpha can
            # still occupy only one podium position.
            _official_run(first.id, strategy_id="alpha", config_hash="alpha-b", score=80, created_at=now),
            _official_run(first.id, strategy_id="beta", config_hash="beta-a", score=70, created_at=now),
            _official_run(first.id, strategy_id="gamma", config_hash="gamma-a", score=60, created_at=now),
            _official_run(first.id, strategy_id="delta", config_hash="delta-a", score=50, created_at=now),
            _official_run(second.id, strategy_id="omega", config_hash="omega-a", score=65, created_at=now),
        ])
        session.commit()

        result = BacktestRepository(session).leaderboard(
            tickers=["ABEV3", "TEST3"], per_asset=3,
        )

    assert list(result) == ["ABEV3", "TEST3"]
    assert [run.strategy_id for run, _asset in result["ABEV3"]] == ["alpha", "beta", "gamma"]
    assert [float(run.ranking_score) for run, _asset in result["ABEV3"]] == [80.0, 70.0, 60.0]
    assert [run.strategy_id for run, _asset in result["TEST3"]] == ["omega"]


def test_owner_complete_round_has_a_server_enforced_twelve_hour_cooldown():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(BacktestBatchJobORM(
            requested_by="owner@example.com",
            source="scheduled",
            status="completed",
            requested_tickers_json=["ABEV3"],
            created_at=now - timedelta(hours=11),
        ))
        session.commit()
        service = BacktestBatchService(session)

        blocked = service.owner_official_round_status(now=now)
        allowed = service.owner_official_round_status(now=now + timedelta(hours=1))

    assert blocked["allowed"] is False
    assert blocked["remaining_seconds"] == 3600
    assert blocked["cooldown_hours"] == 12
    assert allowed["allowed"] is True
    assert allowed["remaining_seconds"] == 0


def test_owner_launch_api_rejects_a_second_round_inside_twelve_hours():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(BacktestBatchJobORM(
            requested_by="owner@example.com",
            source="scheduled",
            status="completed",
            requested_tickers_json=["ABEV3"],
            created_at=datetime.now(timezone.utc) - timedelta(hours=11),
        ))
        session.commit()

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_owner] = lambda: {
        "email": "owner@example.com",
        "is_owner": True,
    }
    try:
        client = TestClient(app, base_url="http://localhost")
        status = client.get("/backtests/batch/official-launch")
        blocked = client.post("/backtests/batch/official-launch")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_owner, None)

    assert status.status_code == 200
    assert status.json()["allowed"] is False
    assert status.json()["cooldown_hours"] == 12
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "official_batch_cooldown"


def test_legacy_combined_backtest_column_expands_without_losing_saved_order():
    assert _expand_legacy_backtest_column(["ticker", "best_signal", "price"]) == [
        "ticker", "backtest_1", "backtest_2", "backtest_3", "price",
    ]


def test_interface_exposes_three_columns_and_owner_launch_control():
    script = browser_source(Path(__file__).resolve().parents[1])
    assert 'id:"backtest_1",label:"1º backtest"' in script
    assert 'id:"backtest_2",label:"2º backtest"' in script
    assert 'id:"backtest_3",label:"3º backtest"' in script
    assert "data-launch-official-backtests" in script
    assert 'api("/backtests/batch/official-launch",{method:"POST"' in script
    assert 'owner?api("/backtests/batch/official-launch",{requestKey:"admin-official-launch",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force})' in script
    assert "12 horas da rodada oficial anterior" in script
