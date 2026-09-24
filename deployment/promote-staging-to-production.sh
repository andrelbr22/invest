#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/home/ubuntu/invest"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
STAGING_IMAGE="formacao-do-investidor-staging:candidate"
PRODUCTION_IMAGE="formacao-do-investidor-production:current"
ROLLBACK_IMAGE="formacao-do-investidor-production:rollback"
LOCK_FILE="/tmp/investment-production-promotion.lock"
WORKER_LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
PRODUCTION_COMMIT_FILE="${PROJECT_DIR}/.git/investment-production-commit"
PRODUCTION_WORKER_COMMIT_FILE="${PROJECT_DIR}/.git/investment-production-worker-commit"
PUBLIC_READY_URL="https://formacaodoinvestidor.com.br/ready"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "Outra promoção já está em andamento."
  exit 1
fi

cd "${PROJECT_DIR}"

log_release_services() {
  docker compose -f "${COMPOSE_FILE}" ps app worker proxy || true
  docker compose -f "${COMPOSE_FILE}" logs --tail=120 app worker proxy || true
}

promotion_failed() {
  local reason="${1:?Informe o motivo da falha}"
  echo "${reason}"
  log_release_services
  echo "Não foi feito downgrade automático: o banco pode já conter migrações da nova versão."
  echo "A imagem anterior permanece preservada em ${ROLLBACK_IMAGE} para recuperação manual compatível com o banco."
  exit 1
}

wait_container_healthy() {
  local container_id="${1:?Informe o contêiner}"
  local attempts="${2:-60}"
  local status
  for _ in $(seq 1 "${attempts}"); do
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_id}" 2>/dev/null || echo missing)"
    [[ "${status}" == "healthy" ]] && return 0
    [[ "${status}" == "missing" || "${status}" == "exited" || "${status}" == "dead" ]] && return 1
    sleep 5
  done
  return 1
}

wait_public_ready() {
  local payload
  for _ in $(seq 1 36); do
    payload="$(curl --fail --silent --show-error --max-time 15 "${PUBLIC_READY_URL}" 2>/dev/null || true)"
    if [[ "${payload}" == *'"status":"ready"'* && "${payload}" == *'"environment":"production"'* ]]; then
      return 0
    fi
    sleep 5
  done
  return 1
}

wait_local_worker_ready() {
  local container_id="${1:?Informe o contêiner do worker}"
  local status reported_commit
  for _ in $(seq 1 72); do
    status="$(docker inspect --format '{{.State.Status}}' "${container_id}" 2>/dev/null || echo missing)"
    [[ "${status}" == "missing" || "${status}" == "exited" || "${status}" == "dead" ]] && return 1
    reported_commit="$(
      docker compose -f "${COMPOSE_FILE}" exec -T postgres \
        psql -U investment -d investment_engine -At \
        -c "SELECT commit_sha FROM service_heartbeats WHERE service_id = 'worker:production:primary-worker' AND status = 'running' AND scheduler_leader IS TRUE AND alert_monitor_leader IS TRUE AND started_at >= '${WORKER_LAUNCH_AT}'::timestamptz AND last_seen_at >= '${WORKER_LAUNCH_AT}'::timestamptz AND last_seen_at >= CURRENT_TIMESTAMP - INTERVAL '180 seconds' ORDER BY last_seen_at DESC LIMIT 1;" \
        2>/dev/null | tr -d '[:space:]' || true
    )"
    if [[ "${reported_commit}" == "${TARGET_COMMIT}" ]]; then
      return 0
    fi
    sleep 5
  done
  return 1
}

mark_app_promotion_complete() {
  printf '%s\n' "${TARGET_COMMIT}" > "${PRODUCTION_COMMIT_FILE}"
}

mark_worker_promotion_complete() {
  printf '%s\n' "${TARGET_COMMIT}" > "${PRODUCTION_WORKER_COMMIT_FILE}"
}

if [[ -f "${PROJECT_DIR}/deployment/quiesce-legacy-stack.sh" ]]; then
  bash "${PROJECT_DIR}/deployment/quiesce-legacy-stack.sh"
fi

