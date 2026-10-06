# Formação do Investidor • V1.23.6

## R2C — coordenação sem bloquear o índice concorrente

A V1.23.6 R2C corrige a espera circular observada na primeira instalação da
R2B. A trava que impede duas migrações simultâneas continua ativa, mas sua
conexão passa a operar em autocommit e deixa de manter um snapshot de transação
aberto. Assim, o `CREATE INDEX CONCURRENTLY` pode concluir normalmente.

A versão, os quatro índices e a revisão esperada permanecem os mesmos da R2B:
`1.23.6` e `0031_v1_23_latest_snapshot_indexes`. Consulte
`PATCH_V1236_R2C.md`, `INSTRUCOES_ORACLE_V1236_R2C.md` e
`RELATORIO_VALIDACAO_V1236_R2C.md`.

## R2B — leitura rápida do último snapshot

A V1.23.6 R2B preserva integralmente a R2A e corrige o gargalo identificado
na homologação real. A materialização deixa de ordenar e numerar todo o
histórico de cada lote para localizar o registro mais recente. No PostgreSQL,
ela passa a usar `DISTINCT ON` sobre índices descendentes específicos para
fundamentos, técnicos, scores e preços.

A migração `0031_v1_23_latest_snapshot_indexes` é somente aditiva, mantém
todos os históricos e cria os novos índices de forma concorrente. Consulte
`PATCH_V1236_R2B.md`, `INSTRUCOES_ORACLE_V1236_R2B.md` e
`RELATORIO_VALIDACAO_V1236_R2B.md`.

## R2A — estabilidade do processamento em homologação

A V1.23.6 R2A mantém integralmente as melhorias da R2 e corrige a disputa por
conexões observada durante a homologação completa. O staging passa a dispor de
conexões suficientes para API, consumidor, lease e heartbeat; notificações
operacionais externas ficam desativadas nesse ambiente isolado.

As projeções de valuation e pódios agora usam pontos de restauração próprios.
Uma falha transitória deixa de invalidar toda a transação e o último resultado
válido permanece disponível. O envio SMTP possui timeout menor e sua falha não
derruba o ciclo de saúde do worker. Não há migração nova: a revisão esperada
continua sendo `0030_v1_23_navigation_metrics`. Consulte
`PATCH_V1236_R2A.md`, `INSTRUCOES_ORACLE_V1236_R2A.md` e
`RELATORIO_VALIDACAO_V1236_R2A.md`.

## R2 — alternância de painéis sem recarga desnecessária

A V1.23.6 R2 atua diretamente no atraso percebido ao trocar de área. Clicar
novamente no painel ou na aba já ativa deixa de cancelar pedidos e reiniciar a
renderização. Consultas avançadas de leitura deixam de apagar o cache das
demais telas, enquanto Notícias e Administração reutilizam por alguns segundos
uma resposta concluída; os botões explícitos de atualizar continuam buscando
dados novos imediatamente.

No servidor, a lista de backtests não transporta curvas e resultados completos,
o Dashboard consulta somente pequenos metadados das rotinas que não exibe e a
Carteira reaproveita o snapshot intradiário já carregado. Antes do benchmark, a
promoção agora exige cobertura materializada de 100% dos ativos ativos para
impedir que a navegação dependa dos fallbacks históricos mais caros.

Não há migração nova. A revisão esperada continua sendo
`0030_v1_23_navigation_metrics`. Consulte `PATCH_V1236_R2.md`,
`INSTRUCOES_ORACLE_V1236_R2.md` e `RELATORIO_VALIDACAO_V1236_R2.md`.

## R1 — velocidade conservadora sem perda funcional

A V1.23.6 R1 reduz consultas e trabalho visual repetidos sem mudar fórmulas,
permissões, filtros, contratos de API ou fontes de dados. A carteira passa a
buscar os preços de todas as posições em lote, mantendo a mesma ordem de
preferência e os mesmos fallbacks. A navegação multiativos usa projeções
compactas onde é seguro, e a verificação de cobertura deixa de contar tabelas
inteiras.

No navegador, o carregamento secundário dos três melhores backtests atualiza
somente suas células; a tabela já exibida não é reconstruída. Backtests,
Finanças e Administração também passam a registrar o tempo real percebido no
navegador. No Painel de Mercado, o antigo JSON monolítico permanece disponível
como recuperação, mas deixa de ser consultado quando os sete snapshots atuais
estão completos.

