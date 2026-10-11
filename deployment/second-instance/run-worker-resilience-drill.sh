#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"
RUNTIME_DIR="${PROJECT_DIR}/deployment/runtime"
MODE="${1:-}"
FINAL_LOCATION="${2:-}"
APPROVAL="${FDI_WORKER_DRILL_APPROVED:-}"

[[ "${MODE}" == "manual" || "${MODE}" == "automatic" ]] || {
  echo "Uso: FDI_WORKER_DRILL_APPROVED=V1.23.8-R2 $0 manual|automatic local|remote" >&2
  exit 2
}
[[ "${FINAL_LOCATION}" == "local" || "${FINAL_LOCATION}" == "remote" ]] || {
  echo "Informe a localização final: local ou remote." >&2
  exit 2
}
[[ "${APPROVAL}" == "V1.23.8-R2" ]] || {
  echo "O ensaio altera a localização do worker. Defina FDI_WORKER_DRILL_APPROVED=V1.23.8-R2 somente na janela aprovada." >&2
  exit 1
}

exec 7>/tmp/investment-worker-resilience-drill.lock
flock -n 7 || { echo "Outro ensaio do worker já está em andamento."; exit 1; }
cd "${PROJECT_DIR}"
# shellcheck disable=SC1090
source "${LOCATION_LIB}"
load_worker_location_config "${LOCATION_FILE}" true
[[ "${FDI_WORKER_LOCATION}" == "local" ]] || {
  echo "O ensaio deve começar com o worker confirmado na VM principal." >&2
  exit 1
}

COMMIT="$(cat "${PROJECT_DIR}/.git/investment-production-commit" 2>/dev/null || true)"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit de produção inválido."; exit 1; }
mkdir -p "${RUNTIME_DIR}"
chmod 700 "${RUNTIME_DIR}"
STAMP="$(date -u +'%Y%m%dT%H%M%SZ')"
STARTED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
LOG_FILE="${RUNTIME_DIR}/worker-drill-${MODE}-${STAMP}.log"
REPORT_FILE="${RUNTIME_DIR}/worker-drill-${MODE}-${STAMP}.json"
touch "${LOG_FILE}"
chmod 600 "${LOG_FILE}"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "DRILL_START mode=${MODE} commit=${COMMIT} final=${FINAL_LOCATION}"
bash "${PROJECT_DIR}/deployment/capture-performance-baseline.sh" production
bash "${PROJECT_DIR}/deployment/second-instance/preflight-cutover.sh"
bash "${PROJECT_DIR}/deployment/second-instance/cutover-worker.sh"
bash "${PROJECT_DIR}/deployment/second-instance/worker-topology-status.sh"
echo "REMOTE_CONFIRMED commit=${COMMIT}"

if [[ "${MODE}" == "manual" ]]; then
  bash "${PROJECT_DIR}/deployment/second-instance/failback-worker.sh"
else
  # Primeiro limpe qualquer contador antigo ainda com o opt-in normal
  # desativado. Depois pare somente o worker remoto e deixe o guardião real
  # alcançar o limiar de três observações antes de executar o failback.
  bash "${PROJECT_DIR}/deployment/second-instance/automatic-failback.sh"
  load_worker_location_config "${LOCATION_FILE}" true
  build_worker_ssh_command
  "${WORKER_SSH[@]}" \
    "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/stop-worker.sh"
  for observation in 1 2 3; do
    echo "AUTO_FAILBACK_OBSERVATION ${observation}/3"
    FDI_AUTO_FAILBACK_DRILL_APPROVED=V1.23.8-R2 \
      bash "${PROJECT_DIR}/deployment/second-instance/automatic-failback.sh"
  done
fi

bash "${PROJECT_DIR}/deployment/second-instance/worker-topology-status.sh"
echo "FAILBACK_CONFIRMED mode=${MODE} commit=${COMMIT}"

if [[ "${FINAL_LOCATION}" == "remote" ]]; then
  bash "${PROJECT_DIR}/deployment/second-instance/preflight-cutover.sh"
  bash "${PROJECT_DIR}/deployment/second-instance/cutover-worker.sh"
fi
bash "${PROJECT_DIR}/deployment/second-instance/worker-topology-status.sh"
bash "${PROJECT_DIR}/deployment/capture-performance-baseline.sh" production
FINISHED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

python3 - "${REPORT_FILE}" "${MODE}" "${FINAL_LOCATION}" "${COMMIT}" \
  "${STARTED_AT}" "${FINISHED_AT}" "${LOG_FILE}" <<'PY'
import json
import os
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = {
    "schema_version": 1,
    "mode": sys.argv[2],
    "final_location": sys.argv[3],
    "release_commit": sys.argv[4],
    "started_at": sys.argv[5],
    "finished_at": sys.argv[6],
    "log_file": sys.argv[7],
    "checks": {
        "remote_worker_confirmed": True,
        "single_scheduler_confirmed": True,
        "single_alert_monitor_confirmed": True,
        "failback_confirmed": True,
        "final_topology_confirmed": True,
    },
    "passed": True,
}
temporary = path.with_name(f".{path.name}.tmp")
temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
os.replace(temporary, path)
PY
worker_require_regular_owned_file "${REPORT_FILE}" 600
echo "FINAL_CONFIRMED location=${FINAL_LOCATION} commit=${COMMIT}"
echo "DRILL_COMPLETE report=${REPORT_FILE}"

