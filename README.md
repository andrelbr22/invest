# Formação do Investidor • Investment Engine V1.7.2

> Edição preparada para substituir o aplicativo atual no Streamlit Community
> Cloud mantendo `app.py` como arquivo principal. Em uma nova publicação,
> `streamlit_app.py` também pode ser usado. Consulte `DEPLOY_STREAMLIT_CLOUD.md`. O GitHub
> contém somente código; o banco compartilhado deve permanecer em PostgreSQL
> externo e as credenciais devem ser configuradas no painel Secrets.

Backend Python/FastAPI/PostgreSQL + Streamlit para triagem fundamentalista/técnica, valuation, carteira e backtests.

## Principais módulos

### Mercado & Análise
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

A V1.6.1 permite carregar e atualizar o catálogo de ações e FIIs pela própria tela do Mercado, identifica claramente um banco Neon vazio e melhora o cadastro da Carteira com classificação automática em português, preço com duas casas decimais e quantidade ajustável em passos de 100, 10 ou 1. Não exige migração adicional do banco. Consulte `V1_6_1.md`.

## V1.6.2

A V1.6.2 libera a autenticação para contas Google externas com perfil inicial de visitante somente leitura. O proprietário passa a controlar individualmente acesso ao Mercado, filtros avançados, Carteira, Backtests e atualização do banco. A quantidade da Carteira ganha botões confiáveis para 100, 25, 10, 5 ou 1 unidade. Consulte `V1_6_2.md`.

## V1.7.0

A V1.7.0 separa cada Carteira por conta Google, distingue novas compras de correções da posição, recalcula o preço médio ponderado e adiciona filtros personalizados persistentes. O proprietário define individualmente um limite de zero a três filtros por usuário. A atualização do banco é automática na primeira inicialização. Consulte `V1_7_0.md`.

## V1.7.1

A V1.7.1 corrige os botões de quantidade para usar callbacks compatíveis com o estado de sessão do Streamlit Cloud. Os botões de compra, redução, aumento, zeragem e restauração do lote padrão deixam de alterar um campo depois de ele ter sido desenhado.

## V1.7.2

A V1.7.2 elimina o seletor de passo da Carteira. Abaixo de cada campo de quantidade ficam somente os botões fixos `(+100)`, `(-100)`, `(+50)`, `(-50)`, `(+10)`, `(-10)`, `(+5)`, `(-5)`, `(+1)` e `(-1)`. Os controles nativos `+` e `-` da própria caixa avançam de 100 em 100.
