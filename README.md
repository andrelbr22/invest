# Formação do Investidor • V1.22.1

O escopo, as invariantes e a sequência completa da linha V1.20 estão documentados em `GUIA_MESTRE_V1.20.md`. A auditoria de valoração, filtros e backtests da V1.21 está em `RELATORIO_AUDITORIA_VALUATION_E_BACKTESTS_V1210.md`.

## Desempenho e estabilidade V1.22.1

A V1.22.1 elimina a varredura integral dos históricos no screener, acrescenta índices próprios para localizar o snapshot mais recente e mostra a lista antes de carregar os sinais complementares de backtests. Consultas simultâneas são reaproveitadas, o cache deixa de ser apagado por simples pedidos de atualização e a produção recebe prioridade de recursos sobre staging e tarefas de fundo.

A pilha anterior é reconhecida por seus rótulos e mantida parada, sem exclusão de volumes ou dados. Consulte `V1_22_1.md`, `RELATORIO_DESEMPENHO_VM1_V1220.md` e `INSTRUCOES_ORACLE_V1221.md` para homologação e medição.

## Portal, duas instâncias e observabilidade V1.22.0

A raiz do domínio agora é um portal editorial que apresenta a Plataforma de Investimentos e sete livros. A aplicação autenticada permanece integral em `/plataforma/`; staging usa `/testefdi/` e `/testefdi/plataforma/`.

A camada pesada pode operar em uma segunda VM Oracle sem duplicar o banco: Caddy, FastAPI, staging e o único PostgreSQL permanecem na VM1; somente o worker vai para a VM2 através da rede privada. Leases no PostgreSQL asseguram um scheduler e um monitor de alertas, enquanto heartbeat, incidentes, recursos e p50/p95 aparecem em `Administração > Operação`.

Consulte `V1_22_0.md`, `ARQUITETURA_DUAS_INSTANCIAS_V1220.md` e `INSTRUCOES_ORACLE_V1220.md` antes do primeiro corte. O procedimento de retorno à VM principal é obrigatoriamente testado antes de considerar a migração concluída.

## Administração, alertas e notícias V1.21.3

A V1.21.3 acrescenta uma camada operacional completa sem remover os recursos homologados:

- interface integral de alertas com cadastro, edição, pausa, reativação, destinatários, teste de e-mail e histórico;
- B3 monitorada a cada 5 minutos no horário do pregão e demais mercados a cada 30 minutos continuamente;
- notícias da carteira e notícias de recomendações em áreas distintas, atualizadas uma vez ao dia já no primeiro acesso autenticado e sem bloquear a navegação;
- níveis compartilhados Convidado, Acesso básico, Membro e Membro VIP, com todas as permissões e limites administráveis em um único lugar;
- atribuição individual ou em lote, busca, filtros, paginação e preservação das permissões antigas até que um nível seja escolhido;
- console com as 13 rotinas automáticas, atualização manual por grupo ou completa, monitor de alertas e fila de trabalhos com reprocessamento seguro.

## Valoração e backtests V1.21

A V1.21.3 preserva os módulos homologados da V1.20.7 e toda a base de valoração da V1.21.2, sem preencher lacunas com estimativas silenciosas. Além dos cenários visíveis e presets técnicos nas cinco classes, permanecem ativas referências de valor próprias para ETFs, BDRs e futuros quando os insumos observáveis estiverem disponíveis:

- quatro famílias combináveis de valoração: Número de Graham, preço-teto por dividend yield-alvo, valuation relativo por pares e valor econômico por classe;
- cenários conservador, base e otimista, qualidade da amostra, premissas visíveis e estado `N/D` quando faltarem dados;
- aplicação correta por classe: ETF usa NAV e prêmio/desconto ao NAV; BDR usa P/VP de pares do mesmo setor/indústria e só calcula paridade com lastro, câmbio e razão verificados; futuro usa contrato frontal, vencimento, preço à vista e custo de carregamento;
- estado `N/D` individual e explicado quando um ativo não possui o insumo próprio, sem reutilizar fórmulas de empresas em fundos ou derivativos;
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

A plataforma autenticada fica em `/plataforma/` nos dois ambientes.

As credenciais, o banco e os backups permanecem somente no servidor. Consulte
`INSTRUCOES_ORACLE_V1221.md` para a homologação desta versão.

## Segurança e escopo

O projeto não constitui recomendação de investimento. Resultados de filtros,
notícias, cotações e backtests devem ser verificados antes de qualquer decisão.
