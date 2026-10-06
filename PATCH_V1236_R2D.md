# Patch V1.23.6 R2D

## Incidente

A R2C removeu corretamente a espera circular e permitiu que a migração
construísse os índices. O registro final da revisão falhou porque o nome usado
pela 0031 tinha 34 caracteres, enquanto a tabela histórica `alembic_version`
aceita no máximo 32.

## Correção

- identificador encurtado para `0031_v123_latest_snapshot_idx`, com 29
  caracteres;
- arquivo de migração renomeado de forma correspondente;
- operações e índices da 0031 permanecem inalterados;
- teste novo valida o tamanho de todas as revisões Alembic.

O staging continua isolado e a produção não foi alterada.
