# Formação do Investidor • V1.21.1

O escopo, as invariantes e a sequência completa da linha V1.20 estão documentados em `GUIA_MESTRE_V1.20.md`. A auditoria de valoração, filtros e backtests da V1.21 está em `RELATORIO_AUDITORIA_VALUATION_E_BACKTESTS_V1210.md`.

## Valoração e backtests V1.21

A V1.21.1 preserva os módulos homologados da V1.20.7 e acrescenta controles auditáveis, sem preencher lacunas de dados com estimativas silenciosas. Esta revisão também torna os cenários visíveis, libera presets técnicos honestos nas cinco classes e reduz consultas repetidas ao trocar de painel:

- quatro famílias combináveis de valoração: Número de Graham, preço-teto por dividend yield-alvo, valuation relativo por pares e valor econômico por classe;
- cenários conservador, base e otimista, qualidade da amostra, premissas visíveis e estado `N/D` quando faltarem dados;
- aplicação correta por classe: ações e FIIs recebem apenas os métodos compatíveis; ETFs, BDRs e futuros ficam em `N/D` até existirem NAV, composição, lastro/câmbio ou dados de carry apropriados;
- permissões independentes para as quatro famílias, com herança automática completa para usuários ALB;
- 13 estratégias de backtest, incluindo Supertrend ATR, Momentum dual relativo e Bollinger Squeeze com rompimento;
- filtros comuns de tendência, volume, RSI, ADX, ATR, MACD, Bandas de Bollinger, força relativa, liquidez, pivôs e fundamentos históricos ponto no tempo;
- validação forte de parâmetros, execução no pregão seguinte ao sinal, preços ajustados, benchmark por classe e separação entre ação atual e posição da estratégia;
- grade oficial determinística e equilibrada, mantendo o limite de 200 combinações por ativo.

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
- worker separado e permanente, com concorrência unitária, agendador próprio e apenas uma conexão reservada ao PostgreSQL;
- snapshots compartilhados que preservam o último resultado válido;
- catálogo e observações de séries econômicas com horário de publicação;
- endpoint `/ready`, request ID e logs de duração;
- pool PostgreSQL limitado e `statement_timeout` configurável;
- descoberta corrigida de todos os diretórios de testes versionados.

Após a homologação da R7, o worker passa a integrar a produção e executa somente tarefas de segundo plano. O processo web não coleta mercado, notícias nem alertas durante uma resposta interativa:

```text
docker compose -f docker-compose.oracle-web.yml up -d worker
```

Plataforma educacional de análise fundamentalista e técnica, carteiras,
alertas, dados de mercado e backtests. A aplicação é hospedada na Oracle
Cloud, usa FastAPI, PostgreSQL e uma interface web própria.

## Destaques

- painel de mercado com fontes identificadas, cache persistente e atualização em segundo plano;
- ações, FIIs, ETFs, BDRs e futuros organizados em abas;
- filtros fundamentalistas e técnicos combináveis;
- quatro famílias de valoração com cenários, qualidade, permissões e porte da empresa;
- pivôs clássicos PP, S1–S3 e R1–R3, RSI, tendências e volume/média 9;
- três melhores backtests e sinal atual por ativo;
- carteiras e permissões isoladas por conta Google;
- comparação e combinação de estratégias conforme os limites de autorização;
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
`INSTRUCOES_ORACLE_V1211.md` para a homologação desta versão.

## Segurança e escopo

O projeto não constitui recomendação de investimento. Resultados de filtros,
notícias, cotações e backtests devem ser verificados antes de qualquer decisão.
