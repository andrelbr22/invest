# Patch V1.23.4

## Backtests oficiais

O repositório de resultados passou a formar o pódio em três etapas: execução
mais recente por configuração, melhor configuração por estratégia e três
estratégias por ativo. Isso elimina repetições como três linhas idênticas para
ABEV3 e evita que um limite global exclua ativos solicitados.

O novo endpoint do proprietário informa a próxima liberação e inicia a rodada
completa. Uma rodada ativa ou criada há menos de 12 horas retorna conflito sem
despachar outro workflow.

## Valorações nas listagens

As listas rápidas agora publicam `dividend_yield_ceiling_value` e o respectivo
potencial, mantendo os nomes legados para compatibilidade. O valor relativo é
enriquecido com dados já persistidos no PostgreSQL, sem consulta externa na
navegação e sem mudar filtros, ordenação ou limite da lista.

## Interface e compatibilidade

O antigo identificador `best_signal` permanece aceito no armazenamento, mas é
expandido para `backtest_1`, `backtest_2` e `backtest_3` nas respostas. Os
arquivos CSS e JavaScript da plataforma receberam o token de cache
`1.23.4-r1`; os ativos do portal público não foram alterados.
