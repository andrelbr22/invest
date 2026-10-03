#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"
STATE_FILE="${PROJECT_DIR}/deployment/runtime/worker-failback.state"
LOCK_FILE="/tmp/investment-worker-location.lock"

exec 9>"${LOCK_FILE}"
flock -n 9 || exit 0
cd "${PROJECT_DIR}"
# shellcheck disable=SC1090
source "${LOCATION_LIB}"
load_worker_location_config "${LOCATION_FILE}" false

clear_failure_state() {
  # rm remove apenas a entrada indicada (inclusive se alguém a trocou por um
  # symlink); nunca segue o link para outro arquivo.
  rm -f -- "${STATE_FILE}"
}

read_failure_state() {
  local value
  if [[ ! -e "${STATE_FILE}" ]]; then
    echo 0
    return 0
  fi
  worker_require_regular_owned_file "${STATE_FILE}" 600
  value="$(tr -d '[:space:]' < "${STATE_FILE}")"
  [[ "${value}" =~ ^[0-9]+$ ]] || worker_location_error "estado do failback inválido."
  echo "${value}"
}

write_failure_state() {
  local value="${1:?Informe o contador}"
  python3 - "${STATE_FILE}" "${value}" <<'PY'
import os
from pathlib import Path
import sys

path = Path(sys.argv[1])
temporary = path.with_name(f".{path.name}.tmp")
temporary.write_text(f"{int(sys.argv[2])}\n", encoding="utf-8", newline="\n")
os.chmod(temporary, 0o600)
os.replace(temporary, path)
PY
}

# Opt-in explícito: instalar o timer não habilita uma troca automática.
if [[ "${FDI_AUTO_FAILBACK_ENABLED:-false}" != "true" ]]; then
  clear_failure_state
  echo "Failback automático desativado; nenhuma alteração foi feita."
  exit 0
fi
[[ "${FDI_WORKER_LOCATION}" == "remote" ]] || { clear_failure_state; exit 0; }
COMMIT="$(cat "${PROJECT_DIR}/.git/investment-production-commit" 2>/dev/null || true)"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit de produção inválido."; exit 1; }
THRESHOLD="${FDI_AUTO_FAILBACK_FAILURE_THRESHOLD:-3}"
[[ "${THRESHOLD}" =~ ^([3-9]|[1-9][0-9]+)$ ]] || { echo "O limiar automático deve ser no mínimo 3."; exit 1; }

if docker compose -f "${COMPOSE_FILE}" exec -T app \
  python /app/deployment/second-instance/verify-worker-coordination.py \
    --expected-node "${FDI_REMOTE_WORKER_NODE_ID}" \
    --expected-environment production-worker \
    --expected-commit "${COMMIT}" >/dev/null 2>&1; then
  clear_failure_state
  exit 0
fi

CURRENT_MISSES="$(read_failure_state)"
MISSES="$(( CURRENT_MISSES + 1 ))"
write_failure_state "${MISSES}"
if (( MISSES < THRESHOLD )); then
  echo "VM2 sem confirmação (${MISSES}/${THRESHOLD}); aguardando novas observações."
  exit 0
fi

echo "VM2 falhou em ${MISSES} verificações consecutivas; iniciando somente o retorno seguro para a VM1."
FDI_WORKER_LOCATION_LOCK_HELD=true \
  bash "${PROJECT_DIR}/deployment/second-instance/failback-worker.sh"
clear_failure_state
# Este guardião nunca executa cutover ou retorno automático à VM2.
