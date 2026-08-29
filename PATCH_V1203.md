# Patch V1.20.3

## Revisão R1

O patch altera a API de filtros salvos, o screener avançado, a interface, os estilos e os testes. Análises personalizadas antigas permanecem legíveis; as novas usam o esquema de configuração 2 para preservar todos os critérios.

A R1 acrescenta a migração `0013_v1_20_backtest_study`, que cria somente um índice de desempenho em `backtest_runs`. Nenhum resultado de backtest é alterado ou excluído.

## Revisão R2

A R2 mantém a mesma API e migração, mas traduz a apresentação das configurações de backtest. Objetos aninhados deixam de aparecer como JSON, códigos internos recebem rótulos em português e campos vazios, booleanos, percentuais e períodos passam a ter descrições compreensíveis.

## Revisão R3

A R3 acrescenta a migração `0014_v1_20_backtest_chunks`. Ela cria a tabela de controle `backtest_batch_chunks`, sem alterar nem excluir resultados existentes. Cada parte recebida possui posição, total, checksum e contadores próprios. A restrição única por rodada, ativo e posição impede duplicações.

O workflow mantém as execuções de sábado direcionadas à produção e encaminha repetições iniciadas no ambiente de teste para `/testefdi`. A produção não recebe o novo protocolo antes da promoção manual.

## Revisão R4

A R4 altera somente o Painel de Mercado, seus estilos, o catálogo do Comparador histórico e os testes. Não cria migração e não altera dados persistidos. IMA-B e IRF-M ficam claramente marcados como proxies de ETFs porque o histórico integral licenciado da ANBIMA não é apresentado como uma série pública direta. As demais fontes e todas as correções das revisões anteriores permanecem preservadas.