TARGET_COMMIT="$(cat "${PROJECT_DIR}/.git/investment-staging-commit" 2>/dev/null || true)"
if [[ ! "${TARGET_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "O commit aprovado do ambiente de teste não foi identificado."
  exit 1
fi

FDI_WORKER_LOCATION="local"
if [[ -f "${WORKER_LOCATION_FILE}" ]]; then
  # Arquivo local, fora do Git, preenchido somente pelo administrador da VM1.
  source "${WORKER_LOCATION_FILE}"
fi
if [[ "${FDI_WORKER_LOCATION}" != "local" && "${FDI_WORKER_LOCATION}" != "remote" ]]; then
  echo "FDI_WORKER_LOCATION deve ser local ou remote."
  exit 1
fi

if ! docker image inspect "${STAGING_IMAGE}" >/dev/null 2>&1; then
  echo "Não existe uma versão de teste saudável para promover."
  exit 1
fi

# O candidato deve cumprir as metas de resposta antes de qualquer backup,
# troca de tag ou recriação de produção. O comando retorna código 2 se ao
# menos uma rota ultrapassar a meta de p95 e também falha em qualquer HTTP
# diferente de 200. Assim, uma regressão de desempenho não toca a produção.
echo "Validando o desempenho da versão aprovada no ambiente de teste..."
if ! docker compose -f "${COMPOSE_FILE}" exec -T staging \
  python -m scripts.benchmark_application_routes --samples 20 --warmup 2; then
  echo "Promoção interrompida: o candidato não cumpriu as metas de desempenho."
  exit 1
fi

if [[ -f "${PROJECT_DIR}/deployment/backup-local-db.sh" ]]; then
  bash "${PROJECT_DIR}/deployment/backup-local-db.sh"
fi
if docker image inspect "${PRODUCTION_IMAGE}" >/dev/null 2>&1; then
  # Apenas uma cópia de segurança. Ela nunca é relançada automaticamente
  # depois que uma migração pode ter avançado o banco.
  docker tag "${PRODUCTION_IMAGE}" "${ROLLBACK_IMAGE}"
fi

docker tag "${STAGING_IMAGE}" "${PRODUCTION_IMAGE}"
if ! FDI_RELEASE_COMMIT="${TARGET_COMMIT}" docker compose -f "${COMPOSE_FILE}" \
  up -d --no-deps --force-recreate app; then
  promotion_failed "A nova aplicação não pôde ser iniciada."
fi
APP_CONTAINER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -q app)"
if ! wait_container_healthy "${APP_CONTAINER_ID}" 120; then
  promotion_failed "A nova aplicação não confirmou saúde dentro do prazo."
fi

# O Caddy resolve o nome do contêiner para um IP. Depois da recriação do
# app, reiniciá-lo evita que continue encaminhando ao endereço antigo.
if ! docker compose -f "${COMPOSE_FILE}" restart proxy; then
  promotion_failed "O proxy não reiniciou após a troca da aplicação."
fi
if ! wait_public_ready; then
  promotion_failed "A produção não respondeu em /ready depois da troca."
fi
mark_app_promotion_complete

if [[ "${FDI_WORKER_LOCATION}" == "remote" ]]; then
  : "${FDI_WORKER_SSH_HOST:?Informe FDI_WORKER_SSH_HOST no arquivo runtime}"
  : "${FDI_WORKER_SSH_USER:?Informe FDI_WORKER_SSH_USER no arquivo runtime}"
  : "${FDI_WORKER_SSH_KEY:?Informe FDI_WORKER_SSH_KEY no arquivo runtime}"
  : "${FDI_WORKER_PROJECT_DIR:?Informe FDI_WORKER_PROJECT_DIR no arquivo runtime}"
  docker compose -f "${COMPOSE_FILE}" stop worker >/dev/null 2>&1 || true
  if ssh -o BatchMode=yes -o ConnectTimeout=15 -i "${FDI_WORKER_SSH_KEY}" \
    "${FDI_WORKER_SSH_USER}@${FDI_WORKER_SSH_HOST}" \
    "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/activate-worker.sh '${TARGET_COMMIT}'"; then
    mark_worker_promotion_complete
    echo "Produção atualizada e worker remoto confirmado no commit aprovado."
    exit 0
  fi
  echo "O worker remoto não confirmou a ativação; iniciando o retorno local."
  ssh -o BatchMode=yes -o ConnectTimeout=15 -i "${FDI_WORKER_SSH_KEY}" \
    "${FDI_WORKER_SSH_USER}@${FDI_WORKER_SSH_HOST}" \
    "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/stop-worker.sh" >/dev/null 2>&1 || true
  sed -i 's/^FDI_WORKER_LOCATION=.*/FDI_WORKER_LOCATION=local/' "${WORKER_LOCATION_FILE}"
  FDI_WORKER_LOCATION="local"
fi

WORKER_LAUNCH_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
if ! FDI_RELEASE_COMMIT="${TARGET_COMMIT}" docker compose -f "${COMPOSE_FILE}" \
  up -d --no-deps --force-recreate worker; then
  promotion_failed "O worker local da nova versão não pôde ser iniciado. A aplicação web permanece online."
fi
WORKER_CONTAINER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -q worker)"
if ! wait_local_worker_ready "${WORKER_CONTAINER_ID}"; then
  promotion_failed "O worker local não publicou um heartbeat fresco no commit aprovado. A aplicação web permanece online."
fi

mark_worker_promotion_complete
echo "Produção, proxy e rotinas automáticas atualizados após aprovação manual."
