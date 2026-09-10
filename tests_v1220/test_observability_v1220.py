from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from investment_engine.core import observability
from investment_engine.core.observability import (
    OperationalHealthService,
    RouteLatencyRegistry,
    request_metric_category,
    screener_metric_category,
)
from investment_engine.core.repositories import operations
from investment_engine.core.repositories.operations import (
    OperationsRepository,
    operational_incident_dict,
    runtime_lease_dict,
    service_heartbeat_dict,
)
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import (
    BackgroundJobORM,
    OperationalIncidentORM,
    RuntimeLeaseORM,
    ServiceHeartbeatORM,
)


UTC = timezone.utc


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def test_route_latency_percentiles_are_bounded_and_count_server_errors():
    registry = RouteLatencyRegistry(max_samples=20)

    for duration in range(1, 26):
        registry.observe("health", duration, 503 if duration >= 24 else 200)

    snapshot = registry.snapshot()
    health = next(item for item in snapshot["categories"] if item["key"] == "health")

    # The registry retains only the newest 20 samples (6..25) and uses the
    # nearest-rank percentile, which is stable for small operational windows.
    assert snapshot["window_size"] == 20
    assert health == {
        "key": "health",
        "count": 20,
        "p50_ms": 15.0,
        "p95_ms": 24.0,
        "max_ms": 25.0,
        "errors": 2,
        "target_p95_ms": 300.0,
        "sample_sufficient": True,
        "within_target": True,
    }

    registry.observe(None, 999, 500)
    assert next(
        item for item in registry.snapshot()["categories"] if item["key"] == "health"
    )["count"] == 20


@pytest.mark.parametrize(
    ("path", "method", "explicit", "expected"),
    [
        ("/health", "GET", None, "health"),
        ("/ready", "get", None, "health"),
        ("/health/db", "GET", None, "health"),
        ("/health/worker", "GET", None, "health"),
        ("/market-dashboard", "GET", None, "dashboard"),
        ("/assets/PETR4", "GET", None, "asset_detail"),
        ("/assets/PETR4/history", "GET", None, None),
        ("/market-dashboard", "POST", None, None),
        ("/anything", "POST", "custom", "custom"),
    ],
)
def test_request_route_classification(path, method, explicit, expected):
    assert request_metric_category(path, method, explicit) == expected


@pytest.mark.parametrize(
    ("limit", "expected"),
    [(1, "screener_50"), (50, "screener_50"), (51, "screener_100"), (100, "screener_100"), (101, "screener_large")],
)
def test_screener_route_classification(limit, expected):
    assert screener_metric_category(limit) == expected


def test_runtime_lease_has_one_holder_and_allows_expired_takeover(
    session_factory, monkeypatch,
):
    initial = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(operations, "utcnow", lambda: initial)

    with session_factory() as first_session:
        first = OperationsRepository(first_session)
        assert first.acquire_lease("scheduler:production", "worker-a", ttl_seconds=90)
        first_session.commit()

    with session_factory() as second_session:
        second = OperationsRepository(second_session)
        assert not second.acquire_lease("scheduler:production", "worker-b", ttl_seconds=90)
        lease = second_session.get(RuntimeLeaseORM, "scheduler:production")
        assert runtime_lease_dict(lease, now=initial)["active"] is True
        lease.expires_at = initial - timedelta(seconds=1)
        second_session.commit()

    takeover_at = initial + timedelta(minutes=2)
    monkeypatch.setattr(operations, "utcnow", lambda: takeover_at)
    with session_factory() as third_session:
        third = OperationsRepository(third_session)
        assert third.acquire_lease(
            "scheduler:production", "worker-b", ttl_seconds=90,
            metadata={"node": "oci-worker-2"},
        )
        lease = third_session.get(RuntimeLeaseORM, "scheduler:production")
        assert lease.holder_id == "worker-b"
        assert operations.aware(lease.acquired_at) == takeover_at
        assert lease.metadata_json == {"node": "oci-worker-2"}
        assert third.release_lease("scheduler:production", "worker-a") is False
        assert third.release_lease("scheduler:production", "worker-b") is True
        assert third.active_leases(now=takeover_at) == []


