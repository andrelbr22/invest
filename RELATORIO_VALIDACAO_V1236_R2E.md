# Relatório de validação — V1.23.6 R2E

## Critérios automatizados

- resultados com `date`, `datetime`, `Decimal`, UUID, conjuntos e valores não
  finitos persistem como JSON seguro;
- uma desconexão SMTP transitória provoca exatamente uma nova tentativa;
- fonte diária bem-sucedida não fica vencida antes do próximo horário real;
- cobertura multiativo não cobra componentes que os pipelines não produzem;
- retenção local aparece somente depois do upload confirmado, valida cada
  caminho e confirma a cópia remota específica antes de removê-lo.

## Homologação necessária na Oracle

1. suíte completa sem falhas;
2. todas as metas p50/p95 aprovadas;
3. monitor ALB concluído como `succeeded`;
4. snapshots principais válidos;
5. três backups locais após uma promoção com upload confirmado;
6. produção condicionada à aprovação manual.

## Resultado local

- testes direcionados: `17 passed`;
- suíte completa: `483 passed, 1 warning`;
- validação do pacote: obrigatória antes da publicação;
- benchmark e integrações externas: permanecem obrigatórios no staging.
