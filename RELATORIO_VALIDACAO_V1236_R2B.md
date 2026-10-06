# Relatório de validação — V1.23.6 R2B

## Evidência que motivou a revisão

- o ciclo R2A avançou, mas diversos lotes exigiram duas ou três tentativas;
- alguns lotes de cinquenta ativos levaram vários minutos;
- os logs registraram `QueryCanceled: canceling statement due to statement
  timeout` em `latest_current_sources_batch`;
- não houve nova ocorrência primária de `QueuePool`,
  `InFailedSqlTransaction` ou falha SMTP operacional.

## Critérios obrigatórios

1. migração final `0031_v1_23_latest_snapshot_indexes`;
2. quatro índices R2B válidos no PostgreSQL;
3. ciclo novo concluído sem retentativa e sem erro de navegação;
4. cobertura integral das métricas, valorações e pódios;
5. suíte oficial integral aprovada;
6. benchmark dentro das metas;
7. logs posteriores à implantação sem `statement timeout`, falha de trabalho,
   pool esgotado ou transação abortada.

A promoção deve permanecer bloqueada se qualquer item divergir.
