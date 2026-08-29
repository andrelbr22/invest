from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investment_engine.core.repositories.backtests import BacktestRepository
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import AssetORM, BacktestRunORM


def _run(asset_id, *, created_at, score, strategy_id="ema9_sma50", config_hash="same"):
    return BacktestRunORM(
        asset_id=asset_id,
        owner_email="owner@example.com",
        scope="official",
        config_hash=config_hash,
        market_date=date(2026, 8, 28),
        engine_version="1.20.3",
        strategy_id=strategy_id,
        strategy_name="Cruzamento de médias",
        requested_start=datetime(2021, 1, 1, tzinfo=timezone.utc),
        requested_end=datetime(2026, 1, 1, tzinfo=timezone.utc),
        initial_capital=Decimal("10000"),
        fee_pct=Decimal("0.03"),
        slippage_pct=Decimal("0.05"),
        risk_free_rate_pct=Decimal("0"),
        parameters_json={"strategy": {"fast_window": 9, "slow_window": 21}},
        metrics_json={"win_rate_pct": 61.5, "cagr_pct": 14.2},
        # These intentionally large fields must never be transferred by the
        # compact study projections.
        equity_curve_json=[{"value": index} for index in range(200)],
        result_json={"large": "x" * 10_000},
        ranking_score=Decimal(str(score)),
        sample_status="adequate",
        current_signal="buy",
        status="valid",
        created_at=created_at,
    )


def test_study_query_deduplicates_in_database_and_omits_heavy_payloads():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 28, 20, tzinfo=timezone.utc)
    with Session(engine) as session:
        asset = AssetORM(ticker="TEST3", name="Teste", asset_type="stock")
        session.add(asset)
        session.flush()
        session.add_all([
            _run(asset.id, created_at=now - timedelta(days=1), score=40),
            _run(asset.id, created_at=now, score=82),
        ])
        session.commit()

        study = BacktestRepository(session).strategy_study_records()
        configurations = BacktestRepository(session).strategy_configuration_records("ema9_sma50")

    assert len(study) == 1
    assert float(study[0]["ranking_score"]) == 82.0
    assert set(study[0]) == {"ticker", "strategy_id", "strategy_name", "ranking_score", "sample_status", "metrics"}
    assert len(configurations) == 1
    assert configurations[0]["parameters"]["strategy"]["fast_window"] == 9
    assert "equity_curve_json" not in configurations[0]
    assert "result_json" not in configurations[0]


def test_study_interface_uses_returned_score_and_opens_configurations():
    script = (Path(__file__).resolve().parents[1] / "investment_engine/web/static/app.js").read_text(encoding="utf-8")
    assert "r.study_score" in script
    assert "data-study-strategy" in script
    assert "/configurations" in script
