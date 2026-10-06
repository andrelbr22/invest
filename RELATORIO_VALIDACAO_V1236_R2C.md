# Relatório de validação — V1.23.6 R2C

## Resultado anterior

- código R2B baixado e imagem construída corretamente;
- banco isolado de staging restaurado;
- produção preservada;
- migração interrompida de forma segura por `LockNotAvailable` ao criar o
  primeiro índice concorrente;
- staging corretamente mantido parado.

## Critérios da R2C

1. trava consultiva adquirida em conexão `AUTOCOMMIT`;
2. migração concluída em `0031_v1_23_latest_snapshot_indexes`;
3. quatro índices prontos e válidos;
4. ciclo de métricas completo com uma tentativa por lote;
5. cobertura integral, testes e benchmark aprovados;
6. logs sem `lock timeout`, `statement timeout` ou falha de trabalho.