Não há migração de banco nesta revisão. A revisão esperada continua sendo
`0030_v1_23_navigation_metrics`. Consulte `V1_23_6.md`,
`PATCH_V1236_R1.md`, `INSTRUCOES_ORACLE_V1236_R1.md` e
`RELATORIO_VALIDACAO_V1236_R1.md`.

## Verificação de transição • V1.23.5 R2B

A R2B resolve o último caso de inicialização da promoção. Antes da troca da
aplicação, o contêiner de produção ainda executa a imagem anterior; agora ele
recebe pela entrada padrão o verificador do commit já aprovado no staging.
Assim, a checagem usa as regras R2A no banco e no ambiente reais da produção,
sem depender da cópia antiga existente dentro do contêiner.

Todas as verificações de unicidade, commit, nó, ambiente, scheduler, monitor e
leases permanecem fechadas em caso de divergência. Não há mudança funcional ou
de banco. Consulte `PATCH_V1235_R2B.md`, `INSTRUCOES_ORACLE_V1235_R2B.md` e
`RELATORIO_VALIDACAO_V1235_R2B.md`.

## Correção operacional segura • V1.23.5 R2A

A R2A corrige a validação final da promoção sem alterar telas, cálculos,
permissões ou o esquema do banco. O scheduler continua identificado pelo
serviço do worker, enquanto o monitor de alertas é validado pelo seu formato
real `alerts:<ambiente>:<nó>:<pid>`. Ambos precisam pertencer ao único worker
fresco, no ambiente, nó e commit aprovados; identificadores estrangeiros ou
malformados continuam sendo rejeitados.

A promoção aguarda por até dois minutos a convergência dos heartbeats e das
duas lideranças. As instruções também validam o marcador de 40 caracteres antes
da consulta do ciclo e usam um arquivo de log exclusivo, sem risco de uma nova
tentativa apagar o acompanhamento já ativo.

Não há nova migração nem mudança de versão da aplicação: permanecem
`1.23.5` e `0030_v1_23_navigation_metrics`. Consulte `PATCH_V1235_R2A.md`,
`INSTRUCOES_ORACLE_V1235_R2A.md` e `RELATORIO_VALIDACAO_V1235_R2A.md`.

## Navegação materializada e isolamento de recursos • V1.23.5 R2

A R2 retira da navegação os dois cálculos mais caros que ainda dependiam de
históricos extensos: as valorações padrão e o pódio oficial de backtests. O
worker os calcula em segundo plano e grava uma projeção atual por ativo. Os
históricos permanecem como fonte de verdade e também como fallback enquanto o
preenchimento inicial ainda não cobriu determinado ativo; um resultado vazio
nunca apaga o último cálculo válido.

A interface exibe primeiro a lista principal e completa os sinais secundários
de forma progressiva. Ao trocar rapidamente de painel, pedidos obsoletos e
temporizadores da tela anterior são cancelados, sem interromper leituras
compartilhadas úteis. Isso reduz a espera visível e evita trabalho concorrente
sem remover filtros, colunas, permissões ou detalhes existentes.

Na operação, o staging volta a ser iniciado sempre que uma homologação é
solicitada e, após uma promoção concluída, pode ficar estacionado por padrão
para devolver memória à produção. A segunda VM recebe verificações mais fortes
de commit, identidade lógica e liderança única; o retorno para a VM principal continua
disponível e exige que o worker remoto esteja comprovadamente parado.

A migração `0030_v1_23_navigation_metrics` apenas amplia a tabela de métricas
atuais com campos reconstruíveis. Nenhuma tabela histórica é removida. Consulte
`V1_23_5.md`, `PATCH_V1235_R2.md`, `INSTRUCOES_ORACLE_V1235_R2.md` e
`RELATORIO_VALIDACAO_V1235_R2.md` antes de publicar ou promover.

## Painéis mais rápidos • V1.23.5 R1

A V1.23.5 R1 reduz o trabalho repetido durante a navegação sem remover
funcionalidades. Leituras de manchetes, comparações, agenda, fatos relevantes
e proventos não gravam mais no banco. Quando uma fonte realmente estiver
ausente ou vencida, o navegador solicita uma atualização separada e preserva
o último resultado válido.

Permissões, presets, respostas compartilhadas e screeners usam janelas de
cache maiores, sempre com invalidação nas operações que alteram esses dados.
Catálogo e filtros personalizados são carregados em paralelo. O painel
operacional também passa a registrar o tempo real até Dashboard, Análises e
Carteira ficarem utilizáveis no navegador, complementando o benchmark interno.

Não há migração de banco nesta revisão. A revisão esperada continua sendo
`0029_v1_23_current_metrics`.

