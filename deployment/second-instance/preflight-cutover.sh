#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
PRIMARY_DB_FILE="${PROJECT_DIR}/deployment/runtime/primary-db.env"
PRIVATE_DB_STATE_FILE="${PROJECT_DIR}/deployment/runtime/private-db.enabled"
COMMIT_FILE="${PROJECT_DIR}/.git/investment-production-commit"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"
LOCK_FILE="/tmp/investment-worker-location.lock"

exec 8>"${LOCK_FILE}"
if ! flock -n 8; then
  echo "Outra troca de localização do worker já está em andamento."
  exit 1
fi

cd "${PROJECT_DIR}"
# shellcheck disable=SC1090
source "${LOCATION_LIB}"
load_worker_location_config "${LOCATION_FILE}" true
[[ "${FDI_WORKER_LOCATION}" == "local" ]] || {
  echo "O worker já está registrado como remoto; use worker-topology-status.sh para validar."
  exit 1
}
build_worker_ssh_command

worker_require_regular_owned_file "${PRIMARY_DB_FILE}" 600
# shellcheck disable=SC1090
source "${PRIMARY_DB_FILE}"
: "${FDI_PRIVATE_DB_BIND:?Informe FDI_PRIVATE_DB_BIND}"
: "${FDI_PRIVATE_DB_VM2_IP:?Informe FDI_PRIVATE_DB_VM2_IP}"
worker_validate_private_ip "${FDI_PRIVATE_DB_BIND}"
worker_validate_private_ip "${FDI_PRIVATE_DB_VM2_IP}"
[[ "${FDI_PRIVATE_DB_VM2_IP}" == "${FDI_WORKER_SSH_HOST}" ]] || {
  echo "O IP liberado para o banco diverge do IP SSH privado da VM2."
  exit 1
}
worker_require_regular_owned_file "${PRIVATE_DB_STATE_FILE}" 600
# shellcheck disable=SC1090
source "${PRIVATE_DB_STATE_FILE}"
[[ "${FDI_PRIVATE_DB_ENABLED:-false}" == "true" && \
    "${FDI_PRIVATE_DB_ENABLED_BIND:-}" == "${FDI_PRIVATE_DB_BIND}" && \
    "${FDI_PRIVATE_DB_ENABLED_CLIENT:-}" == "${FDI_PRIVATE_DB_VM2_IP}" ]] || {
  echo "A publicação privada aprovada não foi registrada pelo procedimento controlado."
  exit 1
}
ip -o addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "${FDI_PRIVATE_DB_BIND}" || {
  echo "O IP privado do banco não pertence à VM principal."
  exit 1
}
ss -lnt | grep -F "${FDI_PRIVATE_DB_BIND}:5432" >/dev/null || {
  echo "O PostgreSQL ainda não está publicado no IP privado aprovado."
  exit 1
}
if ss -lnt | grep -E '(^|[[:space:]])(0\.0\.0\.0|\[::\]|\*):5432([[:space:]]|$)' >/dev/null; then
  echo "FALHA SEGURA: a porta 5432 está publicada em endereço amplo."
  exit 1
fi

COMMIT="$(cat "${COMMIT_FILE}" 2>/dev/null || true)"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit de produção inválido."; exit 1; }
docker compose -f "${COMPOSE_FILE}" exec -T app \
  python /app/deployment/second-instance/verify-worker-coordination.py \
    --expected-node primary-worker \
    --expected-environment production \
    --expected-commit "${COMMIT}" >/dev/null

"${WORKER_SSH[@]}" \
  "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/prepare-worker.sh '${COMMIT}' && ./deployment/second-instance/assert-worker-stopped.sh"

echo "Pré-validação concluída sem iniciar outro consumidor."
echo "Commit aprovado: ${COMMIT}"
echo "Próximo passo controlado: ./deployment/second-instance/cutover-worker.sh"

