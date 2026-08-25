# Formação do Investidor • Investment Engine V1.13.0

## Novidades da V1.13.0

- novo **Painel de Mercado** em um menu próprio, compacto e responsivo;
- notícias das ações e recomendações de bancos organizadas na aba **Notícias** da carteira;
- estudo de consistência das estratégias movido para a aba **Estudo dos Backtests**, sem um menu separado;
- Selic atual e projeções Focus para o fim do ano corrente e do ano seguinte;
- curva brasileira de juros ANBIMA com gráfico, intervalo de vencimentos, pesquisa por anos/dias úteis e tabela;
- CDI, IMA-B, IRF-M, IBOV, IFIX e principais bolsas mundiais com variações de 1 dia, 1 semana, 1 mês e 1 ano;
- VIX, DXY, juros americanos de 2 e 10 anos e spread 10a-2a;
- Bitcoin e Ethereum em dólar e real, além de USD/BRL e EUR/USD;
- IPCA, INPC, IGP-M e CPI americano acumulados em 12 meses;
- ouro, prata, petróleo Brent e petróleo WTI;
- próximas reuniões do Copom, divulgações de CPI e Payroll e feriados da B3/NYSE;
- atualização diária em segundo plano, com último retrato preservado e atualização manual sem travar a navegação;
- cada dado identifica sua fonte; proxies de IMA-B, IRF-M ou MSCI Europe nunca são apresentados como o índice oficial;
- falhas isoladas de fontes externas não derrubam o restante do painel;
- a implementação reaproveita o cache existente e não exige nova migração de banco.

## Novidades da V1.12.5

- ações, FIIs, ETFs e BDRs fracionários, identificados pelo sufixo `F`, deixam de ser gravados e exibidos;
- livros especiais de grandes lotes, variantes de balcão, direitos/recibos de subscrição e vencimentos duplicados de futuros também ficam fora do catálogo do usuário;
- ações, units, FIIs, ETFs e BDRs regulares permanecem disponíveis; futuros usam uma série contínua por ativo-base;
- registros antigos incompatíveis são desativados sem apagar histórico ou posições de carteira;
- notícias de todas as carteiras e recomendações de bancos são carregadas em segundo plano no primeiro acesso do usuário a cada dia;
- o conteúdo diário fica salvo por usuário e abre sem aguardar as fontes externas;
- um botão permite solicitar manualmente nova atualização no mesmo dia;
- a migração do cache de notícias é aplicada automaticamente durante a inicialização.

## Novidades da V1.12.4

- o título da página agora começa abaixo da barra fixa do Streamlit, sem cortes;
- o cabeçalho superior recebeu fundo consistente, evitando a sensação de uma área vazia sobre o conteúdo;
- o espaçamento do topo se adapta a telas de computador, tablet e celular;
- a organização compacta, os filtros recolhidos e todas as regras da V1.12.3 foram preservados;
- nenhuma migração de banco é necessária.

## Novidades da V1.12.3

- páginas mais compactas, com menor espaçamento e melhor aproveitamento da tela;
- universo, subfiltros e filtros de análise ficam recolhidos e abrem com um clique;
- resumos visuais permanentes mostram mercado, universo, filtro e quantidade de ativos ativos;
- filtros e regras de backtest ficam em um painel recolhido, sem alterar a estratégia executada;
- a estratégia selecionada e os filtros ativos aparecem em etiquetas de leitura rápida;
- movimentações da carteira ficam recolhidas, mantendo patrimônio e composição em destaque;
- screener avançado permanece disponível, mas deixa de ocupar a página quando não está em uso;
- nenhuma migração de banco é necessária.

## Novidades da V1.12.2

- domínio canônico único: `https://formacaodoinvestidor.com.br`;
- exemplos de login Google usam somente `/oauth2callback` no domínio oficial;
- referências e instruções da hospedagem anterior foram substituídas pela arquitetura Oracle;
- links institucionais deixaram de apontar para o subdomínio antigo `app`;
- ambiente identificado como `oracle-production` no diagnóstico do motor;
- publicação interrompe automaticamente se detectar uma cópia completa do projeto dentro da pasta `investment_engine`;
- sem nova migração de banco.

## Novidades da V1.12.1

- o andamento dos lotes oficiais é atualizado automaticamente a cada 15 segundos enquanto a Administração estiver aberta;
- o proprietário pode cancelar com confirmação um lote na fila ou em execução, interrompendo a execução correspondente no GitHub e bloqueando novas entregas para o pedido cancelado;
- resultados que já chegaram antes do cancelamento são preservados;
- pedidos com falhas, cancelados ou concluídos com falhas podem repetir somente os ativos que falharam ou permaneceram pendentes;
- cada repetição recebe um novo identificador e não recalcula ativos que já terminaram corretamente;
- os estados `Cancelado` e `Repetição de falhas` aparecem claramente no histórico administrativo.

