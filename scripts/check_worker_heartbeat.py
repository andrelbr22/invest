from __future__ import annotations

from datetime import datetime, timezone
import sys

from investment_engine.core.repositories.operations import OperationsRepository, aware
from investment_engine.infrastructure.config import settings
from investment_engine.infrastructure.db.session import get_session_factory


def main() -> None:
    node_id = str(settings.service_node_id or "").strip()
    service_id = f"worker:{settings.app_environment}:{node_id}"
    session = get_session_factory()()
    try:
        row = OperationsRepository(session).get_service(service_id)
    finally:
        session.close()
    if row is None or row.status != "running" or aware(row.last_seen_at) is None:
        raise SystemExit(1)
    age = (datetime.now(timezone.utc) - aware(row.last_seen_at)).total_seconds()
    if age > max(90, settings.service_heartbeat_seconds * 3):
        raise SystemExit(1)
    expected_commit = str(settings.app_commit_sha or "").strip()
    reported_commit = str(row.commit_sha or "").strip()
    if expected_commit and expected_commit != "unknown" and reported_commit != expected_commit:
        raise SystemExit(1)
    sys.stdout.write("worker heartbeat ok\n")


if __name__ == "__main__":
    main()
