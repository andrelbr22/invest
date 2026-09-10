#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/deployment/second-instance/docker-compose.worker.yml"
ENV_FILE="${PROJECT_DIR}/deployment/second-instance/worker.env"
SECRETS_FILE="${PROJECT_DIR}/deployment/second-instance/worker_secrets.toml"

cd "${PROJECT_DIR}"
for file in "${COMPOSE_FILE}" "${ENV_FILE}" "${SECRETS_FILE}"; do
  [[ -f "${file}" ]] || { echo "Arquivo obrigatório ausente: ${file}"; exit 1; }
done
MODE="$(stat -c '%a' "${SECRETS_FILE}")"
if (( 10#${MODE} % 10 != 0 )); then
  echo "O segredo não pode ter permissão para outros usuários. Use modo 0640."
  exit 1
fi
python3 - "${SECRETS_FILE}" <<'PY'
import ipaddress, pathlib, sys, tomllib
from urllib.parse import urlsplit

payload = tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
url = str(payload.get("DATABASE_URL") or "")
parsed = urlsplit(url)
if not parsed.hostname:
    raise SystemExit("DATABASE_URL ausente no segredo do worker.")
try:
    address = ipaddress.ip_address(parsed.hostname)
except ValueError as exc:
    raise SystemExit("Use o IP privado da VM1 em DATABASE_URL.") from exc
if not address.is_private or address.is_loopback or address.is_unspecified:
    raise SystemExit("DATABASE_URL deve usar somente o IP privado da VM1.")
if parsed.port != 5432:
    raise SystemExit("A porta privada do PostgreSQL deve ser 5432.")
print("Endereço privado do banco validado sem expor a credencial.")
PY

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config --quiet
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" run --rm --no-deps worker python - <<'PY'
import socket
from sqlalchemy import text
from investment_engine.infrastructure.db.session import get_session_factory

for host in ("api.bcb.gov.br", "query1.finance.yahoo.com", "scanner.tradingview.com", "www.fundamentus.com.br"):
    socket.gethostbyname(host)
session = get_session_factory()()
try:
    session.execute(text("SELECT 1"))
    revision = session.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one()
finally:
    session.close()
if revision != "0022_v1_22_observability":
    raise SystemExit(f"Migração inesperada no banco: {revision}")
print("DNS externo, banco privado e migração V1.22.0 validados.")
PY
echo "Worker remoto pronto para a preparação em modo de espera."