## Novidades da V1.12.0

- o PostgreSQL da Oracle continua privado e não recebe conexões diretas do GitHub;
- o GitHub Actions usa um PostgreSQL temporário e descartável apenas durante os cálculos;
- resultados são enviados por uma rota HTTPS exclusiva, autenticada e limitada a 8 MB por ativo;
- entregas repetidas são idempotentes e não duplicam backtests no catálogo;
- somente um lote oficial pode ficar ativo por vez; cliques repetidos reaproveitam o mesmo pedido;
- uma execução interrompida retoma somente os ativos ainda pendentes;
- o painel administrativo mostra percentual, ativos processados, último ativo, resultados, falhas e diagnósticos;
- execuções antigas concluídas no GitHub sem entregar dados à Oracle são identificadas como falha de entrega;
- nova migração registra o recebimento por ativo para auditoria e controle de duplicidade.

## Novidades da V1.11.1

- o ranking do estudo dos backtests agora é clicável;
- cada estratégia abre todas as configurações efetivamente executadas, sem repetir a mesma combinação para cada ativo;
- parâmetros, filtros, custos, premissas, ativos avaliados e métricas médias ficam disponíveis para auditoria;
- a busca de notícias passa a combinar GDELT DOC 2.0 e Google News RSS, com alternativa automática quando uma fonte falha;
- consultas de ativos reconhecem códigos e nomes corporativos, incluindo BBAS3/Banco do Brasil;
- mensagens distinguem ausência real de notícias de indisponibilidade temporária das fontes;
- não exige nova migração de banco.

## Novidades da V1.11.0

- histórico de backtests explicitamente ordenado pela data/hora da análise, do mais recente para o mais antigo;
- estudo restrito das cinco estratégias mais consistentes do catálogo oficial;
- pontuação por recorrência no Top 3, qualidade de colocação, robustez e cobertura, sem permitir que várias configurações da mesma estratégia ocupem o mesmo pódio;
- nova área restrita **Estudos e notícias**;
- três notícias importantes por ação efetivamente mantida na carteira;
- notícias sobre ações recomendadas, carteiras e preços-alvo de bancos brasileiros e mundiais;
- duas novas permissões independentes, controladas exclusivamente pelo proprietário;
- atualização automática do banco por migração Alembic, sem edição SQL manual.

> Edição preparada para hospedagem própria na Oracle Cloud. `app.py` permanece
> como entrada estável e `streamlit_app.py` inicializa a interface e a API
> privada. Consulte `DEPLOY_STREAMLIT_CLOUD.md` — nome histórico preservado para
> compatibilidade. O GitHub contém somente código; banco e credenciais ficam no servidor.

Backend Python/FastAPI/PostgreSQL + Streamlit para triagem fundamentalista/técnica, valuation, carteira e backtests.

## Novidades da V1.10.4

- os ativos visíveis na tabela de Mercado e análise são reaproveitados automaticamente no lote oficial;
- novo botão leva a seleção filtrada diretamente para Administração → Backtests oficiais;
- universo, Padrão/CNPI/ALB/personalizado, porte, IBOV, setor e limite exibido passam a ser respeitados na transferência;
- resultados do screener avançado também podem ser enviados diretamente;
- a origem e a quantidade da seleção ficam visíveis antes do processamento;
- permanece o limite de 100 ativos por lote e não há migração de banco.

## Novidades da V1.10.3

- pedidos de lotes oficiais agora são registrados no banco antes do acionamento do GitHub;
- andamento do GitHub e histórico interno aparecem juntos no painel administrativo;
- falhas, cancelamentos e estouros de tempo deixam de permanecer silenciosamente como pedidos na fila;
- workflow valida a conexão PostgreSQL antes de iniciar os backtests e exibe uma orientação segura se o Secret estiver incorreto;
- o motor aceita URLs PostgreSQL padrão e ignora uma variável inválida quando a alternativa está correta;
- não exige migração de banco.

## Novidades da V1.10.2

- menu lateral redesenhado com identidade visual própria;
- conta, perfil e situação do acesso reunidos em um cartão compacto;
- estado do motor apresentado de forma mais clara;
- opções de navegação com largura e espaçamento uniformes;
- seleção ativa mais evidente, sem os antigos círculos de rádio;
- textos redundantes removidos e perfis traduzidos para português;
- não exige migração de banco.

## Novidades da V1.10.1

