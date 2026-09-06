# Auditoria de valoração, filtros e backtests — V1.21.0

## Resumo executivo

A revisão preservou o produto existente e adotou uma regra conservadora: um método só é calculado quando a classe e os dados disponíveis realmente sustentam a fórmula. Ausência de dados é exibida como `N/D`; nunca como zero, aprovação no filtro ou preço calculado com premissa escondida.

## 1. Métodos de valoração

### Número de Graham

Fórmula auditada: `√(22,5 × LPA × VPA)`. A fórmula existente estava matematicamente correta. A apresentação foi corrigida para **Número de Graham**, uma referência conservadora, e não “preço justo universal”. Exige LPA e VPA positivos. É inaplicável a FIIs, ETFs e futuros; em BDRs só seria válido após calcular no ativo-lastro e converter por razão e câmbio.

### Preço-teto por dividend yield-alvo

Fórmula auditada: `DPA anual ÷ yield-alvo decimal`. A fórmula existente estava correta, mas o nome Bazin/Barsi era forte demais para um cálculo baseado apenas no dividend yield atual/TTM. O novo nome revela exatamente o que foi calculado. O valor exige proventos recorrentes; para FIIs, distribuições atípicas, amortizações e inflação devem ser normalizadas antes de interpretação.

### Valuation relativo por pares

Nova família escolhida porque utiliza os múltiplos que a base atual já consegue obter. A amostra é restrita por classe e setor/segmento. Múltiplos nulos, negativos, zero, infinitos e `NaN` são eliminados; os extremos são winsorizados; a amostra mínima padrão é cinco pares. Os cenários usam quartis e mediana e combinam apenas métricas com dados suficientes.

- ações comuns: P/L e P/VP; EV/EBITDA somente quando EBITDA e dívida por ação estiverem disponíveis;
- bancos e seguradoras: P/VP entre pares da mesma atividade; ROE, crescimento e risco permanecem critérios de qualidade separados;
- FIIs: P/VP/NAV e FFO yield entre fundos do mesmo segmento;
- ETFs e BDRs: aguardam composição ou dados do ativo-lastro no mercado de origem.

### Valor econômico por classe

Nova família escolhida para receber a metodologia econômica apropriada a cada classe. O componente implementado agora é Gordon/DDM, com `D1 ÷ (k − g)`, três cenários explícitos e margem de segurança opcional. Não existe taxa, crescimento ou margem global silenciosa.

Os componentes seguintes estão estruturados no catálogo, mas não são calculados sem os insumos corretos:

- ações não financeiras: DCF por FCFF/FCFE;
- bancos e seguradoras: FCFE/DDM e restrições regulatórias;
- FIIs de tijolo: NAV, NOI/cap rate e AFFO;
- FIIs de papel: DCF da carteira, spread, duration, garantias e perdas;
- ETFs: NAV/iNAV ou look-through;
- BDRs: valor do lastro × câmbio × razão do programa;
- futuros: fair value/cost of carry e basis, em módulo próprio.

## 2. Dados fundamentalistas

O mapeamento do Fundamentus foi revisado. ROIC estava ausente apesar de existir no HTML e passou a ser carregado da coluna correta. As unidades percentuais permanecem percentuais, e dividend yield é convertido para valor por ação apenas quando o cálculo necessita disso. Campos não publicados pela fonte não são inferidos como zero.

Recomendação operacional: manter data de referência e fonte visíveis e não comparar resultados de datas diferentes sem aviso. DCF/NAV deve ser ativado somente após criar fontes, histórico e testes próprios desses insumos.

## 3. Indicadores técnicos do screener

- pivôs clássicos seguem as fórmulas PP, S1–S3 e R1–R3 aprovadas;
- pivô diário usa somente a barra anterior;
- semanal e mensal usam apenas períodos concluídos;
- preços e OHLC são ajustados na mesma base para evitar falsos níveis em splits;
- RSI usa suavização de Wilder e retorna 50 em mercado perfeitamente plano;
- volume diário/mensal compara o período corrente com a média de períodos anteriores;
- tendência usa a média e o período informados na resposta.

## 4. Backtests

O catálogo tem 13 estratégias, agrupadas por tendência, momentum, reversão, breakout e volatilidade. As novas estratégias ampliam a diversidade sem multiplicar variações quase idênticas:

- Supertrend ATR: tendência adaptada à volatilidade;
- Momentum dual relativo: exige retorno absoluto positivo e superior ao benchmark;
- Bollinger Squeeze + rompimento: expansão após compressão de volatilidade;
- cruzamento configurável: permite testar médias sem criar uma estratégia fixa para cada par.

Filtros comuns acrescentados: tendência multi-timeframe, volume, RSI, ADX, ATR, MACD, Bandas de Bollinger, força relativa, liquidez, pivôs e fundamentos ponto no tempo.

Controles contra viés e erro:

- execução em `t+1`, sem usar o fechamento que criou o sinal;
- OHLC ajustado;
- warm-up por estratégia e filtro;
- benchmark externo obrigatório e alinhado no tempo para sinais relativos, sem substituir a comparação histórica com o buy-and-hold do próprio ativo;
- cobertura mínima e data máxima para fundamentos históricos;
- parâmetros tipados, finitos, limitados e relacionados;
- parâmetros fixos não sobrescrevíveis;
- custos por lado;
- profit factor monetário;
- ação atual separada do estado da posição.

## 5. Autorizações

As permissões são independentes para Graham, preço-teto por yield, pares e valor econômico. ALB concede automaticamente as quatro. A API valida o uso do filtro e também remove colunas e histórico não autorizados da resposta. Ocultar um botão no navegador não é considerado controle de acesso.

## 6. Referências metodológicas

- Aswath Damodaran, introdução a DCF, dividend discount models e valuation relativo: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/background/valintro.htm
- Aswath Damodaran, conciliação entre DCF e valuation relativo: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/littlebook/reconcilingdcfandrelative.htm
- CME Group, fair value de índices futuros: https://www.cmegroup.com/trading/equity-index/fairvalue.html
- CME Group, basis em futuros de índices: https://www.cmegroup.com/education/courses/introduction-to-equity-index-products/what-is-equity-index-basis

## 7. Conclusão

As duas fórmulas existentes foram mantidas e nomeadas com precisão. As duas novas famílias escolhidas são as melhores para a fase atual porque uma aproveita dados de múltiplos já disponíveis e a outra cria a estrutura econômica correta sem inventar fluxos. A arquitetura está pronta para DCF, NAV, look-through e cost of carry quando suas fontes confiáveis forem adicionadas.
