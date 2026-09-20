from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...infrastructure.db.models import (
    EconomicSeriesORM,
    EconomicSeriesPointORM,
    InterestCurveSnapshotORM,
    SharedSnapshotORM,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class EconomicSeriesRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_series(self, code: str) -> EconomicSeriesORM | None:
        return self.session.scalar(
            select(EconomicSeriesORM).where(EconomicSeriesORM.code == str(code).strip().upper())
        )

    def upsert_series(
        self,
        *,
        code: str,
        name: str,
        unit: str,
        frequency: str,
        source: str,
        source_url: str | None = None,
        timezone_name: str = "America/Sao_Paulo",
        accumulation_method: str = "level",
        metadata: dict | None = None,
    ) -> EconomicSeriesORM:
        clean_code = str(code or "").strip().upper()
        if not clean_code:
            raise ValueError("economic_series_code_required")
        row = self.get_series(clean_code)
        if row is None:
            row = EconomicSeriesORM(code=clean_code, name=str(name).strip(), unit=str(unit).strip(),
                                    frequency=str(frequency).strip(), source=str(source).strip())
            self.session.add(row)
        row.name = str(name).strip()
        row.unit = str(unit).strip()
        row.frequency = str(frequency).strip().lower()
        row.source = str(source).strip()
        row.source_url = str(source_url or "").strip() or None
        row.timezone = str(timezone_name or "America/Sao_Paulo").strip()
        row.accumulation_method = str(accumulation_method or "level").strip().lower()
        row.metadata_json = dict(metadata or {})
        row.is_active = True
        row.updated_at = utcnow()
        self.session.flush()
        return row

    def add_point(
        self,
        series: EconomicSeriesORM,
        *,
        observed_at: datetime,
        value: Decimal | int | float | str,
        reference_period: str = "",
        published_at: datetime | None = None,
        source_payload_hash: str | None = None,
        quality_status: str = "valid",
        metadata: dict | None = None,
    ) -> tuple[EconomicSeriesPointORM, bool]:
        clean_reference = str(reference_period or "").strip()
        row = self.session.scalar(select(EconomicSeriesPointORM).where(
            EconomicSeriesPointORM.series_id == series.id,
            EconomicSeriesPointORM.observed_at == observed_at,
            EconomicSeriesPointORM.reference_period == clean_reference,
        ))
        created = row is None
        if row is None:
            row = EconomicSeriesPointORM(
                series_id=series.id,
                observed_at=observed_at,
                reference_period=clean_reference,
                value=Decimal(str(value)),
            )
            self.session.add(row)
        row.value = Decimal(str(value))
        row.published_at = published_at
        row.source_payload_hash = str(source_payload_hash or "").strip() or None
        row.quality_status = str(quality_status or "valid").strip().lower()
        row.metadata_json = dict(metadata or {})
        self.session.flush()
        return row, created

    def latest_points(self, code: str, limit: int = 100) -> list[EconomicSeriesPointORM]:
        series = self.get_series(code)
        if series is None:
            return []
        return list(self.session.scalars(
            select(EconomicSeriesPointORM)
            .where(EconomicSeriesPointORM.series_id == series.id)
            .order_by(EconomicSeriesPointORM.observed_at.desc())
            .limit(max(1, min(5000, int(limit))))
        ))


class SharedSnapshotRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, snapshot_key: str) -> SharedSnapshotORM | None:
        return self.session.scalar(select(SharedSnapshotORM).where(
            SharedSnapshotORM.snapshot_key == str(snapshot_key).strip().lower(),
        ))

    def save_valid(
        self,
        *,
        snapshot_key: str,
        snapshot_kind: str,
        payload: dict,
        source: str | None = None,
        source_url: str | None = None,
        as_of: datetime | None = None,
        published_at: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> SharedSnapshotORM:
        clean_key = str(snapshot_key or "").strip().lower()
        if not clean_key:
            raise ValueError("snapshot_key_required")
        row = self.get(clean_key)
        if row is None:
            row = SharedSnapshotORM(snapshot_key=clean_key, snapshot_kind=str(snapshot_kind).strip().lower())
            self.session.add(row)
        row.snapshot_kind = str(snapshot_kind).strip().lower()
        row.status = "valid"
        row.payload_json = dict(payload)
        row.source = str(source or "").strip() or None
        row.source_url = str(source_url or "").strip() or None
        row.as_of = as_of or utcnow()
        row.published_at = published_at
        row.valid_until = valid_until
        row.payload_hash = payload_hash(payload)
        row.last_error_code = None
        row.last_error_at = None
        row.updated_at = utcnow()
        self.session.flush()
        return row

    def mark_refresh_failed(self, snapshot_key: str, error_code: str) -> SharedSnapshotORM | None:
        row = self.get(snapshot_key)
        if row is None:
            return None
        # Preserve the valid payload. Only record that the latest refresh failed.
        row.last_error_code = str(error_code or "refresh_failed").strip()[:120]
        row.last_error_at = utcnow()
        row.updated_at = utcnow()
        self.session.flush()
        return row


class InterestCurveHistoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, curve: dict) -> InterestCurveSnapshotORM | None:
        points = list(curve.get("points") or [])
        if not points:
            return None
        raw_date = str(curve.get("as_of") or "").strip()[:10]
        try:
            reference_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            reference_date = utcnow().date()
        curve_type = str(curve.get("curve_type") or "unknown")[:40]
        row = self.session.scalar(select(InterestCurveSnapshotORM).where(
            InterestCurveSnapshotORM.reference_date == reference_date,
            InterestCurveSnapshotORM.curve_type == curve_type,
        ))
        if row is None:
            row = InterestCurveSnapshotORM(
                reference_date=reference_date, curve_type=curve_type,
                title=str(curve.get("title") or "Curva de juros")[:160],
            )
            self.session.add(row)
        row.title = str(curve.get("title") or row.title)[:160]
        row.source = str(curve.get("source") or "")[:160] or None
        row.source_url = str(curve.get("url") or "")[:500] or None
        row.points_json = points
        row.retrieved_at = utcnow()
        self.session.flush()
        return row

    def list_recent(self, limit: int = 12):
        return list(self.session.scalars(select(InterestCurveSnapshotORM).order_by(
            InterestCurveSnapshotORM.reference_date.desc(),
        ).limit(max(1, min(60, int(limit))))))
