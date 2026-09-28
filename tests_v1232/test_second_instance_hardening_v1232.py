from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_remote_worker_preflight_requires_clean_exact_approved_commit_and_private_db():
    sync = read("deployment/second-instance/sync-approved-commit.sh")
    preflight = read("deployment/second-instance/preflight-worker-node.sh")

    assert "git status --porcelain --untracked-files=normal" in sync
    assert "git merge-base --is-ancestor" in sync
    assert 'git switch --detach --quiet "${COMMIT}"' in sync
    assert '[[ "$(git rev-parse HEAD)" == "${COMMIT}" ]]' in preflight
    assert "worker.env deve pertencer ao usuário atual e usar modo 0600" in preflight
    assert "grupo 10001 e modo 0640" in preflight
    assert 'unquote(parsed.username or "") != "investment_worker"' in preflight
    assert "address.is_private" in preflight
    assert "inet_server_addr" in preflight
    assert "has_database_privilege" in preflight
    assert "has_schema_privilege" in preflight
    assert "ScriptDirectory.from_config" in preflight
    assert "revision != head" in preflight
    assert "FDI_COORDINATOR_ENABLED=false" in preflight


def test_ssh_path_is_private_pinned_and_uses_strict_file_permissions():
    helper = read("deployment/second-instance/worker-location-lib.sh")
    location = read("deployment/runtime/worker-location.env.example")
    promote = read("deployment/promote-staging-to-production.sh")

    assert "worker_validate_private_ip" in helper
    assert 'worker_require_regular_owned_file "${FDI_WORKER_SSH_KEY}" 600' in helper
    assert 'worker_require_regular_owned_file "${FDI_WORKER_KNOWN_HOSTS}" 600' in helper
    assert "StrictHostKeyChecking=yes" in helper
    assert "IdentitiesOnly=yes" in helper
    assert "UserKnownHostsFile=" in helper
    assert "ssh-keygen -F" in helper
    assert "FDI_WORKER_KNOWN_HOSTS=" in location
    assert "FDI_REMOTE_WORKER_NODE_ID=worker-02" in location
    assert 'build_worker_ssh_command' in promote
    assert '"${WORKER_SSH[@]}"' in promote
    assert "ssh -o BatchMode=yes -o ConnectTimeout=15 -i" not in promote


def test_cutover_and_failback_prove_single_worker_and_both_leaders():
    verifier = read("deployment/second-instance/verify-worker-coordination.py")
    activate = read("deployment/second-instance/activate-worker.sh")
    cutover = read("deployment/second-instance/cutover-worker.sh")
    failback = read("deployment/second-instance/failback-worker.sh")

    assert "len(workers) != 1" in verifier
    assert "scheduler_leader" in verifier and "alert_monitor_leader" in verifier
    assert 'LEADER_LEASES = {"background-scheduler", "price-alert-monitor-leader"}' in verifier
    assert "metadata.get(\"node_id\")" in verifier
    assert "verify-worker-coordination.py" in activate
    assert "verify_expected_worker" in cutover
    assert "start_and_verify_local" in cutover
    assert cutover.index("stop -t 600 worker") < cutover.index("activate-worker.sh")
    assert "remote_worker_inactive" in failback
    assert "Retorno interrompido" in failback
    assert failback.index("remote_worker_inactive ||") < failback.index("up -d --no-deps --force-recreate worker")
    assert "verify_local_worker" in failback


def test_automatic_failback_is_opt_in_conservative_and_never_auto_returns_remote():
    guard = read("deployment/second-instance/automatic-failback.sh")
    location = read("deployment/runtime/worker-location.env.example")
    timer = read("deployment/investment-worker-failback-guard.timer.example")

    assert "FDI_AUTO_FAILBACK_ENABLED=false" in location
    assert "FDI_AUTO_FAILBACK_FAILURE_THRESHOLD=3" in location
    assert '"${FDI_AUTO_FAILBACK_ENABLED:-false}" != "true"' in guard
    assert "flock -n 9" in guard
    assert "MISSES < THRESHOLD" in guard
    assert "verify-worker-coordination.py" in guard
    assert "failback-worker.sh" in guard
    assert "cutover-worker.sh" not in guard
    assert "OnUnitActiveSec=2min" in timer


def test_remote_container_runs_non_root_read_only_without_linux_capabilities():
    compose = read("deployment/second-instance/docker-compose.worker.yml")

    assert 'user: "10001:10001"' in compose
    assert "read_only: true" in compose
    assert "privileged: false" in compose
    assert "cap_drop:\n      - ALL" in compose
    assert "no-new-privileges:true" in compose
    assert "/tmp:rw,noexec,nosuid,nodev" in compose
    assert "ports:" not in compose
    assert "pids_limit:" in compose and "nofile:" in compose


def test_worker_database_role_has_no_administrative_or_ddl_privileges():
    role = read("deployment/second-instance/create-worker-db-role.sh")
    preflight = read("deployment/second-instance/preflight-worker-node.sh")

    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS" in role
    assert "CONNECTION LIMIT 8" in role
    assert "REVOKE ALL PRIVILEGES ON DATABASE investment_engine FROM investment_worker" in role
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in role
    assert "GRANT CONNECT ON DATABASE investment_engine TO investment_worker" in role
    assert "GRANT USAGE ON SCHEMA public TO investment_worker" in role
    # O worker precisa escrever snapshots/fila/alertas, mas não recebe DDL,
    # ownership, criação de função, credenciais ou conteúdo administrativo.
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE" in role
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES" not in role
    assert "email_login_codes" in role
    assert "user_access_policies" in role
    assert "REVOKE ALL PRIVILEGES ON TABLE" in role
    assert "REVOKE ALL PRIVILEGES ON TABLES FROM investment_worker" in role
    assert "GRANT ALL" not in role
    assert "ALTER TABLE" not in role
    assert "has_table_privilege(current_user, 'email_login_codes', 'SELECT')" in preflight
    assert "tabelas privadas fora do seu escopo" in preflight


def test_no_cloud_mutation_is_hidden_in_the_release_scripts():
    scripts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "deployment" / "second-instance").glob("*.sh")
    )
    assert "oci compute instance launch" not in scripts
    assert "oci network" not in scripts
    assert "terraform apply" not in scripts
