from __future__ import annotations

from pathlib import Path
import runpy

import pytest


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_remote_worker_has_a_non_mutating_guided_preflight():
    preflight = read("deployment/second-instance/preflight-cutover.sh")
    remote_wait = read("deployment/second-instance/assert-worker-stopped.sh")

    assert "verify-worker-coordination.py" in preflight
    assert "prepare-worker.sh" in preflight
    assert "assert-worker-stopped.sh" in preflight
    assert "FDI_PRIVATE_DB_BIND" in preflight
    assert "0\\.0\\.0\\.0" in preflight
    assert "cutover-worker.sh" in preflight
    assert "activate-worker.sh" not in preflight
    assert "up -d" not in preflight
    assert 'RESTART_POLICY}" != "no"' in remote_wait


def test_all_worker_location_changes_share_one_exclusive_lock():
    scripts = {
        name: read(f"deployment/second-instance/{name}")
        for name in (
            "preflight-cutover.sh",
            "cutover-worker.sh",
            "failback-worker.sh",
            "automatic-failback.sh",
        )
    }
    for content in scripts.values():
        assert "/tmp/investment-worker-location.lock" in content
        assert "flock" in content
    promote = read("deployment/promote-staging-to-production.sh")
    assert "/tmp/investment-worker-location.lock" in promote
    assert "flock -w 60" in promote
    assert "FDI_WORKER_LOCATION_LOCK_HELD=true" in scripts["automatic-failback.sh"]


def test_inactive_worker_cannot_resurrect_after_daemon_restart():
    helper = read("deployment/second-instance/worker-location-lib.sh")
    activate = read("deployment/second-instance/activate-worker.sh")
    stop = read("deployment/second-instance/stop-worker.sh")
    cutover = read("deployment/second-instance/cutover-worker.sh")
    failback = read("deployment/second-instance/failback-worker.sh")
    promote = read("deployment/promote-staging-to-production.sh")

    assert "worker_set_restart_policy" in helper
    assert 'worker_set_restart_policy "${CONTAINER_ID}" unless-stopped' in activate
    assert 'worker_set_restart_policy "${CONTAINER_ID}" no' in stop
    assert 'worker_set_restart_policy "${LOCAL_WORKER_ID}" no' in cutover
    assert 'worker_set_restart_policy "${CONTAINER_ID}" unless-stopped' in failback
    assert 'worker_set_restart_policy "${LOCAL_WORKER_ID}" no' in promote
    assert 'worker_set_restart_policy "${WORKER_CONTAINER_ID}" unless-stopped' in promote
    assert stop.index('worker_set_restart_policy "${CONTAINER_ID}" no') < stop.index(
        'stop -t 600 worker'
    )


def test_location_marker_is_written_atomically_and_topology_is_provable():
    helper = read("deployment/second-instance/worker-location-lib.sh")
    topology = read("deployment/second-instance/worker-topology-status.sh")
    cutover = read("deployment/second-instance/cutover-worker.sh")
    failback = read("deployment/second-instance/failback-worker.sh")

    assert "os.replace(temporary, path)" in helper
    assert "exatamente uma chave FDI_WORKER_LOCATION" in helper
    assert "sed -i 's/^FDI_WORKER_LOCATION=" not in cutover
    assert "sed -i 's/^FDI_WORKER_LOCATION=" not in failback
    assert "verify-worker-coordination.py" in topology
    assert "LOCAL_RESTART" in topology
    assert 'EXPECTED_NODE="primary-worker"' in topology
    assert 'EXPECTED_NODE="${FDI_REMOTE_WORKER_NODE_ID}"' in topology


def test_promotion_keeps_migrations_isolated_and_parks_staging_after_success():
    promote = read("deployment/promote-staging-to-production.sh")

    migration = promote.index("run --rm --no-deps production-migration")
    start_app = promote.index("--force-recreate app")
    park_definition = promote.index("park_staging_after_promotion()")
    mark_worker = promote.index("mark_worker_promotion_complete", park_definition)
    park_call = promote.index("park_staging_after_promotion", mark_worker)
    assert migration < start_app
    assert mark_worker < park_call
    assert "FDI_KEEP_STAGING_RUNNING_AFTER_PROMOTION" in promote
    assert 'worker_set_restart_policy "${staging_id}" no' in promote
    assert 'stop -t 60 staging' in promote
    assert "post_promotion_failed" in promote
    assert "O staging não confirmou o estado estacionado" in promote


