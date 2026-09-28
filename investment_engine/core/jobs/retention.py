from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import math
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ...infrastructure.db.models import (
    BackgroundJobORM,
    BacktestRequestUsageORM,
    OperationalArchiveORM,
    OperationalIncidentORM,
    ServiceHeartbeatORM,
)
from ..repositories.background_jobs import BackgroundJobRepository


SAFE_AUTOMATIC_JOB_TYPES = frozenset({
    "market_dashboard_refresh",
    "economy_headlines_refresh",
    "market_group_refresh",
    "historical_comparison_refresh",
    "market_catalog_refresh",
    "market_fundamentals_refresh",
    "market_technicals_refresh",
    "market_intraday_refresh",
    "investor_dividends_refresh",
    "cvm_relevant_facts_refresh",
    "official_calendar_refresh",
    "anbima_ima_history_refresh",
    "alb_universe_monitor",
    "data_quality_refresh",
    "operational_retention",
})


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _checksum(payload: dict) -> str:
    encoded = json.dumps(
        _json_safe(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _column_payload(row) -> dict:
    return {
        column.name: _json_safe(getattr(row, column.name))
        for column in row.__table__.columns
    }


class OperationalRetentionService:
    """Archive only old, reproducible system data before removing hot rows.

    User requests, backtests, failures, queued/running jobs and the newest row
    for every refresh key are intentionally never eligible.
    """

    def __init__(self, session: Session):
        self.session = session

    def _archive_and_delete(
        self,
        row,
        *,
        entity_type: str,
        source_id: str,
        source_created_at: datetime | None,
        source_updated_at: datetime | None,
    ) -> None:
        payload = _column_payload(row)
        checksum = _checksum(payload)
        existing = self.session.scalar(select(OperationalArchiveORM).where(
            OperationalArchiveORM.entity_type == entity_type,
            OperationalArchiveORM.source_id == source_id,
        ))
        if existing is None:
            self.session.add(OperationalArchiveORM(
                entity_type=entity_type,
                source_id=source_id,
                source_created_at=source_created_at,
                source_updated_at=source_updated_at,
                archived_at=datetime.now(timezone.utc),
                schema_version="1",
                checksum=checksum,
                record_json=payload,
            ))
            self.session.flush()
        elif existing.checksum != checksum:
            raise ValueError("operational_archive_checksum_mismatch")
        self.session.delete(row)
        self.session.flush()

    def _eligible_jobs(self, cutoff: datetime, limit: int) -> list[BackgroundJobORM]:
        # Scan with a keyset cursor until ``limit`` genuinely safe rows are
        # found.  A fixed pre-filter limit would let an old prefix of manual or
        # access-triggered jobs permanently hide eligible scheduled rows.
        eligible: list[BackgroundJobORM] = []
        cursor_finished_at: datetime | None = None
        cursor_id: UUID | None = None
        page_size = max(50, min(1000, limit * 5))

        while len(eligible) < limit:
            statement = select(BackgroundJobORM).where(
                BackgroundJobORM.status == "succeeded",
                BackgroundJobORM.finished_at.is_not(None),
                BackgroundJobORM.finished_at < cutoff,
                BackgroundJobORM.requested_by.is_(None),
                BackgroundJobORM.deduplication_key.like("refresh:%"),
                BackgroundJobORM.job_type.in_(sorted(SAFE_AUTOMATIC_JOB_TYPES)),
            )
            if cursor_finished_at is not None and cursor_id is not None:
                statement = statement.where(or_(
                    BackgroundJobORM.finished_at > cursor_finished_at,
                    and_(
                        BackgroundJobORM.finished_at == cursor_finished_at,
                        BackgroundJobORM.id > cursor_id,
                    ),
                ))
            candidates = list(self.session.scalars(
                statement
                .order_by(BackgroundJobORM.finished_at, BackgroundJobORM.id)
                .limit(page_size)
                .with_for_update(skip_locked=True)
            ))
            if not candidates:
                break

            last = candidates[-1]
            cursor_finished_at = last.finished_at
            cursor_id = last.id
            latest = BackgroundJobRepository(self.session).latest_for_deduplications(
                row.deduplication_key for row in candidates if row.deduplication_key
            )
            referenced = set(self.session.scalars(
                select(BacktestRequestUsageORM.background_job_id).where(
                    BacktestRequestUsageORM.background_job_id.in_([row.id for row in candidates])
                )
            ))
            for row in candidates:
                trigger = str((row.payload_json or {}).get("trigger") or "").strip().lower()
                newest = latest.get(row.deduplication_key)
                if trigger != "scheduled" or row.id in referenced or newest is None or newest.id == row.id:
                    continue
                eligible.append(row)
                if len(eligible) >= limit:
                    break
        return eligible

    def run(
        self,
        *,
        apply: bool = False,
        job_retention_days: int = 45,
        operational_retention_days: int = 180,
        limit: int = 200,
        now: datetime | None = None,
    ) -> dict:
        current = _aware(now or datetime.now(timezone.utc))
        batch_limit = max(1, min(1000, int(limit)))
        job_cutoff = current - timedelta(days=max(30, int(job_retention_days)))
        operational_cutoff = current - timedelta(days=max(90, int(operational_retention_days)))

        jobs = self._eligible_jobs(job_cutoff, batch_limit)
        remaining = max(0, batch_limit - len(jobs))
        incidents = list(self.session.scalars(
            select(OperationalIncidentORM)
            .where(
                OperationalIncidentORM.status == "resolved",
                OperationalIncidentORM.resolved_at.is_not(None),
                OperationalIncidentORM.resolved_at < operational_cutoff,
            )
            .order_by(OperationalIncidentORM.resolved_at, OperationalIncidentORM.code)
            .limit(remaining)
            .with_for_update(skip_locked=True)
        )) if remaining else []
        remaining = max(0, remaining - len(incidents))
        services = list(self.session.scalars(
            select(ServiceHeartbeatORM)
            .where(
                ServiceHeartbeatORM.status == "stopped",
                ServiceHeartbeatORM.last_seen_at < operational_cutoff,
            )
            .order_by(ServiceHeartbeatORM.last_seen_at, ServiceHeartbeatORM.service_id)
            .limit(remaining)
            .with_for_update(skip_locked=True)
        )) if remaining else []

        result = {
            "mode": "apply" if apply else "dry_run",
            "job_retention_days": max(30, int(job_retention_days)),
            "operational_retention_days": max(90, int(operational_retention_days)),
            "batch_limit": batch_limit,
            "eligible": {
                "background_jobs": len(jobs),
                "resolved_incidents": len(incidents),
                "stopped_services": len(services),
            },
            "archived": 0,
            "deleted": 0,
            "safety": {
                "user_jobs_preserved": True,
                "backtests_preserved": True,
                "failed_jobs_preserved": True,
                "active_jobs_preserved": True,
                "latest_refresh_per_key_preserved": True,
                "archive_checksum_required": True,
            },
        }
        if not apply:
            return result

        for row in jobs:
            self._archive_and_delete(
                row,
                entity_type="background_job",
                source_id=str(row.id),
                source_created_at=row.created_at,
                source_updated_at=row.updated_at,
            )
        for row in incidents:
            self._archive_and_delete(
                row,
                entity_type="operational_incident",
                # Incident codes can be reopened after an old resolved cycle
                # has been retired.  Include the cycle boundary so both
                # immutable records can coexist in the archive.
                source_id=f"{row.code}@{_aware(row.resolved_at).isoformat()}",
                source_created_at=row.first_seen_at,
                source_updated_at=row.last_seen_at,
            )
        for row in services:
            self._archive_and_delete(
                row,
                entity_type="service_heartbeat",
                # A service_id is stable across deployments; last_seen_at
                # distinguishes consecutive stopped lifecycles.
                source_id=f"{row.service_id}@{_aware(row.last_seen_at).isoformat()}",
                source_created_at=row.started_at,
                source_updated_at=row.last_seen_at,
            )
        total = len(jobs) + len(incidents) + len(services)
        result["archived"] = total
        result["deleted"] = total
        return result

    def verify_archive(self, *, limit: int = 5000) -> dict:
        """Recompute archive checksums without changing any stored row."""
        rows = list(self.session.scalars(
            select(OperationalArchiveORM)
            .order_by(OperationalArchiveORM.archived_at, OperationalArchiveORM.id)
            .limit(max(1, min(100000, int(limit))))
        ))
        mismatches = []
        for row in rows:
            actual = _checksum(dict(row.record_json or {}))
            if actual != row.checksum:
                mismatches.append({
                    "entity_type": row.entity_type,
                    "source_id": row.source_id,
                    "expected": row.checksum,
                    "actual": actual,
                })
        return {
            "checked": len(rows),
            "valid": not mismatches,
            "mismatch_count": len(mismatches),
            "mismatches": mismatches[:100],
        }
