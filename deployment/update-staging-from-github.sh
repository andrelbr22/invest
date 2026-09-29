#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/home/ubuntu/invest"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
DEPLOYED_FILE="${PROJECT_DIR}/.git/investment-staging-commit"
FAILED_FILE="${PROJECT_DIR}/.git/investment-staging-failed-commit"
LOCK_FILE="/tmp/investment-staging-update.lock"
CANDIDATE_IMAGE="formacao-do-investidor-staging:candidate"
ROLLBACK_IMAGE="formacao-do-investidor-staging:rollback"
PUBLIC_READY_URL="https://formacaodoinvestidor.com.br/testefdi/ready"
STAGING_MIGRATION_ATTEMPTS=2
STAGING_MIGRATION_RETRY_SECONDS=5

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "Outra atualização de teste já está em andamento."
  exit 0
fi

cd "${PROJECT_DIR}"
if [[ -f "${PROJECT_DIR}/deployment/quiesce-legacy-stack.sh" ]]; then
  bash "${PROJECT_DIR}/deployment/quiesce-legacy-stack.sh"
fi
echo "Consultando atualizações para o ambiente de teste..."
git fetch --quiet origin main
CURRENT_COMMIT="$(git rev-parse HEAD)"
TARGET_COMMIT="$(git rev-parse origin/main)"
DEPLOYED_COMMIT="$(cat "${DEPLOYED_FILE}" 2>/dev/null || true)"
FAILED_COMMIT="$(cat "${FAILED_FILE}" 2>/dev/null || true)"

if [[ "${TARGET_COMMIT}" == "${DEPLOYED_COMMIT}" ]]; then
  echo "O ambiente de teste já está atualizado."
  exit 0
fi
if [[ "${TARGET_COMMIT}" == "${FAILED_COMMIT}" ]]; then
  echo "Este commit já falhou no teste; aguardando uma nova versão."
  exit 0
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Atualização cancelada: existem alterações locais em arquivos controlados."
  exit 1
fi

git merge --ff-only "${TARGET_COMMIT}"
python3 "${PROJECT_DIR}/deployment/create-staging-runtime.py" \
  --source "${PROJECT_DIR}/deployment/secrets/app_secrets.toml" \
  --output "${PROJECT_DIR}/deployment/runtime/staging.env"
if docker image inspect "${CANDIDATE_IMAGE}" >/dev/null 2>&1; then
  docker tag "${CANDIDATE_IMAGE}" "${ROLLBACK_IMAGE}"
fi

echo "Construindo a versão de teste com baixa prioridade para preservar a produção..."
if ! COMPOSE_PARALLEL_LIMIT=1 nice -n 10 docker compose -f "${COMPOSE_FILE}" build staging; then
  echo "${TARGET_COMMIT}" > "${FAILED_FILE}"
  exit 1
fi
"${PROJECT_DIR}/deployment/refresh-staging-db.sh"
echo "Aplicando as migrações do candidato no banco isolado de teste..."
migration_succeeded=false
for ((attempt = 1; attempt <= STAGING_MIGRATION_ATTEMPTS; attempt++)); do
  if docker compose --profile operations -f "${COMPOSE_FILE}" \
    run --rm --no-deps staging-migration; then
    migration_succeeded=true
    break
  fi
  if [[ "${attempt}" -lt "${STAGING_MIGRATION_ATTEMPTS}" ]]; then
    echo "A migração isolada falhou na tentativa ${attempt}; repetindo em ${STAGING_MIGRATION_RETRY_SECONDS}s..." >&2
    sleep "${STAGING_MIGRATION_RETRY_SECONDS}"
  fi
done
if [[ "${migration_succeeded}" != "true" ]]; then
  # refresh-staging-db.sh already stops staging before replacing its isolated
  # database. Stop it again defensively and never start an older image against
  # a database whose migration did not reach the exact expected head.
  docker compose -f "${COMPOSE_FILE}" stop staging >/dev/null 2>&1 || true
  echo "${TARGET_COMMIT}" > "${FAILED_FILE}"
  echo "A migração isolada do staging falhou após duas tentativas; o staging permanece parado e a produção não foi alterada."
  exit 1
fi
FDI_RELEASE_COMMIT="${TARGET_COMMIT}" docker compose -f "${COMPOSE_FILE}" up -d --no-deps --force-recreate staging

CONTAINER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -q staging)"
for _ in $(seq 1 120); do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${CONTAINER_ID}" 2>/dev/null || echo missing)"
  if [[ "${STATUS}" == "healthy" ]]; then
    # O site já está saudável; a carga pesada segue no worker interno e não
    # bloqueia a troca. O job é idempotente para o commit homologado.
    if ! FDI_RELEASE_COMMIT="${TARGET_COMMIT}" docker compose -f "${COMPOSE_FILE}" \
      exec -T staging python -m scripts.enqueue_current_metrics_refresh \
        --requested-by system:staging-release --commit "${TARGET_COMMIT}"; then
      echo "Não foi possível enfileirar as métricas atuais do staging." >&2
      break
    fi
    # Compatibilidade histórica: o fallback interno pode executar
    # `docker compose ... restart proxy`, mas a via normal é validação seguida
    # de caddy reload. Os upstreams A dinâmicos acompanham a troca de IP.
    if ! bash "${PROJECT_DIR}/deployment/reload-proxy.sh"; then
      break
    fi
    for _ in $(seq 1 36); do
      PAYLOAD="$(curl --fail --silent --show-error --max-time 15 "${PUBLIC_READY_URL}" 2>/dev/null || true)"
      if [[ "${PAYLOAD}" == *'"status":"ready"'* && "${PAYLOAD}" == *'"environment":"staging"'* ]]; then
        echo "${TARGET_COMMIT}" > "${DEPLOYED_FILE}"
        rm -f "${FAILED_FILE}"
        echo "Teste atualizado: https://formacaodoinvestidor.com.br/testefdi/"
        exit 0
      fi
      sleep 5
    done
    break
  fi
  if [[ "${STATUS}" == "unhealthy" || "${STATUS}" == "missing" ]]; then break; fi
  sleep 5
done

docker compose -f "${COMPOSE_FILE}" logs --tail=120 staging || true
echo "${TARGET_COMMIT}" > "${FAILED_FILE}"
echo "A versão nova falhou; o ambiente oficial não foi alterado e não houve downgrade automático do banco de teste."
exit 1
