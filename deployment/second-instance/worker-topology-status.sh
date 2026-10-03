#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
COMMIT_FILE="${PROJECT_DIR}/.git/investment-production-commit"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"

cd "${PROJECT_DIR}"
# shellcheck disable=SC1090
source "${LOCATION_LIB}"
load_worker_location_config "${LOCATION_FILE}" false
COMMIT="$(cat "${COMMIT_FILE}" 2>/dev/null || true)"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit de produção inválido."; exit 1; }

LOCAL_CONTAINER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -aq worker)"
LOCAL_RUNNING="false"
LOCAL_RESTART="ausente"
if [[ -n "${LOCAL_CONTAINER_ID}" ]] && docker inspect "${LOCAL_CONTAINER_ID}" >/dev/null 2>&1; then
  LOCAL_RUNNING="$(docker inspect --format '{{.State.Running}}' "${LOCAL_CONTAINER_ID}")"
  LOCAL_RESTART="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "${LOCAL_CONTAINER_ID}")"
fi

if [[ "${FDI_WORKER_LOCATION}" == "local" ]]; then
  [[ "${LOCAL_RUNNING}" == "true" && "${LOCAL_RESTART}" == "unless-stopped" ]] || {
    echo "Topologia inválida: o worker local deve estar ativo e protegido por reinício automático."
    exit 1
  }
  EXPECTED_NODE="primary-worker"
  EXPECTED_ENVIRONMENT="production"
else
  [[ "${LOCAL_RUNNING}" == "false" && "${LOCAL_RESTART}" == "no" ]] || {
    echo "Topologia inválida: o worker local deve estar parado e sem reinício automático."
    exit 1
  }
  EXPECTED_NODE="${FDI_REMOTE_WORKER_NODE_ID}"
  EXPECTED_ENVIRONMENT="production-worker"
fi

docker compose -f "${COMPOSE_FILE}" exec -T app \
  python /app/deployment/second-instance/verify-worker-coordination.py \
    --expected-node "${EXPECTED_NODE}" \
    --expected-environment "${EXPECTED_ENVIRONMENT}" \
    --expected-commit "${COMMIT}"
echo "Topologia confirmada: localização=${FDI_WORKER_LOCATION}, nó=${EXPECTED_NODE}, commit=${COMMIT}."

