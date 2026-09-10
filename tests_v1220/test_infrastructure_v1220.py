from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _service_block(compose: str, service: str) -> str:
    marker = f"  {service}:\n"
    start = compose.index(marker)
    match = re.search(r"(?m)^  [A-Za-z0-9_-]+:\s*$", compose[start + len(marker):])
    next_service = -1 if match is None else start + len(marker) + match.start()
    return compose[start:] if next_service == -1 else compose[start:next_service]


def test_worker_credentials_and_runtime_files_are_excluded_from_git_and_images():
    gitignore = _read(".gitignore").splitlines()
    dockerignore = _read(".dockerignore").splitlines()

    assert "deployment/second-instance/worker_secrets.toml" in gitignore
    assert "deployment/second-instance/worker.env" in gitignore
    assert "deployment/runtime/*.env" in gitignore
    assert "deployment/second-instance/worker_secrets.toml" in dockerignore
    assert "deployment/second-instance/worker.env" in dockerignore
    assert "deployment/runtime" in dockerignore

    # A release may contain templates, but never the material privado itself.
    assert not (ROOT / "deployment/second-instance/worker_secrets.toml").exists()
    assert not (ROOT / "deployment/second-instance/worker.env").exists()
    assert not (ROOT / "deployment/runtime/worker-location.env").exists()
    assert not (ROOT / "deployment/runtime/primary-db.env").exists()


def test_primary_compose_keeps_database_private_and_has_explicit_roles():
    compose = _read("docker-compose.oracle-web.yml")
    postgres = _service_block(compose, "postgres")
    app = _service_block(compose, "app")
    staging = _service_block(compose, "staging")
    worker = _service_block(compose, "worker")

    assert "ports:" not in postgres
    assert "backend:\n    internal: true" in compose
    assert "ALERT_MONITOR_ENABLED: \"false\"" in app
    assert "SERVICE_NODE_ID: primary-web" in app
    assert 'APP_COMMIT_SHA: "${FDI_RELEASE_COMMIT:-unknown}"' in app
    assert 'BACKGROUND_SCHEDULER_ENABLED: "false"' in staging
    assert "SERVICE_NODE_ID: primary-staging" in staging
    assert 'BACKGROUND_SCHEDULER_ENABLED: "true"' in worker
    assert 'ALERT_MONITOR_ENABLED: "true"' in worker
    assert "SERVICE_NODE_ID: primary-worker" in worker
    assert "- frontend" in worker and "- backend" in worker
    assert "scripts.check_worker_heartbeat" in worker
    assert "stop_grace_period: 10m" in worker


def test_remote_compose_contains_only_a_worker_and_safe_coordinator_defaults():
    compose = _read("deployment/second-instance/docker-compose.worker.yml")
    worker = _service_block(compose, "worker")

    assert "\n  postgres:" not in compose
    assert "\n  app:" not in compose
    assert "\n  proxy:" not in compose
    assert "ports:" not in worker
    assert "APP_ENVIRONMENT: production-worker" in worker
    assert 'APP_COMMIT_SHA: "${FDI_RELEASE_COMMIT:-unknown}"' in worker
    assert 'BACKGROUND_SCHEDULER_ENABLED: "${FDI_COORDINATOR_ENABLED:-false}"' in worker
    assert 'ALERT_MONITOR_ENABLED: "${FDI_COORDINATOR_ENABLED:-false}"' in worker
    assert "./worker_secrets.toml:/app/secrets/worker_secrets.toml:ro" in worker
    assert "DATABASE_POOL_SIZE: \"3\"" in worker
    assert "DATABASE_MAX_OVERFLOW: \"0\"" in worker
    assert "scripts.check_worker_heartbeat" in worker
    assert "stop_grace_period: 10m" in worker

    environment = _read("deployment/second-instance/worker.env.example")
    assert "FDI_COORDINATOR_ENABLED=false" in environment
    assert "FDI_RELEASE_COMMIT=commit_aprovado" in environment


