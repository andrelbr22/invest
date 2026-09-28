# Homologação Oracle — V1.23.2

Execute comandos Windows somente no PowerShell local. Execute comandos Linux
somente depois de entrar por SSH na VM Oracle.

## 1. Publicação no GitHub (PowerShell local)

Na pasta extraída do pacote:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

Esperado: `Pacote validado. Nenhum arquivo foi enviado.`

Após aprovação explícita:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Esperado: publicação concluída e orientação para validar `/testefdi`.

## 2. Atualização do staging (VM Oracle)

```bash
cd ~/invest
```

```bash
./deployment/update-staging-from-github.sh
```

Esperado: migração isolada, staging saudável, proxy recarregado e URL de teste.

```bash
curl -sS -w '\nHTTP %{http_code}\n' https://formacaodoinvestidor.com.br/testefdi/ready
```

Esperado: versão `1.23.2`, ambiente `staging`, banco `reachable`, migração
`0029_v1_23_current_metrics` e HTTP 200.

## 3. Regressão

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 tests_v1231 tests_v1232 -q -p no:cacheprovider
```

Esperado: todos os testes aprovados; avisos de depreciação não são falhas.

## 4. Acompanhar o preenchimento das métricas atuais

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT status, attempts, message, updated_at FROM background_jobs WHERE job_type='current_metrics_refresh' ORDER BY created_at DESC LIMIT 5;"
```

Esperado: lotes `succeeded` ou um lote atual `queued/running`. Nenhum lote deve
ficar em `failed`.

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT COUNT(*) AS ativos_atuais, COUNT(*) FILTER (WHERE technical_features_json <> '{}'::json) AS tecnicos_precalculados FROM asset_current_metrics;"
```

Esperado: a primeira contagem cresce até cobrir o catálogo. Ativos sem histórico
podem legitimamente não ter recursos técnicos.

## 5. Benchmark obrigatório

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 20 --warmup 2
```

Esperado: rotas com HTTP 200 e metas p50/p95 aprovadas. A promoção repete esta
verificação antes de tocar a produção.

## 6. Homologação visual

Validar em `https://formacaodoinvestidor.com.br/testefdi/`:

- Painel de Mercado, screener 50/100 e detalhe de ativo;
- filtros Padrão, FDI e ALB;
- notícias e composição do IBOV sem espera de provedor externo;
- Administração > Atualizações, incluindo `Composição do Ibovespa` e
  `Métricas atuais pré-calculadas`;
- backtests, alertas, carteira, finanças, portal e login.

## 7. Promoção aprovada

Somente após aprovação explícita:

```bash
./deployment/promote-staging-to-production.sh
```

Esperado: benchmark, backup, migração isolada, aplicação, recarga do proxy,
worker e enfileiramento das métricas atuais concluídos.

```bash
curl -sS -w '\nHTTP %{http_code}\n' https://formacaodoinvestidor.com.br/ready
```

Esperado: versão `1.23.2`, ambiente `production`, banco `reachable`, migração
`0029_v1_23_current_metrics` e HTTP 200.

## 8. Segunda VM

O pacote deixa toda a automação pronta, mas não cria recursos OCI sem
autorização. Antes do corte real ainda será necessário informar/criar VM2,
subnet/NSG, IPs privados e chave SSH. Depois disso, seguir
`ARQUITETURA_DUAS_INSTANCIAS_V1220.md` e executar primeiro o preflight, depois
um cutover e um failback documentado. Não mover o staging antes de uma semana
estável.

