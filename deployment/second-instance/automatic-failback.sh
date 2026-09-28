#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"
STATE_FILE="/var/tmp/formacao-investidor-worker-failback.state"
LOCK_FILE="/tmp/formacao-investidor-worker-failback.lock"

exec 9>"${LOCK_FILE}"
flock -n 9 || exit 0
cd "${PROJECT_DIR}"
# shellcheck disable=SC1090
source "${LOCATION_LIB}"
load_worker_location_config "${LOCATION_FILE}" false

# Opt-in explícito: instalar o timer não habilita uma troca automática.
if [[ "${FDI_AUTO_FAILBACK_ENABLED:-false}" != "true" ]]; then
  rm -f "${STATE_FILE}"
  echo "Failback automático desativado; nenhuma alteração foi feita."
  exit 0
fi
[[ "${FDI_WORKER_LOCATION}" == "remote" ]] || { rm -f "${STATE_FILE}"; exit 0; }
COMMIT="$(cat "${PROJECT_DIR}/.git/investment-production-commit" 2>/dev/null || true)"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit de produção inválido."; exit 1; }

if docker compose -f "${COMPOSE_FILE}" exec -T app \
  python /app/deployment/second-instance/verify-worker-coordination.py \
    --expected-node "${FDI_REMOTE_WORKER_NODE_ID}" \
    --expected-environment production-worker \
    --expected-commit "${COMMIT}" >/dev/null 2>&1; then
  rm -f "${STATE_FILE}"
  exit 0
fi

MISSES="$(( $(cat "${STATE_FILE}" 2>/dev/null || echo 0) + 1 ))"
printf '%s\n' "${MISSES}" > "${STATE_FILE}"
THRESHOLD="${FDI_AUTO_FAILBACK_FAILURE_THRESHOLD:-3}"
[[ "${THRESHOLD}" =~ ^[3-9][0-9]*$ ]] || { echo "O limiar automático deve ser no mínimo 3."; exit 1; }
if (( MISSES < THRESHOLD )); then
  echo "VM2 sem confirmação (${MISSES}/${THRESHOLD}); aguardando novas observações."
  exit 0
fi

echo "VM2 falhou em ${MISSES} verificações consecutivas; iniciando somente o retorno seguro para a VM1."
bash "${PROJECT_DIR}/deployment/second-instance/failback-worker.sh"
rm -f "${STATE_FILE}"
# Este guardião nunca executa cutover ou retorno automático à VM2.
