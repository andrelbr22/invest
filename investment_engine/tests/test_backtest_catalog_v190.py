from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investment_engine.core.backtesting.grid import official_grid
from investment_engine.core.backtesting.ranking import enrich_result, robust_ranking
from investment_engine.core.backtesting.strategies import STRATEGIES
from investment_engine.core.repositories.backtests import BacktestRepository, build_config_hash
from investment_engine.core.repositories.access import full_owner_policy
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import AssetORM


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def save(repository, asset, *, owner, scope, fingerprint, score=50, strategy="ema9_sma50"):
    now = datetime(2026, 8, 22, tzinfo=timezone.utc)
    return repository.save_run(
        asset=asset, owner_email=owner, scope=scope, config_hash=fingerprint,
        strategy_id=strategy, strategy_name=STRATEGIES[strategy].name,
        requested_start=now, requested_end=now, actual_start=now, actual_end=now,
        initial_capital=10000, fee_pct=0.03, slippage_pct=0.05, risk_free_rate_pct=0,
        parameters={}, metrics={"closed_trades": 10}, equity_curve=[], trades=[],
        ranking_score=score, sample_status="adequate",
        current_signal={"status": "buy", "as_of": now.isoformat()},
    )


def test_official_grid_is_bounded_and_covers_every_strategy():
    grid = official_grid(200)
    assert len(grid) == 200
    assert {row["strategy_id"] for row in grid} == set(STRATEGIES)
    assert {row["filters"].get("trend_combination") for row in grid} >= {"all", "any", "majority"}
    assert grid == official_grid(200)


def test_ranking_penalizes_small_samples_and_adds_validation():
    limited_score, status = robust_ranking({
        "cagr_pct": 100, "sharpe_ratio": 4, "sortino_ratio": 5,
        "max_drawdown_pct": -2, "profit_factor": 10, "closed_trades": 1, "bars": 1000,
    })
    adequate_score, adequate_status = robust_ranking({
        "cagr_pct": 15, "sharpe_ratio": 1.2, "sortino_ratio": 1.5,
        "max_drawdown_pct": -12, "profit_factor": 1.8, "closed_trades": 12, "bars": 1000,
    })
    assert status == "insufficient"
    assert adequate_status == "adequate"
    assert limited_score < adequate_score

    curve = [{"timestamp": f"2025-01-{day:02d}T00:00:00+00:00", "equity": 10000 + day * 10} for day in range(1, 29)]
    result = enrich_result({"metrics": {"closed_trades": 5, "bars": 28}, "equity_curve": curve})
    assert result["metrics"]["validation_bars"] >= 20
    assert result["ranking_score"] >= 0


def test_personal_history_is_isolated_and_official_catalog_is_shared():
    with make_session() as session:
        asset = AssetORM(ticker="BBAS3", asset_type="stock", sector="Financeiro")
        session.add(asset); session.flush()
        repository = BacktestRepository(session)
        personal_a = save(repository, asset, owner="a@example.com", scope="personal", fingerprint="a")
        save(repository, asset, owner="b@example.com", scope="personal", fingerprint="b")
        official = save(repository, asset, owner="official@system.local", scope="official", fingerprint="official", score=80)
        session.flush()

        visible = repository.list_runs(owner_email="a@example.com", limit=100)
        ids = {run.id for run, _asset in visible}
        assert personal_a.id in ids
        assert official.id in ids
        assert len(ids) == 2
        assert repository.get_run(personal_a.id, owner_email="b@example.com") is None
        assert repository.get_run(official.id, owner_email="b@example.com") is not None


def test_daily_cache_and_official_leaderboard_use_configuration_identity():
    with make_session() as session:
        asset = AssetORM(ticker="TAEE11", asset_type="stock", sector="Energia")
        session.add(asset); session.flush()
        repository = BacktestRepository(session)
        fingerprint = build_config_hash({"ticker": "TAEE11", "strategy": "ema9_sma50"})
        run = save(repository, asset, owner="owner@example.com", scope="personal", fingerprint=fingerprint)
        save(repository, asset, owner="official@system.local", scope="official", fingerprint="official-1", score=70)
        save(repository, asset, owner="official@system.local", scope="official", fingerprint="official-2", score=90)
        session.flush()

        assert repository.find_daily_cached(
            owner_email="owner@example.com", scope="personal", config_hash=fingerprint,
            market_date=run.market_date,
        ).id == run.id
        leaders = repository.leaderboard(tickers=["TAEE11"], per_asset=1)
        assert float(leaders["TAEE11"][0][0].ranking_score) == 90.0


def test_owner_has_signal_refresh_permission():
    policy = full_owner_policy("owner@example.com")
    assert policy["can_refresh_backtest_signals"] is True
