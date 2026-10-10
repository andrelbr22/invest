#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/home/ubuntu/invest"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
STAGING_IMAGE="formacao-do-investidor-staging:candidate"
PRODUCTION_IMAGE="formacao-do-investidor-production:current"
ROLLBACK_IMAGE="formacao-do-investidor-production:rollback"
LOCK_FILE="/tmp/investment-production-promotion.lock"
WORKER_LOCK_FILE="/tmp/investment-worker-location.lock"
WORKER_LOCATION_FILE="${PROJECT_DIR}/deployment/runtime/worker-location.env"
WORKER_LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"
PRODUCTION_COMMIT_FILE="${PROJECT_DIR}/.git/investment-production-commit"
PRODUCTION_WORKER_COMMIT_FILE="${PROJECT_DIR}/.git/investment-production-worker-commit"
PUBLIC_READY_URL="https://formacaodoinvestidor.com.br/ready"
BROWSER_PERFORMANCE_REPORT="${FDI_BROWSER_PERFORMANCE_REPORT:-${PROJECT_DIR}/deployment/runtime/browser-performance-report.json}"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "Outra promoção já está em andamento."
  exit 1
fi

cd "${PROJECT_DIR}"
# shellcheck disable=SC1090
source "${WORKER_LOCATION_LIB}"

# A promoção altera a imagem do mesmo consumidor que pode estar sendo
# transferido entre VMs. Segure a trava durante todo o procedimento para que
# cutover e failback não mudem a topologia entre o pre-flight e a ativação.
exec 8>"${WORKER_LOCK_FILE}"
if ! flock -w 60 8; then
  echo "Outra troca de localização do worker continua em andamento."
  exit 1
fi

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

