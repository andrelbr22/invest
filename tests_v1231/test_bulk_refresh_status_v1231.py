from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from investment_engine.api.app import _market_dashboard_payload
from investment_engine.core.jobs.schedules import (
    REFRESH_SCHEDULES,
    all_refresh_statuses,
    refresh_status,
)
from investment_engine.core.repositories.background_jobs import BackgroundJobRepository
from investment_engine.core.repositories.economic_series import SharedSnapshotRepository
from investment_engine.infrastructure.db.base import Base


def _database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_bulk_repositories_normalize_keys_and_keep_only_the_latest_job():
    engine = _database()
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        snapshots = SharedSnapshotRepository(session)
        snapshots.save_valid(
            snapshot_key="MARKET:FX",
            snapshot_kind="market_fx",
            payload={"fx": [{"symbol": "USD/BRL"}]},
            as_of=now,
        )
        jobs = BackgroundJobRepository(session)
        old, _ = jobs.enqueue(
            "market_group_refresh",
            deduplication_key="refresh:fx",
            idempotency_key="bulk-old",
        )
        jobs.complete(old)
        old.created_at = now - timedelta(minutes=10)
        latest, _ = jobs.enqueue(
            "market_group_refresh",
            deduplication_key="refresh:fx",
            idempotency_key="bulk-latest",
        )
        jobs.complete(latest)
        latest.created_at = now
        session.commit()

        snapshot_map = snapshots.get_many([" market:FX ", "missing", "market:fx"])
        job_map = jobs.latest_for_deduplications(["refresh:fx", "refresh:missing"])

        assert list(snapshot_map) == ["market:fx"]
        assert job_map["refresh:fx"].id == latest.id
        assert "refresh:missing" not in job_map


def test_all_refresh_statuses_preserves_payload_and_uses_two_selects():
    engine = _database()
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        SharedSnapshotRepository(session).save_valid(
            snapshot_key=REFRESH_SCHEDULES["macro"].snapshot_key,
            snapshot_kind="market_macro",
            payload={
                "inflation": [{"label": "IPCA"}],
                "refresh": {"status": "partial", "warnings": [{"field": "fixed_income"}]},
            },
            source="BCB",
            as_of=now,
        )
        row, _ = BackgroundJobRepository(session).enqueue(
            "market_group_refresh",
            deduplication_key="refresh:fx",
            idempotency_key="bulk-status-fx",
        )
        session.commit()

        expected_macro = refresh_status(session, "macro", now + timedelta(minutes=1))
        expected_fx = refresh_status(session, "fx", now + timedelta(minutes=1))
        session.expire_all()
        select_count = 0

        def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
            nonlocal select_count
            if statement.lstrip().upper().startswith("SELECT"):
                select_count += 1

        event.listen(engine, "before_cursor_execute", count_selects)
        try:
            statuses = all_refresh_statuses(session, now + timedelta(minutes=1))
        finally:
            event.remove(engine, "before_cursor_execute", count_selects)

        assert statuses["macro"] == expected_macro
        assert statuses["fx"] == expected_fx
        assert statuses["macro"]["status"] == "partial"
        assert statuses["fx"]["status"] == "queued"
        assert statuses["fx"]["job_id"] == str(row.id)
        assert select_count == 2


def test_market_dashboard_reuses_the_snapshot_batch(monkeypatch):
    engine = _database()
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        SharedSnapshotRepository(session).save_valid(
            snapshot_key=REFRESH_SCHEDULES["fx"].snapshot_key,
            snapshot_kind="market_fx",
            payload={"fx": [{"symbol": "USD/BRL", "price": 5.42}]},
            as_of=now,
        )
        session.commit()

        def unexpected_single_read(_self, _snapshot_key):
            raise AssertionError("the dashboard must reuse the bulk-loaded snapshot map")

        monkeypatch.setattr(SharedSnapshotRepository, "get", unexpected_single_read)
        payload = _market_dashboard_payload(session)

        assert payload["data"]["fx"][0]["symbol"] == "USD/BRL"
        assert set(payload["updates"]) == set(REFRESH_SCHEDULES)
