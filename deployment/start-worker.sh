#!/bin/sh
set -eu

exec python -m scripts.run_background_worker \
  --poll-seconds="${BACKGROUND_WORKER_POLL_SECONDS:-2}"
