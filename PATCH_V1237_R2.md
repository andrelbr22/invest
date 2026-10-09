# Patch V1.23.7 R2 — carregamento modular progressivo

## Alterações

- reduz o JavaScript inicial de aproximadamente 338 KB para 178 KB;
- move Carteira, Backtests, Finanças e Administração para quatro arquivos
  independentes;
- baixa cada módulo somente quando a área correspondente é aberta;
- antecipa o download ao passar o mouse ou navegar pelo teclado sobre a área;
- reúne solicitações simultâneas do mesmo módulo;
- permite nova tentativa automática depois de falha de rede;
- mostra carregamento ou erro claro, nunca um painel vazio;
- preserva o cache seletivo, URLs, filtros, rolagem e painéis aquecidos da R1.

## Segurança

- nenhuma fórmula, fonte, permissão ou rota foi removida;
- nenhuma tabela ou migração foi alterada;
- os módulos usam exatamente as funções anteriormente contidas em `app.js`;
- a produção continua dependendo de aprovação manual.