def test_worker_lifecycle_scripts_prepare_activate_stop_and_validate_safely():
    prepare = _read("deployment/second-instance/prepare-worker.sh")
    activate = _read("deployment/second-instance/activate-worker.sh")
    stop = _read("deployment/second-instance/stop-worker.sh")
    validate = _read("deployment/second-instance/validate-worker.sh")

    for script in (prepare, activate, stop, validate):
        assert script.startswith("#!/usr/bin/env bash\nset -Eeuo pipefail")
        assert "docker compose" in script

    assert "git fetch --quiet origin main" in prepare
    assert prepare.count("FDI_COORDINATOR_ENABLED=false") >= 2
    assert "build worker" in prepare and "run --rm --no-deps worker" in prepare
    assert "up -d --force-recreate worker" not in prepare
    assert "nenhum consumidor adicional foi iniciado" in prepare

    exact_commit_check = '[[ "$(git rev-parse HEAD)" == "${COMMIT}" ]]'
    assert exact_commit_check in activate
    assert activate.index(exact_commit_check) < activate.index("build worker")
    assert activate.count("FDI_COORDINATOR_ENABLED=true") >= 2
    assert '[[ "${STATUS}" == "healthy" ]]' in activate

    assert "stop -t 600 worker" in stop
    assert 'SECRETS_FILE="${PROJECT_DIR}/deployment/second-instance/worker_secrets.toml"' in validate
    assert "10#${MODE} % 10 != 0" in validate
    assert "address.is_private" in validate
    assert "address.is_loopback" in validate
    assert "parsed.port != 5432" in validate
    assert 'revision != "0022_v1_22_observability"' in validate
    assert "SELECT 1" in validate


def test_private_database_templates_never_bind_postgres_publicly():
    override = _read("deployment/second-instance/primary-db.override.yml.example")
    primary_env = _read("deployment/runtime/primary-db.env.example")
    worker_secret = _read("deployment/second-instance/worker_secrets.toml.example")
    location = _read("deployment/runtime/worker-location.env.example")

    assert "${FDI_PRIVATE_DB_BIND:?" in override
    assert "0.0.0.0:5432" not in override
    assert "FDI_PRIVATE_DB_BIND=10.0.0.10" in primary_env
    assert "@10.0.0.10:5432/investment_engine" in worker_secret
    assert "investment_worker:" in worker_secret
    assert "FDI_WORKER_LOCATION=local" in location
    assert "FDI_WORKER_SSH_HOST=10.0.0.20" in location


def test_staging_and_production_propagate_the_exact_approved_commit():
    update = _read("deployment/update-staging-from-github.sh")
    promote = _read("deployment/promote-staging-to-production.sh")

    assert 'TARGET_COMMIT="$(git rev-parse origin/main)"' in update
    assert 'FDI_RELEASE_COMMIT="${TARGET_COMMIT}" docker compose' in update
    assert 'echo "${TARGET_COMMIT}" > "${DEPLOYED_FILE}"' in update

    assert 'TARGET_COMMIT="$(cat "${PROJECT_DIR}/.git/investment-staging-commit"' in promote
    assert 'FDI_RELEASE_COMMIT="${TARGET_COMMIT}" docker compose' in promote
    assert 'activate-worker.sh \'${TARGET_COMMIT}\'' in promote
    assert "investment-production-commit" in promote


def test_promotion_has_remote_cutover_local_fallback_and_truthful_rollback_metadata():
    promote = _read("deployment/promote-staging-to-production.sh")

    assert 'FDI_WORKER_LOCATION="local"' in promote
    assert 'source "${WORKER_LOCATION_FILE}"' in promote
    assert '[[ "${FDI_WORKER_LOCATION}" == "remote" ]]' in promote
    remote_branch = promote.index('if [[ "${FDI_WORKER_LOCATION}" == "remote" ]]')
    stop_local = promote.index('stop worker', remote_branch)
    activate_remote = promote.index('activate-worker.sh', remote_branch)
    assert stop_local < activate_remote
    assert 'FDI_RELEASE_COMMIT="${TARGET_COMMIT}" docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate worker' in promote

    # Regression: a failed release must not advertise the failed commit after
    # restoring the rollback image, nor start a second coordinator while the
    # remote coordinator is still active.
    assert 'FDI_RELEASE_COMMIT="${TARGET_COMMIT}" docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate app worker' not in promote
    assert "ROLLBACK_COMMIT" in promote
    assert 'FDI_RELEASE_COMMIT="${ROLLBACK_COMMIT}"' in promote


