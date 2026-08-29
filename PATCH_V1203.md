# Patch V1.20.3

## Revisão R1

O patch altera a API de filtros salvos, o screener avançado, a interface, os estilos e os testes. Análises personalizadas antigas permanecem legíveis; as novas usam o esquema de configuração 2 para preservar todos os critérios.

A R1 acrescenta a migração `0013_v1_20_backtest_study`, que cria somente um índice de desempenho em `backtest_runs`. Nenhum resultado de backtest é alterado ou excluído.

## Revisão R2

A R2 mantém a mesma API e migração, mas traduz a apresentação das configurações de backtest. Objetos aninhados deixam de aparecer como JSON, códigos internos recebem rótulos em português e campos vazios, booleanos, percentuais e períodos passam a ter descrições compreensíveis.
