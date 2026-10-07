#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/home/ubuntu/invest"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
BACKUP_DIR="${PROJECT_DIR}/backups/postgres"
BUCKET_NAME="${OCI_BACKUP_BUCKET:-formacao-investidor-backups}"
LOCAL_BACKUP_KEEP_COUNT="${LOCAL_BACKUP_KEEP_COUNT:-3}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/investment_engine_${TIMESTAMP}.sql.gz"
TEMP_FILE="${BACKUP_FILE}.tmp"

if ! [[ "${LOCAL_BACKUP_KEEP_COUNT}" =~ ^[0-9]+$ ]] || \
   (( LOCAL_BACKUP_KEEP_COUNT < 1 || LOCAL_BACKUP_KEEP_COUNT > 30 )); then
  echo "LOCAL_BACKUP_KEEP_COUNT deve estar entre 1 e 30." >&2
  exit 1
fi

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

  # A limpeza só ocorre depois de o OCI confirmar o upload. Os caminhos são
  # enumerados pelo find dentro do diretório fixo e validados novamente antes
  # da remoção; nenhum volume, banco ou objeto remoto é alterado.
  mapfile -t LOCAL_BACKUPS < <(
    find "${BACKUP_DIR}" -maxdepth 1 -type f \
      -name 'investment_engine_*.sql.gz' \
      -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-
  )
  REMOVED=0
  PRESERVED=0
  for CANDIDATE in "${LOCAL_BACKUPS[@]:LOCAL_BACKUP_KEEP_COUNT}"; do
    RESOLVED="$(readlink -f -- "${CANDIDATE}")"
    case "${RESOLVED}" in
      "${BACKUP_DIR}"/investment_engine_*.sql.gz)
        REMOTE_NAME="postgres/$(basename "${RESOLVED}")"
        if "${OCI_BIN}" os object head \
          --auth instance_principal \
          --bucket-name "${BUCKET_NAME}" \
          --name "${REMOTE_NAME}" >/dev/null 2>&1; then
          rm -- "${RESOLVED}"
          REMOVED=$((REMOVED + 1))
        else
          echo "Backup local preservado por falta de confirmação remota: ${RESOLVED}"
          PRESERVED=$((PRESERVED + 1))
        fi
        ;;
      *)
        echo "Limpeza recusada para caminho inesperado: ${RESOLVED}" >&2
        exit 1
        ;;
    esac
  done
  echo "Retenção local concluída: ${LOCAL_BACKUP_KEEP_COUNT} recente(s) mantido(s), ${REMOVED} antigo(s) removido(s), ${PRESERVED} sem cópia remota preservado(s)."
fi