def test_same_approved_commit_reactivates_a_parked_staging():
    update = read("deployment/update-staging-from-github.sh")

    assert "ensure_staging_active()" in update
    assert 'if [[ "${TARGET_COMMIT}" == "${DEPLOYED_COMMIT}" ]]' in update
    assert 'docker update --restart=unless-stopped "${container_id}"' in update
    assert 'start staging' in update
    assert "reload-proxy.sh" in update
    assert "já estava atualizado e está ativo para homologação" in update


def test_promotion_serializes_topology_and_uses_safe_failback_on_remote_failure():
    promote = read("deployment/promote-staging-to-production.sh")

    lock = promote.index('flock -w 60 8')
    topology = promote.index("CURRENT_WORKER_COMMIT")
    benchmark = promote.index("benchmark_application_routes")
    assert lock < topology < benchmark
    assert 'assert_local_worker_runtime_state "${FDI_WORKER_LOCATION}"' in promote
    remote_branch = promote.index('if [[ "${FDI_WORKER_LOCATION}" == "remote" ]]', benchmark)
    stop_remote = promote.index("stop-worker.sh", remote_branch)
    activate_remote = promote.index("activate-worker.sh", stop_remote)
    assert stop_remote < activate_remote
    assert "REMOTE_QUIESCED=false" in promote
    assert "FDI_FAILBACK_REMOTE_MAY_BE_ACTIVE=true" in promote
    assert "failback-worker.sh" in promote


def test_promotion_rejects_invalid_worker_marker_and_records_commit_before_enqueue():
    promote = read("deployment/promote-staging-to-production.sh")

    assert 'if [[ -f "${PRODUCTION_WORKER_COMMIT_FILE}" ]]' in promote
    assert 'elif [[ -f "${PRODUCTION_COMMIT_FILE}" ]]' in promote
    assert 'if [[ ! "${CURRENT_WORKER_COMMIT}" =~ ^[0-9a-f]{40}$ ]]' in promote
    assert "marcador atual do worker está vazio ou inválido" in promote
    assert promote.count("enqueue_current_metrics_after_worker_promotion") == 4
    assert promote.count("scripts.enqueue_current_metrics_refresh") == 1

    definition_end = promote.index("verify_exact_worker()")
    release_flow = promote[definition_end:]
    cursor = 0
    for _ in range(3):
        marker = release_flow.index("mark_worker_promotion_complete", cursor)
        enqueue = release_flow.index(
            "enqueue_current_metrics_after_worker_promotion", marker,
        )
        assert marker < enqueue
        cursor = enqueue + 1

    helper_start = promote.index("enqueue_current_metrics_after_worker_promotion()")
    helper_end = promote.index("\n}\n", helper_start)
    helper = promote[helper_start:helper_end]
    assert "post_promotion_failed" in helper
    assert "\n    promotion_failed " not in helper


def test_cutover_refuses_repeating_an_already_remote_transition_and_failed_activation_stops():
    cutover = read("deployment/second-instance/cutover-worker.sh")
    activate = read("deployment/second-instance/activate-worker.sh")
    promote = read("deployment/promote-staging-to-production.sh")

    assert '[[ "${FDI_WORKER_LOCATION}" == "local" ]]' in cutover
    failure_log = activate.index("logs --tail=100 worker")
    disable_restart = activate.index(
        'worker_set_restart_policy "${CONTAINER_ID}" no', failure_log,
    )
    stop_worker = activate.index("stop -t 600 worker", disable_restart)
    assert failure_log < disable_restart < stop_worker
    assert "worker_write_location \"${WORKER_LOCATION_FILE}\" local" not in promote


def test_remote_activation_refuses_to_replace_an_existing_consumer():
    activate = read("deployment/second-instance/activate-worker.sh")
    assert "assert-worker-stopped.sh" in activate
    assert activate.index("assert-worker-stopped.sh") < activate.index("up -d --force-recreate worker")


def test_automatic_failback_is_opt_in_debounced_and_uses_protected_state():
    automatic = read("deployment/second-instance/automatic-failback.sh")
    failback = read("deployment/second-instance/failback-worker.sh")

    assert 'FDI_AUTO_FAILBACK_ENABLED:-false' in automatic
    assert "FDI_AUTO_FAILBACK_FAILURE_THRESHOLD" in automatic
    assert "worker-failback.state" in automatic
    assert "worker_require_regular_owned_file" in automatic
    assert "os.replace(temporary, path)" in automatic
    assert "MISSES < THRESHOLD" in automatic
    assert "remote_worker_inactive" in failback
    assert "FDI_FAILBACK_REMOTE_MAY_BE_ACTIVE" in failback
    assert 'worker_set_restart_policy "${CONTAINER_ID}" no' in failback