O escopo, as invariantes e a sequência completa da linha V1.20 estão documentados em `GUIA_MESTRE_V1.20.md`. A auditoria de valoração, filtros e backtests da V1.21 está em `RELATORIO_AUDITORIA_VALUATION_E_BACKTESTS_V1210.md`.

## Valorações e pódio oficial V1.23.4

A V1.23.4 corrige a apresentação de Mercado e Análises sem remover filtros,
históricos, permissões ou configurações existentes. O preço-teto por
dividend yield-alvo passa a usar os campos canônicos esperados pela tabela, e
o valor relativo é calculado com os pares locais elegíveis antes da resposta.
Quando não existem pelo menos cinco pares válidos, o estado permanece `N/D`
em vez de produzir uma estimativa artificial.

As três melhores estratégias agora ocupam três colunas independentes. A
classificação retém somente a execução mais recente de cada configuração,
seleciona a melhor configuração de cada estratégia e impede que a mesma
estratégia ocupe mais de uma posição. Configurações de coluna já salvas com a
antiga coluna combinada são convertidas automaticamente, sem migração ou
perda das preferências do proprietário.

O proprietário também pode iniciar uma rodada oficial completa em
`Administração > Atualizações` ou em `Backtests > Oficiais`. A API rejeita uma
nova solicitação enquanto houver rodada ativa ou antes de completar 12 horas
desde a rodada oficial anterior; a restrição não depende apenas do botão.

Não há nova migração de banco nesta versão. A revisão esperada continua sendo
`0029_v1_23_current_metrics`. Consulte `V1_23_4.md`, `PATCH_V1234.md`,
`INSTRUCOES_ORACLE_V1234.md` e `RELATORIO_VALIDACAO_V1234.md` antes de
publicar ou promover.

## Desempenho sob carga V1.23.3

A V1.23.3 preserva a tabela materializada, todos os snapshots históricos e
os fallbacks da V1.23.2, mas reduz o custo de mantê-los atualizados. As fontes
mais recentes e as linhas atuais passam a ser buscadas por lote, em vez de por
ativo. Quando os identificadores, datas de observação e algoritmo não mudaram,
o worker não relê 600 barras nem recalcula indicadores com Pandas.

Na VM principal de 1 GB, os lotes são menores, espaçados e recebem menor peso
de CPU que a API e o PostgreSQL. Isso evita que um preenchimento inicial ou uma
atualização diária monopolize os recursos usados pelos painéis. A mesma
configuração é compatível com o worker da segunda VM.

A atualização automática do staging também repete uma migração isolada uma
vez em caso de falha transitória. Se ambas as tentativas falharem, o staging
permanece parado e a produção não é tocada. Não há nova migração de banco
nesta versão; a revisão esperada continua sendo `0029_v1_23_current_metrics`.

Consulte `V1_23_3.md`, `PATCH_V1233.md`, `INSTRUCOES_ORACLE_V1233.md` e
`RELATORIO_VALIDACAO_V1233.md` antes de publicar ou promover.

## Otimização estrutural V1.23.2

A V1.23.2 preserva todos os históricos e acrescenta uma tabela materializada
com os valores atuais por ativo. O worker atualiza essa tabela de forma
idempotente e pré-calcula tendências, RSI, volume e pivôs; screeners e detalhe
do ativo usam o caminho rápido somente depois de confirmar cobertura integral.
Até lá, o caminho histórico anterior continua ativo automaticamente.

As sincronizações completas, ingestões de preços, composição do Ibovespa e
notícias legadas deixam de consultar fontes externas durante a navegação. Elas
entram na fila e a interface acompanha o trabalho sem manter a requisição web
aberta. A composição e as notícias exibidas vêm de snapshots locais.

Migrações agora são executadas por um serviço isolado antes da troca da
aplicação; API e worker apenas verificam a revisão. O proxy valida e recarrega
a configuração sem interrupção, com reinício somente como contingência. A
segunda VM recebe validação estrita de commit, SSH, liderança única e retorno
seguro para a VM principal; sua criação física na Oracle continua sendo uma
etapa operacional explicitamente aprovada.

Consulte `V1_23_2.md`, `PATCH_V1232.md`, `INSTRUCOES_ORACLE_V1232.md` e
`RELATORIO_VALIDACAO_V1232.md` antes de publicar ou promover.

## Conclusão da revisão conservadora V1.23.1 R2

A R2 conclui os dois itens conservadores que permaneceram pendentes após a
primeira homologação da V1.23.1: cache curto para permissões, presets e
respostas compartilhadas; e retenção segura da fila e dos registros
operacionais. O cache é limitado, devolve cópias independentes e usa geração
de invalidação, impedindo uma leitura simultânea antiga de recolocar uma
permissão revogada. Toda alteração administrativa invalida a entrada depois
da confirmação no banco.

