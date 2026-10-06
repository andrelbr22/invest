# Relatório de validação — V1.23.6 R2D

## Evidência

- a migração R2C superou a fase de criação concorrente dos índices;
- a falha ocorreu no `UPDATE alembic_version` por
  `StringDataRightTruncation`;
- o identificador anterior tinha 34 caracteres;
- a produção permaneceu intacta e o staging foi estacionado.

## Critérios de aceite

1. revisão `0031_v123_latest_snapshot_idx` registrada;
2. quatro índices descendentes prontos e válidos;
3. nenhuma revisão Alembic com mais de 32 caracteres;
4. ciclo de métricas concluído com uma tentativa por lote;
5. cobertura, testes, benchmark e homologação visual aprovados;
6. nenhum timeout ou trabalho falho nos logs novos.
