#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
docker compose --env-file "${PROJECT_DIR}/deployment/second-instance/worker.env" \
  -f "${PROJECT_DIR}/deployment/second-instance/docker-compose.worker.yml" stop -t 600 worker
CONTAINER_ID="$(docker compose --env-file "${PROJECT_DIR}/deployment/second-instance/worker.env" \
  -f "${PROJECT_DIR}/deployment/second-instance/docker-compose.worker.yml" ps -aq worker)"
if [[ -n "${CONTAINER_ID}" && "$(docker inspect --format '{{.State.Running}}' "${CONTAINER_ID}")" != "false" ]]; then
  echo "O contêiner remoto ainda está em execução."
  exit 1
fi
echo "Worker remoto parado com encerramento gracioso."
