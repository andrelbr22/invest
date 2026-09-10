#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/deployment/second-instance/docker-compose.worker.yml"
ENV_FILE="${PROJECT_DIR}/deployment/second-instance/worker.env"
cd "${PROJECT_DIR}"
COMMIT="${1:-$(git rev-parse HEAD)}"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit inválido."; exit 1; }
git fetch --quiet origin main
git merge --ff-only "${COMMIT}"
FDI_COORDINATOR_ENABLED=false FDI_RELEASE_COMMIT="${COMMIT}" \
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" build worker
# A preparação não inicia um segundo consumidor. Ela apenas comprova que a
# imagem aprovada acessa o banco privado e as fontes externas.
FDI_COORDINATOR_ENABLED=false FDI_RELEASE_COMMIT="${COMMIT}" \
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" run --rm --no-deps worker \
  python -c 'from sqlalchemy import text; from investment_engine.infrastructure.db.session import get_session_factory; s=get_session_factory()(); print(s.execute(text("SELECT 1")).scalar_one()); s.close()'
echo "Worker remoto preparado em espera; nenhum consumidor adicional foi iniciado."
