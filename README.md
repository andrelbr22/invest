# Formação do Investidor • V1.20.3

O escopo, as invariantes e a sequência completa da linha V1.20 estão documentados em `GUIA_MESTRE_V1.20.md`.

## Fundação V1.20

A V1.20.3 preserva todas as funções da V1.17.4, a base assíncrona da V1.20.0, o Painel de Mercado da V1.20.2 e torna o painel Mercado e Análises explicável e personalizável:

- critérios completos e restauráveis das análises Padrão, FDI-CNPI e ALB;
- análises personalizadas que preservam filtros fundamentalistas, técnicos, de universo e de valoração;
- guia integrado com conceitos, fórmulas, médias e composição das notas;
- três melhores estratégias de backtest e sinal atual por ativo;
- continuidade do painel quando a consulta externa da composição do IBOV estiver temporariamente indisponível.
- estudo de backtests com consulta enxuta e configurações inspecionáveis, sem carregar curvas completas desnecessariamente.
- parâmetros, filtros, premissas e métricas dos estudos apresentados em português, sem JSON ou códigos internos na interface.
- rodadas oficiais entregues em partes autenticadas e idempotentes, evitando o limite HTTP 413 sem perder curvas ou operações.
- detalhes de falha, progresso por partes e repetição apenas dos ativos pendentes no painel do proprietário.
- Mercados globais reorganizados e Comparador histórico com 26 séries em ordem estável, opções separadas e proxies claramente identificados.

A fundação para atualizações sem bloquear o usuário continua disponível:

- fila persistente PostgreSQL com idempotência, lease, heartbeat e novas tentativas;
- worker separado, ativado por profile e com concorrência inicial unitária;
- snapshots compartilhados que preservam o último resultado válido;
- catálogo e observações de séries econômicas com horário de publicação;
- endpoint `/ready`, request ID e logs de duração;
- pool PostgreSQL limitado e `statement_timeout` configurável;
- descoberta corrigida de todos os diretórios de testes versionados.

O worker é opcional nesta primeira etapa e não altera o fluxo atual de produção até a homologação:

```text
docker compose -f docker-compose.oracle-web.yml --profile worker up -d worker
```

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
