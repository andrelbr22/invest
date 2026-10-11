"""Validate the evidence produced by the controlled VM2 resilience drill."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


REQUIRED_CHECKS = {
    "remote_worker_confirmed",
    "single_scheduler_confirmed",
    "single_alert_monitor_confirmed",
    "failback_confirmed",
    "final_topology_confirmed",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida a evidência do ensaio do worker remoto.")
    parser.add_argument("report")
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-mode", choices=("manual", "automatic"), required=True)
    parser.add_argument("--expected-final-location", choices=("local", "remote"), default="remote")
    parser.add_argument("--max-age-hours", type=float, default=24)
    args = parser.parse_args()

    payload = json.loads(Path(args.report).read_text(encoding="utf-8"))
    failures = []
    if payload.get("schema_version") != 1:
        failures.append("versão da evidência inválida")
    if payload.get("release_commit") != args.expected_commit:
        failures.append("commit diferente da produção")
    if payload.get("mode") != args.expected_mode:
        failures.append("modo do ensaio diferente")
    if payload.get("final_location") != args.expected_final_location:
        failures.append("localização final diferente")
    if payload.get("passed") is not True:
        failures.append("ensaio não aprovado")
    checks = payload.get("checks") or {}
    for check in sorted(REQUIRED_CHECKS):
        if checks.get(check) is not True:
            failures.append(f"verificação ausente: {check}")
    finished_at = datetime.fromisoformat(str(payload.get("finished_at", "")).replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - finished_at > timedelta(hours=max(1, args.max_age_hours)):
        failures.append("evidência vencida")
    if failures:
        raise SystemExit("Ensaio do worker inválido: " + "; ".join(failures))
    print(
        "Ensaio do worker validado:", args.expected_mode,
        args.expected_final_location, args.expected_commit,
    )


if __name__ == "__main__":
    main()

