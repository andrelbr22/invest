#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
STATE_FILE="${1:-}"
REPORT_FILE="${FDI_BROWSER_PERFORMANCE_REPORT:-${PROJECT_DIR}/deployment/runtime/browser-performance-report.json}"
PYTHON_BIN="${FDI_BROWSER_PYTHON:-python3}"
LOCATION_LIB="${PROJECT_DIR}/deployment/second-instance/worker-location-lib.sh"

[[ -n "${STATE_FILE}" ]] || {
  echo "Uso: $0 /caminho/absoluto/storage-state.json" >&2
  exit 2
}
[[ "${STATE_FILE}" == /* ]] || { echo "A sessão deve usar caminho absoluto." >&2; exit 2; }
cd "${PROJECT_DIR}"
# shellcheck disable=SC1090
source "${LOCATION_LIB}"
worker_require_regular_owned_file "${STATE_FILE}" 600
TARGET_COMMIT="$(cat "${PROJECT_DIR}/.git/investment-staging-commit" 2>/dev/null || true)"
[[ "${TARGET_COMMIT}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "O commit homologado do staging não foi identificado." >&2
  exit 1
}

"${PYTHON_BIN}" - "${STATE_FILE}" <<'PY'
import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not isinstance(payload.get("cookies"), list) or not isinstance(payload.get("origins"), list):
    raise SystemExit("O arquivo não é um storage state válido do Playwright.")
if not payload["cookies"]:
    raise SystemExit("A sessão autenticada não contém cookies.")
print("Estrutura da sessão autenticada validada sem exibir credenciais.")
PY

mkdir -p "$(dirname "${REPORT_FILE}")"
TEMP_REPORT="$(mktemp "$(dirname "${REPORT_FILE}")/.browser-performance.XXXXXX")"
trap 'rm -f -- "${TEMP_REPORT}"' EXIT
"${PYTHON_BIN}" -m scripts.benchmark_browser_journeys \
  --storage-state "${STATE_FILE}" \
  --commit "${TARGET_COMMIT}" \
  --samples 5 \
  --output "${TEMP_REPORT}"
"${PYTHON_BIN}" -m scripts.verify_browser_performance_report \
  "${TEMP_REPORT}" --expected-commit "${TARGET_COMMIT}"
chmod 600 "${TEMP_REPORT}"
mv "${TEMP_REPORT}" "${REPORT_FILE}"
worker_require_regular_owned_file "${REPORT_FILE}" 600
echo "Evidência real do navegador aprovada: ${REPORT_FILE}"

