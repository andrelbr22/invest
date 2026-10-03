#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
COMMIT_FILE="${PROJECT_DIR}/.git/investment-production-commit"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"
LOCK_FILE="/tmp/investment-worker-location.lock"

exec 8>"${LOCK_FILE}"
if ! flock -n 8; then
  echo "Outra troca de localização do worker já está em andamento."
  exit 1
fi

cd "${PROJECT_DIR}"
[[ -f "${LOCATION_LIB}" ]] || { echo "Biblioteca segura da VM2 ausente."; exit 1; }
# shellcheck disable=SC1090
source "${LOCATION_LIB}"
load_worker_location_config "${LOCATION_FILE}" true
[[ "${FDI_WORKER_LOCATION}" == "local" ]] || {
  echo "O worker já está registrado como remoto; valide a topologia em vez de repetir o corte."
  exit 1
}
build_worker_ssh_command
COMMIT="$(cat "${COMMIT_FILE}" 2>/dev/null || git rev-parse HEAD)"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit de produção inválido."; exit 1; }

verify_expected_worker() {
  local expected_node="${1:?Informe o nó}"
  local expected_environment="${2:?Informe o ambiente}"
  docker compose -f "${COMPOSE_FILE}" exec -T app \
    python /app/deployment/second-instance/verify-worker-coordination.py \
      --expected-node "${expected_node}" \
      --expected-environment "${expected_environment}" \
      --expected-commit "${COMMIT}"
}

"${WORKER_SSH[@]}" "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/prepare-worker.sh '${COMMIT}'"

LOCAL_WORKER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -q worker)"
worker_set_restart_policy "${LOCAL_WORKER_ID}" no
docker compose -f "${COMPOSE_FILE}" stop -t 600 worker
if "${WORKER_SSH[@]}" "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/activate-worker.sh '${COMMIT}'" && \
  verify_expected_worker "${FDI_REMOTE_WORKER_NODE_ID}" production-worker >/dev/null; then
  # O helper persiste atomicamente a linha FDI_WORKER_LOCATION=remote.
  worker_write_location "${LOCATION_FILE}" remote
  echo "Worker transferido para a VM2; um único consumidor, scheduler e monitor foram confirmados."
  exit 0
fi

echo "A ativação remota falhou; executando retorno local."
# Mesmo que o marcador ainda seja local, a ativação pode ter iniciado um
# contêiner remoto antes de falhar. O failback centralizado exige a parada via
# SSH por stop-worker.sh ou a expiração comprovada de heartbeat e leases
# antes de iniciar a VM1. Ao concluir, ele persiste FDI_WORKER_LOCATION=local.
FDI_WORKER_LOCATION_LOCK_HELD=true \
FDI_FAILBACK_REMOTE_MAY_BE_ACTIVE=true \
  bash "${PROJECT_DIR}/deployment/second-instance/failback-worker.sh" || {
    echo "O retorno local não confirmou saúde e lideranças únicas."
    exit 1
  }
exit 1
