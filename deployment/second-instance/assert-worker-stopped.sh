#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/deployment/second-instance/docker-compose.worker.yml"
ENV_FILE="${PROJECT_DIR}/deployment/second-instance/worker.env"

CONTAINER_ID="$(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps -aq worker)"
if [[ -z "${CONTAINER_ID}" ]]; then
  echo "Nenhum worker remoto foi criado; estado de espera confirmado."
  exit 0
fi

RUNNING="$(docker inspect --format '{{.State.Running}}' "${CONTAINER_ID}")"
RESTART_POLICY="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "${CONTAINER_ID}")"
if [[ "${RUNNING}" != "false" ]]; then
  echo "Pré-validação interrompida: já existe um worker remoto em execução."
  exit 1
fi
if [[ "${RESTART_POLICY}" != "no" ]]; then
  echo "Pré-validação interrompida: o worker remoto parado ainda pode reiniciar sozinho."
  echo "Execute stop-worker.sh na VM2 antes de continuar."
  exit 1
fi
echo "Worker remoto parado e com reinício automático desabilitado."

