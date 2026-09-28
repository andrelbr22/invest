from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from investment_engine.core.cache import BoundedTTLCache
from investment_engine.core.jobs.retention import OperationalRetentionService
from investment_engine.infrastructure.db.base import Base
from investment_engine.infrastructure.db.models import (
    BackgroundJobORM,
    OperationalArchiveORM,
    OperationalIncidentORM,
    ServiceHeartbeatORM,
)


api_module = importlib.import_module("investment_engine.api.app")


def _old_job(
    *,
    key: str,
    created_at: datetime,
    trigger: str = "scheduled",
    requested_by: str | None = None,
    status: str = "succeeded",
) -> BackgroundJobORM:
    return BackgroundJobORM(
        job_type="market_group_refresh",
        status=status,
        payload_json={"trigger": trigger, "snapshot_key": "market:macro"},
        result_json={"ok": True},
        requested_by=requested_by,
        deduplication_key=key,
        created_at=created_at,
        updated_at=created_at,
        finished_at=created_at if status == "succeeded" else None,
        run_after=created_at,
    )


def test_bounded_ttl_cache_copies_values_and_evicts_oldest_entry():
    cache = BoundedTTLCache(30, max_entries=2)
    original = {"items": [1]}
    cache.set("a", original)
    original["items"].append(2)
    found, first = cache.get("a")
    assert found is True
    assert first == {"items": [1]}
    first["items"].append(3)
    assert cache.get("a")[1] == {"items": [1]}

    cache.set("b", {"value": 2})
    cache.set("c", {"value": 3})
    assert cache.get("a") == (False, None)
    assert len(cache) == 2


def test_cache_invalidation_wins_over_a_concurrent_stale_loader():
    cache = BoundedTTLCache(30, max_entries=2)
    found, _value, generation = cache.get_with_generation("permission")
    assert found is False

    # The update can invalidate a key before the older request publishes its
    # database result.  That old result must never be reinserted.
    cache.invalidate(lambda key: key == "permission")
    assert cache.set_if_generation("permission", {"allowed": True}, generation) is False
    assert cache.get("permission") == (False, None)


def test_access_policy_cache_is_short_lived_and_explicitly_invalidated(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    calls = {"count": 0}

    def fake_get(_repository, _email):
        calls["count"] += 1
        return None

    monkeypatch.setattr(api_module.AccessPolicyRepository, "get", fake_get)
    api_module._ACCESS_POLICY_CACHE.invalidate()
    with Session(engine) as session:
        first = api_module._access_policy(session, "cache@example.com")
        second = api_module._access_policy(session, "cache@example.com")
        assert first == second
        assert calls["count"] == 1
        api_module._invalidate_access_policy_cache(session, "cache@example.com")
        api_module._access_policy(session, "cache@example.com")
        assert calls["count"] == 2


def test_shared_payload_cache_avoids_rebuilding_and_returns_copies(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    calls = {"count": 0}

    def fake_build(_session):
        calls["count"] += 1
        return {"data": {"version": calls["count"]}}

    monkeypatch.setattr(api_module, "_build_market_dashboard_payload", fake_build)
    api_module._SHARED_RESPONSE_CACHE.invalidate()
    with Session(engine) as session:
        first = api_module._market_dashboard_payload(session)
        first["data"]["version"] = 99
        second = api_module._market_dashboard_payload(session)
        assert second == {"data": {"version": 1}}
        assert calls["count"] == 1
        api_module._invalidate_shared_response_cache(session)
        assert api_module._market_dashboard_payload(session) == {"data": {"version": 2}}


def test_retention_archives_only_old_reproducible_scheduled_jobs_and_keeps_latest():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=80)
    with Session(engine) as session:
        oldest = _old_job(key="refresh:macro", created_at=old)
        latest = _old_job(key="refresh:macro", created_at=old + timedelta(days=1))
        manual = _old_job(
            key="refresh:fx", created_at=old, trigger="manual", requested_by="owner@example.com",
        )
        failed = _old_job(key="refresh:crypto", created_at=old, status="failed")
        session.add_all([oldest, latest, manual, failed])
        session.commit()

        preview = OperationalRetentionService(session).run(
            apply=False, job_retention_days=45, operational_retention_days=180, now=now,
        )
        assert preview["mode"] == "dry_run"
        assert preview["eligible"]["background_jobs"] == 1
        assert preview["deleted"] == 0
        assert session.get(BackgroundJobORM, oldest.id) is not None

        applied = OperationalRetentionService(session).run(
            apply=True, job_retention_days=45, operational_retention_days=180, now=now,
        )
        session.commit()
        assert applied["archived"] == 1
        assert session.get(BackgroundJobORM, oldest.id) is None
        assert session.get(BackgroundJobORM, latest.id) is not None
        assert session.get(BackgroundJobORM, manual.id) is not None
        assert session.get(BackgroundJobORM, failed.id) is not None
        archive = session.scalar(select(OperationalArchiveORM))
        assert archive.source_id == str(oldest.id)
        assert archive.schema_version == "1"
        assert len(archive.checksum) == 64
        assert archive.record_json["payload_json"]["trigger"] == "scheduled"
        assert OperationalRetentionService(session).verify_archive()["valid"] is True


def test_retention_never_removes_the_only_refresh_status_row():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        only = _old_job(key="refresh:macro", created_at=now - timedelta(days=120))
        session.add(only)
        session.commit()
        result = OperationalRetentionService(session).run(apply=True, now=now)
        session.commit()
        assert result["eligible"]["background_jobs"] == 0
        assert session.get(BackgroundJobORM, only.id) is not None


def test_ineligible_prefix_cannot_starve_later_safe_retention_rows():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=100)
    with Session(engine) as session:
        # More than the historical scan multiplier, all deliberately unsafe.
        for index in range(8):
            session.add(_old_job(
                key=f"refresh:access-{index}",
                created_at=old + timedelta(minutes=index),
                trigger="access",
            ))
        removable = _old_job(
            key="refresh:scheduled", created_at=old + timedelta(hours=1),
        )
        newest = _old_job(
            key="refresh:scheduled", created_at=old + timedelta(hours=2),
        )
        session.add_all([removable, newest])
        session.commit()

        result = OperationalRetentionService(session).run(apply=True, limit=1, now=now)
        session.commit()
        assert result["deleted"] == 1
        assert session.get(BackgroundJobORM, removable.id) is None
        assert session.get(BackgroundJobORM, newest.id) is not None


