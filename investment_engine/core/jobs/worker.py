from __future__ import annotations

import logging
import socket
import threading
import time
from datetime import datetime, timezone
from collections.abc import Callable

from ...infrastructure.db.session import get_session_factory
from ...infrastructure.config import settings
from ... import __version__
from ..observability import OperationalHealthService, collect_resource_metrics
from ..repositories.background_jobs import BackgroundJobRepository
from ..repositories.operations import OperationsRepository
from .handlers import DEFAULT_JOB_HANDLERS
from .schedules import enqueue_due_refreshes


LOGGER = logging.getLogger("investment_engine.background_worker")
JobHandler = Callable[[dict], dict]


class BackgroundWorker:
    """Single-concurrency worker. Scale only after measuring the Oracle host."""

    def __init__(
        self,
        *,
        worker_id: str | None = None,
        handlers: dict[str, JobHandler] | None = None,
        poll_seconds: float = 2.0,
        lease_timeout_seconds: int = 300,
        scheduler_enabled: bool = False,
        scheduler_tick_seconds: int = 60,
        node_id: str | None = None,
        alert_leader_provider: Callable[[], bool] | None = None,
    ):
        self.node_id = str(node_id or settings.service_node_id or socket.gethostname()).strip()[:120]
        self.worker_id = worker_id or f"{self.node_id}:{threading.get_native_id()}"
        self.service_id = f"worker:{settings.app_environment}:{self.node_id}"
        self.handlers = dict(handlers or DEFAULT_JOB_HANDLERS)
        self.poll_seconds = max(0.2, float(poll_seconds))
        self.lease_timeout_seconds = max(30, int(lease_timeout_seconds))
        self.scheduler_enabled = bool(scheduler_enabled)
        self.scheduler_tick_seconds = max(30, int(scheduler_tick_seconds))
        self.alert_leader_provider = alert_leader_provider or (lambda: False)
        self._scheduler_leader = False
        self._started_at = datetime.now(timezone.utc)

    def schedule_due(self) -> list[str]:
        session = get_session_factory()()
        try:
            created = enqueue_due_refreshes(session)
            session.commit()
            if created:
                LOGGER.info("background_refreshes_scheduled groups=%s", ",".join(created))
            return created
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _renew_lease(self, job_id, stop_event: threading.Event) -> None:
        """Keep long jobs leased without sharing the handler's database session."""
        interval = max(10.0, min(60.0, self.lease_timeout_seconds / 3))
        while not stop_event.wait(interval):
            session = get_session_factory()()
            try:
                repository = BackgroundJobRepository(session)
                current = repository.get(job_id)
                if current is None or current.status != "running" or current.locked_by != self.worker_id:
                    return
                repository.heartbeat(current, self.worker_id)
                session.commit()
            except Exception:
                session.rollback()
                LOGGER.warning("background_job_heartbeat_failed job_id=%s", job_id)
            finally:
                session.close()

    def run_once(self) -> bool:
        session = get_session_factory()()
        try:
            repository = BackgroundJobRepository(session)
            repository.recover_stale(self.lease_timeout_seconds)
            row = repository.lease_next(self.worker_id, allowed_types=set(self.handlers))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        if row is None:
            return False

        handler = self.handlers.get(row.job_type)
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._renew_lease,
            args=(row.id, heartbeat_stop),
            name=f"background-heartbeat-{row.id}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            if handler is None:
                raise LookupError("background_job_handler_not_registered")
            handler_payload = dict(row.payload_json or {})
            handler_payload["_background_job_id"] = str(row.id)
            handler_payload["_background_job_attempt"] = int(row.attempts)
            handler_payload["_background_job_max_attempts"] = int(row.max_attempts)
            result = handler(handler_payload)
            session = get_session_factory()()
            try:
                current = BackgroundJobRepository(session).get(row.id)
                if current is not None:
                    BackgroundJobRepository(session).complete(current, result)
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
            LOGGER.info("background_job_succeeded job_type=%s job_id=%s", row.job_type, row.id)
        except Exception as exc:
            session = get_session_factory()()
            try:
                current = BackgroundJobRepository(session).get(row.id)
                if current is not None:
                    BackgroundJobRepository(session).fail(
                        current,
                        error_code=type(exc).__name__,
                        error_message="Falha durante o processamento em segundo plano.",
                    )
                session.commit()
            except Exception:
                session.rollback()
                LOGGER.exception("background_job_failure_persistence_error job_id=%s", row.id)
            finally:
                session.close()
            LOGGER.warning("background_job_failed job_type=%s job_id=%s", row.job_type, row.id)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=5)
        return True

    def _scheduler_loop(self, stop: threading.Event) -> None:
        lease_name = "background-scheduler"
        ttl = max(settings.runtime_lease_seconds, self.scheduler_tick_seconds * 3)
        try:
            while not stop.is_set():
                session = get_session_factory()()
                try:
                    self._scheduler_leader = OperationsRepository(session).acquire_lease(
                        lease_name, self.service_id, ttl_seconds=ttl,
                        metadata={"node_id": self.node_id, "version": __version__},
                    )
                    session.commit()
                except Exception:
                    session.rollback()
                    self._scheduler_leader = False
                    LOGGER.exception("background_scheduler_leadership_failed")
                finally:
                    session.close()
                if self._scheduler_leader:
                    try:
                        self.schedule_due()
                    except Exception:
                        LOGGER.exception("background_scheduler_tick_failed")
                stop.wait(self.scheduler_tick_seconds)
        finally:
            if self._scheduler_leader:
                session = get_session_factory()()
                try:
                    OperationsRepository(session).release_lease(lease_name, self.service_id)
                    session.commit()
                except Exception:
                    session.rollback()
                finally:
                    session.close()
            self._scheduler_leader = False

    def _service_heartbeat_loop(self, stop: threading.Event) -> None:
        interval = max(10, int(settings.service_heartbeat_seconds))
        cycle = 0
        while not stop.is_set():
            resources = collect_resource_metrics()
            session = get_session_factory()()
            try:
                OperationsRepository(session).upsert_heartbeat(
                    service_id=self.service_id,
                    node_id=self.node_id,
                    role="worker",
                    environment=settings.app_environment,
                    version=__version__,
                    commit_sha=settings.app_commit_sha,
                    scheduler_leader=self._scheduler_leader,
                    alert_monitor_leader=bool(self.alert_leader_provider()),
                    metrics=resources,
                    started_at=self._started_at,
                )
                session.commit()
            except Exception:
                session.rollback()
                LOGGER.exception("worker_service_heartbeat_failed")
            finally:
                session.close()
            cycle += 1
            if cycle % 2 == 0:
                session = get_session_factory()()
                try:
                    operations = OperationalHealthService(session)
                    operations.overview(
                        local_resources=resources,
                        include_route_metrics=False,
                        sync_incidents=True,
                        local_label=self.node_id,
                    )
                    operations.notify_open_incidents()
                    session.commit()
                except Exception:
                    session.rollback()
                    LOGGER.exception("operational_health_cycle_failed")
                finally:
                    session.close()
            stop.wait(interval)
        session = get_session_factory()()
        try:
            OperationsRepository(session).mark_service_stopped(self.service_id)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        stop = stop_event or threading.Event()
        threads = [
            threading.Thread(
                target=self._service_heartbeat_loop,
                args=(stop,),
                name="worker-service-heartbeat",
                daemon=True,
            )
        ]
        if self.scheduler_enabled:
            threads.append(threading.Thread(
                target=self._scheduler_loop,
                args=(stop,),
                name="background-scheduler",
                daemon=True,
            ))
        for thread in threads:
            thread.start()
        LOGGER.info("background_worker_started worker_id=%s node_id=%s", self.worker_id, self.node_id)
        try:
            while not stop.is_set():
                worked = self.run_once()
                if not worked:
                    stop.wait(self.poll_seconds)
        finally:
            stop.set()
            for thread in threads:
                thread.join(timeout=8)


def worker_loop(*, poll_seconds: float = 2.0) -> None:
    worker = BackgroundWorker(poll_seconds=poll_seconds)
    while True:
        try:
            worker.run_forever()
        except KeyboardInterrupt:
            return
        except Exception:
            LOGGER.exception("background_worker_loop_error")
            time.sleep(min(30.0, max(1.0, poll_seconds)))
