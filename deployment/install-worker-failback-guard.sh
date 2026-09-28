#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
sudo install -o root -g root -m 0644 \
  "${PROJECT_DIR}/deployment/investment-worker-failback-guard.service.example" \
  /etc/systemd/system/investment-worker-failback-guard.service
sudo install -o root -g root -m 0644 \
  "${PROJECT_DIR}/deployment/investment-worker-failback-guard.timer.example" \
  /etc/systemd/system/investment-worker-failback-guard.timer
sudo systemctl daemon-reload
sudo systemctl enable --now investment-worker-failback-guard.timer
echo "Guardião instalado. Ele permanece observacional enquanto FDI_AUTO_FAILBACK_ENABLED=false."