def test_private_database_publication_is_serialized_with_release_and_cutover():
    enable = read("deployment/second-instance/enable-primary-private-db.sh")
    disable = read("deployment/second-instance/disable-primary-private-db.sh")

    for content in (enable, disable):
        assert "/tmp/investment-production-promotion.lock" in content
        assert "/tmp/investment-worker-location.lock" in content
        assert "flock -n" in content
    assert "worker_require_regular_owned_file" in enable
    assert "failback-worker.sh" in disable


def test_private_database_is_explicit_scoped_recorded_and_reversible():
    enable = read("deployment/second-instance/enable-primary-private-db.sh")
    disable = read("deployment/second-instance/disable-primary-private-db.sh")
    preflight = read("deployment/second-instance/preflight-cutover.sh")
    example = read("deployment/runtime/primary-db.env.example")

    for token in (
        "FDI_PRIVATE_DB_VM2_IP",
        "FDI_PRIVATE_DB_NSG_RULE_CONFIRMED",
        "FDI_PRIVATE_DB_EXPOSURE_APPROVED",
    ):
        assert token in enable
        assert token in example
    assert 'FDI_WORKER_SSH_HOST}" == "${FDI_PRIVATE_DB_VM2_IP}' in enable
    assert "private-db.enabled" in enable
    assert "os.replace(temporary, path)" in enable
    assert "private-db.enabled" in preflight
    assert "FDI_PRIVATE_DB_ENABLED_CLIENT" in preflight
    assert "rm -f -- \"${STATE_FILE}\"" in disable
    assert "up -d --no-deps app staging worker" not in enable
    assert "up -d --no-deps app staging worker" not in disable


def test_leadership_verification_accepts_the_real_scheduler_and_alert_identities():
    namespace = runpy.run_path(str(
        ROOT / "deployment" / "second-instance" / "verify-worker-coordination.py"
    ))
    validate = namespace["validate_lease_owner"]
    worker = {
        "service_id": "worker:production:primary-worker",
        "environment": "production",
        "node_id": "primary-worker",
    }

    validate({
        "lease_name": "background-scheduler",
        "holder_id": "worker:production:primary-worker",
        "metadata_json": {"node_id": "primary-worker"},
    }, worker, "primary-worker")
    validate({
        "lease_name": "price-alert-monitor-leader",
        "holder_id": "alerts:production:primary-worker:7",
        "metadata_json": {"node_id": "primary-worker"},
    }, worker, "primary-worker")

    remote_worker = {
        "service_id": "worker:production-worker:worker-02",
        "environment": "production-worker",
        "node_id": "worker-02",
    }
    validate({
        "lease_name": "background-scheduler",
        "holder_id": "worker:production-worker:worker-02",
        "metadata_json": {"node_id": "worker-02"},
    }, remote_worker, "worker-02")
    validate({
        "lease_name": "price-alert-monitor-leader",
        "holder_id": "alerts:production-worker:worker-02:314",
        "metadata_json": {"node_id": "worker-02"},
    }, remote_worker, "worker-02")


@pytest.mark.parametrize("holder", [
    "worker:production:primary-worker",
    "alerts:production:other-node:7",
    "alerts:production:primary-worker:not-a-pid",
    "alerts:production:primary-worker:0",
    "alerts:production:primary-worker:-1",
    "alerts:production:primary-worker:",
    "alerts:production:primary-worker:7:extra",
    "alerts:production:primary-worker:٧",
])
def test_alert_leadership_verification_rejects_a_foreign_or_invalid_holder(holder):
    namespace = runpy.run_path(str(
        ROOT / "deployment" / "second-instance" / "verify-worker-coordination.py"
    ))
    validate = namespace["validate_lease_owner"]
    worker = {
        "service_id": "worker:production:primary-worker",
        "environment": "production",
        "node_id": "primary-worker",
    }
    with pytest.raises(SystemExit, match="monitor do worker esperado"):
        validate({
            "lease_name": "price-alert-monitor-leader",
            "holder_id": holder,
            "metadata_json": {"node_id": "primary-worker"},
        }, worker, "primary-worker")


