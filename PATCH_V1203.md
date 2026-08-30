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

## Revisão R5

A R5 corrige a coleta dos indicadores econômicos do Comparador histórico. As séries oficiais do Banco Central passam a ser consultadas em sequência, por uma conexão isolada e com validação do formato da resposta. Uma página HTML temporária recebida com HTTP 200 é repetida automaticamente e não fica mais armazenada como atualização vazia. Nenhuma série oficial foi substituída.

## Revisão R6

A R6 melhora somente a navegação temporal do Comparador histórico. O eixo horizontal passa a mostrar mês e ano em janelas de até cinco anos e somente anos em janelas maiores. A opção `Personalizar` permite escolher datas inicial e final dentro dos 20 anos já carregados, sem nova consulta ao servidor a cada alteração. Os períodos rápidos e o botão `Atualizar séries` permanecem disponíveis.

## Revisão R7

A R7 reorganiza as atualizações externas sem alterar tabelas de negócio nem excluir dados. Mercado, manchetes, comparador, catálogo, fundamentos, indicadores técnicos, cotações de carteiras e notícias passam pela fila persistente do PostgreSQL. O navegador recebe imediatamente o último resultado válido e não espera a fonte externa.

O agendador separa as fontes por necessidade: cripto a cada 30 minutos, câmbio a cada duas horas, dados globais e juros em duas rodadas, macro e Focus em uma rodada, além de catálogo, fundamentos e técnica em horários próprios. Somente ativos presentes em carteiras ou alertas recebem consulta intradiária de 15 em 15 minutos durante o pregão. Não há repetição intradiária atrasada à noite ou em fins de semana.

Cada painel mostra fonte, estado, última atualização e próxima rodada. Falhas parciais preservam o campo anterior e são identificadas sem apagar as demais fontes. Todos os botões manuais respeitam intervalo mínimo de cinco minutos.

Em produção, o worker passa a ser permanente e também executa o monitor de alertas. Ele tem concorrência unitária, pool de uma conexão e limite de memória. O processo web não executa esses monitores. Em staging, um worker interno processa apenas os pedidos de homologação, sem manter outro contêiner. A promoção verifica aplicação e worker e restaura ambos em caso de falha.