post_promotion_failed() {
  local reason="${1:?Informe o motivo da falha}"
  echo "${reason}"
  log_release_services
  echo "A produção já foi atualizada; não repita a promoção. Corrija somente a pós-condição indicada."
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

enqueue_current_metrics_after_worker_promotion() {
  if ! FDI_RELEASE_COMMIT="${TARGET_COMMIT}" docker compose -f "${COMPOSE_FILE}" exec -T app \
    python -m scripts.enqueue_current_metrics_refresh \
      --requested-by system:production-release --commit "${TARGET_COMMIT}"; then
    post_promotion_failed "A aplicação e o worker já estão no commit aprovado, mas o preenchimento idempotente das métricas atuais não pôde ser enfileirado."
  fi
}

verify_exact_worker() {
  local expected_node="${1:?Informe o nó esperado}"
  local expected_environment="${2:?Informe o ambiente esperado}"
  local expected_commit="${3:?Informe o commit esperado}"
  # A primeira verificação ocorre antes da troca da aplicação. Portanto o
  # contêiner ainda pode conter o verificador da versão anterior. Execute o
  # verificador do commit aprovado no ambiente/banco da aplicação atual.
  docker compose -f "${COMPOSE_FILE}" exec -T app \
    python - \
      --expected-node "${expected_node}" \
      --expected-environment "${expected_environment}" \
      --expected-commit "${expected_commit}" \
    < "${PROJECT_DIR}/deployment/second-instance/verify-worker-coordination.py"
}

wait_exact_worker() {
  local expected_node="${1:?Informe o nó esperado}"
  local expected_environment="${2:?Informe o ambiente esperado}"
  local expected_commit="${3:?Informe o commit esperado}"
  local attempts="${4:-24}"
  for _ in $(seq 1 "${attempts}"); do
    if verify_exact_worker "${expected_node}" "${expected_environment}" "${expected_commit}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  # Preserve the actionable diagnostic on the final attempt.
  verify_exact_worker "${expected_node}" "${expected_environment}" "${expected_commit}"
}

assert_local_worker_runtime_state() {
  local expected_location="${1:?Informe local ou remote}"
  local container_id running restart_policy
  container_id="$(docker compose -f "${COMPOSE_FILE}" ps -aq worker)"
  if [[ -z "${container_id}" ]]; then
    [[ "${expected_location}" == "remote" ]] && return 0
    echo "O worker local esperado ainda não foi criado."
    return 1
  fi
  running="$(docker inspect --format '{{.State.Running}}' "${container_id}")"
  restart_policy="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "${container_id}")"
  if [[ "${expected_location}" == "remote" ]]; then
    [[ "${running}" == "false" && "${restart_policy}" == "no" ]] || {
      echo "O worker local deve estar parado e sem reinício automático enquanto a VM2 está ativa."
      return 1
    }
  else
    [[ "${running}" == "true" && "${restart_policy}" == "unless-stopped" ]] || {
      echo "O worker local deve estar ativo com reinício automático no modo local."
      return 1
    }
  fi
}

park_staging_after_promotion() {
  local staging_id
  if [[ "${FDI_KEEP_STAGING_RUNNING_AFTER_PROMOTION:-false}" == "true" ]]; then
    echo "Staging mantido ativo por configuração explícita."
    return 0
  fi
  staging_id="$(docker compose -f "${COMPOSE_FILE}" ps -aq staging)"
  [[ -n "${staging_id}" ]] || return 0
  # Primeiro removemos a possibilidade de retorno após reinício do daemon;
  # depois paramos o ambiente de homologação, liberando RAM/CPU à produção.
  worker_set_restart_policy "${staging_id}" no
  docker compose -f "${COMPOSE_FILE}" stop -t 60 staging >/dev/null
  [[ "$(docker inspect --format '{{.State.Running}}' "${staging_id}" 2>/dev/null || echo missing)" == "false" && \
      "$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "${staging_id}" 2>/dev/null || echo missing)" == "no" ]] || {
    echo "O staging não confirmou o estado estacionado."
    return 1
  }
  echo "Staging estacionado após a promoção para preservar recursos da produção."
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
  # Para o modo local basta ler a chave sem executar o arquivo. O modo remoto
  # somente é carregado depois de validar owner, modo 0600, IP, chave e
  # known_hosts pelo helper compartilhado.
  CONFIGURED_LOCATION="$(sed -n 's/^FDI_WORKER_LOCATION=//p' "${WORKER_LOCATION_FILE}" | tail -n 1)"
  if [[ "${CONFIGURED_LOCATION}" == "remote" ]]; then
    load_worker_location_config "${WORKER_LOCATION_FILE}" true
    build_worker_ssh_command
  elif [[ -n "${CONFIGURED_LOCATION}" && "${CONFIGURED_LOCATION}" != "local" ]]; then
    echo "FDI_WORKER_LOCATION deve ser local ou remote."
    exit 1
  fi
fi

# Antes de tocar na aplicação, confirme que existe exatamente um consumidor e
# que ele detém sozinho scheduler e monitor. Isso impede promover durante uma
# topologia dividida ou durante outra troca de VM.
if [[ -f "${PRODUCTION_WORKER_COMMIT_FILE}" ]]; then
  CURRENT_WORKER_COMMIT="$(tr -d '[:space:]' < "${PRODUCTION_WORKER_COMMIT_FILE}")"
elif [[ -f "${PRODUCTION_COMMIT_FILE}" ]]; then
  CURRENT_WORKER_COMMIT="$(tr -d '[:space:]' < "${PRODUCTION_COMMIT_FILE}")"
else
  echo "O commit atual do worker não foi identificado; a topologia não pode ser promovida com segurança."
  exit 1
fi
if [[ ! "${CURRENT_WORKER_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "O marcador atual do worker está vazio ou inválido; corrija-o antes da promoção."
  exit 1
fi
assert_local_worker_runtime_state "${FDI_WORKER_LOCATION}" || exit 1
if [[ "${FDI_WORKER_LOCATION}" == "remote" ]]; then
  verify_exact_worker "${FDI_REMOTE_WORKER_NODE_ID}" production-worker "${CURRENT_WORKER_COMMIT}" >/dev/null || {
    echo "Promoção interrompida: a topologia remota atual não possui worker, scheduler e monitor únicos."
    exit 1
  }
else
  verify_exact_worker primary-worker production "${CURRENT_WORKER_COMMIT}" >/dev/null || {
    echo "Promoção interrompida: a topologia local atual não possui worker, scheduler e monitor únicos."
    exit 1
  }
fi
if [[ "${FDI_WORKER_LOCATION}" != "local" && "${FDI_WORKER_LOCATION}" != "remote" ]]; then
  echo "FDI_WORKER_LOCATION deve ser local ou remote."
  exit 1
fi

if ! docker image inspect "${STAGING_IMAGE}" >/dev/null 2>&1; then
  echo "Não existe uma versão de teste saudável para promover."
  exit 1
fi

# A API preserva fallbacks históricos para segurança, mas eles são muito mais
# caros que a leitura materializada. Uma promoção só pode avançar quando todos
# os ativos ativos possuem valuation e pódio prontos no banco homologado.
echo "Validando a cobertura das métricas usadas pela navegação..."
if ! docker compose -f "${COMPOSE_FILE}" exec -T staging \
  python -m scripts.check_navigation_coverage; then
  echo "Promoção interrompida: conclua a materialização das métricas atuais no ambiente de teste."
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

# A homologação em navegador exige uma sessão autenticada do proprietário e,
# por isso, é produzida fora do contêiner. Quando a evidência existe, ela deve
# pertencer ao mesmo commit, conter cinco amostras de cada jornada e ter menos
# de 24 horas. A instalação pode torná-la obrigatória após configurar o robô
# autenticado, sem enfraquecer o bloqueio do benchmark de API já obrigatório.
if [[ -f "${BROWSER_PERFORMANCE_REPORT}" ]]; then
  if ! python -m scripts.verify_browser_performance_report \
    "${BROWSER_PERFORMANCE_REPORT}" --expected-commit "${TARGET_COMMIT}"; then
    echo "Promoção interrompida: a experiência real no navegador não foi homologada."
    exit 1
  fi
elif [[ "${FDI_REQUIRE_BROWSER_PERFORMANCE_REPORT:-false}" == "true" ]]; then
  echo "Promoção interrompida: falta o relatório obrigatório do navegador real."
  exit 1
else
  echo "Aviso: relatório do navegador real ainda não configurado nesta VM; o benchmark de API foi aprovado."
fi

if [[ -f "${PROJECT_DIR}/deployment/backup-local-db.sh" ]]; then
  bash "${PROJECT_DIR}/deployment/backup-local-db.sh"
fi
if docker image inspect "${PRODUCTION_IMAGE}" >/dev/null 2>&1; then
  # Apenas uma cópia de segurança. Ela nunca é relançada automaticamente
  # depois que uma migração pode ter avançado o banco.
  docker tag "${PRODUCTION_IMAGE}" "${ROLLBACK_IMAGE}"
fi

echo "Aplicando as migrações aprovadas como etapa isolada..."
if ! docker compose --profile operations -f "${COMPOSE_FILE}" \
  run --rm --no-deps production-migration; then
  promotion_failed "A migração isolada da produção falhou; a aplicação anterior continuou ativa."
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

# A via normal usa upstream DNS dinâmico e `caddy reload`; apenas o helper,
# depois de validar a configuração, pode recorrer a `restart proxy`.
if ! bash "${PROJECT_DIR}/deployment/reload-proxy.sh"; then
  promotion_failed "O proxy não aceitou a configuração validada após a troca da aplicação."
fi
if ! wait_public_ready; then
  promotion_failed "A produção não respondeu em /ready depois da troca."
fi
mark_app_promotion_complete

if [[ "${FDI_WORKER_LOCATION}" == "remote" ]]; then
  LOCAL_WORKER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -aq worker)"
  worker_set_restart_policy "${LOCAL_WORKER_ID}" no
  docker compose -f "${COMPOSE_FILE}" stop worker >/dev/null 2>&1 || true
  # A VM2 pode estar executando o commit anterior com saúde. Encerre primeiro
  # esse processo de forma graciosa e confirme restart=no; activate-worker.sh
  # recusa corretamente substituir um consumidor remoto ainda ativo.
  REMOTE_QUIESCED=false
  if "${WORKER_SSH[@]}" \
    "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/stop-worker.sh && ./deployment/second-instance/assert-worker-stopped.sh"; then
    REMOTE_QUIESCED=true
  fi
  if [[ "${REMOTE_QUIESCED}" == "true" ]] && "${WORKER_SSH[@]}" \
    "cd '${FDI_WORKER_PROJECT_DIR}' && ./deployment/second-instance/activate-worker.sh '${TARGET_COMMIT}'"; then
    mark_worker_promotion_complete
    enqueue_current_metrics_after_worker_promotion
    park_staging_after_promotion || post_promotion_failed "A produção e o worker remoto foram atualizados, mas o staging não foi estacionado."
    echo "Produção atualizada e worker remoto confirmado no commit aprovado."
    exit 0
  fi
  echo "O worker remoto não confirmou a ativação; iniciando o retorno local."
  if ! FDI_WORKER_LOCATION_LOCK_HELD=true \
       FDI_FAILBACK_REMOTE_MAY_BE_ACTIVE=true \
       bash "${PROJECT_DIR}/deployment/second-instance/failback-worker.sh"; then
    promotion_failed "A VM2 falhou e o retorno seguro para o worker local não foi confirmado. A aplicação web permanece online."
  fi
  mark_worker_promotion_complete
  enqueue_current_metrics_after_worker_promotion
  park_staging_after_promotion || post_promotion_failed "A produção e o worker local de contingência foram atualizados, mas o staging não foi estacionado."
  echo "Produção atualizada; a VM2 falhou e o worker retornou com segurança à VM principal."
  exit 0
fi

WORKER_LAUNCH_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
if ! FDI_RELEASE_COMMIT="${TARGET_COMMIT}" docker compose -f "${COMPOSE_FILE}" \
  up -d --no-deps --force-recreate worker; then
  promotion_failed "O worker local da nova versão não pôde ser iniciado. A aplicação web permanece online."
fi
WORKER_CONTAINER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -q worker)"
worker_set_restart_policy "${WORKER_CONTAINER_ID}" unless-stopped
if ! wait_local_worker_ready "${WORKER_CONTAINER_ID}"; then
  promotion_failed "O worker local não publicou um heartbeat fresco no commit aprovado. A aplicação web permanece online."
fi
if ! wait_exact_worker primary-worker production "${TARGET_COMMIT}" 24; then
  promotion_failed "A verificação final encontrou mais de um worker ou lideranças divergentes."
fi

mark_worker_promotion_complete
enqueue_current_metrics_after_worker_promotion
park_staging_after_promotion || post_promotion_failed "A produção foi atualizada, mas o staging não foi estacionado."
echo "Produção, proxy e rotinas automáticas atualizados após aprovação manual."
