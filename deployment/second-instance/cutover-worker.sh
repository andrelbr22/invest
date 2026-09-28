#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
COMMIT_FILE="${PROJECT_DIR}/.git/investment-production-commit"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"

cd "${PROJECT_DIR}"
[[ -f "${LOCATION_LIB}" ]] || { echo "Biblioteca segura da VM2 ausente."; exit 1; }
# shellcheck disable=SC1090
source "${LOCATION_LIB}"
load_worker_location_config "${LOCATION_FILE}" true
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

start_and_verify_local() {
  local container_id status
  FDI_RELEASE_COMMIT="${COMMIT}" docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate worker
  container_id="$(docker compose -f "${COMPOSE_FILE}" ps -q worker)"
  for _ in $(seq 1 120); do
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_id}" 2>/dev/null || echo missing)"
    if [[ "${status}" == "healthy" ]] && verify_expected_worker primary-worker production >/dev/null 2>&1; then
      return 0
    fi
    [[ "${status}" == "missing" || "${status}" == "exited" || "${status}" == "dead" ]] && break
    sleep 5
  done
  return 1
}

"${WORKER_SSH[@]}" "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/prepare-worker.sh '${COMMIT}'"

docker compose -f "${COMPOSE_FILE}" stop -t 600 worker
if "${WORKER_SSH[@]}" "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/activate-worker.sh '${COMMIT}'" && \
  verify_expected_worker "${FDI_REMOTE_WORKER_NODE_ID}" production-worker >/dev/null; then
  sed -i 's/^FDI_WORKER_LOCATION=.*/FDI_WORKER_LOCATION=remote/' "${LOCATION_FILE}"
  echo "Worker transferido para a VM2; um único consumidor, scheduler e monitor foram confirmados."
  exit 0
fi

echo "A ativação remota falhou; executando retorno local."
"${WORKER_SSH[@]}" "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/stop-worker.sh" || true
start_and_verify_local || { echo "O retorno local não confirmou saúde e lideranças únicas."; exit 1; }
sed -i 's/^FDI_WORKER_LOCATION=.*/FDI_WORKER_LOCATION=local/' "${LOCATION_FILE}"
exit 1
