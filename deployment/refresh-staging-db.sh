#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/home/ubuntu/invest"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
SOURCE_DB="investment_engine"
STAGING_DB="investment_engine_staging"
STAGING_RUNTIME="${PROJECT_DIR}/deployment/runtime/staging.env"
STAGING_CONFIG_GENERATOR="${PROJECT_DIR}/deployment/create-staging-runtime.py"

cd "${PROJECT_DIR}"
python3 "${STAGING_CONFIG_GENERATOR}" \
  --source "${PROJECT_DIR}/deployment/secrets/app_secrets.toml" \
  --output "${STAGING_RUNTIME}"

IFS=$'\t' read -r STAGING_USER STAGING_PASSWORD CONFIGURED_STAGING_DB < <(
  python3 "${STAGING_CONFIG_GENERATOR}" \
    --output "${STAGING_RUNTIME}" \
    --database-fields
)
if [[ "${STAGING_USER}" != "investment_staging" || "${CONFIGURED_STAGING_DB}" != "${STAGING_DB}" || -z "${STAGING_PASSWORD}" ]]; then
  echo "A configuracao isolada do banco de teste e invalida." >&2
  exit 1
fi

docker compose -f "${COMPOSE_FILE}" stop staging >/dev/null 2>&1 || true

# The fixed role name is intentionally not configurable.  The password is
# passed to psql through standard input and is never printed or put on the
# process command line. Repeated runs rotate it to the value kept in the
# private runtime file without granting any administrative capability.
{
  printf "\\set staging_password '%s'\n" "${STAGING_PASSWORD}"
  cat <<'SQL'
DO $role$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'investment_staging') THEN
    CREATE ROLE investment_staging LOGIN;
  END IF;
END
$role$;
ALTER ROLE investment_staging WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'staging_password';
SQL
} | docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U investment -d postgres >/dev/null

docker compose -f "${COMPOSE_FILE}" exec -T postgres dropdb --if-exists --force -U investment "${STAGING_DB}"
docker compose -f "${COMPOSE_FILE}" exec -T postgres createdb -U investment -O "${STAGING_USER}" "${STAGING_DB}"
docker compose -f "${COMPOSE_FILE}" exec -T postgres pg_dump -U investment -d "${SOURCE_DB}" --no-owner --no-privileges | \
  docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    psql -v ON_ERROR_STOP=1 -U "${STAGING_USER}" -d "${STAGING_DB}" >/dev/null

# Never copy a usable production passwordless challenge into homologation.
# Active background work is also cancelled inside the copy so the staging
# worker cannot replay an e-mail or external integration requested in
# production before the snapshot was taken.
docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U "${STAGING_USER}" -d "${STAGING_DB}" >/dev/null <<'SQL'
DO $scrub$
BEGIN
  IF to_regclass('public.email_login_codes') IS NOT NULL THEN
    EXECUTE 'TRUNCATE TABLE public.email_login_codes';
  END IF;
  IF to_regclass('public.background_jobs') IS NOT NULL THEN
    EXECUTE $update$
      UPDATE public.background_jobs
      SET status = 'cancelled',
          message = 'Cancelado na copia isolada de homologacao.',
          locked_by = NULL,
          locked_at = NULL,
          heartbeat_at = NULL,
          finished_at = CURRENT_TIMESTAMP,
          updated_at = CURRENT_TIMESTAMP,
          last_error_code = 'staging_clone_quiesced',
          last_error_message = NULL
      WHERE status IN ('queued', 'running')
    $update$;
  END IF;
END
$scrub$;
SQL

unset STAGING_PASSWORD
echo "Banco de teste atualizado a partir de uma copia isolada da producao."
echo "Credenciais, sessao, codigos de acesso e trabalhos ativos do staging foram isolados."
