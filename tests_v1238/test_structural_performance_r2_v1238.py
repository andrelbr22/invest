from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from investment_engine.core.database_performance import collect_database_performance
from scripts.verify_worker_drill_report import main as verify_worker_drill_main


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_r2_release_identity_and_static_assets_are_current():
    publisher = read("PUBLICAR_GITHUB.ps1")
    platform = read("investment_engine/web/index.html")
    assert "Corrige a validacao de compatibilidade da V1.23.8 R2A em teste" in publisher
    assert "valide a V1.23.8 R2A" in publisher
    assert 'const FEATURE_ASSET_VERSION="1.23.8-r2"' in read(
        "investment_engine/web/static/app.js"
    )
    for asset in ("app.css", "web-vitals.js", "app.js"):
        assert f"{asset}?v=1.23.8-r2" in platform
    for relative in (
        "PATCH_V1238_R2.md",
        "RELATORIO_VALIDACAO_V1238_R2.md",
        "INSTRUCOES_ORACLE_V1238_R2.md",
    ):
        assert (ROOT / relative).is_file()


def test_database_baseline_is_read_only_and_handles_non_postgresql():
    source = read("investment_engine/core/database_performance.py").upper()
    for forbidden in (
        "ALTER SYSTEM",
        "CREATE INDEX",
        "DROP INDEX",
        "PG_STAT_RESET",
        "TRUNCATE ",
        "DELETE FROM",
    ):
        assert forbidden not in source
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with Session(engine) as session:
        payload = collect_database_performance(session)
    assert payload["supported"] is False
    assert payload["database"] == {}
    assert "database_performance_requires_postgresql" in payload["warnings"]


def test_owner_operations_exposes_database_evidence_without_automatic_tuning():
    api = read("investment_engine/api/app.py")
    admin = read("investment_engine/web/static/feature-admin.js")
    assert 'payload["database_performance"] = collect_database_performance' in api
    assert "include_statements=False" in api
    assert 'sectionCard("Banco, conexões e I/O"' in admin
    assert 'sectionCard("Candidatos para análise de índice"' in admin
    assert "nenhum índice é criado automaticamente" in admin


def test_vm2_drill_requires_explicit_approval_and_proves_both_failbacks():
    drill = read("deployment/second-instance/run-worker-resilience-drill.sh")
    automatic = read("deployment/second-instance/automatic-failback.sh")
    assert 'FDI_WORKER_DRILL_APPROVED:-' in drill
    assert '"V1.23.8-R2"' in drill
    assert "preflight-cutover.sh" in drill
    assert "cutover-worker.sh" in drill
    assert "failback-worker.sh" in drill
    assert "AUTO_FAILBACK_OBSERVATION" in drill
    assert "worker-topology-status.sh" in drill
    assert "capture-performance-baseline.sh" in drill
    assert "FDI_AUTO_FAILBACK_DRILL_APPROVED" in automatic
    assert "THRESHOLD=3" in automatic
    assert "cutover-worker.sh" not in automatic


def test_worker_drill_report_is_bound_to_commit_mode_and_final_location(tmp_path, monkeypatch):
    commit = "a" * 40
    report = tmp_path / "drill.json"
    report.write_text(
        json.dumps({
            "schema_version": 1,
            "mode": "automatic",
            "final_location": "remote",
            "release_commit": commit,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "checks": {
                "remote_worker_confirmed": True,
                "single_scheduler_confirmed": True,
                "single_alert_monitor_confirmed": True,
                "failback_confirmed": True,
                "final_topology_confirmed": True,
            },
            "passed": True,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_worker_drill_report",
            str(report),
            "--expected-commit", commit,
            "--expected-mode", "automatic",
            "--expected-final-location", "remote",
        ],
    )
    verify_worker_drill_main()


def test_browser_gate_becomes_persistent_only_after_valid_evidence():
    promotion = read("deployment/promote-staging-to-production.sh")
    runner = read("deployment/run-browser-performance-gate.sh")
    enabler = read("deployment/enable-browser-performance-gate.sh")
    capture = read("scripts/capture_browser_storage_state.py")
    assert "browser-performance.required" in promotion
    assert "worker_require_regular_owned_file" in promotion
    assert "BROWSER_REPORT_REQUIRED=true" in promotion
    assert "verify_browser_performance_report" in runner
    assert "worker_require_regular_owned_file \"${STATE_FILE}\" 600" in runner
    assert "verify_browser_performance_report" in enabler
    assert "storage_state" in capture
    assert "/testefdi/" in capture


def test_r2_does_not_create_a_second_database_or_a_new_migration():
    instructions = read("INSTRUCOES_ORACLE_V1238_R2.md")
    compose = read("deployment/second-instance/docker-compose.worker.yml")
    assert "um único PostgreSQL" in instructions
    assert "0.0.0.0/0" in instructions
    assert "postgres:" not in compose
    assert not list((ROOT / "alembic" / "versions").glob("0033*"))

