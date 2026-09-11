# Instruções Oracle — V1.22.1

## Atualizar somente o ambiente de teste

```bash
cd ~/invest
./deployment/update-staging-from-github.sh
```

Esperado: construção concluída, banco de teste copiado da produção e contêiner de staging saudável.

## Validar disponibilidade e migração

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Esperado: versão `1.22.1`, ambiente `staging`, banco `reachable`, migração `0023_v1_22_screener_performance` e HTTP 200.

## Executar regressão

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 -q -p no:cacheprovider
```

Esperado: todos os testes aprovados; avisos de depreciação das bibliotecas não são falhas.

## Confirmar índices no staging

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT indexname FROM pg_indexes WHERE indexname IN ('ix_assets_type_active_ticker','ix_fundamental_latest_lookup','ix_technical_latest_lookup','ix_score_latest_lookup') ORDER BY indexname;"
```

Esperado: quatro linhas.

## Medir as consultas sem depender do navegador

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python - <<'PY'
from time import perf_counter
from investment_engine.core.models.strategy import StockFilterSet
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.infrastructure.db.session import get_session_factory

session = get_session_factory()()
try:
    repository = AssetRepository(session)
    checks = (
        ("Ações — filtro padrão", lambda: repository.screen_latest_stocks(
            StockFilterSet(
                roe_min=8, ebit_margin_min=5, pe_min=0.1, pe_max=20,
                pbv_max=5, current_ratio_min=1, daily_liquidity_min=1_000_000,
            ), limit=50,
        )),
        ("ETFs — universo", lambda: repository.latest_universe("etf", limit=50)),
        ("FIIs — universo", lambda: repository.latest_universe("fii", limit=50)),
    )
    for label, operation in checks:
        started = perf_counter()
        rows = operation()
        elapsed = perf_counter() - started
        print(f"{label}: {len(rows)} ativos em {elapsed:.3f}s")
finally:
    session.close()
PY
```

Esperado: nenhuma consulta atinge 12 segundos. Registre os tempos; a meta inicial é ficar abaixo de 3 segundos na VM atual, admitindo uma primeira leitura fria um pouco maior.

## Confirmar que a pilha antiga não pode retornar

```bash
bash deployment/quiesce-legacy-stack.sh
```

```bash
docker inspect -f '{{.Name}} | execução={{.State.Running}} | reinício={{.HostConfig.RestartPolicy.Name}}' invest-app-1 invest-postgres-1 invest-proxy-1
```

Esperado: `execução=false` e `reinício=no` nos três. Nenhum volume ou dado é removido.

## Homologação visual obrigatória

Em `https://formacaodoinvestidor.com.br/testefdi/plataforma/`:

1. abrir Mercado e Análises > Ações e confirmar a lista;
2. alternar entre Ações, FIIs, ETFs, BDRs e Futuros;
3. voltar a uma aba já visitada e confirmar carregamento imediato pelo cache;
4. confirmar que os sinais de backtest aparecem depois da lista sem bloquear a navegação;
5. aplicar um filtro avançado e abrir o detalhe de um ativo;
6. validar Painel de Mercado, Carteira, Alertas, Notícias, Backtests, Finanças e Administração.

## Promover somente após aprovação explícita

```bash
./deployment/promote-staging-to-production.sh
```

Depois valide:

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/ready
```

Esperado: versão `1.22.1`, ambiente `production`, migração `0023_v1_22_screener_performance` e HTTP 200.
