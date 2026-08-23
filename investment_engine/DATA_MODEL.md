# Investment Engine V1.5 — Data Model

## Princípios
- `NULL` = desconhecido/indisponível; nunca é convertido silenciosamente para zero.
- Dados variáveis no tempo ficam em snapshots/barras.
- Identidade estável do ativo fica em `assets`.
- Ingestões e cálculos são auditáveis por fonte, data e versão.

## Tabelas de mercado

### assets
Ticker, nome, tipo do ativo, bolsa, moeda, setor, indústria, segmento, categoria de market cap e metadados.

### fundamental_snapshots
Fundamentos de ações/FIIs por data de referência e fonte.

### technical_snapshots
Estado técnico por data/fonte: médias, RSI, Bollinger, MACD, ATR, retornos, volatilidade, drawdown e liquidez.

### price_bars
OHLCV histórico normalizado. É a base dos indicadores próprios, Pivot Points, tendências e backtests.

### valuation_snapshots
Histórico por método e versão: Graham, Bazin/Barsi e Gordon DDM.

### score_snapshots
Quality, Value, Growth, Technical, Risk, Liquidity, ALB, cobertura e detalhes explicáveis.

### ingestion_runs
Auditoria das ingestões.

## Tabelas V1.5 — Carteira

### portfolios
- nome;
- moeda-base;
- caixa atual;
- percentual-alvo de caixa;
- observações.

### portfolio_positions
- carteira;
- ativo;
- situação: `position`, `target` ou `analysis`;
- quantidade;
- preço médio;
- percentual-alvo global;
- `classification_override` opcional;
- notas.

A composição atual é derivada de quantidade x preço de mercado. Ativos sem cotação permanecem N/D.

## Tabelas V1.5 — Backtests

### backtest_runs
Guarda ativo, proprietário, origem pessoal/oficial, identidade da configuração, data de mercado, versão do motor, estratégia, período, capital, custos, parâmetros, métricas, curva de capital, nota de robustez, qualidade da amostra e sinal do último pregão. Históricos pessoais só podem ser lidos pelo proprietário da conta ou pelo usuário master.

### backtest_trades
Guarda cada operação vinculada ao backtest: entrada, saída, retorno, P&L, duração e motivo da saída.

### backtest_batch_jobs
Audita as atualizações semanais e manuais do catálogo oficial: solicitante, ativos, versão da grade, quantidade de combinações, progresso, falhas, início e término.
