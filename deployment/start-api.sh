#!/bin/sh
set -eu

python /app/deployment/run-migrations.py verify --timeout-seconds 60
exec python -m uvicorn investment_engine.api.app:app \
  --host 0.0.0.0 \
  --port 8000 \
  --no-access-log \
  --proxy-headers \
  --forwarded-allow-ips="*"
