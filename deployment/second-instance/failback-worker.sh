#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
COMMIT_FILE="${PROJECT_DIR}/.git/investment-production-commit"
cd "${PROJECT_DIR}"
[[ -f "${LOCATION_FILE}" ]] || { echo "Arquivo de localização do worker ausente."; exit 1; }
source "${LOCATION_FILE}"
COMMIT="$(cat "${COMMIT_FILE}" 2>/dev/null || git rev-parse HEAD)"

if [[ "${FDI_WORKER_LOCATION:-local}" == "remote" ]]; then
  ssh -o BatchMode=yes -o ConnectTimeout=15 -i "${FDI_WORKER_SSH_KEY}" \
    "${FDI_WORKER_SSH_USER}@${FDI_WORKER_SSH_HOST}" \
    "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/stop-worker.sh"
fi
FDI_RELEASE_COMMIT="${COMMIT}" docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate worker
CONTAINER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -q worker)"
for _ in $(seq 1 36); do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${CONTAINER_ID}" 2>/dev/null || echo missing)"
  if [[ "${STATUS}" == "healthy" ]]; then
    sed -i 's/^FDI_WORKER_LOCATION=.*/FDI_WORKER_LOCATION=local/' "${LOCATION_FILE}"
    echo "Retorno concluído: worker ativo novamente na VM principal."
    exit 0
  fi
  [[ "${STATUS}" == "unhealthy" || "${STATUS}" == "missing" ]] && break
  sleep 5
done
docker compose -f "${COMPOSE_FILE}" logs --tail=120 worker || true
echo "O worker local não ficou saudável."
exit 1
