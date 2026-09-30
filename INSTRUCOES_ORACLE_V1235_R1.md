# Instruções Oracle • V1.23.5 R1

A publicação deve seguir o fluxo existente: validar o pacote no Windows,
enviar ao GitHub, atualizar somente o staging e homologar antes da promoção.

## Regressão

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 tests_v1231 tests_v1232 tests_v1233 tests_v1234 tests_v1235 -q -p no:cacheprovider
```

## Benchmark

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 20 --warmup 2
```

Após pelo menos 20 aberturas reais dos painéis, conferir em
Administração > Operação os p50/p95 de `panel_dashboard`,
`panel_analysis` e `panel_portfolio`.

