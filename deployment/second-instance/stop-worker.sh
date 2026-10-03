#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"
# shellcheck disable=SC1090
source "${LOCATION_LIB}"
CONTAINER_ID="$(docker compose --env-file "${PROJECT_DIR}/deployment/second-instance/worker.env" \
  -f "${PROJECT_DIR}/deployment/second-instance/docker-compose.worker.yml" ps -aq worker)"
# Desabilite o reinício antes de pedir a parada. Assim, nem uma reinicialização
# do daemon no meio do encerramento pode ressuscitar o consumidor remoto.
worker_set_restart_policy "${CONTAINER_ID}" no
docker compose --env-file "${PROJECT_DIR}/deployment/second-instance/worker.env" \
  -f "${PROJECT_DIR}/deployment/second-instance/docker-compose.worker.yml" stop -t 600 worker
if [[ -n "${CONTAINER_ID}" && "$(docker inspect --format '{{.State.Running}}' "${CONTAINER_ID}")" != "false" ]]; then
  echo "O contêiner remoto ainda está em execução."
  exit 1
fi
echo "Worker remoto parado com encerramento gracioso."
