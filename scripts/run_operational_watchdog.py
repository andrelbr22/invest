from __future__ import annotations

import argparse
import json

from investment_engine.core.observability import OperationalHealthService, collect_resource_metrics
from investment_engine.infrastructure.config import settings
from investment_engine.infrastructure.db.session import get_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verifica fila, worker, dados e recursos fora do processo do worker.",
    )
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        help="Retorna código diferente de zero quando houver incidente crítico.",
    )
    args = parser.parse_args()

    session = get_session_factory()()
    try:
        payload = OperationalHealthService(session).overview(
            local_resources=collect_resource_metrics(),
            include_route_metrics=False,
            sync_incidents=True,
            local_label=settings.service_node_id or "primary-web",
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    notified = 0
    notification_error = None
    session = get_session_factory()()
    try:
        notified = OperationalHealthService(session).notify_open_incidents()
        session.commit()
    except Exception as exc:
        session.rollback()
        notification_error = type(exc).__name__
    finally:
        session.close()

    print(json.dumps({
        "status": payload["status"],
        "open_alerts": len(payload.get("alerts") or []),
        "notifications_sent": notified,
        "notification_error": notification_error,
    }, ensure_ascii=False))
    if notification_error:
        raise SystemExit(3)
    if args.fail_on_critical and payload["status"] == "critical":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
