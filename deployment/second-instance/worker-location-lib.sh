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

worker_write_location() {
  local location_file="${1:?Informe o arquivo de localização}"
  local location="${2:?Informe local ou remote}"
  [[ "${location}" == "local" || "${location}" == "remote" ]] || \
    worker_location_error "localização inválida: ${location}"
  worker_require_regular_owned_file "${location_file}" 600
  python3 - "${location_file}" "${location}" <<'PY'
import os
from pathlib import Path
import sys

path = Path(sys.argv[1])
location = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
matches = [index for index, line in enumerate(lines) if line.startswith("FDI_WORKER_LOCATION=")]
if len(matches) != 1:
    raise SystemExit("worker-location.env deve conter exatamente uma chave FDI_WORKER_LOCATION.")
lines[matches[0]] = f"FDI_WORKER_LOCATION={location}"
temporary = path.with_name(f".{path.name}.tmp")
temporary.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
os.chmod(temporary, 0o600)
os.replace(temporary, path)
PY
  worker_require_regular_owned_file "${location_file}" 600
}

worker_set_restart_policy() {
  local container_id="${1:-}"
  local policy="${2:?Informe a política de reinício}"
  [[ "${policy}" == "no" || "${policy}" == "unless-stopped" ]] || \
    worker_location_error "política de reinício inválida: ${policy}"
  if [[ -n "${container_id}" ]] && docker inspect "${container_id}" >/dev/null 2>&1; then
    docker update --restart="${policy}" "${container_id}" >/dev/null
  fi
}
