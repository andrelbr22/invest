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

# Remover a política de reinício evita o retorno no próximo boot. Nenhum
# contêiner, volume ou dado é excluído; o rollback manual continua possível.
docker update --restart=no "${containers[@]}" >/dev/null
docker stop --time 30 "${containers[@]}" >/dev/null
echo "Pilha legada pausada com segurança (${#containers[@]} contêineres); nenhum dado foi removido."
