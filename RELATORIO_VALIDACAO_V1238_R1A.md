# Relatório de validação — V1.23.8 R1A

## Falhas observadas no staging

- `test_analysis_renders_rows_before_loading_backtest_leaders`;
- `test_catalog_prefetch_and_inflight_get_dedup_do_not_block_first_panel`.

As duas falhas eram incompatibilidades de testes baseados em texto. A
implementação continuava renderizando antes do enriquecimento e deduplicando
requisições GET simultâneas.

## Resultado da correção

- a ordem cache limitado → renderização → enriquecimento foi validada;
- a chave de deduplicação por caminho e chave lógica foi validada;
- nenhuma alteração de produção ou migração foi necessária;
- a suíte completa deve ser repetida no contêiner Linux do staging.
