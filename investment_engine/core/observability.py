from __future__ import annotations

import math
import os
import re
import shutil
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from .. import __version__
from ..integrations.email_delivery import AlertEmailSender
from ..infrastructure.config import settings
from ..infrastructure.db.models import BackgroundJobORM
from .jobs.schedules import all_refresh_statuses
from .repositories.operations import (
    OperationsRepository,
    aware,
    operational_incident_dict,
    runtime_lease_dict,
    service_heartbeat_dict,
)


ROUTE_TARGETS_MS = {
    "health": 300.0,
    "dashboard": 1500.0,
    "screener_50": 2000.0,
    "screener_100": 3000.0,
    "asset_detail": 2000.0,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(float(ordered[index]), 2)


class RouteLatencyRegistry:
    """Bounded process-local rolling measurements; no write on every request."""

    def __init__(self, max_samples: int = 500):
        self.max_samples = max(20, int(max_samples))
        self.started_at = utcnow()
        self._values: dict[str, deque[tuple[float, int]]] = defaultdict(
            lambda: deque(maxlen=self.max_samples)
        )
        self._lock = threading.Lock()

    def observe(self, category: str | None, duration_ms: float, status_code: int) -> None:
        if not category:
            return
        with self._lock:
            self._values[str(category)].append((max(0.0, float(duration_ms)), int(status_code)))

    def snapshot(self) -> dict:
        with self._lock:
            copied = {key: list(values) for key, values in self._values.items()}
        categories = []
        for key in sorted(set(ROUTE_TARGETS_MS) | set(copied)):
            rows = copied.get(key, [])
            durations = [value for value, _status in rows]
            target = ROUTE_TARGETS_MS.get(key)
            p95 = _percentile(durations, .95)
            categories.append({
                "key": key,
                "count": len(rows),
                "p50_ms": _percentile(durations, .50),
                "p95_ms": p95,
                "max_ms": round(max(durations), 2) if durations else None,
                "errors": sum(1 for _duration, status in rows if status >= 500),
                "target_p95_ms": target,
                "sample_sufficient": len(rows) >= 20,
                "within_target": None if len(rows) < 20 or target is None or p95 is None else p95 <= target,
            })
        return {"since": self.started_at, "window_size": self.max_samples, "categories": categories}


ROUTE_LATENCIES = RouteLatencyRegistry()


def request_metric_category(path: str, method: str, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    clean_method = str(method or "GET").upper()
    clean_path = str(path or "")
    if clean_method == "GET" and clean_path in {"/health", "/ready", "/health/db", "/health/worker"}:
        return "health"
    if clean_method == "GET" and clean_path == "/market-dashboard":
        return "dashboard"
    if clean_method == "GET" and re.fullmatch(r"/assets/[^/]+", clean_path):
        return "asset_detail"
    return None


def screener_metric_category(limit: int) -> str:
    return "screener_50" if int(limit) <= 50 else "screener_100" if int(limit) <= 100 else "screener_large"


def _read_meminfo(path: Path = Path("/proc/meminfo")) -> dict:
    if not path.is_file():
        return {}
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        key, separator, raw = line.partition(":")
        if not separator:
            continue
        parts = raw.strip().split()
        if parts and parts[0].isdigit():
            values[key] = int(parts[0]) * 1024
    return values


def _read_number(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        return None if raw == "max" else int(raw)
    except (OSError, ValueError):
        return None


def _usage(total: int | None, available: int | None = None, used: int | None = None) -> dict:
    if not total or total <= 0:
        return {"total_bytes": total, "used_bytes": used, "used_pct": None}
    actual_used = used if used is not None else max(0, total - int(available or 0))
    return {
        "total_bytes": int(total),
        "used_bytes": int(actual_used),
        "used_pct": round(actual_used / total * 100, 2),
    }


def collect_resource_metrics() -> dict:
    mem = _read_meminfo()
    memory = _usage(mem.get("MemTotal"), mem.get("MemAvailable"))
    swap = _usage(mem.get("SwapTotal"), mem.get("SwapFree"))
    cgroup_used = _read_number(Path("/sys/fs/cgroup/memory.current"))
    cgroup_limit = _read_number(Path("/sys/fs/cgroup/memory.max"))
    if cgroup_used is None:
        cgroup_used = _read_number(Path("/sys/fs/cgroup/memory/memory.usage_in_bytes"))
        cgroup_limit = _read_number(Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"))
    cgroup = _usage(cgroup_limit, used=cgroup_used)
    disk = shutil.disk_usage("/")
    try:
        load = [round(float(value), 2) for value in os.getloadavg()]
    except (AttributeError, OSError):
        load = []
    return {
        "memory": memory,
        "swap": swap,
        "container_memory": cgroup,
        "disk": {
            "total_bytes": int(disk.total),
            "used_bytes": int(disk.used),
            "used_pct": round(disk.used / disk.total * 100, 2) if disk.total else None,
        },
        "load_average": load,
        "collected_at": utcnow().isoformat(),
    }


def _threshold_alert(
    alerts: list[dict], *, code: str, title: str, value: float | None,
    warning: float, critical: float, location: str,
) -> None:
    if value is None or value < warning:
        return
    severity = "critical" if value >= critical else "warning"
    alerts.append({
        "code": f"{code}:{location}",
        "severity": severity,
        "title": title,
        "message": f"{title}: {value:.1f}% em {location}.",
        "details": {"used_pct": round(value, 2), "location": location},
    })


class OperationalHealthService:
    def __init__(self, session):
        self.session = session
        self.repository = OperationsRepository(session)

    def worker_health(self, *, now: datetime | None = None) -> dict:
        current = now or utcnow()
        target_environment = "staging" if settings.app_environment == "staging" else "production"
        rows = [
            row for row in self.repository.recent_services(role="worker", limit=20)
            if row.environment.startswith(target_environment) and row.status == "running"
        ]
        fresh = [
            row for row in rows
            if aware(row.last_seen_at) and (current - aware(row.last_seen_at)).total_seconds() <= settings.operational_worker_stale_seconds
        ]
        newest = rows[0] if rows else None
        return {
            "status": "ok" if fresh else "unavailable",
            "workers_fresh": len(fresh),
            "last_seen_at": newest.last_seen_at if newest else None,
            "version": newest.version if newest else None,
        }

    def overview(
        self, *, local_resources: dict | None = None, include_route_metrics: bool = True,
        sync_incidents: bool = True, now: datetime | None = None, local_label: str = "aplicação principal",
    ) -> dict:
        current = now or utcnow()
        alerts: list[dict] = []
        managed_codes = {
            "worker_missing",
            "multiple_workers",
            "scheduler_leader_count",
            "alert_monitor_leader_count",
            "queue_stalled",
            "running_heartbeat_stale",
        }
        managed_prefixes = {"repeated_job_failure:", "snapshot_"}
        worker_health = self.worker_health(now=current)
        services = self.repository.recent_services(limit=30)
        serialized_services = [service_heartbeat_dict(row, now=current) for row in services]
        target_environment = "staging" if settings.app_environment == "staging" else "production"
        fresh_workers = [
            row for row in services
            if row.role == "worker" and row.environment.startswith(target_environment) and row.status == "running"
            and aware(row.last_seen_at)
            and (current - aware(row.last_seen_at)).total_seconds() <= settings.operational_worker_stale_seconds
        ]
        if not fresh_workers:
            alerts.append({
                "code": "worker_missing", "severity": "critical",
                "title": "Worker de produção sem heartbeat",
                "message": "Nenhum worker de produção enviou sinal dentro da janela esperada.",
                "details": {"stale_seconds": settings.operational_worker_stale_seconds},
            })
        elif len(fresh_workers) > 1:
            alerts.append({
                "code": "multiple_workers", "severity": "warning",
                "title": "Mais de um worker de produção ativo",
                "message": "Há mais de um consumidor ativo; confirme se a migração ou o failback está em andamento.",
                "details": {"count": len(fresh_workers)},
            })
        scheduler_leaders = [row for row in fresh_workers if row.scheduler_leader]
        alert_leaders = [row for row in fresh_workers if row.alert_monitor_leader]
        if len(scheduler_leaders) != 1:
            alerts.append({
                "code": "scheduler_leader_count", "severity": "critical" if not scheduler_leaders else "warning",
                "title": "Liderança do agendador inconsistente",
                "message": f"Foram identificados {len(scheduler_leaders)} líderes do agendador; o esperado é exatamente um.",
                "details": {"count": len(scheduler_leaders)},
            })
        if len(alert_leaders) != 1:
            alerts.append({
                "code": "alert_monitor_leader_count", "severity": "critical" if not alert_leaders else "warning",
                "title": "Liderança do monitor de alertas inconsistente",
                "message": f"Foram identificados {len(alert_leaders)} líderes do monitor; o esperado é exatamente um.",
                "details": {"count": len(alert_leaders)},
            })

        queued = int(self.session.scalar(select(func.count()).select_from(BackgroundJobORM).where(
            BackgroundJobORM.status == "queued",
        )) or 0)
        running = int(self.session.scalar(select(func.count()).select_from(BackgroundJobORM).where(
            BackgroundJobORM.status == "running",
        )) or 0)
        oldest_due = self.session.scalar(
            select(func.min(BackgroundJobORM.run_after)).where(
                BackgroundJobORM.status == "queued", BackgroundJobORM.run_after <= current,
            )
        )
        oldest_due = aware(oldest_due)
        queue_age_minutes = round((current - oldest_due).total_seconds() / 60, 1) if oldest_due else 0.0
        if queue_age_minutes >= settings.operational_queue_warning_minutes:
            critical = queue_age_minutes >= settings.operational_queue_critical_minutes
            alerts.append({
                "code": "queue_stalled", "severity": "critical" if critical else "warning",
                "title": "Fila de trabalhos parada",
                "message": f"O trabalho pronto mais antigo aguarda há {queue_age_minutes:.0f} minutos.",
                "details": {"oldest_due_minutes": queue_age_minutes, "queued": queued},
            })
        stale_cutoff = current - timedelta(seconds=settings.background_job_lease_timeout_seconds)
        stale_running = int(self.session.scalar(select(func.count()).select_from(BackgroundJobORM).where(
            BackgroundJobORM.status == "running",
            BackgroundJobORM.heartbeat_at < stale_cutoff,
        )) or 0)
        if stale_running:
            alerts.append({
                "code": "running_heartbeat_stale", "severity": "critical",
                "title": "Trabalho em execução sem heartbeat",
                "message": f"{stale_running} trabalho(s) perderam a renovação de execução.",
                "details": {"count": stale_running},
            })

        failure_cutoff = current - timedelta(hours=settings.operational_failure_window_hours)
        recent_terminal = list(self.session.scalars(
            select(BackgroundJobORM).where(
                BackgroundJobORM.finished_at >= failure_cutoff,
                BackgroundJobORM.status.in_(("failed", "succeeded")),
            ).order_by(BackgroundJobORM.job_type, BackgroundJobORM.finished_at.desc()).limit(1500)
        ))
        consecutive: dict[str, int] = defaultdict(int)
        stopped: set[str] = set()
        for row in recent_terminal:
            if row.job_type in stopped:
                continue
            if row.status == "succeeded":
                stopped.add(row.job_type)
            else:
                consecutive[row.job_type] += 1
        repeated_failures = [
            {"job_type": job_type, "count": count}
            for job_type, count in sorted(consecutive.items())
            if count >= settings.operational_failure_count
        ]
        for item in repeated_failures:
            alerts.append({
                "code": f"repeated_job_failure:{item['job_type']}", "severity": "warning",
                "title": "Falhas repetidas em atualização",
                "message": f"{item['job_type']} falhou {item['count']} vezes consecutivas na janela monitorada.",
                "details": item,
            })

        update_statuses = all_refresh_statuses(self.session, current)
        for key, status in update_statuses.items():
            if status.get("status") not in {"failed", "stale", "unavailable"}:
                continue
            if key == "technical_intraday":
                local = current.astimezone(ZoneInfo("America/Sao_Paulo"))
                if local.weekday() >= 5 or not (10 <= local.hour < 18):
                    continue
            alerts.append({
                "code": f"snapshot_{status.get('status')}:{key}",
                "severity": "critical" if status.get("status") == "failed" else "warning",
                "title": "Dados de mercado precisam de atenção",
                "message": f"{status.get('label') or key}: situação {status.get('status')}.",
                "details": {"key": key, "status": status.get("status")},
            })

        resources = local_resources or collect_resource_metrics()
        monitored_resources = [(local_label, resources)]
        for service in serialized_services:
            if (
                service["role"] == "worker"
                and service.get("metrics")
                and service.get("status") == "running"
                and service.get("age_seconds") is not None
                and service["age_seconds"] <= settings.operational_worker_stale_seconds
            ):
                monitored_resources.append((service["node_id"], service["metrics"]))
        seen_locations: set[str] = set()
        for location, metrics in monitored_resources:
            if location in seen_locations:
                continue
            seen_locations.add(location)
            managed_codes.update({
                f"memory_pressure:{location}",
                f"swap_pressure:{location}",
                f"disk_pressure:{location}",
            })
            _threshold_alert(alerts, code="memory_pressure", title="Uso elevado de memória", value=(metrics.get("container_memory") or {}).get("used_pct") or (metrics.get("memory") or {}).get("used_pct"), warning=settings.operational_memory_warning_pct, critical=settings.operational_memory_critical_pct, location=location)
            _threshold_alert(alerts, code="swap_pressure", title="Uso elevado de swap", value=(metrics.get("swap") or {}).get("used_pct"), warning=settings.operational_swap_warning_pct, critical=settings.operational_swap_critical_pct, location=location)
            _threshold_alert(alerts, code="disk_pressure", title="Pouco espaço disponível em disco", value=(metrics.get("disk") or {}).get("used_pct"), warning=settings.operational_disk_warning_pct, critical=settings.operational_disk_critical_pct, location=location)

        route_metrics = ROUTE_LATENCIES.snapshot() if include_route_metrics else {"since": None, "categories": []}
        if include_route_metrics:
            managed_prefixes.add("route_latency:")
        for metric in route_metrics.get("categories", []):
            if metric.get("sample_sufficient") and metric.get("within_target") is False:
                alerts.append({
                    "code": f"route_latency:{metric['key']}", "severity": "warning",
                    "title": "Rota acima da meta de resposta",
                    "message": f"{metric['key']}: p95 de {metric['p95_ms']} ms, meta de {metric['target_p95_ms']} ms.",
                    "details": {"category": metric["key"], "p95_ms": metric["p95_ms"], "target_ms": metric["target_p95_ms"]},
                })

        incidents = self.repository.sync_incidents(
            alerts,
            now=current,
            managed_codes=managed_codes,
            managed_prefixes=managed_prefixes,
        ) if sync_incidents else []
        leases = [runtime_lease_dict(row, now=current) for row in self.repository.active_leases(now=current)]
        severity = "critical" if any(item["severity"] == "critical" for item in alerts) else "warning" if alerts else "healthy"
        return {
            "status": severity,
            "generated_at": current,
            "version": __version__,
            "worker_health": worker_health,
            "services": serialized_services,
            "leases": leases,
            "queue": {
                "queued": queued, "running": running,
                "oldest_due_at": oldest_due, "oldest_due_minutes": queue_age_minutes,
                "stale_running": stale_running,
            },
            "repeated_failures": repeated_failures,
            "updates": update_statuses,
            "resources": resources,
            "route_metrics": route_metrics,
            "alerts": alerts,
            "incidents": [operational_incident_dict(row) for row in incidents],
        }

    def notify_open_incidents(self, sender: AlertEmailSender | None = None) -> int:
        recipients = sorted(settings.owner_emails)
        mailer = sender or AlertEmailSender()
        if not recipients or not mailer.configured:
            return 0
        rows = self.repository.notification_candidates(
            cooldown_hours=settings.operational_notification_cooldown_hours,
        )
        if not rows:
            return 0
        lines = [f"- [{row.severity.upper()}] {row.title}: {row.message}" for row in rows]
        mailer.send(
            recipients=recipients,
            subject=f"[Formação do Investidor] {len(rows)} alerta(s) operacional(is)",
            text_body="A infraestrutura requer atenção:\n\n" + "\n".join(lines) + "\n\nConsulte Administração > Operação para detalhes.",
        )
        for row in rows:
            self.repository.mark_notified(row)
        return len(rows)
