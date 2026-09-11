from __future__ import annotations

from pathlib import Path

from investment_engine.core.jobs import worker as worker_module
from investment_engine.core.jobs.worker import BackgroundWorker


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _service_block(compose: str, service: str, next_service: str | None) -> str:
    start = compose.index(f"  {service}:\n")
    if next_service is None:
        return compose[start:]
    return compose[start:compose.index(f"  {next_service}:\n", start + 1)]


def test_primary_runtime_prioritizes_the_site_and_bounds_auxiliary_services():
    compose = _read("docker-compose.oracle-web.yml")
    postgres = _service_block(compose, "postgres", "app")
    app = _service_block(compose, "app", "staging")
    staging = _service_block(compose, "staging", "worker")
    worker = _service_block(compose, "worker", "proxy")
    proxy = _service_block(compose, "proxy", None)

    assert "cpu_shares: 1024" in postgres
    assert "cpu_shares: 1024" in app
    assert "cpu_shares: 128" in staging
    assert "cpu_shares: 256" in worker
    assert 'BACKGROUND_WORKER_POLL_SECONDS: "10"' in staging
    assert 'BACKGROUND_WORKER_POLL_SECONDS: "5"' in worker
    assert 'DATABASE_POOL_SIZE: "4"' in app
    assert 'DATABASE_MAX_OVERFLOW: "1"' in app
    assert 'DATABASE_POOL_SIZE: "2"' in staging
    assert 'DATABASE_MAX_OVERFLOW: "0"' in staging

    for service in (postgres, app, staging, worker, proxy):
        assert "pids_limit:" in service
        assert "driver: json-file" in service
        assert 'max-size: "10m"' in service
        assert 'max-file: "3"' in service


def test_release_scripts_quiesce_only_the_exact_legacy_stack():
    guard = _read("deployment/quiesce-legacy-stack.sh")
    update = _read("deployment/update-staging-from-github.sh")
    promote = _read("deployment/promote-staging-to-production.sh")

    assert guard.startswith("#!/usr/bin/env bash\nset -Eeuo pipefail")
    assert 'LEGACY_PROJECT="invest"' in guard
    assert 'docker-compose.oracle-micro.yml' in guard
    assert "com.docker.compose.project.working_dir" in guard
    assert "com.docker.compose.project.config_files" in guard
    assert "com.docker.compose.service" in guard
    assert 'docker ps -aq --filter "label=com.docker.compose.project=${LEGACY_PROJECT}"' in guard
    assert "docker update --restart=no" in guard
    assert "docker stop --time 30" in guard
    assert "docker rm" not in guard
    assert "docker volume" not in guard
    assert "docker compose down" not in guard

    for release_script in (update, promote):
        assert 'bash "${PROJECT_DIR}/deployment/quiesce-legacy-stack.sh"' in release_script
    assert "nice -n 10 docker compose" in update


def test_worker_does_not_scan_for_expired_leases_on_every_idle_poll(monkeypatch):
    moments = iter((100.0, 101.0, 201.0))
    monkeypatch.setattr(worker_module.time, "monotonic", lambda: next(moments))

    class Repository:
        calls = 0

        def recover_stale(self, _timeout):
            self.calls += 1

    repository = Repository()
    worker = BackgroundWorker(handlers={}, lease_timeout_seconds=300)

    assert worker._recover_stale_if_due(repository) is True
    assert worker._recover_stale_if_due(repository) is False
    assert worker._recover_stale_if_due(repository) is True
    assert repository.calls == 2
