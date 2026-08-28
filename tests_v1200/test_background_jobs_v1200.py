from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investment_engine.core.repositories.background_jobs import BackgroundJobRepository
from investment_engine.infrastructure.db.base import Base


def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_enqueue_deduplicates_active_job_and_completes():
    with database_session() as session:
        repository = BackgroundJobRepository(session)
        first, created = repository.enqueue(
            "market_dashboard_refresh",
            {"snapshot_key": "main"},
            deduplication_key="market-dashboard:main",
        )
        second, created_again = repository.enqueue(
            "market_dashboard_refresh",
            {"snapshot_key": "main"},
            deduplication_key="market-dashboard:main",
        )
        assert created is True
        assert created_again is False
        assert second.id == first.id

        leased = repository.lease_next("worker-test", allowed_types={"market_dashboard_refresh"})
        assert leased.id == first.id
        assert leased.status == "running"
        assert leased.attempts == 1

        repository.heartbeat(leased, "worker-test", current=1, total=2, message="metade")
        repository.complete(leased, {"snapshot_key": "main"})
        session.commit()
        assert leased.status == "succeeded"
        assert leased.result_json == {"snapshot_key": "main"}
        assert leased.progress_current == 2


def test_failed_job_is_retried_then_becomes_terminal():
    with database_session() as session:
        repository = BackgroundJobRepository(session)
        row, _ = repository.enqueue("noop", {}, max_attempts=2)
        leased = repository.lease_next("worker-test")
        assert repository.fail(leased, error_code="temporary", retry_delay_seconds=1) is True
        assert row.status == "queued"

        row.run_after = datetime.now(timezone.utc)
        leased = repository.lease_next("worker-test")
        assert repository.fail(leased, error_code="permanent") is False
        assert row.status == "failed"
        assert row.finished_at is not None


def test_idempotency_key_reuses_terminal_job():
    with database_session() as session:
        repository = BackgroundJobRepository(session)
        first, _ = repository.enqueue("noop", {}, idempotency_key="same-request")
        leased = repository.lease_next("worker-test")
        repository.complete(leased, {"ok": True})
        second, created = repository.enqueue("noop", {}, idempotency_key="same-request")
        assert created is False
        assert second.id == first.id


def test_manual_retry_resets_attempt_budget_and_safe_error_fields():
    with database_session() as session:
        repository = BackgroundJobRepository(session)
        row, _ = repository.enqueue("noop", {}, max_attempts=1)
        leased = repository.lease_next("worker-test")
        repository.fail(leased, error_code="temporary", error_message="safe detail")
        assert row.status == "failed"
        assert row.attempts == 1

        repository.retry(row, requested_by="OWNER@EXAMPLE.COM")
        assert row.status == "queued"
        assert row.attempts == 0
        assert row.requested_by == "owner@example.com"
        assert row.last_error_code is None
        assert row.last_error_message is None
