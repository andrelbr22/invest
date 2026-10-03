#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
BASE_COMPOSE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
OVERRIDE_TEMPLATE="${PROJECT_DIR}/deployment/second-instance/primary-db.override.yml.example"
RUNTIME_FILE="${PROJECT_DIR}/deployment/runtime/primary-db.env"
LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
STATE_FILE="${PROJECT_DIR}/deployment/runtime/private-db.enabled"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"
PROMOTION_LOCK="/tmp/investment-production-promotion.lock"
WORKER_LOCK="/tmp/investment-worker-location.lock"

exec 8>"${PROMOTION_LOCK}"
flock -n 8 || { echo "Há uma promoção em andamento; o banco não foi alterado."; exit 1; }
exec 7>"${WORKER_LOCK}"
flock -n 7 || { echo "Há uma troca de worker em andamento; o banco não foi alterado."; exit 1; }

cd "${PROJECT_DIR}"
[[ -f "${RUNTIME_FILE}" ]] || { echo "Crie deployment/runtime/primary-db.env a partir do exemplo."; exit 1; }
# shellcheck disable=SC1090
source "${LOCATION_LIB}"
worker_require_regular_owned_file "${RUNTIME_FILE}" 600
# shellcheck disable=SC1090
source "${RUNTIME_FILE}"
: "${FDI_PRIVATE_DB_BIND:?Informe FDI_PRIVATE_DB_BIND}"
: "${FDI_PRIVATE_DB_VM2_IP:?Informe FDI_PRIVATE_DB_VM2_IP}"
[[ "${FDI_PRIVATE_DB_EXPOSURE_APPROVED:-false}" == "true" ]] || {
  echo "A exposição privada não foi aprovada explicitamente no arquivo runtime."; exit 1;
}
[[ "${FDI_PRIVATE_DB_NSG_RULE_CONFIRMED:-false}" == "true" ]] || {
  echo "Confirme primeiro a regra NSG TCP 5432 com origem exclusiva na VM2/32."; exit 1;
}
# worker_validate_private_ip aplica as condições Python equivalentes a
# address.is_private, address.is_loopback e address.is_unspecified.
worker_validate_private_ip "${FDI_PRIVATE_DB_BIND}"
worker_validate_private_ip "${FDI_PRIVATE_DB_VM2_IP}"
[[ "${FDI_PRIVATE_DB_BIND}" != "${FDI_PRIVATE_DB_VM2_IP}" ]] || {
  echo "Os IPs privados da VM1 e da VM2 não podem ser iguais."; exit 1;
}
load_worker_location_config "${LOCATION_FILE}" true
[[ "${FDI_WORKER_SSH_HOST}" == "${FDI_PRIVATE_DB_VM2_IP}" ]] || {
  echo "O cliente aprovado do banco deve coincidir com o IP SSH privado da VM2."; exit 1;
}
ip -o addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "${FDI_PRIVATE_DB_BIND}" || {
  echo "O IP informado não pertence a esta VM."; exit 1;
}

if [[ -e "${STATE_FILE}" ]]; then
  worker_require_regular_owned_file "${STATE_FILE}" 600
  # shellcheck disable=SC1090
  source "${STATE_FILE}"
  [[ "${FDI_PRIVATE_DB_ENABLED:-false}" == "true" && \
      "${FDI_PRIVATE_DB_ENABLED_BIND:-}" == "${FDI_PRIVATE_DB_BIND}" && \
      "${FDI_PRIVATE_DB_ENABLED_CLIENT:-}" == "${FDI_PRIVATE_DB_VM2_IP}" ]] || {
    echo "O estado privado existente diverge da configuração aprovada; feche-o antes de alterar."; exit 1;
  }
  POSTGRES_ID="$(docker compose -f "${BASE_COMPOSE}" ps -q postgres)"
  if [[ -n "${POSTGRES_ID}" ]] && \
      docker port "${POSTGRES_ID}" 5432/tcp 2>/dev/null | grep -Fxq "${FDI_PRIVATE_DB_BIND}:5432"; then
    echo "PostgreSQL privado já habilitado para a VM2 aprovada; nenhuma recriação foi feita."
    exit 0
  fi
  echo "O marcador privado existe, mas a publicação não coincide; feche e reabra de forma controlada."
  exit 1
fi

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
ss -lnt | grep -F "${FDI_PRIVATE_DB_BIND}:5432" >/dev/null || {
  echo "A porta privada não foi confirmada."; exit 1;
}
if ss -lnt | grep -E '(^|[[:space:]])(0\.0\.0\.0|\[::\]|\*):5432([[:space:]]|$)' >/dev/null; then
  echo "FALHA SEGURA: o PostgreSQL apareceu em um endereço amplo. Reverta antes de continuar."
  exit 1
fi
docker port "${POSTGRES_ID}" 5432/tcp | grep -Fxq "${FDI_PRIVATE_DB_BIND}:5432" || {
  echo "O Docker não confirmou a publicação privada exata."; exit 1;
}
python3 - "${STATE_FILE}" "${FDI_PRIVATE_DB_BIND}" "${FDI_PRIVATE_DB_VM2_IP}" <<'PY'
import os
from pathlib import Path
import sys

path = Path(sys.argv[1])
temporary = path.with_name(f".{path.name}.tmp")
temporary.write_text(
    "FDI_PRIVATE_DB_ENABLED=true\n"
    f"FDI_PRIVATE_DB_ENABLED_BIND={sys.argv[2]}\n"
    f"FDI_PRIVATE_DB_ENABLED_CLIENT={sys.argv[3]}\n",
    encoding="utf-8",
    newline="\n",
)
os.chmod(temporary, 0o600)
os.replace(temporary, path)
PY
worker_require_regular_owned_file "${STATE_FILE}" 600
echo "PostgreSQL disponível em ${FDI_PRIVATE_DB_BIND}:5432; o acesso de rede deve permanecer restrito no NSG à VM2 ${FDI_PRIVATE_DB_VM2_IP}/32."
