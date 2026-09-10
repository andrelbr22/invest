#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
docker compose --env-file "${PROJECT_DIR}/deployment/second-instance/worker.env" \
  -f "${PROJECT_DIR}/deployment/second-instance/docker-compose.worker.yml" stop -t 600 worker
echo "Worker remoto parado com encerramento gracioso."
