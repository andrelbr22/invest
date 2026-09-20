#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/home/ubuntu/invest"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
BACKUP_DIR="${PROJECT_DIR}/backups/postgres"
BUCKET_NAME="${OCI_BACKUP_BUCKET:-formacao-investidor-backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/investment_engine_${TIMESTAMP}.sql.gz"
TEMP_FILE="${BACKUP_FILE}.tmp"

umask 077
mkdir -p "${BACKUP_DIR}"
trap 'rm -f "${TEMP_FILE}"' EXIT

docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  pg_dump -U investment -d investment_engine --no-owner --no-privileges | \
  gzip -9 > "${TEMP_FILE}"

test -s "${TEMP_FILE}"
mv "${TEMP_FILE}" "${BACKUP_FILE}"
trap - EXIT
echo "Backup local criado: ${BACKUP_FILE}"

OCI_BIN="$(command -v oci 2>/dev/null || true)"
if [[ -z "${OCI_BIN}" && -x "/home/ubuntu/bin/oci" ]]; then
  OCI_BIN="/home/ubuntu/bin/oci"
fi
if [[ -n "${OCI_BIN}" ]]; then
  "${OCI_BIN}" os object put \
    --auth instance_principal \
    --bucket-name "${BUCKET_NAME}" \
    --file "${BACKUP_FILE}" \
    --name "postgres/$(basename "${BACKUP_FILE}")" \
    --force >/dev/null
  echo "Backup enviado ao Object Storage: ${BUCKET_NAME}/postgres/$(basename "${BACKUP_FILE}")"
fi
