#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
COMMIT_FILE="${PROJECT_DIR}/.git/investment-production-commit"

cd "${PROJECT_DIR}"
[[ -f "${LOCATION_FILE}" ]] || { echo "Crie ${LOCATION_FILE} a partir do exemplo."; exit 1; }
source "${LOCATION_FILE}"
: "${FDI_WORKER_SSH_HOST:?Informe o IP privado da VM2}"
: "${FDI_WORKER_SSH_USER:?Informe o usuário SSH da VM2}"
: "${FDI_WORKER_SSH_KEY:?Informe a chave SSH da VM1 para a VM2}"
: "${FDI_WORKER_PROJECT_DIR:?Informe o diretório do projeto na VM2}"
COMMIT="$(cat "${COMMIT_FILE}" 2>/dev/null || git rev-parse HEAD)"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit de produção inválido."; exit 1; }

REMOTE="${FDI_WORKER_SSH_USER}@${FDI_WORKER_SSH_HOST}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "${FDI_WORKER_SSH_KEY}" "${REMOTE}")
"${SSH[@]}" "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/prepare-worker.sh '${COMMIT}'"

docker compose -f "${COMPOSE_FILE}" stop -t 600 worker
if "${SSH[@]}" "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/activate-worker.sh '${COMMIT}'"; then
  sed -i 's/^FDI_WORKER_LOCATION=.*/FDI_WORKER_LOCATION=remote/' "${LOCATION_FILE}"
  echo "Worker transferido para a VM2. Scheduler e monitor possuem líder único no PostgreSQL."
  exit 0
fi

echo "A ativação remota falhou; executando retorno local."
"${SSH[@]}" "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/stop-worker.sh" || true
FDI_RELEASE_COMMIT="${COMMIT}" docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate worker
sed -i 's/^FDI_WORKER_LOCATION=.*/FDI_WORKER_LOCATION=local/' "${LOCATION_FILE}"
exit 1
