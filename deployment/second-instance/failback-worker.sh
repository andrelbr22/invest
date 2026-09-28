#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
COMMIT_FILE="${PROJECT_DIR}/.git/investment-production-commit"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"
cd "${PROJECT_DIR}"

# shellcheck disable=SC1090
source "${LOCATION_LIB}"
load_worker_location_config "${LOCATION_FILE}" false
COMMIT="$(cat "${COMMIT_FILE}" 2>/dev/null || git rev-parse HEAD)"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit de produção inválido."; exit 1; }

remote_worker_inactive() {
  local result
  result="$(docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    psql -U investment -d investment_engine -At -v ON_ERROR_STOP=1 -c "
      SELECT CASE WHEN
        NOT EXISTS (
          SELECT 1 FROM service_heartbeats
          WHERE role = 'worker' AND node_id = '${FDI_REMOTE_WORKER_NODE_ID}'
            AND status = 'running'
            AND last_seen_at >= CURRENT_TIMESTAMP - INTERVAL '210 seconds'
        )
        AND NOT EXISTS (
          SELECT 1 FROM runtime_leases
          WHERE lease_name IN ('background-scheduler','price-alert-monitor-leader')
            AND expires_at > CURRENT_TIMESTAMP
            AND metadata_json->>'node_id' = '${FDI_REMOTE_WORKER_NODE_ID}'
        )
      THEN 'inactive' ELSE 'active' END;" 2>/dev/null | tr -d '[:space:]' || true)"
  [[ "${result}" == "inactive" ]]
}

verify_local_worker() {
  docker compose -f "${COMPOSE_FILE}" exec -T worker \
    python /app/deployment/second-instance/verify-worker-coordination.py \
      --expected-node primary-worker \
      --expected-environment production \
      --expected-commit "${COMMIT}"
}

if [[ "${FDI_WORKER_LOCATION:-local}" == "remote" ]]; then
  build_worker_ssh_command
  "${WORKER_SSH[@]}" "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/stop-worker.sh" \
    || echo "SSH da VM2 indisponível; aguardando expiração comprovada de heartbeat e leases."
  # Nunca inicie o consumidor local enquanto o remoto ainda estiver fresco.
  # Se somente o SSH caiu, a VM2 continua trabalhando e esta verificação
  # interrompe o retorno em vez de criar dois consumidores.
  for _ in $(seq 1 60); do
    remote_worker_inactive && break
    sleep 5
  done
  remote_worker_inactive || {
    echo "Retorno interrompido: o worker remoto ou suas lideranças ainda estão ativos."
    exit 1
  }
fi
FDI_RELEASE_COMMIT="${COMMIT}" docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate worker
CONTAINER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -q worker)"
for _ in $(seq 1 120); do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${CONTAINER_ID}" 2>/dev/null || echo missing)"
  if [[ "${STATUS}" == "healthy" ]] && verify_local_worker >/dev/null 2>&1; then
    sed -i 's/^FDI_WORKER_LOCATION=.*/FDI_WORKER_LOCATION=local/' "${LOCATION_FILE}"
    echo "Retorno concluído: worker, scheduler e monitor únicos confirmados na VM principal."
    exit 0
  fi
  [[ "${STATUS}" == "missing" || "${STATUS}" == "exited" || "${STATUS}" == "dead" ]] && break
  sleep 5
done
docker compose -f "${COMPOSE_FILE}" logs --tail=120 worker || true
echo "O worker local não ficou saudável."
exit 1