- correção da importação do pacote no workflow de backtests semanais;
- seleção de até 100 ativos e acionamento do lote oficial diretamente na Administração do site;
- credencial do GitHub mantida somente nos Secrets privados do servidor Oracle;
- mensagens claras para credencial ausente, expirada ou sem permissão;
- não exige migração de banco.

## Novidades da V1.10.0

- A tela Mercado abre com o filtro Padrão e exibe no máximo 50 ativos.
- Tamanho da Empresa, IBOV e Setor/Categoria passaram a ser subfiltros cumulativos do universo principal.
- Nova categoria Demais Ativos B3, separando ETF, BDR e Futuro/derivativo.
- Filtros incompatíveis de empresas/FIIs ficam ocultos em Demais Ativos B3; permanecem liquidez e filtros técnicos.
- Nova área Administração, exclusiva do proprietário, com acesso aos backtests manuais, lotes oficiais e permissões.
- Não há migração adicional de banco nesta versão.

## Novidades da V1.9.0

- histórico de backtests isolado por conta Google, com reaproveitamento de testes idênticos no mesmo dia;
- resultado completo auditável, incluindo data/hora, versão do motor, parâmetros, filtros, operações e sinal atual;
- catálogo oficial semanal para as 50 ações do filtro Padrão, com seleção manual de até 100 ativos pelo proprietário;
- grade oficial limitada a 200 combinações por ativo e distribuída entre todas as estratégias disponíveis;
- ranking robusto com validação nos 30% finais, drawdown, Sharpe, Sortino, Profit Factor e penalidade por amostra pequena;
- três melhores backtests e sinais Comprar/Vender/Neutro dentro do Universo de ativos;
- cinco melhores resultados oficiais e os 100 testes mais recentes na aba Backtests;
- automação de sábado às 00h01 de Brasília pelo GitHub Actions.

Consulte `V1_9_0.md` e `ATIVAR_BACKTESTS_SEMANAIS.md`.

## Principais módulos

### Mercado & Análise
- universo selecionável: mercado completo, carteira do usuário, método BESST, setor/categoria/segmento/porte ou ativos específicos;
- troca de universo segura: limpa refinamentos anteriores, mostra 100% do novo grupo e oferece retorno imediato ao mercado completo;
- presets Padrão / CNPI / ALB;
- até três filtros personalizados salvos por usuário, conforme permissão do proprietário;
- análise individual por perfil setorial;
- Graham Number;
- Preço Teto Bazin/Barsi (6%);
- Gordon DDM com premissas explícitas;
- Quality, Value, Growth, Technical, Risk, Liquidity e ALB Score;
- screener avançado que combina filtros fundamentalistas, scores e filtros técnicos;
- tendências diária/semanal/mensal por SMA 20 ou 21;
- RSI 14;
- Pivot Points clássicos PP, S1-S3 e R1-R3.

### Carteira
- isolamento completo das carteiras por conta Google;
- cadastro de novas compras com soma automática e recálculo do preço médio ponderado;
- edição do total com botões de 100, 50, 25, 10, 5 ou 1 ação;
- posição atual, ativos-alvo e ativos em análise;
- quantidade, preço médio e cotação atual;
- valor de mercado, custo e P&L;
- % atual da carteira e % alvo;
- % dentro de Ações, FIIs, ETFs e outras classes;
- composição geral por classe;
- composição por setor/segmento/categoria dentro de cada classe;
- classificação manual opcional, útil para ETFs;
- rebalanceamento em R$ e quantidade estimada;
- N/D de cotação nunca é tratado como zero.

### Backtests
Períodos: 6 meses, 1, 2, 3, 5, 10, 15 e 20 anos, além de datas personalizadas.

Estratégias incluídas:
- EMA 9 x SMA 50;
- EMA 9 x SMA 40;
- SMA 3 + EMA 9 + SMA 21;
- Golden Cross SMA 50 x SMA 200;
- MACD 12/26/9;
- RSI 14 + filtro SMA 200;
- Donchian Breakout 20/10;
- Bollinger 20/2 + RSI + SMA 200;
- Momentum 12 meses;
- cruzamento de médias personalizado.

O motor usa warm-up, evita preenchimento no mesmo fechamento do sinal, permite custos/slippage, compara com Buy & Hold e mede CAGR, volatilidade, Sharpe, Sortino, drawdown, Calmar, taxa de acerto, profit factor, exposição e operações.

A V1.5.4 acrescenta o backtest de cesta com pesos iniciais iguais, curva e drawdown consolidados, benchmark da cesta, contribuição por ativo, concentração dos lucros, Profit Factor incluindo posições abertas marcadas a mercado e remuneração opcional do caixa. Códigos antigos conhecidos, como VIVT4 e EMBR3, são resolvidos automaticamente para os códigos atuais.

