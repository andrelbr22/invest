# Formação do Investidor • V1.17.0

Plataforma educacional de análise fundamentalista e técnica, carteiras,
alertas, dados de mercado e backtests. A aplicação é hospedada na Oracle
Cloud, usa FastAPI, PostgreSQL e uma interface web própria.

## Destaques

- painel de mercado com fontes identificadas, cache persistente e atualização em segundo plano;
- ações, FIIs, ETFs, BDRs e futuros organizados em abas;
- filtros fundamentalistas e técnicos combináveis;
- preço justo de Graham, preço-teto de dividendos e porte da empresa;
- pivôs clássicos PP, S1–S3 e R1–R3, RSI, tendências e volume/média 9;
- três melhores backtests e sinal atual por ativo;
- carteiras e permissões isoladas por conta Google;
- comparação de até três estratégias para até 30 ativos, conforme autorização;
- limites individuais de ativos e solicitações diárias de backtest;
- alertas de preço e variação enviados por e-mail;
- ambiente de teste isolado em `/testefdi/` e promoção manual para produção.

## Publicação segura

O GitHub atualiza automaticamente apenas o ambiente de teste:

`https://formacaodoinvestidor.com.br/testefdi/`

Depois da validação do proprietário, a versão testada é promovida
manualmente para:

`https://formacaodoinvestidor.com.br/`

As credenciais, o banco e os backups permanecem somente no servidor. Consulte
`INSTRUCOES_ORACLE_V1170.md` para a primeira migração.

## Segurança e escopo

O projeto não constitui recomendação de investimento. Resultados de filtros,
notícias, cotações e backtests devem ser verificados antes de qualquer decisão.
