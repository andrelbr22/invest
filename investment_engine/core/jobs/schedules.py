from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..repositories.background_jobs import BackgroundJobRepository
from ..repositories.economic_series import SharedSnapshotRepository


SAO_PAULO = ZoneInfo("America/Sao_Paulo")
MANUAL_COOLDOWN = timedelta(minutes=5)


@dataclass(frozen=True)
class RefreshSchedule:
    key: str
    label: str
    job_type: str
    snapshot_key: str
    source: str
    stale_after: timedelta
    fixed_times: tuple[time, ...] = ()
    interval_minutes: int | None = None
    interval_offset_minutes: int = 0
    weekdays_only: bool = False
    window_start: time | None = None
    window_end: time | None = None
    extra_times: tuple[time, ...] = ()
    catch_up: bool = True
    priority: int = 100


REFRESH_SCHEDULES: dict[str, RefreshSchedule] = {
    "selic_current": RefreshSchedule(
        "selic_current", "Selic atual", "market_group_refresh", "market:selic-current",
        "Banco Central do Brasil • SGS 432", timedelta(hours=3),
        fixed_times=(time(6), time(13)), priority=30,
    ),
    "selic_focus": RefreshSchedule(
        "selic_focus", "Selic projetada (Focus)", "market_group_refresh", "market:selic-focus",
        "Banco Central do Brasil • Relatório Focus", timedelta(hours=12),
        fixed_times=(time(4),), priority=35,
    ),
    "macro": RefreshSchedule(
        "macro", "CDI, inflação, IMA-B e IRF-M", "market_group_refresh", "market:macro",
        "BCB, IBGE, FGV, Fipe, BLS e ANBIMA", timedelta(hours=12),
        fixed_times=(time(4),), priority=40,
    ),
    "global_markets": RefreshSchedule(
        "global_markets", "Mercados globais e commodities", "market_group_refresh", "market:global",
        "Yahoo Finance", timedelta(hours=6), fixed_times=(time(6), time(13)), priority=50,
    ),
    "rates_calendar": RefreshSchedule(
        "rates_calendar", "Treasuries, curva DI e agenda", "market_group_refresh", "market:rates-calendar",
        "U.S. Treasury, FRED, B3, ANBIMA, BCB e BLS", timedelta(hours=6),
        fixed_times=(time(6), time(13)), priority=45,
    ),
    "crypto": RefreshSchedule(
        "crypto", "Criptoativos", "market_group_refresh", "market:crypto",
        "Yahoo Finance", timedelta(minutes=30), interval_minutes=30,
        interval_offset_minutes=5, priority=20,
    ),
    "fx": RefreshSchedule(
        "fx", "Câmbio", "market_group_refresh", "market:fx",
        "Yahoo Finance", timedelta(hours=2), interval_minutes=120,
        interval_offset_minutes=5, priority=25,
    ),
    "headlines": RefreshSchedule(
        "headlines", "Manchetes de economia", "economy_headlines_refresh", "economy-headlines:main",
        "Agência Brasil e ADVFN", timedelta(hours=1), interval_minutes=60, priority=60,
    ),
    "comparison": RefreshSchedule(
        "comparison", "Comparador histórico", "historical_comparison_refresh", "market-comparison:main",
        "BCB e Yahoo Finance", timedelta(hours=24), fixed_times=(time(5),), priority=90,
    ),
    "catalog": RefreshSchedule(
        "catalog", "Catálogo de ativos", "market_catalog_refresh", "market-catalog:main",
        "Fundamentus e TradingView", timedelta(hours=6), fixed_times=(time(8, 30),),
        weekdays_only=True, priority=110,
    ),
    "fundamentals": RefreshSchedule(
        "fundamentals", "Fundamentos e notas", "market_fundamentals_refresh", "market-fundamentals:main",
        "Fundamentus", timedelta(hours=6), fixed_times=(time(19),), weekdays_only=True, priority=120,
    ),
    "technical_daily": RefreshSchedule(
        "technical_daily", "Indicadores técnicos diários", "market_technicals_refresh", "market-technicals:daily",
        "TradingView", timedelta(hours=6), fixed_times=(time(18, 15),),
        weekdays_only=True, priority=115,
    ),
    "technical_intraday": RefreshSchedule(
        "technical_intraday", "Ativos relevantes durante o pregão", "market_intraday_refresh",
        "market-technicals:intraday", "Yahoo Finance", timedelta(hours=6),
        interval_minutes=15, interval_offset_minutes=5, weekdays_only=True,
        window_start=time(10, 5), window_end=time(17, 50), extra_times=(time(18),),
        catch_up=False, priority=70,
    ),
}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _local(now: datetime | None = None) -> datetime:
    current = _aware(now or datetime.now(timezone.utc))
    return current.astimezone(SAO_PAULO)


