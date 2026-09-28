#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/deployment/second-instance/docker-compose.worker.yml"
ENV_FILE="${PROJECT_DIR}/deployment/second-instance/worker.env"
SECRETS_FILE="${PROJECT_DIR}/deployment/second-instance/worker_secrets.toml"
COMMIT="${1:-$(git -C "${PROJECT_DIR}" rev-parse HEAD)}"

[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit aprovado inválido."; exit 1; }
cd "${PROJECT_DIR}"
for command in git docker python3 stat; do
  command -v "${command}" >/dev/null || { echo "Comando obrigatório ausente na VM2: ${command}"; exit 1; }
done
docker compose version >/dev/null
docker info >/dev/null
case "$(uname -m)" in
  x86_64|aarch64|arm64) ;;
  *) echo "Arquitetura não homologada para o worker: $(uname -m)"; exit 1 ;;
esac

[[ -f "${COMPOSE_FILE}" && -f "${ENV_FILE}" && -f "${SECRETS_FILE}" ]] || {
  echo "Compose, worker.env ou worker_secrets.toml ausente na VM2."
  exit 1
}
[[ ! -L "${ENV_FILE}" && ! -L "${SECRETS_FILE}" ]] || { echo "Links simbólicos não são aceitos nos arquivos privados."; exit 1; }
[[ "$(stat -c '%u' "${ENV_FILE}")" == "$(id -u)" && "$(stat -c '%a' "${ENV_FILE}")" == "600" ]] || {
  echo "worker.env deve pertencer ao usuário atual e usar modo 0600."
  exit 1
}
[[ "$(stat -c '%u' "${SECRETS_FILE}")" == "$(id -u)" && "$(stat -c '%g' "${SECRETS_FILE}")" == "10001" && "$(stat -c '%a' "${SECRETS_FILE}")" == "640" ]] || {
  echo "worker_secrets.toml deve pertencer ao usuário atual, grupo 10001 e modo 0640."
  exit 1
}
[[ "$(git rev-parse HEAD)" == "${COMMIT}" ]] || { echo "HEAD diverge do commit aprovado."; exit 1; }
[[ -z "$(git status --porcelain --untracked-files=normal)" ]] || { echo "A cópia da VM2 não está limpa."; exit 1; }
git merge-base --is-ancestor "${COMMIT}" origin/main || { echo "O commit não pertence a origin/main."; exit 1; }
grep -Eq '^FDI_COORDINATOR_ENABLED=false([[:space:]]*)$' "${ENV_FILE}" || {
  echo "Mantenha FDI_COORDINATOR_ENABLED=false no arquivo; a ativação é feita somente pelo comando controlado."
  exit 1
}

python3 - "${SECRETS_FILE}" <<'PY'
import ipaddress
import pathlib
import sys
import tomllib
from urllib.parse import unquote, urlsplit

payload = tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
parsed = urlsplit(str(payload.get("DATABASE_URL") or ""))
if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
    raise SystemExit("DATABASE_URL do worker deve usar PostgreSQL/psycopg.")
if unquote(parsed.username or "") != "investment_worker":
    raise SystemExit("A VM2 deve usar exclusivamente a função investment_worker.")
if not parsed.password:
    raise SystemExit("A senha exclusiva do worker não foi configurada.")
try:
    address = ipaddress.ip_address(parsed.hostname or "")
except ValueError as exc:
    raise SystemExit("Use o IP privado literal da VM1 em DATABASE_URL.") from exc
if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
    raise SystemExit("DATABASE_URL deve apontar somente ao IP privado da VM1.")
if parsed.port != 5432 or parsed.path != "/investment_engine":
    raise SystemExit("Use a porta 5432 e o banco investment_engine.")
print("Destino privado e função exclusiva do banco validados.")
PY

FDI_COORDINATOR_ENABLED=false FDI_RELEASE_COMMIT="${COMMIT}" \
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config --quiet
FDI_COORDINATOR_ENABLED=false FDI_RELEASE_COMMIT="${COMMIT}" \
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" build worker
FDI_COORDINATOR_ENABLED=false FDI_RELEASE_COMMIT="${COMMIT}" \
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" run --rm --no-deps worker python - <<'PY'
import ipaddress
import socket

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from investment_engine.infrastructure.db.session import get_session_factory

for host in ("api.bcb.gov.br", "query1.finance.yahoo.com", "scanner.tradingview.com", "www.fundamentus.com.br"):
    socket.gethostbyname(host)

session = get_session_factory()()
try:
    row = session.execute(text("""
        SELECT current_user,
               current_database(),
               inet_server_addr()::text,
               has_database_privilege(current_user, current_database(), 'CREATE'),
               has_schema_privilege(current_user, 'public', 'CREATE'),
               r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolreplication, r.rolbypassrls,
               has_table_privilege(current_user, 'email_login_codes', 'SELECT'),
               has_table_privilege(current_user, 'user_access_policies', 'SELECT'),
               has_table_privilege(current_user, 'portal_media', 'SELECT'),
               has_table_privilege(current_user, 'finance_transactions', 'SELECT')
        FROM pg_roles r WHERE r.rolname = current_user
    """)).one()
    revision = session.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one()
finally:
    session.close()

if row[0] != "investment_worker" or row[1] != "investment_engine":
    raise SystemExit("A conexão não usa a função/banco exclusivos esperados.")
address = ipaddress.ip_address(row[2])
if not address.is_private or address.is_loopback or address.is_unspecified:
    raise SystemExit("O PostgreSQL respondeu por um endereço que não é privado.")
if any(bool(value) for value in row[3:10]):
    raise SystemExit("A função investment_worker possui privilégio administrativo indevido.")
if any(bool(value) for value in row[10:]):
    raise SystemExit("A função investment_worker alcança tabelas privadas fora do seu escopo.")
head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
if not head or revision != head:
    raise SystemExit(f"Banco e código divergem: banco={revision}, código={head}.")
print(f"DNS, banco privado, privilégios mínimos e migração {head} validados.")
PY
echo "Pré-validação da VM2 concluída; nenhum consumidor foi iniciado."
