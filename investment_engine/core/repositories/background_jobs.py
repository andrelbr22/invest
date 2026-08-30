from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...infrastructure.db.models import BackgroundJobORM


ACTIVE_JOB_STATUSES = ("queued", "running")
TERMINAL_JOB_STATUSES = ("succeeded", "failed", "cancelled")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_message(value: object, limit: int = 500) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ")[:limit]


def background_job_dict(row: BackgroundJobORM, *, include_payload: bool = False) -> dict:
    payload = {
        "id": str(row.id),
        "job_type": row.job_type,
        "status": row.status,
        "priority": row.priority,
        "requested_by": row.requested_by,
        "attempts": row.attempts,
        "max_attempts": row.max_attempts,
        "run_after": row.run_after,
        "progress_current": row.progress_current,
        "progress_total": row.progress_total,
        "message": row.message,
        "last_error_code": row.last_error_code,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "updated_at": row.updated_at,
    }
    if include_payload:
        payload["payload"] = dict(row.payload_json or {})
        payload["result"] = dict(row.result_json or {})
        payload["last_error_message"] = row.last_error_message
    return payload


class BackgroundJobRepository:
    """Small PostgreSQL-backed queue with idempotency and worker leases."""

    def __init__(self, session: Session):
        self.session = session

    def get(self, job_id: UUID | str) -> BackgroundJobORM | None:
        return self.session.get(BackgroundJobORM, UUID(str(job_id)))

    def enqueue(
        self,
        job_type: str,
        payload: dict | None = None,
        *,
        requested_by: str | None = None,
        priority: int = 100,
        max_attempts: int = 3,
        run_after: datetime | None = None,
        deduplication_key: str | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[BackgroundJobORM, bool]:
        clean_type = str(job_type or "").strip().lower()
        if not clean_type or len(clean_type) > 64:
            raise ValueError("invalid_background_job_type")
        clean_idempotency = str(idempotency_key or "").strip() or None
        if clean_idempotency:
            existing = self.session.scalar(
                select(BackgroundJobORM).where(BackgroundJobORM.idempotency_key == clean_idempotency)
            )
            if existing is not None:
                return existing, False
        clean_deduplication = str(deduplication_key or "").strip() or None
        if clean_deduplication:
            existing = self.session.scalar(
                select(BackgroundJobORM)
                .where(
                    BackgroundJobORM.deduplication_key == clean_deduplication,
                    BackgroundJobORM.status.in_(ACTIVE_JOB_STATUSES),
                )
                .order_by(BackgroundJobORM.created_at.desc())
                .limit(1)
            )
            if existing is not None:
                return existing, False
        row = BackgroundJobORM(
            job_type=clean_type,
            payload_json=dict(payload or {}),
            requested_by=str(requested_by or "").strip().lower() or None,
            priority=max(0, min(1000, int(priority))),
            max_attempts=max(1, min(10, int(max_attempts))),
            run_after=run_after or utcnow(),
            deduplication_key=clean_deduplication,
            idempotency_key=clean_idempotency,
        )
        self.session.add(row)
        self.session.flush()
        return row, True

    def lease_next(
        self,
        worker_id: str,
        *,
        allowed_types: set[str] | None = None,
    ) -> BackgroundJobORM | None:
        now = utcnow()
        statement = select(BackgroundJobORM).where(
            BackgroundJobORM.status == "queued",
            BackgroundJobORM.run_after <= now,
        )
        if allowed_types:
            statement = statement.where(BackgroundJobORM.job_type.in_(sorted(allowed_types)))
        statement = (
            statement
            .order_by(
                BackgroundJobORM.priority.asc(),
                BackgroundJobORM.run_after.asc(),
                BackgroundJobORM.created_at.asc(),
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        row = self.session.scalar(statement)
        if row is None:
            return None
        row.status = "running"
        row.locked_by = _safe_message(worker_id, 160)
        row.locked_at = now
        row.heartbeat_at = now
        row.started_at = row.started_at or now
        row.finished_at = None
        row.attempts += 1
        row.message = "Trabalho em execução."
        row.updated_at = now
        self.session.flush()
        return row

    def heartbeat(
        self,
        row: BackgroundJobORM,
        worker_id: str,
        *,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        if row.status != "running" or row.locked_by != _safe_message(worker_id, 160):
            raise ValueError("background_job_lease_lost")
        row.heartbeat_at = utcnow()
        if current is not None:
            row.progress_current = max(0, int(current))
        if total is not None:
            row.progress_total = max(0, int(total))
        if message is not None:
            row.message = _safe_message(message)
        self.session.flush()

    def complete(self, row: BackgroundJobORM, result: dict | None = None) -> None:
        now = utcnow()
        row.status = "succeeded"
        row.result_json = dict(result or {})
        row.progress_current = max(row.progress_current, row.progress_total)
        row.message = "Trabalho concluído."
        row.finished_at = now
        row.heartbeat_at = now
        row.locked_by = None
        row.locked_at = None
        row.last_error_code = None
        row.last_error_message = None
        row.updated_at = now
        self.session.flush()

    def fail(
        self,
        row: BackgroundJobORM,
        *,
        error_code: str,
        error_message: str = "",
        retry_delay_seconds: int | None = None,
    ) -> bool:
        now = utcnow()
        row.last_error_code = _safe_message(error_code, 120) or "background_job_failed"
        row.last_error_message = _safe_message(error_message)
        retrying = row.attempts < row.max_attempts
        if retrying:
            delay = retry_delay_seconds
            if delay is None:
                delay = min(300, 2 ** max(0, row.attempts - 1) * 5)
            row.status = "queued"
            row.run_after = now + timedelta(seconds=max(1, int(delay)))
            row.message = "Nova tentativa agendada."
            row.finished_at = None
        else:
            row.status = "failed"
            row.message = "Trabalho não concluído."
            row.finished_at = now
        row.locked_by = None
        row.locked_at = None
        row.heartbeat_at = now
        row.updated_at = now
        self.session.flush()
        return retrying

    def retry(self, row: BackgroundJobORM, *, requested_by: str | None = None) -> None:
        if row.status not in TERMINAL_JOB_STATUSES:
            raise ValueError("background_job_not_terminal")
        row.status = "queued"
        row.attempts = 0
        row.requested_by = str(requested_by or row.requested_by or "").strip().lower() or None
        row.run_after = utcnow()
        row.locked_by = None
        row.locked_at = None
        row.heartbeat_at = None
        row.finished_at = None
        row.message = "Nova tentativa solicitada."
        row.last_error_code = None
        row.last_error_message = None
        row.updated_at = utcnow()
        self.session.flush()

    def recover_stale(self, lease_timeout_seconds: int = 300) -> int:
        threshold = utcnow() - timedelta(seconds=max(30, int(lease_timeout_seconds)))
        rows = list(self.session.scalars(
            select(BackgroundJobORM).where(
                BackgroundJobORM.status == "running",
                BackgroundJobORM.heartbeat_at < threshold,
            )
        ))
        for row in rows:
            self.fail(
                row,
                error_code="worker_heartbeat_expired",
                error_message="O worker deixou de renovar a execução.",
                retry_delay_seconds=5,
            )
        return len(rows)

    def list_recent(self, limit: int = 50) -> list[BackgroundJobORM]:
        return list(self.session.scalars(
            select(BackgroundJobORM)
            .order_by(BackgroundJobORM.created_at.desc())
            .limit(max(1, min(200, int(limit))))
        ))

    def latest_for_deduplication(self, key: str) -> BackgroundJobORM | None:
        return self.session.scalar(
            select(BackgroundJobORM)
            .where(BackgroundJobORM.deduplication_key == str(key or "").strip())
            .order_by(BackgroundJobORM.created_at.desc())
            .limit(1)
        )
