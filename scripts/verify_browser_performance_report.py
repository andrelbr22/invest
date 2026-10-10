"""Validate freshness, commit and p95 targets of a browser benchmark report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.benchmark_browser_journeys import REQUIRED_JOURNEYS


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida a evidência do benchmark no navegador.")
    parser.add_argument("report")
    parser.add_argument("--expected-commit")
    parser.add_argument("--max-age-hours", type=float, default=24)
    parser.add_argument("--min-samples", type=int, default=5)
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    generated_at = datetime.fromisoformat(str(report["generated_at"]).replace("Z", "+00:00"))
    failures: list[str] = []
    if datetime.now(timezone.utc) - generated_at > timedelta(hours=args.max_age_hours):
        failures.append("relatório vencido")
    if args.expected_commit and report.get("release_commit") != args.expected_commit:
        failures.append("commit diferente do staging aprovado")
    if "/testefdi/" not in str(report.get("base_url", "")):
        failures.append("o relatório não foi produzido no ambiente de teste")
    summary = report.get("summary") or {}
    for journey in REQUIRED_JOURNEYS:
        item = summary.get(journey) or {}
        if int(item.get("sample_count", 0)) < args.min_samples:
            failures.append(f"{journey}: amostras insuficientes")
        elif not item.get("within_target"):
            failures.append(f"{journey}: p95 acima da meta")
    if not report.get("passed"):
        failures.append("resultado geral reprovado")
    if failures:
        raise SystemExit("Benchmark real inválido: " + "; ".join(dict.fromkeys(failures)))
    print("Benchmark real validado para", report.get("release_commit"))


if __name__ == "__main__":
    main()