def _valid_day(spec: RefreshSchedule, local_day) -> bool:
    return not spec.weekdays_only or local_day.weekday() < 5


def slots_for_day(spec: RefreshSchedule, local_day) -> list[datetime]:
    if not _valid_day(spec, local_day):
        return []
    slots = [datetime.combine(local_day, item, SAO_PAULO) for item in spec.fixed_times]
    if spec.interval_minutes:
        if spec.window_start is None:
            cursor = datetime.combine(local_day, time(0), SAO_PAULO) + timedelta(
                minutes=spec.interval_offset_minutes,
            )
            end = datetime.combine(local_day, time(23, 59, 59), SAO_PAULO)
        else:
            cursor = datetime.combine(local_day, spec.window_start, SAO_PAULO)
            end = datetime.combine(local_day, spec.window_end or time(23, 59, 59), SAO_PAULO)
        while cursor <= end:
            slots.append(cursor)
            cursor += timedelta(minutes=spec.interval_minutes)
    slots.extend(datetime.combine(local_day, item, SAO_PAULO) for item in spec.extra_times)
    return sorted(set(item.astimezone(timezone.utc) for item in slots))


def latest_scheduled_slot(spec: RefreshSchedule, now: datetime | None = None) -> datetime | None:
    local_now = _local(now)
    current = local_now.astimezone(timezone.utc)
    for offset in range(0, 8):
        day = local_now.date() - timedelta(days=offset)
        candidates = [item for item in slots_for_day(spec, day) if item <= current]
        if candidates:
            return max(candidates)
    return None


def next_scheduled_slot(spec: RefreshSchedule, now: datetime | None = None) -> datetime | None:
    local_now = _local(now)
    current = local_now.astimezone(timezone.utc)
    for offset in range(0, 8):
        day = local_now.date() + timedelta(days=offset)
        candidates = [item for item in slots_for_day(spec, day) if item > current]
        if candidates:
            return min(candidates)
    return None


def snapshot_is_stale(session: Session, spec: RefreshSchedule, now: datetime | None = None) -> bool:
    current = _aware(now or datetime.now(timezone.utc))
    snapshot = SharedSnapshotRepository(session).get(spec.snapshot_key)
    return snapshot is None or _aware(snapshot.as_of) < current - spec.stale_after


