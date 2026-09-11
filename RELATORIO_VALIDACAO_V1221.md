# Relatório de validação — V1.22.1

## Causa confirmada

O PostgreSQL cancelava `/screen/db/stocks/default` após 12 segundos. A consulta aplicava `row_number()` sobre aproximadamente 107 mil snapshots para então devolver até 50 ativos. Ao mesmo tempo, uma pilha antiga consumia CPU e a interface aguardava também o leaderboard de backtests antes de mostrar a lista.

## Correções validadas

- semântica do snapshot mais recente preservada em ações e demais classes;
- timeframe técnico diário preservado;
- ativos sem snapshots permanecem no universo quando aplicável;
- nenhuma janela global permanece nas consultas do screener;
- índices da migração correspondem às colunas consultadas;
- lista principal renderizada antes dos backtests;
- cache, coalescimento e proteção contra respostas atrasadas testados;
- pilha legada pausada somente após validação simultânea de projeto, pasta, arquivo Compose e serviço;
- limites e prioridades dos cinco serviços verificados.

## Resultado local

Foram aprovados 224 testes. A compilação Python, a sintaxe JavaScript e a migração integral desde banco vazio até `0023_v1_22_screener_performance` também passaram. A homologação Oracle deve medir a consulta no banco de staging e validar visualmente todas as classes de ativos.
