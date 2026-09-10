from __future__ import annotations

import argparse
import logging
import signal
import threading

from investment_engine.core.jobs.worker import BackgroundWorker
from investment_engine.core.alerts.service import AlertMonitor
from investment_engine.infrastructure.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa a fila persistente da Formação do Investidor.")
    parser.add_argument("--once", action="store_true", help="Processa no máximo um trabalho e termina.")
    parser.add_argument("--poll-seconds", type=float, default=settings.background_worker_poll_seconds)
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    alert_monitor = AlertMonitor() if settings.alert_monitor_enabled and not args.once else None
    worker = BackgroundWorker(
        poll_seconds=args.poll_seconds,
        lease_timeout_seconds=settings.background_job_lease_timeout_seconds,
        scheduler_enabled=settings.background_scheduler_enabled,
        scheduler_tick_seconds=settings.background_scheduler_tick_seconds,
        node_id=settings.service_node_id or None,
        alert_leader_provider=(lambda: alert_monitor.is_leader) if alert_monitor is not None else None,
    )
    if args.once:
        worker.run_once()
        return
    stop = threading.Event()

    def request_stop(_signum, _frame):
        logging.getLogger("investment_engine.background_worker").info("worker_shutdown_requested")
        stop.set()

    for signal_name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signal_name, request_stop)
    if alert_monitor is not None:
        alert_monitor.start()
    try:
        worker.run_forever(stop)
    finally:
        if alert_monitor is not None:
            alert_monitor.stop()


if __name__ == "__main__":
    main()
