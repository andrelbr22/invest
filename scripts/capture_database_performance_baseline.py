"""Capture a read-only PostgreSQL, pool and I/O baseline for release decisions."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from investment_engine.core.database_performance import (
    collect_database_performance,
    sample_io_wait,
)
from investment_engine.infrastructure.db.session import get_session_factory


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Registra a linha de base do banco sem alterar configurações ou contadores."
    )
    parser.add_argument("--output", help="Caminho opcional do relatório JSON.")
    parser.add_argument("--without-statements", action="store_true")
    parser.add_argument("--io-sample-seconds", type=float, default=0.5)
    args = parser.parse_args()

    with get_session_factory()() as session:
        report = collect_database_performance(
            session, include_statements=not args.without_statements
        )
    report["host_io"] = sample_io_wait(seconds=args.io_sample_seconds)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, default=_json_default)
    if args.output:
        target = Path(args.output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_text(rendered + "\n", encoding="utf-8", newline="\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    print(rendered)


if __name__ == "__main__":
    main()

