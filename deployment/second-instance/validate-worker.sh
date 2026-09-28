#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
cd "${PROJECT_DIR}"
COMMIT="$(git rev-parse HEAD)"
bash "${PROJECT_DIR}/deployment/second-instance/preflight-worker-node.sh" "${COMMIT}"
echo "Worker remoto validado no commit exato ${COMMIT}."