def test_operational_archive_migration_preserves_nonempty_archive_on_downgrade():
    migration = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "alembic" / "versions" / "0028_v1_23_operational_retention.py"
    ).read_text(encoding="utf-8")
    assert "SELECT COUNT(*) FROM operational_archive" in migration
    assert "if archived_rows:" in migration
    assert "return" in migration
    assert "operational_archive_immutable" in migration
    assert "ix_background_jobs_retention_scan" in migration
    handlers = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "investment_engine" / "core" / "jobs" / "handlers.py"
    ).read_text(encoding="utf-8")
    assert "apply=settings.operational_retention_apply_enabled" in handlers


def test_archive_verification_detects_a_changed_payload_in_test_database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        old = _old_job(key="refresh:verify", created_at=now - timedelta(days=100))
        newest = _old_job(key="refresh:verify", created_at=now - timedelta(days=90))
        session.add_all([old, newest])
        session.commit()
        service = OperationalRetentionService(session)
        service.run(apply=True, now=now)
        session.commit()
        archive = session.scalar(select(OperationalArchiveORM))
        archive.record_json = {**archive.record_json, "message": "changed"}
        session.commit()
        result = service.verify_archive()
        assert result["valid"] is False
        assert result["mismatch_count"] == 1


def test_retention_archives_repeated_incident_and_service_lifecycles():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    first_cycle = now - timedelta(days=240)
    second_cycle = now - timedelta(days=220)

    with Session(engine) as session:
        session.add(OperationalIncidentORM(
            code="queue:stalled", severity="warning", status="resolved",
            title="Fila", message="Resolvida", details_json={},
            first_seen_at=first_cycle - timedelta(hours=1), last_seen_at=first_cycle,
            resolved_at=first_cycle,
        ))
        session.add(ServiceHeartbeatORM(
            service_id="worker:production:primary", node_id="primary", role="worker",
            environment="production", version="1.23.1", started_at=first_cycle - timedelta(hours=1),
            last_seen_at=first_cycle, status="stopped", metrics_json={},
        ))
        session.commit()
        OperationalRetentionService(session).run(apply=True, now=now)
        session.commit()

        session.add(OperationalIncidentORM(
            code="queue:stalled", severity="warning", status="resolved",
            title="Fila", message="Resolvida novamente", details_json={"cycle": 2},
            first_seen_at=second_cycle - timedelta(hours=1), last_seen_at=second_cycle,
            resolved_at=second_cycle,
        ))
        session.add(ServiceHeartbeatORM(
            service_id="worker:production:primary", node_id="primary", role="worker",
            environment="production", version="1.23.1", started_at=second_cycle - timedelta(hours=1),
            last_seen_at=second_cycle, status="stopped", metrics_json={"cycle": 2},
        ))
        session.commit()
        OperationalRetentionService(session).run(apply=True, now=now)
        session.commit()

        archives = list(session.scalars(
            select(OperationalArchiveORM).order_by(OperationalArchiveORM.entity_type),
        ))
        assert len(archives) == 4
        assert len({row.source_id for row in archives}) == 4