def test_service_heartbeat_upsert_preserves_start_and_marks_stopped(
    session_factory, monkeypatch,
):
    started = datetime(2026, 9, 9, 10, 0, tzinfo=UTC)
    first_seen = started + timedelta(seconds=5)
    monkeypatch.setattr(operations, "utcnow", lambda: first_seen)

    with session_factory() as session:
        repository = OperationsRepository(session)
        row = repository.upsert_heartbeat(
            service_id="worker-2:4321",
            node_id="worker-2",
            role="worker",
            environment="production-worker",
            version="1.22.0",
            commit_sha="abc123",
            scheduler_leader=True,
            alert_monitor_leader=True,
            metrics={"memory": {"used_pct": 42.5}},
            started_at=started,
        )
        session.commit()
        assert service_heartbeat_dict(row, now=first_seen + timedelta(seconds=15))["age_seconds"] == 15.0

        second_seen = first_seen + timedelta(seconds=30)
        monkeypatch.setattr(operations, "utcnow", lambda: second_seen)
        updated = repository.upsert_heartbeat(
            service_id="worker-2:4321",
            node_id="worker-2",
            role="worker",
            environment="production-worker",
            version="1.22.0",
            scheduler_leader=False,
            alert_monitor_leader=True,
            metrics={"memory": {"used_pct": 44.0}},
        )
        assert updated is row
        assert updated.started_at == started
        assert updated.last_seen_at == second_seen
        assert updated.scheduler_leader is False
        assert updated.metrics_json["memory"]["used_pct"] == 44.0

        repository.mark_service_stopped(row.service_id)
        assert row.status == "stopped"
        assert row.scheduler_leader is False
        assert row.alert_monitor_leader is False


def test_incident_lifecycle_is_deduplicated_resolved_and_reopened(
    session_factory, monkeypatch,
):
    first_seen = datetime(2026, 9, 9, 9, 0, tzinfo=UTC)
    monkeypatch.setattr(operations, "utcnow", lambda: first_seen)

    with session_factory() as session:
        repository = OperationsRepository(session)
        alerts = [{
            "code": "queue_stalled",
            "severity": "warning",
            "title": "Fila parada",
            "message": "A fila não avança.",
            "details": {"minutes": 20},
        }]
        repository.sync_incidents(alerts, now=first_seen)
        repository.sync_incidents(
            [{**alerts[0], "severity": "critical", "message": "A fila continua parada."}],
            now=first_seen + timedelta(minutes=5),
        )
        row = session.get(OperationalIncidentORM, "queue_stalled")
        assert operations.aware(row.first_seen_at) == first_seen
        assert operations.aware(row.last_seen_at) == first_seen + timedelta(minutes=5)
        assert row.severity == "critical"
        assert len(list(session.scalars(select(OperationalIncidentORM)))) == 1

        repository.sync_incidents([], now=first_seen + timedelta(minutes=10))
        assert row.status == "resolved"
        assert row.resolved_at == first_seen + timedelta(minutes=10)

        row.last_notified_at = first_seen + timedelta(minutes=11)
        repository.sync_incidents(alerts, now=first_seen + timedelta(minutes=15))
        assert row.status == "open"
        assert row.first_seen_at == first_seen + timedelta(minutes=15)
        assert row.resolved_at is None
        assert row.last_notified_at is None
        assert operational_incident_dict(row)["details"] == {"minutes": 20}


