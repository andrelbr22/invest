#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/home/ubuntu/invest"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
DEPLOYED_FILE="${PROJECT_DIR}/.git/investment-staging-commit"
FAILED_FILE="${PROJECT_DIR}/.git/investment-staging-failed-commit"
LOCK_FILE="/tmp/investment-staging-update.lock"
CANDIDATE_IMAGE="formacao-do-investidor-staging:candidate"
ROLLBACK_IMAGE="formacao-do-investidor-staging:rollback"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "Outra atualização de teste já está em andamento."
  exit 0
fi

cd "${PROJECT_DIR}"
echo "Consultando atualizações para o ambiente de teste..."
git fetch --quiet origin main
CURRENT_COMMIT="$(git rev-parse HEAD)"
TARGET_COMMIT="$(git rev-parse origin/main)"
DEPLOYED_COMMIT="$(cat "${DEPLOYED_FILE}" 2>/dev/null || true)"
FAILED_COMMIT="$(cat "${FAILED_FILE}" 2>/dev/null || true)"

if [[ "${TARGET_COMMIT}" == "${DEPLOYED_COMMIT}" ]]; then
  echo "O ambiente de teste já está atualizado."
  exit 0
fi
if [[ "${TARGET_COMMIT}" == "${FAILED_COMMIT}" ]]; then
  echo "Este commit já falhou no teste; aguardando uma nova versão."
  exit 0
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Atualização cancelada: existem alterações locais em arquivos controlados."
  exit 1
fi

git merge --ff-only "${TARGET_COMMIT}"
if docker image inspect "${CANDIDATE_IMAGE}" >/dev/null 2>&1; then
  docker tag "${CANDIDATE_IMAGE}" "${ROLLBACK_IMAGE}"
fi

echo "Construindo a versão de teste..."
if ! COMPOSE_PARALLEL_LIMIT=1 docker compose -f "${COMPOSE_FILE}" build staging; then
  echo "${TARGET_COMMIT}" > "${FAILED_FILE}"
  exit 1
fi
"${PROJECT_DIR}/deployment/refresh-staging-db.sh"
docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate staging

CONTAINER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -q staging)"
for _ in $(seq 1 48); do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${CONTAINER_ID}" 2>/dev/null || echo missing)"
  if [[ "${STATUS}" == "healthy" ]]; then
    echo "${TARGET_COMMIT}" > "${DEPLOYED_FILE}"
    rm -f "${FAILED_FILE}"
    echo "Teste atualizado: https://formacaodoinvestidor.com.br/testefdi/"
    exit 0
  fi
  if [[ "${STATUS}" == "unhealthy" || "${STATUS}" == "missing" ]]; then break; fi
  sleep 5
done

docker compose -f "${COMPOSE_FILE}" logs --tail=120 staging || true
if docker image inspect "${ROLLBACK_IMAGE}" >/dev/null 2>&1; then
  docker tag "${ROLLBACK_IMAGE}" "${CANDIDATE_IMAGE}"
  docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate staging
fi
echo "${TARGET_COMMIT}" > "${FAILED_FILE}"
echo "A versão nova falhou; o ambiente oficial não foi alterado."
exit 1
