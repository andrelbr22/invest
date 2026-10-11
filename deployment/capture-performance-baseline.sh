#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
RUNTIME_DIR="${PROJECT_DIR}/deployment/runtime"
ENVIRONMENT="${1:-production}"

[[ "${ENVIRONMENT}" == "production" || "${ENVIRONMENT}" == "staging" ]] || {
  echo "Uso: $0 [production|staging]" >&2
  exit 2
}
SERVICE="app"
[[ "${ENVIRONMENT}" == "staging" ]] && SERVICE="staging"
mkdir -p "${RUNTIME_DIR}"
chmod 700 "${RUNTIME_DIR}"
STAMP="$(date -u +'%Y%m%dT%H%M%SZ')"
REPORT="${RUNTIME_DIR}/database-performance-${ENVIRONMENT}-${STAMP}.json"
HOST_REPORT="${RUNTIME_DIR}/host-performance-${ENVIRONMENT}-${STAMP}.txt"
TMP_REPORT="$(mktemp "${RUNTIME_DIR}/.database-performance.XXXXXX")"
trap 'rm -f -- "${TMP_REPORT}"' EXIT

cd "${PROJECT_DIR}"
docker compose -f "${COMPOSE_FILE}" exec -T "${SERVICE}" \
  python -m scripts.capture_database_performance_baseline > "${TMP_REPORT}"
python3 -m json.tool "${TMP_REPORT}" >/dev/null
chmod 600 "${TMP_REPORT}"
mv "${TMP_REPORT}" "${REPORT}"

{
  echo "captured_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "environment=${ENVIRONMENT}"
  echo "--- free -h ---"
  free -h
  echo "--- df -h / ---"
  df -h /
  echo "--- docker stats --no-stream ---"
  docker stats --no-stream
} > "${HOST_REPORT}"
chmod 600 "${HOST_REPORT}"

echo "Linha de base do banco: ${REPORT}"
echo "Linha de base da máquina: ${HOST_REPORT}"
echo "Nenhuma configuração, contador, índice ou dado foi alterado."
