from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import text

from investment_engine.infrastructure.db.session import get_session_factory


LEADER_LEASES = {"background-scheduler", "price-alert-monitor-leader"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Confirma o worker e as duas lideranças distribuídas.")
    parser.add_argument("--expected-node", required=True)
    parser.add_argument("--expected-environment", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--fresh-seconds", type=int, default=180)
    args = parser.parse_args()
    if not args.expected_commit or len(args.expected_commit) != 40:
        raise SystemExit("Commit esperado inválido.")

    session = get_session_factory()()
    try:
        workers = session.execute(text("""
            SELECT service_id, node_id, environment, commit_sha,
                   scheduler_leader, alert_monitor_leader, last_seen_at
            FROM service_heartbeats
            WHERE role = 'worker'
              AND status = 'running'
              AND environment IN ('production', 'production-worker')
              AND last_seen_at >= CURRENT_TIMESTAMP - make_interval(secs => :fresh_seconds)
            ORDER BY service_id
        """), {"fresh_seconds": max(90, min(args.fresh_seconds, 600))}).mappings().all()
        leases = session.execute(text("""
            SELECT lease_name, holder_id, metadata_json, expires_at
            FROM runtime_leases
            WHERE lease_name IN ('background-scheduler', 'price-alert-monitor-leader')
              AND expires_at > CURRENT_TIMESTAMP
            ORDER BY lease_name
        """)).mappings().all()
    finally:
        session.close()

    if len(workers) != 1:
        raise SystemExit(f"Esperado exatamente um worker de produção fresco; encontrados {len(workers)}.")
    worker = workers[0]
    expected = {
        "node_id": args.expected_node,
        "environment": args.expected_environment,
        "commit_sha": args.expected_commit,
    }
    for field, value in expected.items():
        if str(worker[field] or "") != value:
            raise SystemExit(f"Worker divergente em {field}: recebido={worker[field]!s}, esperado={value}.")
    if not worker["scheduler_leader"] or not worker["alert_monitor_leader"]:
        raise SystemExit("O worker esperado ainda não assumiu as duas lideranças.")
    if {str(row["lease_name"]) for row in leases} != LEADER_LEASES or len(leases) != 2:
        raise SystemExit("As leases ativas não correspondem exatamente ao scheduler e ao monitor de alertas.")
    for lease in leases:
        metadata = dict(lease["metadata_json"] or {})
        if str(metadata.get("node_id") or "") != args.expected_node:
            raise SystemExit(f"A lease {lease['lease_name']} pertence a outro nó.")

    print(json.dumps({
        "ok": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "worker": str(worker["service_id"]),
        "node_id": args.expected_node,
        "commit": args.expected_commit,
        "leaders": sorted(LEADER_LEASES),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