def test_scheduler_leadership_verification_requires_the_canonical_worker_id():
    namespace = runpy.run_path(str(
        ROOT / "deployment" / "second-instance" / "verify-worker-coordination.py"
    ))
    validate = namespace["validate_lease_owner"]
    worker = {
        "service_id": "worker:production:primary-worker",
        "environment": "production",
        "node_id": "primary-worker",
    }
    with pytest.raises(SystemExit, match="outro worker"):
        validate({
            "lease_name": "background-scheduler",
            "holder_id": "worker:production:other-worker",
            "metadata_json": {"node_id": "primary-worker"},
        }, worker, "primary-worker")


def test_leadership_verification_rejects_metadata_from_another_node():
    namespace = runpy.run_path(str(
        ROOT / "deployment" / "second-instance" / "verify-worker-coordination.py"
    ))
    validate = namespace["validate_lease_owner"]
    worker = {
        "service_id": "worker:production:primary-worker",
        "environment": "production",
        "node_id": "primary-worker",
    }
    with pytest.raises(SystemExit, match="outro nó"):
        validate({
            "lease_name": "background-scheduler",
            "holder_id": "worker:production:primary-worker",
            "metadata_json": {"node_id": "remote-worker"},
        }, worker, "primary-worker")


def test_local_promotion_retries_the_final_coordination_check():
    promote = read("deployment/promote-staging-to-production.sh")
    assert "wait_exact_worker()" in promote
    assert 'wait_exact_worker primary-worker production "${TARGET_COMMIT}" 24' in promote
    assert "Preserve the actionable diagnostic on the final attempt" in promote


def test_worker_verifier_requires_the_canonical_service_identity():
    verifier = read("deployment/second-instance/verify-worker-coordination.py")
    assert 'expected_service_id = f"worker:{expected_environment}:{expected_node}"' in verifier
    assert 'worker["service_id"]' in verifier
    assert "process_id.isascii()" in verifier


def _valid_worker_topology():
    worker = {
        "service_id": "worker:production:primary-worker",
        "node_id": "primary-worker",
        "environment": "production",
        "commit_sha": "a" * 40,
        "scheduler_leader": True,
        "alert_monitor_leader": True,
    }
    leases = [
        {
            "lease_name": "background-scheduler",
            "holder_id": worker["service_id"],
            "metadata_json": {"node_id": "primary-worker"},
        },
        {
            "lease_name": "price-alert-monitor-leader",
            "holder_id": "alerts:production:primary-worker:7",
            "metadata_json": {"node_id": "primary-worker"},
        },
    ]
    return worker, leases


def test_complete_worker_topology_accepts_only_the_canonical_logical_worker():
    namespace = runpy.run_path(str(
        ROOT / "deployment" / "second-instance" / "verify-worker-coordination.py"
    ))
    validate = namespace["validate_worker_topology"]
    worker, leases = _valid_worker_topology()
    result = validate(
        [worker], leases,
        expected_node="primary-worker",
        expected_environment="production",
        expected_commit="a" * 40,
    )
    assert result is worker


@pytest.mark.parametrize("mutation,match", [
    (lambda worker, leases: worker.update(service_id="worker:production:alias"), "service_id"),
    (lambda worker, leases: worker.update(commit_sha="b" * 40), "commit_sha"),
    (lambda worker, leases: worker.update(scheduler_leader=False), "duas lideranças"),
    (lambda worker, leases: leases.pop(), "leases ativas"),
    (lambda worker, leases: leases.append(dict(leases[0])), "leases ativas"),
])
def test_complete_worker_topology_fails_closed(mutation, match):
    namespace = runpy.run_path(str(
        ROOT / "deployment" / "second-instance" / "verify-worker-coordination.py"
    ))
    validate = namespace["validate_worker_topology"]
    worker, leases = _valid_worker_topology()
    mutation(worker, leases)
    with pytest.raises(SystemExit, match=match):
        validate(
            [worker], leases,
            expected_node="primary-worker",
            expected_environment="production",
            expected_commit="a" * 40,
        )


@pytest.mark.parametrize("workers", [[], [{}, {}]])
def test_complete_worker_topology_rejects_zero_or_multiple_workers(workers):
    namespace = runpy.run_path(str(
        ROOT / "deployment" / "second-instance" / "verify-worker-coordination.py"
    ))
    validate = namespace["validate_worker_topology"]
    _, leases = _valid_worker_topology()
    with pytest.raises(SystemExit, match="exatamente um worker"):
        validate(
            workers, leases,
            expected_node="primary-worker",
            expected_environment="production",
            expected_commit="a" * 40,
        )

