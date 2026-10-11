#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
REPORT_FILE="${FDI_BROWSER_PERFORMANCE_REPORT:-${PROJECT_DIR}/deployment/runtime/browser-performance-report.json}"
GATE_FILE="${PROJECT_DIR}/deployment/runtime/browser-performance.required"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"

cd "${PROJECT_DIR}"
# shellcheck disable=SC1090
source "${LOCATION_LIB}"
TARGET_COMMIT="$(cat "${PROJECT_DIR}/.git/investment-staging-commit" 2>/dev/null || true)"
[[ "${TARGET_COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit de staging inválido."; exit 1; }
worker_require_regular_owned_file "${REPORT_FILE}" 600
python3 -m scripts.verify_browser_performance_report \
  "${REPORT_FILE}" --expected-commit "${TARGET_COMMIT}"
TEMP_GATE="$(mktemp "${PROJECT_DIR}/deployment/runtime/.browser-performance-required.XXXXXX")"
trap 'rm -f -- "${TEMP_GATE}"' EXIT
printf 'enabled\n' > "${TEMP_GATE}"
chmod 600 "${TEMP_GATE}"
mv "${TEMP_GATE}" "${GATE_FILE}"
worker_require_regular_owned_file "${GATE_FILE}" 600
echo "Bloqueio de navegador habilitado. Promoções futuras exigirão uma evidência válida e recente."

