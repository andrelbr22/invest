# Instruções Oracle — V1.23.8 R1

Execute comandos de Windows somente no PowerShell e comandos Linux somente
depois de entrar na VM por SSH. Não copie o texto do prompt.

## 1. Publicar pelo Windows PowerShell

Na pasta extraída do pacote:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

Resultado esperado: `Pacote validado. Nenhum arquivo foi enviado.`

Depois da aprovação explícita:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Resultado esperado: publicação concluída e orientação para validar a V1.23.8
R1 em `/testefdi`.

## 2. Atualizar o staging na VM

```bash
cd ~/invest
```

```bash
./deployment/update-staging-from-github.sh
```

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Resultado esperado: versão `1.23.8`, ambiente `staging`, banco `reachable`,
migração `0032_v1237_browser_perf` e HTTP 200.

## 3. Suíte e benchmark interno

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 tests_v1231 tests_v1232 tests_v1233 tests_v1234 tests_v1235 tests_v1236 tests_v1237 tests_v1238 -q -p no:cacheprovider
```

Resultado esperado: todos os testes aprovados; avisos de bibliotecas não são
falhas.

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 20 --warmup 2
```

Resultado esperado: todas as rotas com `OK`.

## 4. Roteiro visual obrigatório

Em `https://formacaodoinvestidor.com.br/testefdi/`:

1. entre como proprietário;
2. abra Mercado e Análises, selecione filtros e um ativo;
3. alterne por Carteira, Finanças, Backtests e Administração;
4. retorne a Mercado e Análises e confirme retorno imediato, filtros e posição;
5. abra Alertas, digite ao menos três letras e confirme sugestões rápidas;
6. use voltar/avançar do navegador e confirme a restauração do painel;
7. confirme fórmulas, permissões, operações de escrita e dados já existentes.

## 5. Benchmark Chromium autenticado

Primeiro, na VM Ubuntu, consulte o commit aprovado:

```bash
cat .git/investment-staging-commit
```

Copie os 40 caracteres mostrados. Em uma pasta de trabalho separada no Windows
PowerShell, instale o executor do navegador e abra o staging para autenticar:

```powershell
python -m pip install -r .\requirements-browser.txt
```

```powershell
python -m playwright install chromium
```

```powershell
python -m playwright codegen --save-storage=browser-auth.json https://formacaodoinvestidor.com.br/testefdi/plataforma/
```

Entre como proprietário, espere o Dashboard abrir e feche a janela. Depois
substitua o valor abaixo pelo commit copiado da VM:

```powershell
$stagingCommit = "COLE_AQUI_OS_40_CARACTERES"
```

```powershell
python -m scripts.benchmark_browser_journeys --storage-state browser-auth.json --samples 5 --commit $stagingCommit --output browser-performance-report.json
```

```powershell
python -m scripts.verify_browser_performance_report browser-performance-report.json --expected-commit $stagingCommit
```

Resultado esperado: nove jornadas presentes, p95 de retorno até 1 segundo,
demais p95 até 4 segundos e relatório aprovado. Para tornar essa evidência um
bloqueio automático na VM, envie somente o relatório — nunca o arquivo
`browser-auth.json` — para `deployment/runtime/browser-performance-report.json`
e defina `FDI_REQUIRE_BROWSER_PERFORMANCE_REPORT=true` no ambiente que inicia a
promoção. A sessão contém credenciais temporárias e deve ficar fora do pacote e
do GitHub.

## 6. Promoção manual, somente após aprovação

```bash
PROMOTION_LOG="$(mktemp /tmp/promocao-v1238-r1.XXXXXX.log)"; printf 'Log da promoção: %s\n' "$PROMOTION_LOG"
```

```bash
nohup ./deployment/promote-staging-to-production.sh >> "$PROMOTION_LOG" 2>&1 & echo "PID da promoção: $!"
```

```bash
tail -f "$PROMOTION_LOG"
```

Saia do acompanhamento com `Ctrl+C` somente depois de aparecer a confirmação
de produção atualizada. Isso não interrompe a promoção em segundo plano.

## 7. Pós-validação

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/ready
```

```bash
docker compose -f docker-compose.oracle-web.yml ps
```

```bash
docker compose -f docker-compose.oracle-web.yml logs --since 30m app worker | grep -Ei "error|traceback|exception|background_job_failed|unhealthy|statement timeout" || echo "Nenhum erro encontrado na produção."
```

Resultado esperado: versão 1.23.8, HTTP 200, serviços de produção saudáveis e
nenhum erro novo. Depois de um período operacional medido, iniciar a R2 conforme
`PLANO_V1238_R2.md`.
