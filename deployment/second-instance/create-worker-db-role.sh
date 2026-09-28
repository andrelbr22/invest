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
ALTER ROLE investment_worker NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 8;
ALTER ROLE investment_worker SET statement_timeout = '30min';
ALTER ROLE investment_worker SET lock_timeout = '30s';
ALTER ROLE investment_worker SET idle_in_transaction_session_timeout = '5min';
REVOKE ALL PRIVILEGES ON DATABASE investment_engine FROM investment_worker;
GRANT CONNECT ON DATABASE investment_engine TO investment_worker;
-- Em PostgreSQL antigos, PUBLIC podia criar objetos no schema public. O
-- proprietário `investment` conserva seus direitos de owner para migrações.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL PRIVILEGES ON SCHEMA public FROM investment_worker;
GRANT USAGE ON SCHEMA public TO investment_worker;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM investment_worker;
-- O worker processa mercado, fila, backtests, alertas e eventos. Ele não
-- recebe acesso às credenciais de login, à administração do portal, aos
-- níveis de acesso, às finanças ou às configurações pessoais de análise.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  assets,
  fundamental_snapshots,
  technical_snapshots,
  price_bars,
  ingestion_runs,
  valuation_snapshots,
  score_snapshots,
  asset_current_metrics,
  user_news_cache,
  user_alert_preferences,
  price_alerts,
  price_alert_events,
  backtest_request_usage,
  backtest_runs,
  backtest_batch_jobs,
  backtest_batch_deliveries,
  backtest_batch_chunks,
  backtest_trades,
  background_jobs,
  shared_snapshots,
  operational_archive,
  runtime_leases,
  service_heartbeats,
  operational_incidents,
  interest_curve_snapshots,
  economic_series,
  economic_series_points,
  corporate_events,
  relevant_facts,
  official_calendar_events,
  alb_universe_observations
TO investment_worker;
GRANT SELECT ON TABLE portfolios, portfolio_positions TO investment_worker;
REVOKE ALL PRIVILEGES ON TABLE
  access_levels,
  user_access_policies,
  email_login_codes,
  portal_pages,
  portal_media,
  portal_books,
  portal_book_links,
  saved_screening_filters,
  screening_preset_settings,
  analysis_column_settings,
  portfolio_custom_investments,
  portfolio_custom_investment_values,
  finance_transactions,
  finance_monthly_budgets
FROM investment_worker;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM investment_worker;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO investment_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE investment IN SCHEMA public
  REVOKE ALL PRIVILEGES ON TABLES FROM investment_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE investment IN SCHEMA public
  REVOKE ALL PRIVILEGES ON SEQUENCES FROM investment_worker;
SQL
unset ROLE_PASSWORD
echo "Usuário exclusivo do worker criado/atualizado sem exibir a senha."