## Executar no Windows
Para desenvolvimento local, leia `RUN_V154_WINDOWS.md`. Para preparar a homologação privada em servidor, leia `PRODUCAO_V160.md`.

Se a pasta do projeto for movida, execute `REPARAR_AMBIENTE_NOVA_PASTA.ps1`. Ambientes virtuais Python guardam caminhos internos e não devem ser simplesmente transportados entre pastas.

## V1.5.1
A atualização V1.5.1 transforma Backtests em um laboratório de filtros: tendência multi-timeframe 21/50, ADX, volume, RSI, ATR%, filtros fundamentalistas point-in-time com proteção contra look-ahead e diagnóstico de setups sem trades. Consulte `V1_5_1.md`.

## V1.5.4
Consulte `V1_5_4.md` para a lista completa de melhorias e premissas da cesta.

## V1.6.0

A V1.6.0 prepara o beta privado do domínio Formação do Investidor: página institucional, login OIDC, API e banco em rede privada, contêineres, proxy HTTPS e configuração segura por ambiente. Consulte `V1_6_0.md`.

## V1.6.1

A V1.6.1 permite carregar e atualizar o catálogo de ações e FIIs pela própria tela do Mercado, identifica claramente um banco vazio e melhora o cadastro da Carteira com classificação automática em português, preço com duas casas decimais e quantidade ajustável em passos de 100, 10 ou 1. Não exige migração adicional do banco. Consulte `V1_6_1.md`.

## V1.6.2

A V1.6.2 libera a autenticação para contas Google externas com perfil inicial de visitante somente leitura. O proprietário passa a controlar individualmente acesso ao Mercado, filtros avançados, Carteira, Backtests e atualização do banco. A quantidade da Carteira ganha botões confiáveis para 100, 25, 10, 5 ou 1 unidade. Consulte `V1_6_2.md`.

## V1.7.0

A V1.7.0 separa cada Carteira por conta Google, distingue novas compras de correções da posição, recalcula o preço médio ponderado e adiciona filtros personalizados persistentes. O proprietário define individualmente um limite de zero a três filtros por usuário. A atualização do banco é automática na primeira inicialização. Consulte `V1_7_0.md`.

## V1.7.1

A V1.7.1 corrige os botões de quantidade para usar callbacks compatíveis com o estado de sessão do Streamlit. Os botões de compra, redução, aumento, zeragem e restauração do lote padrão deixam de alterar um campo depois de ele ter sido desenhado.

## V1.7.2

A V1.7.2 elimina o seletor de passo da Carteira. Abaixo de cada campo de quantidade ficam somente os botões fixos `(+100)`, `(-100)`, `(+50)`, `(-50)`, `(+10)`, `(-10)`, `(+5)`, `(-5)`, `(+1)` e `(-1)`. Os controles nativos `+` e `-` da própria caixa avançam de 100 em 100.

## V1.7.3

A V1.7.3 transforma os controles de quantidade em fragmentos independentes do Streamlit. Cada clique atualiza somente a caixa e seus botões; catálogo, carteira, cotações, gráficos e demais cálculos deixam de ser recarregados. O aplicativo completo e o banco são atualizados apenas ao salvar a compra ou a edição.

## V1.7.4

A V1.7.4 torna o cadastro de compras compatível com a rota estável de posições já disponível nas instalações anteriores. A interface soma a quantidade, calcula o preço médio ponderado, preserva alvo, classificação e observações existentes e envia o resultado consolidado ao salvar, eliminando o erro genérico `Not Found`.

## V1.7.5

A V1.7.5 mantém o cálculo consolidado da compra dentro da própria página da Carteira. Isso evita falha de inicialização quando o Streamlit atualiza o arquivo da interface antes de atualizar módulos auxiliares em cache.

## V1.8.0

A V1.8.0 reorganiza a navegação e separa a triagem em duas etapas: universo de ativos e refinamento. O usuário pode trabalhar com o mercado completo, suas próprias carteiras, o método BESST, setor/categoria/segmento/porte ou uma seleção de tickers. Padrão, CNPI, ALB, filtros personalizados e screener avançado passam a respeitar o universo escolhido. Não exige migração do banco. Consulte `V1_8_0.md` e `PATCH_V180.md`.

## V1.8.1

A V1.8.1 torna **Tamanho da empresa** uma opção direta do universo, com Blue Chip/Large Cap, Mid Cap e Small Cap calculadas pelo valor de mercado. Também acrescenta **Ibovespa (IBOV)** com as escolhas “está no IBOV” e “não está no IBOV”, consultando a carteira vigente no portal da B3. Não exige migração. Consulte `V1_8_1.md` e `PATCH_V181.md`.
