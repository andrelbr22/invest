# Relatório de correção — Backtests oficiais V1.20.7 R4

## Falha confirmada

A execução agendada `#21`, iniciada em 5 de setembro de 2026 às 00:14 (Brasília), terminou em 1 minuto e 11 segundos. O GitHub registrou `ProgrammingError` imediatamente depois de iniciar a migração `0017_v1_20_personal_finances`.

## Causa

O PostgreSQL usado pelo GitHub é vazio e descartável. A migração histórica `0001_v1_1` usa os modelos atuais e, por isso, já cria as estruturas mais recentes. Em seguida, a `0017` tentava criar novamente as colunas e tabelas financeiras. As migrações `0018` e `0019` apresentavam o mesmo risco.

Produção e staging não perderam dados: a falha ocorreu somente no banco temporário do executor do GitHub, antes do cálculo do primeiro ativo.

## Correções

1. O executor semanal cria diretamente o esquema atual no banco temporário.
2. Essa operação falha de forma segura se o banco não for exatamente `backtests_ci` em `localhost`.
3. A `0015` reconhece a chave estrangeira mesmo quando o banco escolhe outro nome; `0017`, `0018` e `0019` verificam tabelas, colunas e índices antes de alterar o banco.
4. O CI passa a validar todas as suítes atuais e uma migração completa em PostgreSQL 16 vazio.
5. O diagnóstico informa a etapa e o ativo sem expor credenciais.
6. As ações `checkout` e `setup-python` usam versões compatíveis com Node.js 24.

## Como retomar uma falha

No site, com a conta proprietária:

`Backtests` → `Rodadas oficiais` → `Detalhes` → `Reprocessar ativos pendentes ou com falha`.

Se nenhum ativo tiver sido entregue, todos serão reprocessados. Se parte da rodada já estiver concluída, somente ativos pendentes ou com execução falha serão enviados. Esse é o caminho preferido porque cria uma execução nova com o código corrigido e preserva entregas já aceitas.

O botão `Tentar novamente` apenas recarrega um painel. No GitHub, `Re-run jobs` executa o commit antigo da falha e, portanto, não deve ser a primeira escolha depois de uma correção de código.
