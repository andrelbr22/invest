#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_DIR}/docker-compose.oracle-web.yml}"

cd "${PROJECT_DIR}"

# Validation is deliberately separate from reload.  A malformed candidate
# must never replace the live routing configuration or trigger a restart.
if ! docker compose -f "${COMPOSE_FILE}" exec -T proxy \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  echo "A configuração do proxy é inválida; o proxy em execução foi preservado." >&2
  exit 1
fi

if docker compose -f "${COMPOSE_FILE}" exec -T proxy \
  caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
  echo "Proxy recarregado sem interrupção."
  exit 0
fi

# Fallback only for an unavailable Caddy admin endpoint, and only after the
# exact mounted configuration has passed caddy validate above.
echo "A recarga sem interrupção falhou; aplicando o fallback validado." >&2
docker compose -f "${COMPOSE_FILE}" restart proxy
echo "Proxy reiniciado pelo fallback seguro."