A retenção opera diariamente em lotes pequenos e somente sobre trabalhos
automáticos, concluídos, antigos e reproduzíveis. Pedidos de usuários,
backtests, falhas, trabalhos ativos e o registro mais recente de cada rotina
são preservados. Antes da remoção da tabela quente, cada linha recebe uma
cópia integral com checksum no arquivo operacional, na mesma transação. A
execução manual é apenas uma simulação, salvo quando `--apply` é informado.
Ao reverter a migração, a tabela é mantida se contiver registros, evitando
apagar a única cópia preservada.

Consulte `PATCH_V1231_R2.md`, `INSTRUCOES_ORACLE_V1231_R2.md` e
`RELATORIO_VALIDACAO_V1231_R2.md` antes de promover.

## Desempenho e publicação segura V1.23.1 R1

A V1.23.1 R1 parte exatamente da R8 homologada e preserva suas rotas,
permissões, dados, filtros, carteiras, eventos e backtests. A revisão reduz
consultas repetidas de situação das atualizações, reaproveita recursos
estáticos no navegador e evita pedidos de atualização redundantes durante a
navegação. O fallback de recuperação por acesso continua ativo quando um
dado estiver ausente, vencido ou com falha.

A publicação também passa a bloquear logs, diagnósticos e caches locais,
atualiza a branch de segurança antes de substituir a `main` e interrompe a
operação se detectar uma alteração concorrente. A pilha legada continua
preservada e pausada; o procedimento deixa de repetir chamadas ao Docker
quando os contêineres já estão parados.
Antes de qualquer alteração em produção, a promoção repete automaticamente
as medições p50/p95 no staging e interrompe o processo se alguma meta falhar.

## Eventos oficiais, qualidade e portal editável V1.23.0

A V1.23.0 mantém integralmente a plataforma homologada e acrescenta recursos que não bloqueiam a navegação:

- calendário de proventos das carteiras com eventos confirmados pelos serviços oficiais de Empresas e Fundos Listados da B3;
- feed de fatos relevantes a partir dos dados abertos IPE da CVM;
- histórico incremental de IMA-B e IRF-M pelo ANBIMA Feed, ativado somente com credenciais oficiais;
- agenda anual renovável, incluindo eleições e feriados de negociação, com fonte e indicação transparente de fallback;
- painel administrativo de qualidade com cobertura, frescor, origem, última atualização e falhas por conjunto de dados;
- monitor diário do filtro ALB, que alerta fora da faixa de 5 a 20 ativos sem alterar critérios;
- editor seguro da página inicial, livros, capas e até três links HTTPS de venda por obra;
- acesso alternativo por código de seis dígitos enviado por e-mail, válido por dez minutos e renovável no máximo uma vez por minuto.

O proprietário recebe a permissão de edição da página automaticamente e pode delegá-la por nível de acesso. A interface pública conserva uma página estática completa como contingência se o banco estiver indisponível.

### Revisão R8 — continuidade, análises e alocação

A R8 preserva os critérios homologados da R7 e acrescenta três recursos sem substituir dados existentes:

- atalho permanente da plataforma para a página principal, mantendo a sessão autenticada;
- configuração alternativa, exclusiva do proprietário, para os filtros Padrão, FDI e ALB em cada classe de ativo, com ativação opcional, revisão contra edições concorrentes e restauração integral do padrão de fábrica;
- padrão administrável de colunas visíveis e de sua ordem, sem retirar do usuário a possibilidade de personalizar a própria visualização;
- gráfico hierárquico da carteira: o anel interno mostra os tipos de investimento e o externo mostra setor ou segmento; o clique abre o detalhamento do tipo sem nova consulta ao servidor.

As configurações originais continuam imutáveis no código. Restaurar um item desativa apenas a alternativa administrativa e nunca apaga filtros pessoais, carteiras, históricos ou resultados.

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
- console com todas as 19 rotinas automáticas, atualização manual por grupo ou completa, monitor de alertas e fila de trabalhos com reprocessamento seguro.

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
- carteiras e permissões isoladas por e-mail autenticado, tanto via Google quanto por código de uso único;
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
`INSTRUCOES_ORACLE_V1234.md` para a homologação desta versão.

## Segurança e escopo

O projeto não constitui recomendação de investimento. Resultados de filtros,
notícias, cotações e backtests devem ser verificados antes de qualquer decisão.
