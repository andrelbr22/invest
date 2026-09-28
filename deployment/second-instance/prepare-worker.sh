#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
cd "${PROJECT_DIR}"
COMMIT="${1:-$(git rev-parse HEAD)}"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit inválido."; exit 1; }
bash "${PROJECT_DIR}/deployment/second-instance/sync-approved-commit.sh" "${COMMIT}"
bash "${PROJECT_DIR}/deployment/second-instance/preflight-worker-node.sh" "${COMMIT}"
echo "Worker remoto preparado em espera; nenhum consumidor adicional foi iniciado."
