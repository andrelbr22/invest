#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/invest}"
COMMIT="${1:?Informe o commit aprovado}"
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit aprovado inválido."; exit 1; }
cd "${PROJECT_DIR}"

[[ -d .git ]] || { echo "O diretório da VM2 não é um repositório Git."; exit 1; }
if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "A VM2 possui alterações locais; nada foi substituído."
  exit 1
fi
git fetch --quiet --prune origin main
git cat-file -e "${COMMIT}^{commit}" 2>/dev/null || { echo "O commit aprovado não existe na VM2."; exit 1; }
git merge-base --is-ancestor "${COMMIT}" origin/main || {
  echo "O commit solicitado não pertence ao histórico publicado de origin/main."
  exit 1
}
git switch --detach --quiet "${COMMIT}"
[[ "$(git rev-parse HEAD)" == "${COMMIT}" ]] || { echo "A VM2 não alcançou o commit aprovado."; exit 1; }
[[ -z "$(git status --porcelain --untracked-files=normal)" ]] || { echo "O checkout aprovado não ficou limpo."; exit 1; }
echo "VM2 posicionada exatamente no commit aprovado ${COMMIT}."
