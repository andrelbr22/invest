#!/usr/bin/env bash
set -Eeuo pipefail

# A instalação anterior usava o projeto Compose "invest" e o arquivo
# docker-compose.oracle-micro.yml. Ela não pode disputar CPU, disco ou banco
# com a arquitetura atual. Este procedimento pausa somente contêineres que
# tenham simultaneamente todos os rótulos conhecidos da pilha antiga.
PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
LEGACY_PROJECT="invest"
LEGACY_COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-micro.yml"
EXPECTED_SERVICES=" app postgres proxy "
containers=()

while IFS= read -r container_id; do
  [[ -n "${container_id}" ]] || continue
  working_dir="$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "${container_id}" 2>/dev/null || true)"
  config_files="$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "${container_id}" 2>/dev/null || true)"
  service="$(docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "${container_id}" 2>/dev/null || true)"
  if [[ "${working_dir}" == "${PROJECT_DIR}" \
    && "${config_files}" == *"${LEGACY_COMPOSE_FILE}"* \
    && "${EXPECTED_SERVICES}" == *" ${service} "* ]]; then
    containers+=("${container_id}")
  fi
done < <(docker ps -aq --filter "label=com.docker.compose.project=${LEGACY_PROJECT}")

if (( ${#containers[@]} == 0 )); then
  exit 0
fi

# Remover a política de reinício evita o retorno no próximo boot. Trate cada
# contêiner isoladamente: um daemon concorrente pode concluir a remoção de um
# ID entre a listagem e o update. Isso não deve abortar uma promoção válida.
paused=0
for container_id in "${containers[@]}"; do
  docker inspect "${container_id}" >/dev/null 2>&1 || continue
  docker update --restart=no "${container_id}" >/dev/null 2>&1 || {
    docker inspect "${container_id}" >/dev/null 2>&1 && exit 1
    continue
  }
  docker inspect "${container_id}" >/dev/null 2>&1 || continue
  docker stop --time 30 "${container_id}" >/dev/null 2>&1 || {
    docker inspect "${container_id}" >/dev/null 2>&1 && exit 1
    continue
  }
  paused=$((paused + 1))
done
if (( paused > 0 )); then
  echo "Pilha legada pausada com segurança (${paused} contêineres); nenhum dado foi removido."
fi
