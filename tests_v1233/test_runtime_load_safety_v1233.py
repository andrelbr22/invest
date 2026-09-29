from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _service_block(compose: str, service: str, next_service: str) -> str:
    start = compose.index(f"  {service}:")
    end = compose.index(f"  {next_service}:", start)
    return compose[start:end]


def test_current_metrics_continuation_is_bounded_delayed_and_low_priority(monkeypatch):
    import investment_engine.core.jobs.handlers as handlers

    fixed_now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
    captured: dict = {}

    class FakeSession:
        committed = False
        rolled_back = False
        closed = False

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    class FakeCurrentMetricsService:
        def __init__(self, session):
            captured["service_session"] = session

        def sync_batch(self, *, after_ticker, limit):
            captured["after_ticker"] = after_ticker
            captured["limit"] = limit
            return {
                "errors": [],
                "remaining": 12,
                "next_cursor": "BBBB3",
            }

    class FakeSnapshotRepository:
        def __init__(self, session):
            captured["snapshot_session"] = session

        def save_valid(self, **kwargs):
            captured["snapshot"] = kwargs

    class FakeJobRepository:
        def __init__(self, session):
            captured["job_session"] = session

        def enqueue(self, job_type, payload, **kwargs):
            captured["job_type"] = job_type
            captured["job_payload"] = payload
            captured["job_options"] = kwargs
            return object(), True

    session = FakeSession()
    monkeypatch.setattr(handlers, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(handlers, "AssetCurrentMetricsService", FakeCurrentMetricsService)
    monkeypatch.setattr(handlers, "SharedSnapshotRepository", FakeSnapshotRepository)
    monkeypatch.setattr(handlers, "BackgroundJobRepository", FakeJobRepository)
    monkeypatch.setattr(handlers, "utcnow", lambda: fixed_now)
    monkeypatch.setattr(handlers.settings, "current_metrics_backfill_max_batch_size", 100)
    monkeypatch.setattr(handlers.settings, "current_metrics_continuation_delay_seconds", 3)
    monkeypatch.setattr(handlers.settings, "current_metrics_continuation_priority", 180)

    result = handlers.handle_current_metrics_refresh({
        "snapshot_key": "market:current-metrics",
        "after_ticker": "AAAA3",
        # Simulates a V1.23.2 queue row already persisted before the safer cap.
        "batch_size": 250,
        "cycle": "release:test",
    })

    assert captured["limit"] == 100
    assert captured["job_type"] == "current_metrics_refresh"
    assert captured["job_payload"]["batch_size"] == 100
    assert captured["job_payload"]["after_ticker"] == "BBBB3"
    assert captured["job_options"]["priority"] == 180
    assert captured["job_options"]["run_after"] == fixed_now + timedelta(seconds=3)
    assert result["status"] == "partial"
    assert session.committed is True
    assert session.rolled_back is False
    assert session.closed is True


def test_release_enqueue_clamps_explicit_oversized_batches():
    enqueue_script = _read("scripts/enqueue_current_metrics_refresh.py")

    assert "settings.current_metrics_backfill_batch_size" in enqueue_script
    assert "settings.current_metrics_backfill_max_batch_size" in enqueue_script
    assert "min(max_batch_size, int(args.batch_size))" in enqueue_script


def test_primary_vm_keeps_web_and_database_ahead_of_batch_worker():
    compose = _read("docker-compose.oracle-web.yml")
    remote_worker = _read("deployment/second-instance/docker-compose.worker.yml")
    postgres = _service_block(compose, "postgres", "app")
    app = _service_block(compose, "app", "staging")
    staging = _service_block(compose, "staging", "worker")
    worker = _service_block(compose, "worker", "production-migration")

    postgres_shares = int(re.search(r"cpu_shares:\s*(\d+)", postgres).group(1))
    app_shares = int(re.search(r"cpu_shares:\s*(\d+)", app).group(1))
    staging_shares = int(re.search(r"cpu_shares:\s*(\d+)", staging).group(1))
    worker_shares = int(re.search(r"cpu_shares:\s*(\d+)", worker).group(1))

    assert app_shares == 1024
    assert postgres_shares == app_shares
    assert worker_shares <= staging_shares < app_shares
    assert 'CURRENT_METRICS_BACKFILL_BATCH_SIZE: "50"' in worker
    assert 'CURRENT_METRICS_BACKFILL_MAX_BATCH_SIZE: "100"' in worker
    assert 'CURRENT_METRICS_CONTINUATION_DELAY_SECONDS: "3"' in worker
    assert 'CURRENT_METRICS_CONTINUATION_PRIORITY: "180"' in worker
    assert 'CURRENT_METRICS_BACKFILL_BATCH_SIZE: "50"' in staging
    assert 'CURRENT_METRICS_BACKFILL_MAX_BATCH_SIZE: "100"' in staging
    assert 'CURRENT_METRICS_BACKFILL_BATCH_SIZE: "50"' in remote_worker
    assert 'CURRENT_METRICS_CONTINUATION_DELAY_SECONDS: "3"' in remote_worker
    assert "stop staging" not in worker


def test_staging_migration_retries_twice_then_fails_closed():
    update = _read("deployment/update-staging-from-github.sh")
    migration = update[
        update.index("migration_succeeded=false"):
        update.index('FDI_RELEASE_COMMIT="${TARGET_COMMIT}"')
    ]

    assert "STAGING_MIGRATION_ATTEMPTS=2" in update
    assert "STAGING_MIGRATION_RETRY_SECONDS=5" in update
    assert "attempt <= STAGING_MIGRATION_ATTEMPTS" in migration
    assert "run --rm --no-deps staging-migration" in migration
    assert 'sleep "${STAGING_MIGRATION_RETRY_SECONDS}"' in migration
    assert 'if [[ "${migration_succeeded}" != "true" ]]' in migration
    assert 'stop staging >/dev/null 2>&1 || true' in migration
    assert 'echo "${TARGET_COMMIT}" > "${FAILED_FILE}"' in migration
    assert "staging permanece parado" in migration
    assert "exit 1" in migration
    assert "alembic downgrade" not in update
