# Instalação e homologação — V1.23.7 R2

## 1. Windows PowerShell

Na pasta extraída, valide:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

Resultado esperado: `Pacote validado. Nenhum arquivo foi enviado.`

Depois de autorização expressa, publique:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

## 2. VM Ubuntu — ambiente de teste

```bash
cd ~/invest
```

```bash
./deployment/update-staging-from-github.sh
```

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Resultado esperado: versão `1.23.7`, ambiente `staging`, banco `reachable`,
migração `0032_v1237_browser_perf` e HTTP 200.

## 3. Testes

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 tests_v1231 tests_v1232 tests_v1233 tests_v1234 tests_v1235 tests_v1236 tests_v1237 -q -p no:cacheprovider
```

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 20 --warmup 2
```

Todos os testes devem passar e todas as rotas devem terminar em `OK`.

## 4. Homologação

Execute o roteiro de `RELATORIO_VALIDACAO_V1237_R2.md`. Verifique especialmente
a primeira abertura e o retorno a Carteira, Backtests, Finanças e Administração.

## 5. Promoção

Somente após aprovação expressa:

```bash
PROMOTION_LOG="$(mktemp /tmp/promocao-v1237-r2.XXXXXX.log)"; printf 'Log da promoção: %s\n' "$PROMOTION_LOG"
```

```bash
nohup ./deployment/promote-staging-to-production.sh >> "$PROMOTION_LOG" 2>&1 & echo "PID da promoção: $!"
```

```bash
tail -f "$PROMOTION_LOG"
```

Ao final, `/ready` deve informar versão `1.23.7`, ambiente `production`, migração
`0032_v1237_browser_perf` e HTTP 200.
