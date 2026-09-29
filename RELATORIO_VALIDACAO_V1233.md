# Relatório de validação — V1.23.3

## Itens automatizados

- [x] validação local do pacote;
- [x] suíte completa até `tests_v1233`: 368 testes aprovados;
- [x] sintaxe Python;
- [x] sintaxe JavaScript;
- [x] ausência de caches, logs, diagnósticos e segredos;
- [ ] `/testefdi/ready` em HTTP 200;
- [ ] benchmark p50/p95 dentro das metas;
- [ ] cobertura integral de `asset_current_metrics`;
- [ ] worker, scheduler e monitor saudáveis.

Os dois avisos locais são depreciações conhecidas de Authlib/httpx e
FastAPI/Starlette. Não houve falha funcional.

## Itens funcionais

- [ ] Painel de Mercado;
- [ ] Mercado e Análises para todas as classes;
- [ ] listas Padrão, FDI e ALB;
- [ ] detalhe do ativo;
- [ ] Minha Carteira;
- [ ] Backtests;
- [ ] Administração;
- [ ] portal e autenticação.

## Critérios de reversão

Não promover se houver divergência de resultados, perda de cobertura,
trabalho repetidamente falho, regressão no benchmark ou qualquer alteração
indevida dos históricos. A produção da V1.23.2 deve permanecer intacta até a
aprovação manual.