def test_partial_monitor_does_not_resolve_incidents_owned_by_another_scope(session_factory):
    now = datetime(2026, 9, 9, 11, 0, tzinfo=UTC)
    with session_factory() as session:
        repository = OperationsRepository(session)
        repository.sync_incidents([{
            "code": "route_latency:dashboard",
            "severity": "warning",
            "title": "Rota lenta",
            "message": "p95 acima da meta.",
        }], now=now)
        repository.sync_incidents(
            [],
            now=now + timedelta(minutes=1),
            managed_codes={"worker_missing", "queue_stalled"},
            managed_prefixes={"snapshot_"},
        )
        assert session.get(OperationalIncidentORM, "route_latency:dashboard").status == "open"

        repository.sync_incidents(
            [],
            now=now + timedelta(minutes=2),
            managed_prefixes={"route_latency:"},
        )
        assert session.get(OperationalIncidentORM, "route_latency:dashboard").status == "resolved"


def test_operational_overview_detects_queue_failures_resources_and_latency(
    session_factory, monkeypatch,
):
    now = datetime(2026, 9, 9, 15, 0, tzinfo=UTC)
    monkeypatch.setattr(observability, "all_refresh_statuses", lambda _session, _now: {})
    monkeypatch.setattr(observability.settings, "app_environment", "production")
    monkeypatch.setattr(observability.settings, "operational_worker_stale_seconds", 120)
    monkeypatch.setattr(observability.settings, "operational_queue_warning_minutes", 15)
    monkeypatch.setattr(observability.settings, "operational_queue_critical_minutes", 45)
    monkeypatch.setattr(observability.settings, "operational_failure_window_hours", 6)
    monkeypatch.setattr(observability.settings, "operational_failure_count", 3)

    registry = RouteLatencyRegistry(max_samples=20)
    for _ in range(20):
        registry.observe("dashboard", 1800, 200)
    monkeypatch.setattr(observability, "ROUTE_LATENCIES", registry)

    with session_factory() as session:
        session.add(ServiceHeartbeatORM(
            service_id="worker-2:123",
            node_id="worker-2",
            role="worker",
            environment="production-worker",
            version="1.22.0",
            started_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(seconds=10),
            status="running",
            scheduler_leader=True,
            alert_monitor_leader=True,
            metrics_json={},
        ))
        session.add(BackgroundJobORM(
            job_type="slow_refresh",
            status="queued",
            run_after=now - timedelta(minutes=50),
        ))
        session.add(BackgroundJobORM(
            job_type="stuck_refresh",
            status="running",
            run_after=now - timedelta(hours=1),
            heartbeat_at=now - timedelta(minutes=10),
        ))
        for minutes in (1, 2, 3):
            session.add(BackgroundJobORM(
                job_type="unstable_refresh",
                status="failed",
                run_after=now - timedelta(minutes=minutes + 1),
                finished_at=now - timedelta(minutes=minutes),
            ))
        session.flush()

        payload = OperationalHealthService(session).overview(
            local_resources={
                "memory": {"used_pct": 10.0},
                "container_memory": {"used_pct": 96.0},
                "swap": {"used_pct": 5.0},
                "disk": {"used_pct": 82.0},
            },
            include_route_metrics=True,
            sync_incidents=True,
            now=now,
            local_label="web-1",
        )

        codes = {item["code"] for item in payload["alerts"]}
        assert payload["status"] == "critical"
        assert payload["worker_health"]["status"] == "ok"
        assert payload["queue"]["oldest_due_minutes"] == 50.0
        assert payload["queue"]["stale_running"] == 1
        assert payload["repeated_failures"] == [{"job_type": "unstable_refresh", "count": 3}]
        assert {
            "queue_stalled",
            "running_heartbeat_stale",
            "repeated_job_failure:unstable_refresh",
            "memory_pressure:web-1",
            "disk_pressure:web-1",
            "route_latency:dashboard",
        } <= codes
        assert "worker_missing" not in codes
        assert "scheduler_leader_count" not in codes
        assert "alert_monitor_leader_count" not in codes

        persisted = {
            row.code: row.status
            for row in session.scalars(select(OperationalIncidentORM))
        }
        assert persisted["queue_stalled"] == "open"
        assert persisted["route_latency:dashboard"] == "open"
