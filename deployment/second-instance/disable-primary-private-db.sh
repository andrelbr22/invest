#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
cd "${PROJECT_DIR}"

bash "${PROJECT_DIR}/deployment/backup-local-db.sh"
docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate postgres
POSTGRES_ID="$(docker compose -f "${COMPOSE_FILE}" ps -q postgres)"
for _ in $(seq 1 24); do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${POSTGRES_ID}" 2>/dev/null || echo missing)"
  [[ "${STATUS}" == "healthy" ]] && break
  [[ "${STATUS}" == "unhealthy" || "${STATUS}" == "missing" ]] && { echo "PostgreSQL não ficou saudável."; exit 1; }
  sleep 5
done
[[ "$(docker inspect --format '{{.State.Health.Status}}' "${POSTGRES_ID}")" == "healthy" ]] || exit 1
docker compose -f "${COMPOSE_FILE}" up -d --no-deps app staging worker
if ss -lnt | grep -E '(^|[[:space:]])[^[:space:]]*:5432([[:space:]]|$)' >/dev/null; then
  echo "A porta 5432 ainda aparece no host; confirme manualmente antes de considerar o fechamento concluído."
  exit 1
fi
echo "A publicação privada do PostgreSQL foi removida do host."
