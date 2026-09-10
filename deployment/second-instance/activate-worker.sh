#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/deployment/second-instance/docker-compose.worker.yml"
ENV_FILE="${PROJECT_DIR}/deployment/second-instance/worker.env"
cd "${PROJECT_DIR}"
COMMIT="${1:?Informe o commit aprovado do staging}"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit inválido."; exit 1; }
git fetch --quiet origin main
git merge --ff-only "${COMMIT}"
[[ "$(git rev-parse HEAD)" == "${COMMIT}" ]] || { echo "A VM2 não alcançou o commit aprovado."; exit 1; }
FDI_COORDINATOR_ENABLED=true FDI_RELEASE_COMMIT="${COMMIT}" \
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" build worker
FDI_COORDINATOR_ENABLED=true FDI_RELEASE_COMMIT="${COMMIT}" \
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --force-recreate worker
CONTAINER_ID="$(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps -q worker)"
for _ in $(seq 1 36); do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${CONTAINER_ID}" 2>/dev/null || echo missing)"
  [[ "${STATUS}" == "healthy" ]] && { echo "Worker remoto ativo no commit ${COMMIT}."; exit 0; }
  [[ "${STATUS}" == "unhealthy" || "${STATUS}" == "missing" ]] && break
  sleep 5
done
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" logs --tail=100 worker || true
echo "O worker remoto não ficou saudável."
exit 1
