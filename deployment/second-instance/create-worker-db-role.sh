#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
ROLE_NAME="investment_worker"

cd "${PROJECT_DIR}"
read -r -s -p "Crie a senha exclusiva do worker remoto (mínimo 32 caracteres): " ROLE_PASSWORD
echo
if (( ${#ROLE_PASSWORD} < 32 )) || [[ ! "${ROLE_PASSWORD}" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "Use ao menos 32 caracteres: letras, números, _ ou -."
  unset ROLE_PASSWORD
  exit 1
fi

# A senha vai pela entrada padrão do psql e não aparece na linha de comando.
docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  psql --set=ON_ERROR_STOP=1 -U investment -d investment_engine \
  --set=worker_password="${ROLE_PASSWORD}" <<'SQL'
SELECT format(
  'CREATE ROLE investment_worker LOGIN PASSWORD %L',
  :'worker_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'investment_worker')
\gexec
ALTER ROLE investment_worker LOGIN PASSWORD :'worker_password';
GRANT CONNECT ON DATABASE investment_engine TO investment_worker;
GRANT USAGE ON SCHEMA public TO investment_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO investment_worker;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO investment_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE investment IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO investment_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE investment IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO investment_worker;
SQL
unset ROLE_PASSWORD
echo "Usuário exclusivo do worker criado/atualizado sem exibir a senha."
