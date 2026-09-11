#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/home/ubuntu/invest"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
STAGING_IMAGE="formacao-do-investidor-staging:candidate"
PRODUCTION_IMAGE="formacao-do-investidor-production:current"
ROLLBACK_IMAGE="formacao-do-investidor-production:rollback"
LOCK_FILE="/tmp/investment-production-promotion.lock"
WORKER_LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "Outra promoção já está em andamento."
  exit 1
fi
cd "${PROJECT_DIR}"
if [[ -f "${PROJECT_DIR}/deployment/quiesce-legacy-stack.sh" ]]; then
  bash "${PROJECT_DIR}/deployment/quiesce-legacy-stack.sh"
fi
TARGET_COMMIT="$(cat "${PROJECT_DIR}/.git/investment-staging-commit" 2>/dev/null || true)"
ROLLBACK_COMMIT="$(cat "${PROJECT_DIR}/.git/investment-production-commit" 2>/dev/null || true)"
if [[ ! "${TARGET_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "O commit aprovado do ambiente de teste não foi identificado."
  exit 1
fi
FDI_WORKER_LOCATION="local"
if [[ -f "${WORKER_LOCATION_FILE}" ]]; then
  # Arquivo local, fora do Git, preenchido somente pelo administrador da VM1.
  source "${WORKER_LOCATION_FILE}"
fi
if [[ "${FDI_WORKER_LOCATION}" != "local" && "${FDI_WORKER_LOCATION}" != "remote" ]]; then
  echo "FDI_WORKER_LOCATION deve ser local ou remote."
  exit 1
fi

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
FDI_RELEASE_COMMIT="${TARGET_COMMIT}" docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate app
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
  if [[ "${FDI_WORKER_LOCATION}" == "remote" ]]; then
    : "${FDI_WORKER_SSH_HOST:?Informe FDI_WORKER_SSH_HOST no arquivo runtime}"
    : "${FDI_WORKER_SSH_USER:?Informe FDI_WORKER_SSH_USER no arquivo runtime}"
    : "${FDI_WORKER_SSH_KEY:?Informe FDI_WORKER_SSH_KEY no arquivo runtime}"
    : "${FDI_WORKER_PROJECT_DIR:?Informe FDI_WORKER_PROJECT_DIR no arquivo runtime}"
    docker compose -f "${COMPOSE_FILE}" stop worker >/dev/null 2>&1 || true
    if ssh -o BatchMode=yes -o ConnectTimeout=15 -i "${FDI_WORKER_SSH_KEY}" \
      "${FDI_WORKER_SSH_USER}@${FDI_WORKER_SSH_HOST}" \
      "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/activate-worker.sh '${TARGET_COMMIT}'"; then
      cat "${PROJECT_DIR}/.git/investment-staging-commit" > "${PROJECT_DIR}/.git/investment-production-commit"
      echo "Produção atualizada e worker remoto confirmado no commit aprovado."
      exit 0
    fi
    echo "O worker remoto não confirmou a ativação; iniciando o retorno local."
    ssh -o BatchMode=yes -o ConnectTimeout=15 -i "${FDI_WORKER_SSH_KEY}" \
      "${FDI_WORKER_SSH_USER}@${FDI_WORKER_SSH_HOST}" \
      "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/stop-worker.sh" >/dev/null 2>&1 || true
    sed -i 's/^FDI_WORKER_LOCATION=.*/FDI_WORKER_LOCATION=local/' "${WORKER_LOCATION_FILE}"
    FDI_WORKER_LOCATION="local"
  fi
  FDI_RELEASE_COMMIT="${TARGET_COMMIT}" docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate worker
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
  if [[ ! "${ROLLBACK_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
    ROLLBACK_COMMIT="unknown"
  fi
  FDI_RELEASE_COMMIT="${ROLLBACK_COMMIT}" docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate app
  if [[ "${FDI_WORKER_LOCATION}" == "local" ]]; then
    FDI_RELEASE_COMMIT="${ROLLBACK_COMMIT}" docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate worker
  fi
fi
echo "A promoção falhou; a aplicação e o trabalhador anteriores foram restaurados."
exit 1