def enqueue_refresh(
    session: Session,
    key: str,
    *,
    trigger: str,
    requested_by: str | None = None,
    now: datetime | None = None,
    force: bool = False,
) -> tuple[object, bool]:
    spec = REFRESH_SCHEDULES[key]
    current = _aware(now or datetime.now(timezone.utc))
    repository = BackgroundJobRepository(session)
    if trigger == "manual":
        recent = repository.latest_for_deduplication(f"refresh:{key}")
        if recent is not None and _aware(recent.created_at) > current - MANUAL_COOLDOWN:
            return recent, False
    elif trigger == "access" and not force and not snapshot_is_stale(session, spec, current):
        recent = repository.latest_for_deduplication(f"refresh:{key}")
        return recent, False

    if trigger == "scheduled":
        slot = latest_scheduled_slot(spec, current) or current
        token = slot.astimezone(SAO_PAULO).strftime("%Y%m%dT%H%M")
    else:
        token = str(int(current.timestamp()) // int(MANUAL_COOLDOWN.total_seconds()))
    payload = {
        "group": key,
        "snapshot_key": spec.snapshot_key,
        "trigger": trigger,
        "scheduled_for": current.isoformat(),
    }
    return repository.enqueue(
        spec.job_type,
        payload,
        requested_by=requested_by,
        priority=spec.priority,
        max_attempts=3,
        deduplication_key=f"refresh:{key}",
        idempotency_key=f"{trigger}:{key}:{token}",
    )


def enqueue_due_refreshes(session: Session, now: datetime | None = None) -> list[str]:
    current = _aware(now or datetime.now(timezone.utc))
    created: list[str] = []
    snapshots = SharedSnapshotRepository(session)
    for key, spec in REFRESH_SCHEDULES.items():
        slot = latest_scheduled_slot(spec, current)
        if slot is None:
            continue
        # Intraday jobs are useful only inside their operating window. A worker
        # restart at night or during the weekend must not replay the last slot.
        if not spec.catch_up and current - slot > timedelta(minutes=2):
            continue
        snapshot = snapshots.get(spec.snapshot_key)
        if snapshot is not None and _aware(snapshot.as_of) >= slot:
            continue
        _row, was_created = enqueue_refresh(session, key, trigger="scheduled", now=current)
        if was_created:
            created.append(key)
    return created


def refresh_status(session: Session, key: str, now: datetime | None = None) -> dict:
    spec = REFRESH_SCHEDULES[key]
    current = _aware(now or datetime.now(timezone.utc))
    snapshot = SharedSnapshotRepository(session).get(spec.snapshot_key)
    job = BackgroundJobRepository(session).latest_for_deduplication(f"refresh:{key}")
    as_of = _aware(snapshot.as_of) if snapshot is not None else None
    stale = as_of is None or as_of < current - spec.stale_after
    status = "unavailable" if snapshot is None else ("stale" if stale else "updated")
    refresh_meta = dict((snapshot.payload_json or {}).get("refresh") or {}) if snapshot is not None else {}
    if status == "updated" and refresh_meta.get("status") == "partial":
        status = "partial"
    if job is not None and job.status in {"queued", "running"}:
        status = job.status
    elif job is not None and job.status == "failed" and (
        as_of is None or _aware(job.finished_at or job.updated_at) > as_of
    ):
        status = "failed"
    elif snapshot is not None and snapshot.last_error_at and (
        as_of is None or _aware(snapshot.last_error_at) > as_of
    ):
        status = "failed"
    return {
        "key": key,
        "label": spec.label,
        "status": status,
        "source": spec.source,
        "last_updated_at": as_of,
        "next_update_at": next_scheduled_slot(spec, current),
        "last_error_at": (
            _aware(snapshot.last_error_at) if snapshot is not None and snapshot.last_error_at
            else _aware(job.finished_at) if job is not None and job.status == "failed"
            else None
        ),
        "last_error_code": (
            snapshot.last_error_code if snapshot is not None and snapshot.last_error_code
            else job.last_error_code if job is not None and job.status == "failed"
            else None
        ),
        "warnings": list(refresh_meta.get("warnings") or []),
        "manual_available_at": (
            _aware(job.created_at) + MANUAL_COOLDOWN
            if job is not None and _aware(job.created_at) > current - MANUAL_COOLDOWN
            else current
        ),
        "job_id": str(job.id) if job is not None and job.status in {"queued", "running"} else None,
    }


def all_refresh_statuses(session: Session, now: datetime | None = None) -> dict[str, dict]:
    return {key: refresh_status(session, key, now) for key in REFRESH_SCHEDULES}
