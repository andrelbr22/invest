from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import text

from investment_engine.infrastructure.db.session import get_session_factory


LEADER_LEASES = {"background-scheduler", "price-alert-monitor-leader"}


def validate_lease_owner(lease, worker, expected_node: str) -> None:
    """Bind each singleton lease to the one fresh worker without conflating IDs.

    The scheduler deliberately uses the stable worker service id.  The alert
    monitor has its own holder id because it owns and releases its lease from a
    separate component in the worker process.  Its production identity is
    ``alerts:<environment>:<node>:<pid>``.  Both still have to point to the
    exact expected node, and the caller has already proved that only one fresh
    production worker exists and reports both leadership flags.
    """
    lease_name = str(lease["lease_name"] or "")
    holder_id = str(lease["holder_id"] or "")
    metadata = dict(lease["metadata_json"] or {})
    if str(metadata.get("node_id") or "") != expected_node:
        raise SystemExit(f"A lease {lease_name} pertence a outro nó.")

    if lease_name == "background-scheduler":
        if holder_id != str(worker["service_id"] or ""):
            raise SystemExit("A lease background-scheduler pertence a outro worker.")
        return

    if lease_name == "price-alert-monitor-leader":
        prefix = f"alerts:{worker['environment']}:{worker['node_id']}:"
        process_id = holder_id.removeprefix(prefix) if holder_id.startswith(prefix) else ""
        if not process_id.isascii() or not process_id.isdigit() or int(process_id) <= 0:
            raise SystemExit(
                "A lease price-alert-monitor-leader não pertence ao monitor "
                "do worker esperado."
            )
        return

    raise SystemExit(f"Lease de liderança inesperada: {lease_name}.")


def validate_worker_topology(
    workers,
    leases,
    *,
    expected_node: str,
    expected_environment: str,
    expected_commit: str,
):
    """Validate one logical worker and the exact two leases it must own."""
    if len(workers) != 1:
        raise SystemExit(
            "Esperado exatamente um worker de produção fresco; "
            f"encontrados {len(workers)}."
        )
    worker = workers[0]
    expected_service_id = f"worker:{expected_environment}:{expected_node}"
    if str(worker["service_id"] or "") != expected_service_id:
        raise SystemExit(
            "Worker divergente em service_id: "
            f"recebido={worker['service_id']!s}, esperado={expected_service_id}."
        )
    expected = {
        "node_id": expected_node,
        "environment": expected_environment,
        "commit_sha": expected_commit,
    }
    for field, value in expected.items():
        if str(worker[field] or "") != value:
            raise SystemExit(
                f"Worker divergente em {field}: "
                f"recebido={worker[field]!s}, esperado={value}."
            )
    if not worker["scheduler_leader"] or not worker["alert_monitor_leader"]:
        raise SystemExit("O worker esperado ainda não assumiu as duas lideranças.")
    if {str(row["lease_name"]) for row in leases} != LEADER_LEASES or len(leases) != 2:
        raise SystemExit(
            "As leases ativas não correspondem exatamente ao scheduler "
            "e ao monitor de alertas."
        )
    for lease in leases:
        validate_lease_owner(lease, worker, expected_node)
    return worker


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

    worker = validate_worker_topology(
        workers,
        leases,
        expected_node=args.expected_node,
        expected_environment=args.expected_environment,
        expected_commit=args.expected_commit,
    )

    print(json.dumps({
        "ok": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "worker": str(worker["service_id"]),
        "node_id": args.expected_node,
        "commit": args.expected_commit,
        "leaders": sorted(LEADER_LEASES),
        "lease_holders": {
            str(row["lease_name"]): str(row["holder_id"]) for row in leases
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
