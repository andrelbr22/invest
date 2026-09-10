from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...infrastructure.db.models import (
    OperationalIncidentORM,
    RuntimeLeaseORM,
    ServiceHeartbeatORM,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def service_heartbeat_dict(row: ServiceHeartbeatORM, *, now: datetime | None = None) -> dict:
    current = now or utcnow()
    seen = aware(row.last_seen_at)
    return {
        "service_id": row.service_id,
        "node_id": row.node_id,
        "role": row.role,
        "environment": row.environment,
        "version": row.version,
        "commit_sha": row.commit_sha,
        "started_at": row.started_at,
        "last_seen_at": row.last_seen_at,
        "age_seconds": round(max(0.0, (current - seen).total_seconds()), 1) if seen else None,
        "status": row.status,
        "scheduler_leader": bool(row.scheduler_leader),
        "alert_monitor_leader": bool(row.alert_monitor_leader),
        "metrics": dict(row.metrics_json or {}),
    }


def runtime_lease_dict(row: RuntimeLeaseORM, *, now: datetime | None = None) -> dict:
    current = now or utcnow()
    expires = aware(row.expires_at)
    return {
        "lease_name": row.lease_name,
        "holder_id": row.holder_id,
        "heartbeat_at": row.heartbeat_at,
        "expires_at": row.expires_at,
        "active": bool(expires and expires > current),
        "metadata": dict(row.metadata_json or {}),
    }


def operational_incident_dict(row: OperationalIncidentORM) -> dict:
    return {
        "code": row.code,
        "severity": row.severity,
        "status": row.status,
        "title": row.title,
        "message": row.message,
        "details": dict(row.details_json or {}),
        "first_seen_at": row.first_seen_at,
        "last_seen_at": row.last_seen_at,
        "resolved_at": row.resolved_at,
        "last_notified_at": row.last_notified_at,
    }


class OperationsRepository:
    def __init__(self, session: Session):
        self.session = session

    def acquire_lease(
        self, lease_name: str, holder_id: str, *, ttl_seconds: int, metadata: dict | None = None,
    ) -> bool:
        now = utcnow()
        name = str(lease_name or "").strip()[:80]
        holder = str(holder_id or "").strip()[:160]
        if not name or not holder:
            raise ValueError("runtime_lease_identity_required")
        row = self.session.scalar(
            select(RuntimeLeaseORM).where(RuntimeLeaseORM.lease_name == name).with_for_update()
        )
        if row is None:
            try:
                with self.session.begin_nested():
                    self.session.add(RuntimeLeaseORM(
                        lease_name=name,
                        holder_id=holder,
                        acquired_at=now,
                        heartbeat_at=now,
                        expires_at=now + timedelta(seconds=max(30, int(ttl_seconds))),
                        metadata_json=dict(metadata or {}),
                    ))
                    self.session.flush()
                return True
            except IntegrityError:
                return False
        if row.holder_id != holder and (aware(row.expires_at) or now) > now:
            return False
        if row.holder_id != holder:
            row.acquired_at = now
        row.holder_id = holder
        row.heartbeat_at = now
        row.expires_at = now + timedelta(seconds=max(30, int(ttl_seconds)))
        row.metadata_json = dict(metadata or {})
        self.session.flush()
        return True

    def release_lease(self, lease_name: str, holder_id: str) -> bool:
        row = self.session.get(RuntimeLeaseORM, str(lease_name or "").strip())
        if row is None or row.holder_id != str(holder_id or "").strip():
            return False
        row.expires_at = utcnow()
        row.heartbeat_at = utcnow()
        self.session.flush()
        return True

    def active_leases(self, *, now: datetime | None = None) -> list[RuntimeLeaseORM]:
        current = now or utcnow()
        return list(self.session.scalars(
            select(RuntimeLeaseORM)
            .where(RuntimeLeaseORM.expires_at > current)
            .order_by(RuntimeLeaseORM.lease_name)
        ))

    def upsert_heartbeat(
        self, *, service_id: str, node_id: str, role: str, environment: str,
        version: str, commit_sha: str | None = None, status: str = "running",
        scheduler_leader: bool = False, alert_monitor_leader: bool = False,
        metrics: dict | None = None, started_at: datetime | None = None,
    ) -> ServiceHeartbeatORM:
        now = utcnow()
        clean_id = str(service_id or "").strip()[:160]
        row = self.session.get(ServiceHeartbeatORM, clean_id)
        if row is None:
            row = ServiceHeartbeatORM(
                service_id=clean_id,
                node_id=str(node_id or "unknown")[:120],
                role=str(role or "unknown")[:40],
                environment=str(environment or "unknown")[:40],
                version=str(version or "unknown")[:32],
                commit_sha=str(commit_sha or "")[:64] or None,
                started_at=started_at or now,
                last_seen_at=now,
                status=str(status or "running")[:24],
                scheduler_leader=bool(scheduler_leader),
                alert_monitor_leader=bool(alert_monitor_leader),
                metrics_json=dict(metrics or {}),
            )
            self.session.add(row)
        else:
            if started_at is not None and (
                aware(row.started_at) is None or aware(started_at) > aware(row.started_at)
            ):
                row.started_at = started_at
            row.node_id = str(node_id or row.node_id)[:120]
            row.role = str(role or row.role)[:40]
            row.environment = str(environment or row.environment)[:40]
            row.version = str(version or row.version)[:32]
            row.commit_sha = str(commit_sha or "")[:64] or row.commit_sha
            row.last_seen_at = now
            row.status = str(status or "running")[:24]
            row.scheduler_leader = bool(scheduler_leader)
            row.alert_monitor_leader = bool(alert_monitor_leader)
            row.metrics_json = dict(metrics or {})
        self.session.flush()
        return row

    def mark_service_stopped(self, service_id: str) -> None:
        row = self.session.get(ServiceHeartbeatORM, str(service_id or "").strip())
        if row is not None:
            row.status = "stopped"
            row.scheduler_leader = False
            row.alert_monitor_leader = False
            row.last_seen_at = utcnow()
            self.session.flush()

    def recent_services(self, *, role: str | None = None, limit: int = 20) -> list[ServiceHeartbeatORM]:
        statement = select(ServiceHeartbeatORM)
        if role:
            statement = statement.where(ServiceHeartbeatORM.role == role)
        return list(self.session.scalars(
            statement.order_by(ServiceHeartbeatORM.last_seen_at.desc()).limit(max(1, min(limit, 100)))
        ))

    def sync_incidents(
        self,
        alerts: list[dict],
        *,
        now: datetime | None = None,
        managed_codes: set[str] | None = None,
        managed_prefixes: set[str] | None = None,
    ) -> list[OperationalIncidentORM]:
        """Open current incidents and resolve only the caller's monitoring scope.

        Different processes contribute complementary checks.  A worker, for
        example, cannot see the web process' in-memory route percentiles.  It
        must therefore never resolve a route incident merely because that
        category was absent from its own observation cycle.
        """
        current = now or utcnow()
        active_codes: set[str] = set()
        for alert in alerts:
            code = str(alert.get("code") or "").strip()[:160]
            if not code:
                continue
            active_codes.add(code)
            row = self.session.get(OperationalIncidentORM, code)
            if row is None:
                row = OperationalIncidentORM(
                    code=code,
                    severity=str(alert.get("severity") or "warning")[:16],
                    status="open",
                    title=str(alert.get("title") or code)[:200],
                    message=str(alert.get("message") or "Atenção operacional necessária.")[:500],
                    details_json=dict(alert.get("details") or {}),
                    first_seen_at=current,
                    last_seen_at=current,
                )
                self.session.add(row)
            else:
                if row.status != "open":
                    row.first_seen_at = current
                    row.last_notified_at = None
                row.status = "open"
                row.severity = str(alert.get("severity") or row.severity)[:16]
                row.title = str(alert.get("title") or row.title)[:200]
                row.message = str(alert.get("message") or row.message)[:500]
                row.details_json = dict(alert.get("details") or {})
                row.last_seen_at = current
                row.resolved_at = None
        exact_scope = set(managed_codes or ())
        prefix_scope = set(managed_prefixes or ())
        manage_everything = managed_codes is None and managed_prefixes is None
        open_rows = list(self.session.scalars(
            select(OperationalIncidentORM).where(OperationalIncidentORM.status == "open")
        ))
        for row in open_rows:
            caller_manages = (
                manage_everything
                or row.code in exact_scope
                or any(row.code.startswith(prefix) for prefix in prefix_scope)
            )
            if caller_manages and row.code not in active_codes:
                row.status = "resolved"
                row.resolved_at = current
                row.last_seen_at = current
        self.session.flush()
        return list(self.session.scalars(
            select(OperationalIncidentORM)
            .order_by(OperationalIncidentORM.status, OperationalIncidentORM.severity, OperationalIncidentORM.last_seen_at.desc())
            .limit(200)
        ))

    def mark_notified(self, row: OperationalIncidentORM) -> None:
        row.last_notified_at = utcnow()
        self.session.flush()

    def notification_candidates(self, *, cooldown_hours: int = 6) -> list[OperationalIncidentORM]:
        cutoff = utcnow() - timedelta(hours=max(1, int(cooldown_hours)))
        return list(self.session.scalars(
            select(OperationalIncidentORM).where(
                OperationalIncidentORM.status == "open",
                or_(
                    OperationalIncidentORM.last_notified_at.is_(None),
                    OperationalIncidentORM.last_notified_at <= cutoff,
                ),
            ).order_by(
                OperationalIncidentORM.severity.desc(),
                OperationalIncidentORM.first_seen_at,
            )
        ))
