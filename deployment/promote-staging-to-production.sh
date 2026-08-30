#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/home/ubuntu/invest"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
STAGING_IMAGE="formacao-do-investidor-staging:candidate"
PRODUCTION_IMAGE="formacao-do-investidor-production:current"
ROLLBACK_IMAGE="formacao-do-investidor-production:rollback"
LOCK_FILE="/tmp/investment-production-promotion.lock"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "Outra promoção já está em andamento."
  exit 1
fi
cd "${PROJECT_DIR}"

if ! docker image inspect "${STAGING_IMAGE}" >/dev/null 2>&1; then
  echo "Não existe uma versão de teste saudável para promover."
  exit 1
fi
if [[ -f "${PROJECT_DIR}/deployment/backup-local-db.sh" ]]; then
  bash "${PROJECT_DIR}/deployment/backup-local-db.sh"
fi
if docker image inspect "${PRODUCTION_IMAGE}" >/dev/null 2>&1; then
  docker tag "${PRODUCTION_IMAGE}" "${ROLLBACK_IMAGE}"
fi

docker tag "${STAGING_IMAGE}" "${PRODUCTION_IMAGE}"
docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate app
APP_CONTAINER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -q app)"
APP_READY="false"
for _ in $(seq 1 48); do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${APP_CONTAINER_ID}" 2>/dev/null || echo missing)"
  if [[ "${STATUS}" == "healthy" ]]; then
    APP_READY="true"
    break
  fi
  if [[ "${STATUS}" == "unhealthy" || "${STATUS}" == "missing" ]]; then break; fi
  sleep 5
done

if [[ "${APP_READY}" == "true" ]]; then
  docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate worker
  WORKER_CONTAINER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -q worker)"
  for _ in $(seq 1 24); do
    STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${WORKER_CONTAINER_ID}" 2>/dev/null || echo missing)"
    if [[ "${STATUS}" == "healthy" ]]; then
      cat "${PROJECT_DIR}/.git/investment-staging-commit" > "${PROJECT_DIR}/.git/investment-production-commit"
      echo "Produção e rotinas automáticas atualizadas após aprovação manual."
      exit 0
    fi
    if [[ "${STATUS}" == "unhealthy" || "${STATUS}" == "missing" ]]; then break; fi
    sleep 5
  done
fi

docker compose -f "${COMPOSE_FILE}" logs --tail=120 app worker || true
if docker image inspect "${ROLLBACK_IMAGE}" >/dev/null 2>&1; then
  docker tag "${ROLLBACK_IMAGE}" "${PRODUCTION_IMAGE}"
  docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate app worker
fi
echo "A promoção falhou; a aplicação e o trabalhador anteriores foram restaurados."
exit 1
