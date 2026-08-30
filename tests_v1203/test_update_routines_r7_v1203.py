from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investment_engine.core.jobs import handlers
from investment_engine.core.jobs.schedules import (
    REFRESH_SCHEDULES,
    enqueue_due_refreshes,
    enqueue_refresh,
    refresh_status,
    slots_for_day,
)
from investment_engine.core.repositories.background_jobs import BackgroundJobRepository
from investment_engine.core.repositories.economic_series import SharedSnapshotRepository
from investment_engine.core.repositories.news_cache import NewsCacheRepository
from investment_engine.infrastructure.db.base import Base


ROOT = Path(__file__).resolve().parents[1]


def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def local_clock(value):
    return value.astimezone(ZoneInfo("America/Sao_Paulo"))


def test_approved_schedule_windows_and_offsets():
    weekday = date(2026, 8, 28)
    crypto = [local_clock(item) for item in slots_for_day(REFRESH_SCHEDULES["crypto"], weekday)]
    intraday = [local_clock(item) for item in slots_for_day(REFRESH_SCHEDULES["technical_intraday"], weekday)]

    assert len(crypto) == 48
    assert (crypto[0].hour, crypto[0].minute) == (0, 5)
    assert (crypto[-1].hour, crypto[-1].minute) == (23, 35)
    assert (intraday[0].hour, intraday[0].minute) == (10, 5)
    assert (intraday[-1].hour, intraday[-1].minute) == (18, 0)
    assert REFRESH_SCHEDULES["technical_intraday"].catch_up is False


def test_intraday_does_not_catch_up_outside_market_window():
    with database_session() as session:
        created = enqueue_due_refreshes(
            session,
            datetime(2026, 8, 29, 15, 0, tzinfo=timezone.utc),  # Saturday noon in Sao Paulo.
        )
        assert "technical_intraday" not in created


def test_manual_refresh_has_five_minute_cooldown():
    now = datetime.now(timezone.utc)
    with database_session() as session:
        first, created = enqueue_refresh(session, "fx", trigger="manual", now=now, force=True)
        leased = BackgroundJobRepository(session).lease_next("test")
        BackgroundJobRepository(session).complete(leased, {"ok": True})
        session.commit()

        same, created_again = enqueue_refresh(
            session, "fx", trigger="manual", now=now + timedelta(minutes=4), force=True,
        )
        assert created is True
        assert created_again is False
        assert same.id == first.id

        _next, created_after_cooldown = enqueue_refresh(
            session, "fx", trigger="manual", now=now + timedelta(minutes=6), force=True,
        )
        assert created_after_cooldown is True


def test_partial_snapshot_is_visible_without_losing_valid_data():
    now = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)
    with database_session() as session:
        SharedSnapshotRepository(session).save_valid(
            snapshot_key=REFRESH_SCHEDULES["macro"].snapshot_key,
            snapshot_kind="market_macro",
            payload={
                "fixed_income": [{"label": "CDI"}],
                "inflation": [{"label": "IPCA"}],
                "refresh": {"status": "partial", "warnings": [{"field": "fixed_income"}]},
            },
            source="BCB",
            as_of=now,
        )
        session.commit()

        status = refresh_status(session, "macro", now + timedelta(minutes=1))
        assert status["status"] == "partial"
        assert status["warnings"] == [{"field": "fixed_income"}]


def test_market_group_preserves_previous_subsource_when_one_provider_fails(monkeypatch):
    class Service:
        def fixed_income(self):
            raise RuntimeError("provider unavailable")

        def inflation(self):
            return [{"label": "IPCA", "value_12m": 4.2}]

    captured = {}
    monkeypatch.setattr(handlers, "MarketDashboardService", Service)
    monkeypatch.setattr(
        handlers,
        "_previous_snapshot_payload",
        lambda _key: {"fixed_income": [{"label": "CDI", "annual_return_pct": 14.9}]},
    )

    def save(**kwargs):
        captured.update(kwargs)
        return {"saved": True}

    monkeypatch.setattr(handlers, "_save_snapshot", save)

    result = handlers.handle_market_group_refresh({"group": "macro", "snapshot_key": "market:macro"})

    assert result == {"saved": True}
    assert captured["result"]["fixed_income"][0]["label"] == "CDI"
    assert captured["result"]["inflation"][0]["label"] == "IPCA"
    assert captured["result"]["refresh"]["status"] == "partial"


def test_news_manual_refresh_uses_the_same_cooldown():
    with database_session() as session:
        repository = NewsCacheRepository(session)
        row, created = repository.request_refresh(
            owner_email="user@example.com", cache_kind="recommendations",
            cache_key="all", trigger="manual", force=True,
        )
        repository.mark_completed(row, {"items": []})
        session.commit()

        same, created_again = repository.request_refresh(
            owner_email="user@example.com", cache_kind="recommendations",
            cache_key="all", trigger="manual", force=True,
        )
        assert created is True
        assert created_again is False
        assert same.id == row.id


def test_interface_shows_update_metadata_and_worker_isolated_from_web_process():
    script = (ROOT / "investment_engine/web/static/app.js").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.oracle-web.yml").read_text(encoding="utf-8")
    api_source = (ROOT / "investment_engine/api/app.py").read_text(encoding="utf-8")
    handler_source = (ROOT / "investment_engine/core/jobs/handlers.py").read_text(encoding="utf-8")

    assert "Atualizações deste painel" in script
    assert "Detalhes das fontes" in script
    assert "próxima rodada" in script
    assert "Atualização parcial" in script
    assert 'IN_PROCESS_BACKGROUND_WORKER_ENABLED: "true"' in compose
    assert 'DATABASE_POOL_SIZE: "1"' in compose
    app_block, worker_block = compose.split("  worker:", 1)
    assert 'ALERT_MONITOR_ENABLED: "false"' in app_block
    assert 'ALERT_MONITOR_ENABLED: "true"' in worker_block
    assert '"user_news_refresh": handle_user_news_refresh' in handler_source
    assert 'BackgroundTasks' not in api_source
