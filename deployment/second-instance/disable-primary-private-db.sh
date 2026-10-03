#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
STATE_FILE="${PROJECT_DIR}/deployment/runtime/private-db.enabled"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"
PROMOTION_LOCK="/tmp/investment-production-promotion.lock"
WORKER_LOCK="/tmp/investment-worker-location.lock"

exec 8>"${PROMOTION_LOCK}"
flock -n 8 || { echo "Há uma promoção em andamento; o banco não foi alterado."; exit 1; }
exec 7>"${WORKER_LOCK}"
flock -n 7 || { echo "Há uma troca de worker em andamento; o banco não foi alterado."; exit 1; }
cd "${PROJECT_DIR}"

# shellcheck disable=SC1090
source "${LOCATION_LIB}"
load_worker_location_config "${LOCATION_FILE}" false
[[ "${FDI_WORKER_LOCATION}" == "local" ]] || {
  echo "Retorne o worker com failback-worker.sh antes de fechar o acesso privado ao banco."
  exit 1
}

bash "${PROJECT_DIR}/deployment/backup-local-db.sh"
docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate postgres
POSTGRES_ID="$(docker compose -f "${COMPOSE_FILE}" ps -q postgres)"
for _ in $(seq 1 24); do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${POSTGRES_ID}" 2>/dev/null || echo missing)"
  [[ "${STATUS}" == "healthy" ]] && break
  [[ "${STATUS}" == "unhealthy" || "${STATUS}" == "missing" ]] && { echo "PostgreSQL não ficou saudável."; exit 1; }
  sleep 5
done
[[ "$(docker inspect --format '{{.State.Health.Status}}' "${POSTGRES_ID}")" == "healthy" ]] || exit 1
if docker port "${POSTGRES_ID}" 5432/tcp 2>/dev/null | grep -q .; then
  echo "A porta 5432 ainda aparece no host; confirme manualmente antes de considerar o fechamento concluído."
  exit 1
fi
rm -f -- "${STATE_FILE}"
echo "A publicação privada do PostgreSQL foi removida do host."
