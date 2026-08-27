#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/home/ubuntu/invest"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
SOURCE_DB="investment_engine"
STAGING_DB="investment_engine_staging"

cd "${PROJECT_DIR}"
docker compose -f "${COMPOSE_FILE}" stop staging >/dev/null 2>&1 || true
docker compose -f "${COMPOSE_FILE}" exec -T postgres dropdb --if-exists --force -U investment "${STAGING_DB}"
docker compose -f "${COMPOSE_FILE}" exec -T postgres createdb -U investment "${STAGING_DB}"
docker compose -f "${COMPOSE_FILE}" exec -T postgres pg_dump -U investment -d "${SOURCE_DB}" --no-owner --no-privileges | \
  docker compose -f "${COMPOSE_FILE}" exec -T postgres psql -v ON_ERROR_STOP=1 -U investment -d "${STAGING_DB}" >/dev/null
echo "Banco de teste atualizado a partir de uma cópia isolada da produção."
