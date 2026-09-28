#!/usr/bin/env bash
set -Eeuo pipefail

# Funções compartilhadas pelos procedimentos executados na VM principal.
# O arquivo runtime é código shell por necessidade do Compose; por isso ele só
# pode ser carregado depois de comprovar propriedade e permissão estritas.

worker_location_error() {
  echo "Configuração segura da segunda instância: $*" >&2
  return 1
}

worker_require_regular_owned_file() {
  local path="${1:?Informe o arquivo}"
  local expected_mode="${2:?Informe o modo octal}"
  [[ -f "${path}" && ! -L "${path}" ]] || worker_location_error "arquivo regular ausente ou link simbólico recusado: ${path}"
  [[ "$(stat -c '%u' "${path}")" == "$(id -u)" ]] || worker_location_error "${path} deve pertencer ao usuário atual."
  [[ "$(stat -c '%a' "${path}")" == "${expected_mode}" ]] || worker_location_error "use chmod ${expected_mode} ${path}."
}

worker_validate_private_ip() {
  python3 - "${1:?Informe o IP privado}" <<'PY'
import ipaddress
import sys

try:
    address = ipaddress.ip_address(sys.argv[1])
except ValueError as exc:
    raise SystemExit("O endereço da VM2 deve ser um IP privado literal.") from exc
if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
    raise SystemExit("O SSH da VM2 deve usar somente o IP privado da VNIC.")
PY
}

load_worker_location_config() {
  local location_file="${1:?Informe o arquivo de localização}"
  local require_remote_fields="${2:-false}"
  worker_require_regular_owned_file "${location_file}" 600
  # shellcheck disable=SC1090
  source "${location_file}"
  FDI_WORKER_LOCATION="${FDI_WORKER_LOCATION:-local}"
  [[ "${FDI_WORKER_LOCATION}" == "local" || "${FDI_WORKER_LOCATION}" == "remote" ]] || \
    worker_location_error "FDI_WORKER_LOCATION deve ser local ou remote."
  if [[ "${FDI_WORKER_LOCATION}" == "remote" || "${require_remote_fields}" == "true" ]]; then
    : "${FDI_WORKER_SSH_HOST:?Informe FDI_WORKER_SSH_HOST}"
    : "${FDI_WORKER_SSH_USER:?Informe FDI_WORKER_SSH_USER}"
    : "${FDI_WORKER_SSH_KEY:?Informe FDI_WORKER_SSH_KEY}"
    : "${FDI_WORKER_KNOWN_HOSTS:?Informe FDI_WORKER_KNOWN_HOSTS}"
    : "${FDI_WORKER_PROJECT_DIR:?Informe FDI_WORKER_PROJECT_DIR}"
    : "${FDI_REMOTE_WORKER_NODE_ID:?Informe FDI_REMOTE_WORKER_NODE_ID}"
    [[ "${FDI_WORKER_SSH_USER}" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || worker_location_error "usuário SSH inválido."
    [[ "${FDI_WORKER_PROJECT_DIR}" =~ ^/[A-Za-z0-9._/-]+$ ]] || worker_location_error "diretório remoto inválido."
    [[ "${FDI_REMOTE_WORKER_NODE_ID}" =~ ^[A-Za-z0-9._-]{1,120}$ ]] || worker_location_error "identificador da VM2 inválido."
    worker_validate_private_ip "${FDI_WORKER_SSH_HOST}"
  fi
}

build_worker_ssh_command() {
  worker_require_regular_owned_file "${FDI_WORKER_SSH_KEY}" 600
  worker_require_regular_owned_file "${FDI_WORKER_KNOWN_HOSTS}" 600
  ssh-keygen -F "${FDI_WORKER_SSH_HOST}" -f "${FDI_WORKER_KNOWN_HOSTS}" >/dev/null || \
    worker_location_error "o IP privado da VM2 não está no arquivo known_hosts aprovado."
  WORKER_REMOTE="${FDI_WORKER_SSH_USER}@${FDI_WORKER_SSH_HOST}"
  WORKER_SSH=(
    ssh
    -o BatchMode=yes
    -o ConnectTimeout=15
    -o IdentitiesOnly=yes
    -o StrictHostKeyChecking=yes
    -o "UserKnownHostsFile=${FDI_WORKER_KNOWN_HOSTS}"
    -o ServerAliveInterval=15
    -o ServerAliveCountMax=2
    -i "${FDI_WORKER_SSH_KEY}"
    "${WORKER_REMOTE}"
  )
}