def test_cutover_and_failback_never_intentionally_run_two_coordinators():
    cutover = _read("deployment/second-instance/cutover-worker.sh")
    failback = _read("deployment/second-instance/failback-worker.sh")

    for script in (cutover, failback):
        assert script.startswith("#!/usr/bin/env bash\nset -Eeuo pipefail")

    # The remote image is prepared without starting a consumer.  During the
    # actual cut, the local worker is stopped before the remote one starts.
    prepare_remote = cutover.index("prepare-worker.sh")
    stop_local = cutover.index("stop -t 600 worker")
    activate_remote = cutover.index("activate-worker.sh")
    assert prepare_remote < stop_local < activate_remote
    assert 'FDI_WORKER_LOCATION=remote' in cutover
    assert "stop-worker.sh" in cutover
    assert 'FDI_WORKER_LOCATION=local' in cutover

    # Failback mirrors the ordering: stop remote, then start local, and only
    # publish the location after the local healthcheck succeeds.
    stop_remote = failback.index("stop-worker.sh")
    start_local = failback.index("up -d --no-deps --force-recreate worker")
    mark_local = failback.index("FDI_WORKER_LOCATION=local")
    assert stop_remote < start_local < mark_local
    assert '[[ "${STATUS}" == "healthy" ]]' in failback


def test_private_database_scripts_require_private_binding_and_keep_a_reversal_path():
    create_role = _read("deployment/second-instance/create-worker-db-role.sh")
    enable = _read("deployment/second-instance/enable-primary-private-db.sh")
    disable = _read("deployment/second-instance/disable-primary-private-db.sh")

    assert 'ROLE_NAME="investment_worker"' in create_role
    assert "${#ROLE_PASSWORD} < 32" in create_role
    assert "GRANT CONNECT ON DATABASE investment_engine" in create_role
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES" in create_role
    assert "CREATE DATABASE" not in create_role
    assert "CREATEDB" not in create_role
    assert "SUPERUSER" not in create_role

    assert "address.is_private" in enable
    assert "address.is_loopback" in enable
    assert "backup-local-db.sh" in enable
    assert "0\\.0\\.0\\.0" in enable and "\\[::\\]" in enable
    assert "primary-db.override.yml.example" in enable

    assert "backup-local-db.sh" in disable
    assert 'docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate postgres' in disable
    assert "A publicação privada do PostgreSQL foi removida" in disable


def test_watchdog_is_independent_from_the_worker_and_installed_as_a_timer():
    runner = _read("scripts/run_operational_watchdog.py")
    service = _read("deployment/investment-operational-watchdog.service.example")
    timer = _read("deployment/investment-operational-watchdog.timer.example")
    installer = _read("deployment/install-operational-watchdog.sh")

    assert "OperationalHealthService" in runner
    assert "notify_open_incidents" in runner
    assert "--fail-on-critical" in runner
    assert "docker compose" in service and "exec -T app" in service
    assert "run_operational_watchdog --fail-on-critical" in service
    assert "OnUnitActiveSec=2min" in timer
    assert "Persistent=true" in timer
    assert "enable --now investment-operational-watchdog.timer" in installer


def test_ci_includes_current_suites_and_postgres_migration_head():
    workflow = _read(".github/workflows/tests.yml")

    assert workflow.count("tests_v1210 tests_v1220") == 2
    assert 'assert revision == "0022_v1_22_observability"' in workflow
