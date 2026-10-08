# Instalação e homologação — V1.23.7 R1

Execute comandos Windows apenas no PowerShell do computador e comandos Ubuntu
somente depois de entrar na VM por SSH.

## 1. Windows PowerShell — validar e publicar

Na pasta extraída do pacote:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

Resultado esperado: `Pacote validado. Nenhum arquivo foi enviado.`

Apó aprovação:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Resultado esperado: publicação concluída e orientação para validar a V1.23.7
R1 em `/testefdi`.

## 2. Ubuntu — atualizar o staging

```bash
cd ~/invest
```

```bash
./deployment/update-staging-from-github.sh
```

Espere a mensagem `Teste atualizado`. A nova migração é aplicada pelo serviço
isolado antes do staging iniciar.

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Resultado esperado: versão `1.23.7`, ambiente `staging`, banco `reachable`,
migração `0032_v1237_browser_perf` e HTTP 200.

## 3. Testes e desempenho do servidor

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 tests_v1231 tests_v1232 tests_v1233 tests_v1234 tests_v1235 tests_v1236 tests_v1237 -q -p no:cacheprovider
```

Resultado esperado: todos aprovados; avisos de depreciação não representam
falha.

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 20 --warmup 2
```

Resultado esperado: todas as linhas terminam em `OK`.

## 4. Validação visual

Use o roteiro de `RELATORIO_VALIDACAO_V1237_R1.md`. O retorno a um painel já
visitado deve ser imediato, preservando seu estado, enquanto aparece apenas o
indicador discreto de atualização.

## 5. Navegador real automatizado — opcional, recomendado

Esta etapa usa uma sessão Playwright autenticada e deve ser executada em uma
máquina de homologação com Chromium. Instale as dependências de
`requirements-browser.txt`, gere um `storage-state.json` da conta de teste e
execute:

```bash
python -m scripts.benchmark_browser_journeys --storage-state storage-state.json --samples 3 --output browser-performance-report.json
```

Resultado esperado: `"passed": true`. O arquivo de sessão é segredo temporário:
não o envie ao GitHub nem o inclua no pacote.

## 6. Promoção manual

Somente após aprovação expressa:

```bash
PROMOTION_LOG="$(mktemp /tmp/promocao-v1237-r1.XXXXXX.log)"; printf 'Log da promoção: %s\n' "$PROMOTION_LOG"
```

```bash
nohup ./deployment/promote-staging-to-production.sh >> "$PROMOTION_LOG" 2>&1 & echo "PID da promoção: $!"
```

```bash
tail -f "$PROMOTION_LOG"
```

Resultado esperado: backup confirmado, migração isolada verificada, aplicação
e worker saudáveis e staging estacionado. Saia do acompanhamento com `Ctrl+C`
somente depois da mensagem de conclusão.

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/ready
```

Resultado esperado: versão `1.23.7`, ambiente `production`, migração
`0032_v1237_browser_perf` e HTTP 200.
