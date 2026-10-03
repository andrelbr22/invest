#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/deployment/second-instance/docker-compose.worker.yml"
ENV_FILE="${PROJECT_DIR}/deployment/second-instance/worker.env"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"
cd "${PROJECT_DIR}"
COMMIT="${1:?Informe o commit aprovado do staging}"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit inválido."; exit 1; }
bash "${PROJECT_DIR}/deployment/second-instance/sync-approved-commit.sh" "${COMMIT}"
[[ "$(git rev-parse HEAD)" == "${COMMIT}" ]] || { echo "A VM2 não alcançou o commit aprovado."; exit 1; }
bash "${PROJECT_DIR}/deployment/second-instance/preflight-worker-node.sh" "${COMMIT}"
# A ativação nunca substitui silenciosamente outro consumidor remoto. O
# cutover deve preparar um contêiner parado, sem política de autorreinício.
bash "${PROJECT_DIR}/deployment/second-instance/assert-worker-stopped.sh"
# shellcheck disable=SC1090
source "${LOCATION_LIB}"
# worker.env é privado, pertence ao usuário atual e foi validado pelo
# preflight. Carregá-lo aqui mantém o identificador verificado igual ao Compose.
# shellcheck disable=SC1090
source "${ENV_FILE}"
FDI_COORDINATOR_ENABLED=true FDI_RELEASE_COMMIT="${COMMIT}" \
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --force-recreate worker
CONTAINER_ID="$(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps -q worker)"
worker_set_restart_policy "${CONTAINER_ID}" unless-stopped
for _ in $(seq 1 120); do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${CONTAINER_ID}" 2>/dev/null || echo missing)"
  if [[ "${STATUS}" == "healthy" ]] && \
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T worker \
      python -m scripts.check_worker_heartbeat >/dev/null 2>&1 && \
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T worker \
      python /app/deployment/second-instance/verify-worker-coordination.py \
        --expected-node "${FDI_WORKER_NODE_ID:-worker-02}" \
        --expected-environment production-worker \
        --expected-commit "${COMMIT}" >/dev/null 2>&1; then
    echo "Worker remoto ativo no commit ${COMMIT}."
    exit 0
  fi
  [[ "${STATUS}" == "missing" || "${STATUS}" == "exited" || "${STATUS}" == "dead" ]] && break
  sleep 5
done
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" logs --tail=100 worker || true
worker_set_restart_policy "${CONTAINER_ID}" no
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" stop -t 600 worker >/dev/null 2>&1 || true
echo "O worker remoto não ficou saudável."
exit 1
