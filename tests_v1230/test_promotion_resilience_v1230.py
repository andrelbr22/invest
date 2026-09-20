from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_promotion_refreshes_proxy_and_checks_public_ready_before_completion():
    script = _read("deployment/promote-staging-to-production.sh")

    app_recreation = script.index('up -d --no-deps --force-recreate app')
    proxy_restart = script.index('restart proxy', app_recreation)
    public_check = script.index('if ! wait_public_ready', proxy_restart)
    app_marker = script.index('mark_app_promotion_complete', public_check)
    local_worker_check = script.index('if ! wait_local_worker_ready', public_check)
    worker_marker = script.rindex('mark_worker_promotion_complete')

    assert 'PUBLIC_READY_URL="https://formacaodoinvestidor.com.br/ready"' in script
    assert "curl --fail --silent --show-error --max-time 15" in script
    assert app_recreation < proxy_restart < public_check < app_marker < local_worker_check < worker_marker
    assert '"environment":"production"' in script


def test_promotion_accepts_only_a_fresh_worker_heartbeat_from_the_approved_commit():
    script = _read("deployment/promote-staging-to-production.sh")

    assert "wait_local_worker_ready()" in script
    assert "service_id = 'worker:production:primary-worker'" in script
    assert "scheduler_leader IS TRUE" in script
    assert "alert_monitor_leader IS TRUE" in script
    assert "started_at >= '${WORKER_LAUNCH_AT}'::timestamptz" in script
    assert "last_seen_at >= '${WORKER_LAUNCH_AT}'::timestamptz" in script
    assert "last_seen_at >= CURRENT_TIMESTAMP - INTERVAL '180 seconds'" in script
    assert '[[ "${reported_commit}" == "${TARGET_COMMIT}" ]]' in script
    assert "for _ in $(seq 1 72)" in script
    assert '"${status}" == "unhealthy"' not in script


def test_worker_healthcheck_validates_the_release_commit_and_keeps_tracebacks():
    checker = _read("scripts/check_worker_heartbeat.py")
    worker = _read("investment_engine/core/jobs/worker.py")
    repository = _read("investment_engine/core/repositories/operations.py")

    assert "OperationsRepository(session).get_service(service_id)" in checker
    assert "recent_services" not in checker
    assert "def get_service(self, service_id: str)" in repository
    assert "expected_commit = str(settings.app_commit_sha" in checker
    assert "reported_commit = str(row.commit_sha" in checker
    assert "reported_commit != expected_commit" in checker
    assert 'LOGGER.exception("background_job_heartbeat_failed job_id=%s", job_id)' in worker
    assert 'LOGGER.warning("background_job_heartbeat_failed job_id=%s", job_id)' not in worker


def test_remote_worker_waits_through_transient_unhealthy_states_and_checks_heartbeat():
    activate = _read("deployment/second-instance/activate-worker.sh")

    assert "for _ in $(seq 1 120)" in activate
    assert "python -m scripts.check_worker_heartbeat" in activate
    assert '"${STATUS}" == "unhealthy"' not in activate
    assert '"${STATUS}" == "missing"' in activate


def test_staging_refreshes_proxy_and_never_runs_old_code_on_the_migrated_test_database():
    update = _read("deployment/update-staging-from-github.sh")

    staging_recreation = update.index("--force-recreate staging")
    proxy_restart = update.index("restart proxy", staging_recreation)
    public_ready = update.index("PUBLIC_READY_URL", proxy_restart)
    deployed_marker = update.index('echo "${TARGET_COMMIT}" > "${DEPLOYED_FILE}"', public_ready)

    assert staging_recreation < proxy_restart < public_ready < deployed_marker
    assert "for _ in $(seq 1 120)" in update
    assert '"environment":"staging"' in update
    assert 'docker tag "${ROLLBACK_IMAGE}" "${CANDIDATE_IMAGE}"' not in update
    assert "não houve downgrade automático do banco de teste" in update
