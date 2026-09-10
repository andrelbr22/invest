#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
BASE_COMPOSE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
OVERRIDE_TEMPLATE="${PROJECT_DIR}/deployment/second-instance/primary-db.override.yml.example"
RUNTIME_FILE="${PROJECT_DIR}/deployment/runtime/primary-db.env"

cd "${PROJECT_DIR}"
[[ -f "${RUNTIME_FILE}" ]] || { echo "Crie deployment/runtime/primary-db.env a partir do exemplo."; exit 1; }
source "${RUNTIME_FILE}"
: "${FDI_PRIVATE_DB_BIND:?Informe FDI_PRIVATE_DB_BIND}"
python3 - "${FDI_PRIVATE_DB_BIND}" <<'PY'
import ipaddress, sys
address = ipaddress.ip_address(sys.argv[1])
if not address.is_private or address.is_loopback or address.is_unspecified:
    raise SystemExit("Informe somente o IP privado da VNIC da VM1.")
PY
ip -o addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "${FDI_PRIVATE_DB_BIND}" || {
  echo "O IP informado não pertence a esta VM."; exit 1;
}

bash "${PROJECT_DIR}/deployment/backup-local-db.sh"
FDI_PRIVATE_DB_BIND="${FDI_PRIVATE_DB_BIND}" docker compose \
  -f "${BASE_COMPOSE}" -f "${OVERRIDE_TEMPLATE}" \
  up -d --no-deps --force-recreate postgres

POSTGRES_ID="$(docker compose -f "${BASE_COMPOSE}" ps -q postgres)"
for _ in $(seq 1 24); do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${POSTGRES_ID}" 2>/dev/null || echo missing)"
  [[ "${STATUS}" == "healthy" ]] && break
  [[ "${STATUS}" == "unhealthy" || "${STATUS}" == "missing" ]] && { echo "PostgreSQL não ficou saudável."; exit 1; }
  sleep 5
done
[[ "$(docker inspect --format '{{.State.Health.Status}}' "${POSTGRES_ID}")" == "healthy" ]] || exit 1
docker compose -f "${BASE_COMPOSE}" up -d --no-deps app staging worker
ss -lnt | grep -F "${FDI_PRIVATE_DB_BIND}:5432" >/dev/null || {
  echo "A porta privada não foi confirmada."; exit 1;
}
if ss -lnt | grep -E '(^|[[:space:]])(0\.0\.0\.0|\[::\]|\*):5432([[:space:]]|$)' >/dev/null; then
  echo "FALHA SEGURA: o PostgreSQL apareceu em um endereço amplo. Reverta antes de continuar."
  exit 1
fi
echo "PostgreSQL disponível somente em ${FDI_PRIVATE_DB_BIND}:5432 e na rede Docker interna."
