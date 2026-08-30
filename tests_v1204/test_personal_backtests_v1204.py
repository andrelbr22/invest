from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from investment_engine.api.app import _request_email, app, get_db
from investment_engine.core.backtesting import engine as backtest_engine
from investment_engine.core.repositories.access import full_owner_policy
from investment_engine.core.repositories.background_jobs import BackgroundJobRepository
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.config import settings


ROOT = Path(__file__).resolve().parents[1]


def database_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def price_bars(count=80):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [{
        "timestamp": start + timedelta(days=index),
        "open": 100 + index, "high": 101 + index, "low": 99 + index,
        "close": 100 + index, "adjusted_close": 100 + index, "volume": 1000,
    } for index in range(count)]


def test_true_strategy_combination_changes_position(monkeypatch):
    def fake_signal(frame, strategy_id, _params=None):
        active = pd.Series(1.0 if strategy_id == "ema9_sma50" else 0.0, index=frame.index)
        return active, pd.DataFrame({"estado": active}, index=frame.index), {}

    monkeypatch.setattr(backtest_engine, "build_signal", fake_signal)
    common = dict(
        bars=price_bars(), strategy_id="ema9_sma50",
        combination_strategy_ids=["ema9_sma50", "ema9_sma40"],
        requested_start=datetime(2025, 1, 10, tzinfo=timezone.utc),
        requested_end=datetime(2025, 3, 15, tzinfo=timezone.utc),
    )
    every = backtest_engine.run_backtest(**common, combination_rule="all")
    either = backtest_engine.run_backtest(**common, combination_rule="any")
    assert every["metrics"]["exposure_pct"] == 0
    assert either["metrics"]["exposure_pct"] > 90
    assert either["strategy_components"] == ["ema9_sma50", "ema9_sma40"]
    assert either["combination_rule"] == "any"


def test_owner_receives_approved_backtest_limits():
    policy = full_owner_policy("owner@example.com")
    assert policy["backtest_asset_limit"] == 10
    assert policy["backtest_strategy_limit"] == 5
    assert policy["backtest_daily_limit"] == 20
    assert policy["backtest_cooldown_seconds"] == 60


def test_personal_request_is_queued_and_visible_without_running_inline():
    factory = database_factory()
    test_email = sorted(settings.owner_emails)[0] if settings.owner_emails else "local-owner@localhost"

    def override_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[_request_email] = lambda: test_email
    try:
        client = TestClient(app, base_url="http://localhost")
        response = client.post("/backtests/matrix", json={
            "tickers": ["PETR4"],
            "strategy_ids": ["ema9_sma50", "ema9_sma40"],
            "execution_mode": "combined", "combination_rule": "all",
            "asset_type": "stock", "period": "1y",
        })
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "queued"
        assert payload["job_id"]
        jobs = client.get("/backtests/jobs").json()
        assert jobs[0]["job_type"] == "personal_backtest_matrix"
        assert jobs[0]["requested_by"] == test_email
    finally:
        app.dependency_overrides.clear()


def test_queue_exposes_safe_progress_and_requester_filter():
    factory = database_factory()
    with factory() as session:
        repository = BackgroundJobRepository(session)
        row, _ = repository.enqueue("personal_backtest_matrix", {}, requested_by="USER@EXAMPLE.COM")
        repository.lease_next("worker", allowed_types={"personal_backtest_matrix"})
        repository.report_progress(row.id, current=2, total=5, message="2 de 5")
        session.commit()
        visible = repository.list_for_requester("user@example.com", job_type="personal_backtest_matrix")
        assert visible == [row]
        assert row.progress_current == 2
        assert row.progress_total == 5


def test_web_ui_contains_async_combination_and_export_controls():
    script = (ROOT / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    for expected in (
        "Combinar estratégias", "Todas confirmam (E)", "Maioria confirma",
        "watchBacktestJob", "Exportar operações em CSV", "Você pode continuar usando o site",
    ):
        assert expected in script
