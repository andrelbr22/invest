from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_default_suite_includes_current_release_tests():
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"tests_v1231"' in project


def test_diagnostic_logs_cannot_enter_package_or_image():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    publisher = (ROOT / "PUBLICAR_GITHUB.ps1").read_text(encoding="utf-8")
    assert "*.log" in dockerignore
    assert "gcm-diagnose*" in dockerignore
    assert "$diagnosticFiles" in publisher
    forbidden = [
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if (
            path.is_dir() and path.name in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        ) or (
            path.is_file() and (
                path.suffix.lower() in {".pyc", ".pyo", ".log"}
                or "diagnose" in path.name.lower()
            )
        )
    ]
    assert forbidden == []


def test_gitignore_matches_release_hygiene_guards():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("__pycache__/", "*.py[cod]", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/", "*.log", "gcm-diagnose*"):
        assert pattern in gitignore


def test_legacy_stack_quiesce_is_idempotent_for_stopped_containers():
    script = (ROOT / "deployment" / "quiesce-legacy-stack.sh").read_text(encoding="utf-8")
    assert "{{.State.Running}}" in script
    assert "{{.HostConfig.RestartPolicy.Name}}" in script
    assert 'if [[ "${running}" == "true" ]]' in script


def test_publisher_only_configures_credential_helper_when_missing_and_updates_backup():
    publisher = (ROOT / "PUBLICAR_GITHUB.ps1").read_text(encoding="utf-8")
    assert "config --get-all credential.helper" in publisher
    assert "if (-not $credentialHelpers)" in publisher
    assert '"HEAD:refs/heads/$backupBranch" $backupLease' in publisher
    assert '--force-with-lease=refs/heads/${backupBranch}:$remoteBackupSha' in publisher
    assert "$localMainSha -ne $remoteMainSha" in publisher


def test_release_identity_is_v1231_r1():
    version = (ROOT / "investment_engine" / "__init__.py").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    publisher = (ROOT / "PUBLICAR_GITHUB.ps1").read_text(encoding="utf-8")
    assert '__version__ = "1.23.1"' in version
    assert 'version = "1.23.1"' in project
    assert "V1.23.1 R1" in publisher


def test_promotion_runs_performance_gate_before_any_production_mutation():
    promotion = (ROOT / "deployment" / "promote-staging-to-production.sh").read_text(encoding="utf-8")
    benchmark = "python -m scripts.benchmark_application_routes --samples 20 --warmup 2"

    assert benchmark in promotion
    gate_position = promotion.index(benchmark)
    assert gate_position < promotion.index('bash "${PROJECT_DIR}/deployment/backup-local-db.sh"')
    assert gate_position < promotion.index('docker tag "${STAGING_IMAGE}" "${PRODUCTION_IMAGE}"')
    assert gate_position < promotion.index('up -d --no-deps --force-recreate app')
    assert "Promoção interrompida: o candidato não cumpriu as metas de desempenho." in promotion
