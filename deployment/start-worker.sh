#!/bin/sh
set -eu

python /app/deployment/run-migrations.py verify --timeout-seconds 60
exec python -m scripts.run_background_worker \
  --poll-seconds="${BACKGROUND_WORKER_POLL_SECONDS:-2}"
