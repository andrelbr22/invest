from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.core.jobs.schedules import (
    REFRESH_SCHEDULES,
    _refresh_status_payload,
    refresh_status,
)
from investment_engine.core.repositories.backtests import BacktestRepository, run_summary
from investment_engine.core.repositories.economic_series import SharedSnapshotRepository
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import AssetORM, SharedSnapshotORM


UTC = timezone.utc
NOW = datetime(2026, 10, 4, 18, tzinfo=UTC)


def _database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _capture(engine):
    statements: list[str] = []

    def listener(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", listener)
    return statements, listener


def test_backtest_history_projects_summary_only_and_detail_remains_complete():
    engine = _database()
    owner = "owner@example.com"
    curve = [{"date": f"2026-01-{day:02d}", "equity": day} for day in range(1, 29)]
    saved_result = {"large_series": list(range(500)), "marker": "detail-preserved"}

    with Session(engine) as session:
        asset = AssetORM(ticker="PETR4", name="Petrobras", asset_type="stock")
        session.add(asset)
        session.flush()
        run = BacktestRepository(session).save_run(
            asset=asset,
            owner_email=owner,
            scope="personal",
            config_hash="a" * 64,
            strategy_id="buy-hold",
            strategy_name="Buy & Hold",
            requested_start=NOW - timedelta(days=365),
            requested_end=NOW,
            actual_start=NOW - timedelta(days=360),
            actual_end=NOW - timedelta(days=1),
            initial_capital=10_000,
            fee_pct=0.1,
            slippage_pct=0.05,
            risk_free_rate_pct=10,
            parameters={"window": 20},
            metrics={"return_pct": 12.5},
            equity_curve=curve,
            trades=[],
            snapshot=saved_result,
            ranking_score=7.25,
            sample_status="adequate",
            current_signal={"status": "buy", "as_of": NOW},
            sector_label="Energia",
            market_date=NOW.date(),
            created_at=NOW,
        )
        run_id = run.id
        session.commit()

    # Re-read through the database before comparing. SQLite intentionally
    # returns timezone-naive DateTime values, while PostgreSQL preserves the
    # timezone; both the compact and complete repository paths must expose the
    # same representation for the active dialect.
    with Session(engine) as session:
        full = BacktestRepository(session).get_run(
            run_id, owner_email=owner, is_owner=True,
        )
        assert full is not None
        full_asset = session.get(AssetORM, full.asset_id)
        assert full_asset is not None
        expected_summary = run_summary(full, full_asset)

    with Session(engine) as session:
        statements, listener = _capture(engine)
        try:
            rows = BacktestRepository(session).list_runs(
                owner_email=owner, is_owner=True, limit=100,
            )
            count_after_query = len(statements)
            actual_summary = run_summary(*rows[0])
        finally:
            event.remove(engine, "before_cursor_execute", listener)

        assert actual_summary == expected_summary
        assert len(statements) == count_after_query == 1
        history_sql = statements[0]
        assert "equity_curve_json" not in history_sql
        assert "result_json" not in history_sql
        assert "metrics_json" in history_sql
        assert "parameters_json" in history_sql

        detailed = BacktestRepository(session).get_run(
            run_id, owner_email=owner, is_owner=True,
        )
        assert detailed is not None
        assert detailed.equity_curve_json == curve
        assert detailed.result_json["marker"] == "detail-preserved"
        assert detailed.result_json["large_series"] == list(range(500))


def test_refresh_status_projection_has_exact_payload_parity_without_large_json():
    engine = _database()
    key = "technical_intraday"
    snapshot_key = REFRESH_SCHEDULES[key].snapshot_key
    payload = {
        "quotes": {f"TICK{i}": {"price": i} for i in range(500)},
        "refresh": {"status": "partial", "warnings": ["provider_delayed"]},
        "status": "stale",
        "reason": "partial_provider_failure",
        "error_code": "upstream_timeout",
        "warnings": ["fallback_warning"],
    }
    with Session(engine) as session:
        session.add(SharedSnapshotORM(
            snapshot_key=snapshot_key,
            snapshot_kind="market_intraday",
            payload_json=payload,
            as_of=NOW - timedelta(minutes=2),
            last_error_code="last_error",
            last_error_at=NOW - timedelta(minutes=1),
        ))
        session.commit()

    with Session(engine) as session:
        repository = SharedSnapshotRepository(session)
        full = repository.get(snapshot_key)
        statements, listener = _capture(engine)
        try:
            projected = repository.get_status(snapshot_key)
        finally:
            event.remove(engine, "before_cursor_execute", listener)

        assert projected is not None
        assert "quotes" not in projected.payload_json
        assert projected.payload_json == {
            "refresh": {"status": "partial", "warnings": ["provider_delayed"]},
            "status": "stale",
            "reason": "partial_provider_failure",
            "error_code": "upstream_timeout",
            "warnings": ["fallback_warning"],
        }
        expected = _refresh_status_payload(
            key=key, current=NOW, snapshot=full, job=None,
        )
        actual = _refresh_status_payload(
            key=key, current=NOW, snapshot=projected, job=None,
        )
        assert actual == expected
        assert len(statements) == 1
        projection_sql = statements[0]
        assert "json_extract" in projection_sql
        assert "shared_snapshots.payload_json as" not in projection_sql


def test_refresh_status_can_reuse_loaded_snapshot_without_second_snapshot_query():
    engine = _database()
    key = "technical_intraday"
    snapshot_key = REFRESH_SCHEDULES[key].snapshot_key
    with Session(engine) as session:
        session.add(SharedSnapshotORM(
            snapshot_key=snapshot_key,
            snapshot_kind="market_intraday",
            payload_json={"quotes": {"PETR4": {"price": 42.0}}},
            as_of=NOW,
        ))
        session.commit()

    with Session(engine) as session:
        row = SharedSnapshotRepository(session).get(snapshot_key)
        statements, listener = _capture(engine)
        try:
            reused = refresh_status(session, key, NOW, row)
        finally:
            event.remove(engine, "before_cursor_execute", listener)

        assert reused["key"] == key
        assert reused["status"] == "updated"
        assert all("shared_snapshots" not in statement for statement in statements)
        # Only the latest background job is still needed for queued/running state.
        assert sum("background_jobs" in statement for statement in statements) == 1
