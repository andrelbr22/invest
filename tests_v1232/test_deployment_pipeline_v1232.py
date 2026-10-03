from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _active_lines(script: str) -> list[str]:
    return [
        line.strip()
        for line in script.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_api_and_worker_only_verify_the_schema_during_startup():
    api = _read("deployment/start-api.sh")
    worker = _read("deployment/start-worker.sh")

    for startup in (api, worker):
        assert "run-migrations.py verify --timeout-seconds 60" in startup
        assert "alembic upgrade" not in startup
        assert "run-migrations.py upgrade" not in startup

    assert api.index("run-migrations.py verify") < api.index("exec python -m uvicorn")
    assert worker.index("run-migrations.py verify") < worker.index(
        "exec python -m scripts.run_background_worker"
    )


def test_migration_runner_serializes_and_verifies_the_exact_alembic_head():
    runner = _read("deployment/run-migrations.py")
    alembic_environment = _read("alembic/env.py")

    assert "pg_try_advisory_lock" in runner
    assert "pg_advisory_unlock" in runner
    assert "len(heads) != 1" in runner
    assert 'command.upgrade(config, "head")' in runner
    assert "get_current_heads" in runner
    assert "current != expected" in runner
    assert "Outra migração continua em andamento" in runner
    assert '.replace("%", "%%")' in alembic_environment


def test_compose_has_explicit_one_shot_migration_services():
    compose = _read("docker-compose.oracle-web.yml")

    assert "  production-migration:" in compose
    assert "  staging-migration:" in compose
    assert compose.count('profiles: ["operations"]') == 2
    assert compose.count(
        'command: ["python", "/app/deployment/run-migrations.py", "upgrade"]'
    ) == 2
    assert compose.count("image: formacao-do-investidor-staging:candidate") >= 3
    staging_migration = compose[compose.index("  staging-migration:"):compose.index("  proxy:")]
    assert "deployment/runtime/staging.env" in staging_migration
    assert "DATABASE_NAME_OVERRIDE: investment_engine_staging" in staging_migration


def test_release_scripts_apply_migrations_before_recreating_applications():
    staging = _read("deployment/update-staging-from-github.sh")
    production = _read("deployment/promote-staging-to-production.sh")

    clone = staging.index('"${PROJECT_DIR}/deployment/refresh-staging-db.sh"')
    migrate_staging = staging.index("run --rm --no-deps staging-migration")
    start_staging = staging.index("--force-recreate staging")
    assert clone < migrate_staging < start_staging

    benchmark = production.index("python -m scripts.benchmark_application_routes")
    backup = production.index('bash "${PROJECT_DIR}/deployment/backup-local-db.sh"')
    migrate_production = production.index("run --rm --no-deps production-migration")
    retag = production.index('docker tag "${STAGING_IMAGE}" "${PRODUCTION_IMAGE}"')
    start_app = production.index("--force-recreate app")
    assert benchmark < backup < migrate_production < retag < start_app
    assert "alembic downgrade" not in production


def test_release_queues_resumable_current_metrics_only_after_healthy_startup():
    staging = _read("deployment/update-staging-from-github.sh")
    production = _read("deployment/promote-staging-to-production.sh")
    enqueue = _read("scripts/enqueue_current_metrics_refresh.py")

    assert "current_metrics_refresh" in enqueue
    assert "deduplication_key" in enqueue and "idempotency_key" in enqueue
    assert staging.index('[[ "${STATUS}" == "healthy" ]]') < staging.index(
        "scripts.enqueue_current_metrics_refresh"
    )
    # Um único helper idempotente atende os três finais mutuamente exclusivos:
    # remoto confirmado, retorno local após falha remota e worker local normal.
    assert production.count("scripts.enqueue_current_metrics_refresh") == 1
    assert production.count("enqueue_current_metrics_after_worker_promotion") == 4
    assert production.index("mark_worker_promotion_complete") < production.index(
        "enqueue_current_metrics_after_worker_promotion"
    )
    assert production.index("wait_local_worker_ready") < production.rindex(
        "scripts.enqueue_current_metrics_refresh"
    )


def test_proxy_uses_dynamic_docker_dns_and_validated_zero_downtime_reload():
    caddy = _read("deployment/Caddyfile.oracle-micro.example")
    reload_script = _read("deployment/reload-proxy.sh")
    staging = _read("deployment/update-staging-from-github.sh")
    production = _read("deployment/promote-staging-to-production.sh")

    assert re.search(r"dynamic a staging 8000\s*\{", caddy)
    assert len(re.findall(r"dynamic a app 8000\s*\{", caddy)) == 2
    assert caddy.count("refresh 2s") == 3
    assert caddy.count("versions ipv4") == 3

    validate = reload_script.index("caddy validate")
    reload = reload_script.index("caddy reload")
    fallback = reload_script.index("restart proxy")
    assert validate < reload < fallback
    assert "a configuração do proxy é inválida" in reload_script.lower()

    assert 'bash "${PROJECT_DIR}/deployment/reload-proxy.sh"' in staging
    assert 'bash "${PROJECT_DIR}/deployment/reload-proxy.sh"' in production
    for release_script in (staging, production):
        active = _active_lines(release_script)
        assert not any("docker compose" in line and "restart proxy" in line for line in active)


def test_migration_and_proxy_scripts_use_linux_line_endings():
    for relative in (
        "deployment/run-migrations.py",
        "deployment/reload-proxy.sh",
        "deployment/start-api.sh",
        "deployment/start-worker.sh",
    ):
        assert b"\r\n" not in (ROOT / relative).read_bytes()
