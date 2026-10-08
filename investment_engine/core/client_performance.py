from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from time import monotonic

from sqlalchemy import select

from ..infrastructure.db.models import ClientPerformanceHourlyORM
from ..infrastructure.db.session import get_session_factory


HISTOGRAM_LIMITS_MS = (100, 250, 500, 1000, 2000, 3000, 5000, 10_000, 30_000, 120_000)


def _hour(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _histogram_key(duration_ms: float) -> str:
    duration = max(0.0, float(duration_ms))
    for limit in HISTOGRAM_LIMITS_MS:
        if duration <= limit:
            return str(limit)
    return "over"


def _percentile_from_histogram(histogram: dict, sample_count: int, percentile: float) -> float | None:
    if sample_count <= 0:
        return None
    target = max(1, int((sample_count * percentile) + .999999))
    seen = 0
    for limit in (*HISTOGRAM_LIMITS_MS, "over"):
        seen += int(histogram.get(str(limit), 0) or 0)
        if seen >= target:
            return 120_000.0 if limit == "over" else float(limit)
    return None


class ClientPerformanceAggregator:
    """Collect real-browser timings in memory and flush compact hourly rows."""

    def __init__(self, flush_interval_seconds: int = 60):
        self.flush_interval_seconds = max(15, int(flush_interval_seconds))
        self._lock = threading.Lock()
        self._values: dict[tuple, dict] = defaultdict(self._empty)
        self._flush_running = False
        self._last_flush = monotonic()

    @staticmethod
    def _empty() -> dict:
        return {
            "sample_count": 0,
            "success_count": 0,
            "total_duration_ms": 0.0,
            "max_duration_ms": 0.0,
            "histogram": {},
            "web_vitals": {},
        }

    def observe(
        self,
        *,
        panel: str,
        duration_ms: float,
        success: bool,
        cache_state: str,
        device_class: str,
        web_vitals: dict | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        key = (_hour(occurred_at), str(panel), str(cache_state), str(device_class))
        with self._lock:
            item = self._values[key]
            duration = max(0.0, float(duration_ms))
            item["sample_count"] += 1
            item["success_count"] += int(bool(success))
            item["total_duration_ms"] += duration
            item["max_duration_ms"] = max(item["max_duration_ms"], duration)
            bucket = _histogram_key(duration)
            item["histogram"][bucket] = int(item["histogram"].get(bucket, 0)) + 1
            for name in ("lcp_ms", "inp_ms", "cls"):
                raw = (web_vitals or {}).get(name)
                if raw is None:
                    continue
                value = max(0.0, float(raw))
                vital = item["web_vitals"].setdefault(name, {"count": 0, "total": 0.0, "max": 0.0})
                vital["count"] += 1
                vital["total"] += value
                vital["max"] = max(vital["max"], value)

    def ready_to_flush(self) -> bool:
        with self._lock:
            return bool(self._values) and not self._flush_running and monotonic() - self._last_flush >= self.flush_interval_seconds

    def begin_flush(self) -> dict:
        with self._lock:
            if self._flush_running or not self._values:
                return {}
            self._flush_running = True
            values = dict(self._values)
            self._values.clear()
            return values

    def finish_flush(self, values: dict, *, succeeded: bool) -> None:
        with self._lock:
            if not succeeded:
                for key, incoming in values.items():
                    current = self._values[key]
                    _merge_aggregate(current, incoming)
            self._flush_running = False
            self._last_flush = monotonic()


def _merge_aggregate(target: dict, incoming: dict) -> None:
    target["sample_count"] += int(incoming.get("sample_count", 0))
    target["success_count"] += int(incoming.get("success_count", 0))
    target["total_duration_ms"] += float(incoming.get("total_duration_ms", 0))
    target["max_duration_ms"] = max(float(target.get("max_duration_ms", 0)), float(incoming.get("max_duration_ms", 0)))
    for key, count in (incoming.get("histogram") or {}).items():
        target["histogram"][str(key)] = int(target["histogram"].get(str(key), 0)) + int(count)
    for name, values in (incoming.get("web_vitals") or {}).items():
        current = target["web_vitals"].setdefault(name, {"count": 0, "total": 0.0, "max": 0.0})
        current["count"] += int(values.get("count", 0))
        current["total"] += float(values.get("total", 0))
        current["max"] = max(float(current.get("max", 0)), float(values.get("max", 0)))


CLIENT_PERFORMANCE = ClientPerformanceAggregator()


def persist_client_performance(values: dict | None = None) -> int:
    batch = values if values is not None else CLIENT_PERFORMANCE.begin_flush()
    if not batch:
        return 0
    succeeded = False
    try:
        with get_session_factory()() as session:
            for (bucket_hour, panel, cache_state, device_class), item in batch.items():
                row = session.scalar(
                    select(ClientPerformanceHourlyORM).where(
                        ClientPerformanceHourlyORM.bucket_hour == bucket_hour,
                        ClientPerformanceHourlyORM.panel == panel,
                        ClientPerformanceHourlyORM.cache_state == cache_state,
                        ClientPerformanceHourlyORM.device_class == device_class,
                    )
                )
                if row is None:
                    row = ClientPerformanceHourlyORM(
                        bucket_hour=bucket_hour,
                        panel=panel,
                        cache_state=cache_state,
                        device_class=device_class,
                    )
                    session.add(row)
                merged = {
                    "sample_count": int(row.sample_count or 0),
                    "success_count": int(row.success_count or 0),
                    "total_duration_ms": float(row.total_duration_ms or 0),
                    "max_duration_ms": float(row.max_duration_ms or 0),
                    "histogram": dict(row.histogram_json or {}),
                    "web_vitals": dict(row.web_vitals_json or {}),
                }
                _merge_aggregate(merged, item)
                row.sample_count = merged["sample_count"]
                row.success_count = merged["success_count"]
                row.total_duration_ms = merged["total_duration_ms"]
                row.max_duration_ms = merged["max_duration_ms"]
                row.histogram_json = merged["histogram"]
                row.web_vitals_json = merged["web_vitals"]
                row.updated_at = datetime.now(timezone.utc)
            session.commit()
        succeeded = True
        return len(batch)
    finally:
        if values is None:
            CLIENT_PERFORMANCE.finish_flush(batch, succeeded=succeeded)


def maybe_flush_client_performance() -> bool:
    if not CLIENT_PERFORMANCE.ready_to_flush():
        return False
    batch = CLIENT_PERFORMANCE.begin_flush()
    if not batch:
        return False

    def run() -> None:
        succeeded = False
        try:
            persist_client_performance(batch)
            succeeded = True
        finally:
            CLIENT_PERFORMANCE.finish_flush(batch, succeeded=succeeded)

    threading.Thread(target=run, name="client-performance-flush", daemon=True).start()
    return True


def recent_client_performance(session, *, hours: int = 24) -> list[dict]:
    cutoff = _hour() - timedelta(hours=max(1, min(int(hours), 168)) - 1)
    rows = list(session.scalars(
        select(ClientPerformanceHourlyORM)
        .where(ClientPerformanceHourlyORM.bucket_hour >= cutoff)
        .order_by(ClientPerformanceHourlyORM.bucket_hour.desc(), ClientPerformanceHourlyORM.panel)
    ))
    result = []
    for row in rows:
        count = int(row.sample_count or 0)
        histogram = dict(row.histogram_json or {})
        vitals = {}
        for name, values in (row.web_vitals_json or {}).items():
            samples = int(values.get("count", 0))
            vitals[name] = {
                "count": samples,
                "average": None if not samples else round(float(values.get("total", 0)) / samples, 2),
                "max": round(float(values.get("max", 0)), 2),
            }
        result.append({
            "bucket_hour": row.bucket_hour,
            "panel": row.panel,
            "cache_state": row.cache_state,
            "device_class": row.device_class,
            "sample_count": count,
            "success_count": int(row.success_count or 0),
            "success_pct": None if not count else round(int(row.success_count or 0) * 100 / count, 2),
            "average_ms": None if not count else round(float(row.total_duration_ms or 0) / count, 2),
            "p50_ms": _percentile_from_histogram(histogram, count, .50),
            "p95_ms": _percentile_from_histogram(histogram, count, .95),
            "max_ms": round(float(row.max_duration_ms or 0), 2),
            "web_vitals": vitals,
        })
    return result
