#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
sudo install -o root -g root -m 0644 \
  "${PROJECT_DIR}/deployment/investment-operational-watchdog.service.example" \
  /etc/systemd/system/investment-operational-watchdog.service
sudo install -o root -g root -m 0644 \
  "${PROJECT_DIR}/deployment/investment-operational-watchdog.timer.example" \
  /etc/systemd/system/investment-operational-watchdog.timer
sudo systemctl daemon-reload
sudo systemctl enable --now investment-operational-watchdog.timer
echo "Watchdog instalado. Alertas operacionais serão verificados a cada dois minutos."
