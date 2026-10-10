"use strict";

// Carregado sob demanda pela V1.23.8 R1. Mantém as mesmas fórmulas,
// permissões e rotas da implementação anteriormente embutida em app.js.
(()=>{
const filterDefinitions = {
  fundamental: [
    ["price","Preço","Cotação mais recente disponível."],["pe","P/L","Preço dividido pelo lucro por ação."],["pbv","P/VP","Preço dividido pelo valor patrimonial por ação."],["dividend_yield_pct","Dividend yield (%)","Proventos dos últimos 12 meses em relação ao preço."],
    ["ev_ebitda","EV/EBITDA","Valor da firma em relação ao EBITDA."],["ebit_margin_pct","Margem EBIT (%)","EBIT dividido pela receita líquida."],["net_margin_pct","Margem líquida (%)","Lucro líquido dividido pela receita."],
    ["current_ratio","Liquidez corrente","Ativo circulante dividido pelo passivo circulante."],["roe_pct","ROE (%)","Lucro líquido em relação ao patrimônio líquido."],["roic_pct","ROIC (%)","Retorno operacional sobre o capital investido."],
    ["gross_debt_to_equity","Dívida bruta/patrimônio","Dívida bruta em relação ao patrimônio."],["net_debt_to_ebitda","Dívida líquida/EBITDA","Anos aproximados de EBITDA para cobrir a dívida líquida."],
    ["revenue_cagr_5y_pct","CAGR receita 5a (%)","Crescimento anual composto da receita em cinco anos."],["earnings_cagr_5y_pct","CAGR lucro 5a (%)","Crescimento anual composto do lucro em cinco anos."],
    ["daily_liquidity","Liquidez diária","Volume financeiro médio negociado por dia."],["ffo_yield_pct","FFO yield (%)","Geração operacional do FII em relação ao preço."],["cap_rate_pct","Cap rate (%)","Renda operacional dos imóveis em relação ao valor dos ativos."],
    ["vacancy_pct","Vacância física (%)","Percentual da área não ocupada."],["financial_vacancy_pct","Vacância financeira (%)","Percentual da receita potencial não recebida."],["ltv_pct","LTV (%)","Dívida do fundo em relação ao valor dos imóveis."],
  ],
  scores: [["quality_score","Qualidade","Rentabilidade, margens, dívida e liquidez corrente, com perfil por setor."],["value_score","Valor","Valuation, dividendos e potencial de Graham."],["growth_score","Crescimento","CAGR de receita e lucro em cinco anos."],["technical_score","Técnica","Médias de 20, 50 e 200 períodos, RSI 14, MACD e momentum de 3 meses."],["risk_score","Risco","Volatilidade, drawdown e alavancagem; quanto maior, melhor o controle de risco."],["liquidity_score","Liquidez","Escala da liquidez financeira diária."],["alb_score","Nota ALB","Média ponderada das notas, ajustada ao perfil setorial."],["data_quality_score","Qualidade dos dados","Cobertura, validade e atualidade dos dados usados no cálculo."]],
};

function helpMark(text) { return text ? `<button type="button" class="help-mark" title="${esc(text)}" aria-label="${esc(text)}">?</button>` : ""; }

function numericRange(key, label, kind="filter", help="") {
  const attr = kind === "score" ? "data-score-field" : kind === "technical" ? "data-technical-field" : "data-filter-field";
  return `<div class="field" ${attr}="${key}"><label>${esc(label)} ${helpMark(help)}</label><div class="range-pair"><input type="number" step="any" data-bound="min" placeholder="Mín."><input type="number" step="any" data-bound="max" placeholder="Máx."></div></div>`;
}

function renderFilterInputs() {
  $("#fundamental-filters").innerHTML = `
    <div class="field"><label>Máximo de ativos: <strong id="analysis-limit-label">${state.analysisLimit}</strong></label><input id="analysis-limit" type="range" min="5" max="100" step="5" value="${state.analysisLimit}"></div>
    <div class="field stock-only-filter"><label>Participação no IBOV</label><select id="ibov-membership"><option value="any">Qualquer</option><option value="inside">Somente no IBOV</option><option value="outside">Fora do IBOV</option></select></div>
    <div class="field stock-only-filter"><label>Porte da empresa</label><select id="company-sizes" multiple size="3"><option value="large">Blue Chip / Large Cap</option><option value="mid">Mid Cap</option><option value="small">Small Cap</option></select></div>
    <div class="field wide-action valuation-filter"><label>Metodologias de valor ${helpMark("Combine até quatro famílias. Um método sem dados suficientes reprova o critério ativo, sem estimativas artificiais.")}</label>
      <div class="valuation-choice-grid">
        <label class="check" data-valuation-types="stock"><input id="below-graham" type="checkbox"><span><span data-valuation-label>Número de Graham</span><small data-valuation-status></small></span></label>
        <label class="check" data-valuation-types="stock,fii"><input id="below-barsi" type="checkbox"><span><span data-valuation-label>Preço-teto por dividend yield-alvo (6%, últimos 12 meses)</span><small data-valuation-status></small></span></label>
        <label class="check" data-valuation-types="stock,fii,etf,bdr"><input id="below-relative" type="checkbox"><span><span data-valuation-label>Valuation relativo por pares comparáveis</span><small data-valuation-status></small></span></label>
        <label class="check" data-valuation-types="stock,etf,bdr,future"><input id="below-economic" type="checkbox"><span><span data-valuation-label>Valor econômico (Gordon com cenários explícitos)</span><small data-valuation-status></small></span></label>
      </div>
      <div class="filter-grid compact-grid valuation-controls">
        <div class="field"><label>Combinação</label><select id="valuation-logic"><option value="all">Todos os métodos selecionados</option><option value="any">Ao menos um método</option></select></div>
        <div class="field"><label>Potencial mínimo (%) ${helpMark("É a valorização mínima exigida entre a referência calculada e o preço atual: 100 × (valor de referência ÷ preço atual − 1). Exemplo: 20 exige potencial de pelo menos 20%. Deixe vazio para exigir apenas que o preço esteja abaixo da referência. Em Todos, cada método selecionado precisa atingir o mínimo; em Qualquer, basta um.")}</label><input id="valuation-min-upside" type="number" min="0" max="10000" step="0.1" placeholder="Opcional — ex.: 20"><small>Valorização mínima sobre o preço atual; vazio = somente abaixo da referência.</small></div>
      </div>
      <details id="economic-assumptions" class="filter-subgroup" open><summary>Cenários do valor econômico: Conservador, Base e Otimista</summary>
        <div class="notice info">O modelo não usa crescimento ou retorno ocultos. Para usar os proventos dos últimos 12 meses, marque a confirmação abaixo; eles podem não representar um dividendo sustentável.</div>
        <label class="check"><input id="economic-use-ttm" type="checkbox"> Usar provento dos últimos 12 meses como D0 não normalizado</label>
        <div class="filter-grid compact-grid">
          <div class="field"><label>Conservador: retorno (%)</label><input id="economic-conservative-return" type="number" min="0.1" max="100" step="0.1" value="16"></div>
          <div class="field"><label>Conservador: crescimento (%)</label><input id="economic-conservative-growth" type="number" min="0" max="99" step="0.1" value="1"></div>
          <div class="field"><label>Base: retorno (%)</label><input id="economic-base-return" type="number" min="0.1" max="100" step="0.1" value="13"></div>
          <div class="field"><label>Base: crescimento (%)</label><input id="economic-base-growth" type="number" min="0" max="99" step="0.1" value="3"></div>
          <div class="field"><label>Otimista: retorno (%)</label><input id="economic-optimistic-return" type="number" min="0.1" max="100" step="0.1" value="11"></div>
          <div class="field"><label>Otimista: crescimento (%)</label><input id="economic-optimistic-growth" type="number" min="0" max="99" step="0.1" value="4"></div>
          <div class="field"><label>Margem de segurança (%)</label><input id="economic-margin" type="number" min="0" max="99" step="0.1" value="20"></div>
        </div>
      </details>
      <div id="class-valuation-note" class="notice info hidden"></div>
      <small id="valuation-permission-note"></small>
    </div>
    <details class="filter-subgroup" open><summary>Indicadores fundamentalistas</summary><div class="filter-grid">${filterDefinitions.fundamental.map(([key,label,help])=>numericRange(key,label,"filter",help)).join("")}</div></details>
    <details class="filter-subgroup"><summary>Notas e qualidade</summary><div class="filter-grid">${filterDefinitions.scores.map(([key,label,help])=>numericRange(key,label,"score",help)).join("")}</div></details>`;
  $("#technical-filters").innerHTML = `
    ${numericRange("rsi14","RSI 14","technical","Força relativa calculada em 14 pregões pelo suavizamento de Wilder.")}
    <div class="field"><label>Média da tendência ${helpMark("Compara o preço atual à média simples de 20 ou 21 períodos, nos gráficos diário, semanal e mensal.")}</label><select id="trend-period"><option value="21">21 períodos</option><option value="20">20 períodos</option></select></div>
    <div class="field"><label>Tendência diária ${helpMark("Preço atual acima ou abaixo da média escolhida no gráfico diário.")}</label><select id="trend-daily"><option value="any">Qualquer</option><option value="up">Alta</option><option value="down">Baixa</option></select></div>
    <div class="field"><label>Tendência semanal ${helpMark("Preço atual acima ou abaixo da média escolhida em semanas concluídas.")}</label><select id="trend-weekly"><option value="any">Qualquer</option><option value="up">Alta</option><option value="down">Baixa</option></select></div>
    <div class="field"><label>Tendência mensal ${helpMark("Preço atual acima ou abaixo da média escolhida em meses concluídos.")}</label><select id="trend-monthly"><option value="any">Qualquer</option><option value="up">Alta</option><option value="down">Baixa</option></select></div>
    <div class="field"><label>Período dos pivôs</label><select id="pivot-timeframe"><option value="daily">Diário</option><option value="weekly">Semanal</option><option value="monthly">Mensal</option></select></div>
    <div class="field"><label>Zona entre pivôs</label><select id="pivot-zone"><option value="any">Qualquer</option><option value="below_s3">Abaixo de S3</option><option value="s3_s2">S3–S2</option><option value="s2_s1">S2–S1</option><option value="s1_pp">S1–Pivô</option><option value="pp_r1">Pivô–R1</option><option value="r1_r2">R1–R2</option><option value="r2_r3">R2–R3</option><option value="above_r3">Acima de R3</option></select></div>
    <div class="field"><label>Próximo de</label><select id="near-pivot"><option value="none">Sem filtro</option><option value="s3">Suporte 3</option><option value="s2">Suporte 2</option><option value="s1">Suporte 1</option><option value="pp">Pivô</option><option value="r1">Resistência 1</option><option value="r2">Resistência 2</option><option value="r3">Resistência 3</option></select></div>
    <div class="field"><label>Tolerância ao pivô (%)</label><input id="pivot-tolerance" type="number" min="0" max="20" step="0.1" value="0.5"></div>
    <div class="field"><label>Volume acima da média de 9 ${helpMark("O volume atual precisa superar a média simples dos nove períodos concluídos anteriores.")}</label><label class="check"><input id="volume-daily-ma9" type="checkbox"> Diário</label><label class="check"><input id="volume-monthly-ma9" type="checkbox"> Mensal</label></div>
    <button id="apply-advanced-filters" class="button primary wide-action">Aplicar ajustes</button>`;
  updateFilterAvailability();
}

function updateFilterAvailability() {
  $$(".stock-only-filter").forEach(node=>node.classList.toggle("hidden",analysisType()!=="stock"));
  const type=analysisType(),supportsFundamentals=["stock","fii"].includes(type),supportsTechnical=["stock","fii","etf","bdr","future"].includes(type);
  const access=state.session?.access||{},alb=Boolean(access.can_use_alb_analysis);
  $$('[data-filter-field] input,[data-score-field] input').forEach(node=>node.disabled=!supportsFundamentals);
  $$("#technical-filters input,#technical-filters select").forEach(node=>node.disabled=!supportsTechnical);
  if($("#analysis-limit"))$("#analysis-limit").disabled=false;
  const permissions={"below-graham":alb||access.can_use_graham_valuation,"below-barsi":alb||access.can_use_dividend_ceiling,"below-relative":alb||access.can_use_relative_valuation,"below-economic":alb||access.can_use_economic_valuation};
  const valuationLabels={
    stock:{"below-graham":"Número de Graham","below-barsi":"Preço-teto por dividend yield-alvo (6%, últimos 12 meses)","below-relative":"Valuation relativo por pares comparáveis","below-economic":"Valor econômico (Gordon com cenários explícitos)"},
    fii:{"below-graham":"Número de Graham","below-barsi":"Preço-teto por dividend yield-alvo (6%, últimos 12 meses)","below-relative":"Valuation relativo por FIIs comparáveis","below-economic":"Valor econômico por classe"},
    etf:{"below-graham":"Número de Graham","below-barsi":"Preço-teto por dividend yield-alvo","below-relative":"Prêmio/desconto relativo ao NAV dos ETFs pares","below-economic":"Referência patrimonial do ETF (NAV)"},
    bdr:{"below-graham":"Número de Graham no ativo-lastro","below-barsi":"Preço-teto de proventos do ativo-lastro","below-relative":"Valuation relativo P/VP entre BDRs comparáveis","below-economic":"Paridade do BDR com o ativo-lastro"},
    future:{"below-graham":"Número de Graham","below-barsi":"Preço-teto por dividendos","below-relative":"Valuation relativo por pares","below-economic":"Preço teórico por custo de carregamento"},
  };
  const classNotes={
    etf:"ETFs: o valor patrimonial recupera o NAV por cota a partir do prêmio/desconto informado; o relativo compara esse prêmio apenas com ETFs na mesma moeda.",
    bdr:"BDRs: o relativo usa P/VP de BDRs do mesmo setor ou indústria. A paridade econômica só é calculada quando preço do lastro, câmbio e razão do programa estiverem verificados.",
    future:"Futuros: o preço teórico usa o contrato frontal, seu vencimento, o ativo à vista e a taxa de carregamento. Contratos sem lastro identificado continuam N/D.",
  };
  Object.entries(permissions).forEach(([id,allowed])=>{
    const input=$(`#${id}`),holder=input?.closest("[data-valuation-types]");
    const applicable=Boolean(holder?.dataset.valuationTypes.split(",").includes(type));
    if(input)input.disabled=!allowed||!applicable;
    if(holder){
      const label=holder.querySelector("[data-valuation-label]");if(label)label.textContent=valuationLabels[type]?.[id]||label.textContent;
      const unavailable=!applicable, reason=unavailable?"N/D: esta metodologia não representa corretamente esta classe.":!allowed?"Disponível mediante autorização individual.":"Disponível para esta conta; cada ativo ainda precisa ter os insumos necessários.";
      holder.classList.toggle("unavailable",unavailable||!allowed);
      holder.title=reason;
      const status=holder.querySelector("[data-valuation-status]");if(status)status.textContent=reason;
    }
  });
  const canEconomic=Boolean(permissions["below-economic"]&&type==="stock");
  $$("#economic-assumptions input").forEach(node=>node.disabled=!canEconomic);
  if($("#economic-assumptions"))$("#economic-assumptions").classList.toggle("hidden",type!=="stock");
  if($("#class-valuation-note")){const note=classNotes[type]||"";$("#class-valuation-note").textContent=note;$("#class-valuation-note").classList.toggle("hidden",!note);}
  if($("#valuation-logic"))$("#valuation-logic").disabled=false;
  if($("#valuation-min-upside"))$("#valuation-min-upside").disabled=false;
  if($("#valuation-permission-note"))$("#valuation-permission-note").textContent="Cada metodologia exige autorização própria; ALB libera as quatro. Métodos sem dados suficientes aparecem como N/D e nunca aprovam artificialmente um ativo.";
  if($("#apply-advanced-filters")) $("#apply-advanced-filters").disabled=!supportsTechnical;
  $$("#analysis-preset-row [data-preset-id]").forEach(node=>{
    const permission=node.dataset.presetId==="cnpi"?"can_use_fdi_analysis":node.dataset.presetId==="alb"?"can_use_alb_analysis":null;
    node.disabled=!supportsTechnical||Boolean(permission&&!access[permission]);
    node.title=node.disabled&&permission?"Análise disponível mediante autorização do administrador.":!supportsFundamentals&&permission?"Versão técnica desta análise para a classe selecionada.":"";
  });
  if($("#analysis-filter-notice")) {
    $("#analysis-filter-notice").textContent=!supportsFundamentals?"Padrão, FDI e ALB usam critérios técnicos próprios nesta classe. As metodologias compatíveis agora usam dados específicos do ativo; cada linha continua N/D quando seu insumo não estiver disponível.":"Filtros fundamentalistas e técnicos estão ativos. As metodologias de valor respeitam autorizações e aplicabilidade.";
  }
}

function resetAdvancedFilters() {
  $$('[data-filter-field] input,[data-score-field] input,[data-technical-field] input').forEach(input=>input.value="");
  ["trend-daily","trend-weekly","trend-monthly"].forEach(id=>{if($(`#${id}`))$(`#${id}`).value="any";});
  if($("#pivot-zone")) $("#pivot-zone").value="any";
  if($("#near-pivot")) $("#near-pivot").value="none";
  if($("#trend-period")) $("#trend-period").value="21";
  if($("#pivot-timeframe")) $("#pivot-timeframe").value="daily";
  if($("#pivot-tolerance")) $("#pivot-tolerance").value="0.5";
  ["below-graham","below-barsi","below-relative","below-economic","economic-use-ttm","volume-daily-ma9","volume-monthly-ma9"].forEach(id=>{if($(`#${id}`))$(`#${id}`).checked=false;});
  if($("#valuation-logic"))$("#valuation-logic").value="all";
  if($("#valuation-min-upside"))$("#valuation-min-upside").value="";
  const economicDefaults={"economic-conservative-return":16,"economic-conservative-growth":1,"economic-base-return":13,"economic-base-growth":3,"economic-optimistic-return":11,"economic-optimistic-growth":4,"economic-margin":20};
  Object.entries(economicDefaults).forEach(([id,value])=>{if($(`#${id}`))$(`#${id}`).value=String(value);});
  if($("#ibov-membership")) $("#ibov-membership").value="any";
  if($("#company-sizes")) [...$("#company-sizes").options].forEach(option=>option.selected=false);
}

function analysisType() {
  return ({stocks:"stock",fiis:"fii",etfs:"etf",bdrs:"bdr",futures:"future"})[state.tabs.analysis];
}

function normalizedConfiguration(saved) {
  const filters=saved?.filters||saved||{};
  if(filters.schema_version===2)return filters.configuration||{};
  if(filters.fundamental_filters)return filters;
  const fundamental_filters={};
  const mapping={roe_min:["roe_pct","min"],net_margin_min:["net_margin_pct","min"],ebit_margin_min:["ebit_margin_pct","min"],revenue_cagr_5y_min:["revenue_cagr_5y_pct","min"],pe_min:["pe","min"],pe_max:["pe","max"],pbv_max:["pbv","max"],dividend_yield_min:["dividend_yield_pct","min"],ev_ebitda_max:["ev_ebitda","max"],gross_debt_to_equity_max:["gross_debt_to_equity","max"],current_ratio_min:["current_ratio","min"],daily_liquidity_min:["daily_liquidity","min"],ffo_yield_min:["ffo_yield_pct","min"],cap_rate_min:["cap_rate_pct","min"],vacancy_max:["vacancy_pct","max"]};
  Object.entries(mapping).forEach(([oldKey,[field,bound]])=>{if(!nullable(filters[oldKey])){fundamental_filters[field]??={min:null,max:null};fundamental_filters[field][bound]=filters[oldKey];}});
  return {asset_type:saved?.asset_type||analysisType(),fundamental_filters,score_filters:{},valuation_flags:{below_graham:Boolean(filters.require_below_graham),below_barsi_6pct:Boolean(filters.require_below_dividend_target)},technical_filters:{},trend_period:21,pivot_timeframe:"daily",include_technical_columns:true,limit:50,company_sizes:[],ibov_membership:"any"};
}

function setRangeValue(selector, range) {
  const group=$(selector); if(!group)return;
  group.querySelector('[data-bound="min"]').value=range?.min??"";
  group.querySelector('[data-bound="max"]').value=range?.max??"";
}

function fillAnalysisForm(configuration={}) {
  resetAdvancedFilters();
  Object.entries(configuration.fundamental_filters||{}).forEach(([key,value])=>setRangeValue(`[data-filter-field="${key}"]`,value));
  Object.entries(configuration.score_filters||{}).forEach(([key,value])=>setRangeValue(`[data-score-field="${key}"]`,value));
  const technical=configuration.technical_filters||{};
  setRangeValue('[data-technical-field="rsi14"]',technical.rsi14);
  if($("#trend-daily")) $("#trend-daily").value=technical.daily_trend||"any";
  if($("#trend-weekly")) $("#trend-weekly").value=technical.weekly_trend||"any";
  if($("#trend-monthly")) $("#trend-monthly").value=technical.monthly_trend||"any";
  if($("#trend-period")) $("#trend-period").value=String(configuration.trend_period||21);
  if($("#pivot-timeframe")) $("#pivot-timeframe").value=configuration.pivot_timeframe||"daily";
  if($("#pivot-zone")) $("#pivot-zone").value=technical.pivot_zone||"any";
  if($("#near-pivot")) $("#near-pivot").value=technical.near_pivot_level||"none";
  if($("#pivot-tolerance")) $("#pivot-tolerance").value=technical.pivot_tolerance_pct??0.5;
  if($("#volume-daily-ma9")) $("#volume-daily-ma9").checked=Boolean(technical.volume_daily_above_ma9);
  if($("#volume-monthly-ma9")) $("#volume-monthly-ma9").checked=Boolean(technical.volume_monthly_above_ma9);
  if($("#below-graham")) $("#below-graham").checked=Boolean(configuration.valuation_flags?.below_graham);
  if($("#below-barsi")) $("#below-barsi").checked=Boolean(configuration.valuation_flags?.below_barsi_6pct);
  if($("#below-relative")) $("#below-relative").checked=Boolean(configuration.valuation_flags?.below_relative_value||configuration.valuation_flags?.below_relative_peers);
  if($("#below-economic")) $("#below-economic").checked=Boolean(configuration.valuation_flags?.below_economic_value||configuration.valuation_flags?.below_gordon_ddm);
  if($("#valuation-logic")) $("#valuation-logic").value=configuration.valuation_flags?.logic||configuration.valuation_flags?.valuation_logic||"all";
  if($("#valuation-min-upside")) $("#valuation-min-upside").value=configuration.valuation_flags?.minimum_upside_pct??"";
  const economic=configuration.valuation_assumptions?.economic_value||configuration.valuation_assumptions?.gordon_growth_ddm||{};
  if($("#economic-use-ttm"))$("#economic-use-ttm").checked=Boolean(economic.use_ttm_dividend);
  [["conservative","economic-conservative"],["base","economic-base"],["optimistic","economic-optimistic"]].forEach(([name,id])=>{const scenario=economic.scenarios?.[name]||economic[name];if(scenario){$(`#${id}-return`).value=scenario.required_return_pct;$(`#${id}-growth`).value=scenario.growth_pct;}});
  if($("#economic-margin")&&!nullable(economic.margin_of_safety_pct))$("#economic-margin").value=economic.margin_of_safety_pct;
  if($("#ibov-membership")) $("#ibov-membership").value=configuration.ibov_membership||"any";
  if($("#company-sizes")) [...$("#company-sizes").options].forEach(option=>option.selected=(configuration.company_sizes||[]).includes(option.value));
  state.analysisLimit=Number(configuration.limit||50);
  if($("#analysis-limit")) $("#analysis-limit").value=String(state.analysisLimit);
  if($("#analysis-limit-label")) $("#analysis-limit-label").textContent=state.analysisLimit;
}

function analysisRequestFromForm() {
  const fundamental_filters={};
  $$("[data-filter-field]").forEach(group=>{
    const min=group.querySelector('[data-bound="min"]').value,max=group.querySelector('[data-bound="max"]').value;
    if(min!==""||max!=="")fundamental_filters[group.dataset.filterField]={min:min===""?null:Number(min),max:max===""?null:Number(max)};
  });
  const score_filters={};
  $$('[data-score-field]').forEach(group=>{
    const min=group.querySelector('[data-bound="min"]').value,max=group.querySelector('[data-bound="max"]').value;
    if(min!==""||max!=="")score_filters[group.dataset.scoreField]={min:min===""?null:Number(min),max:max===""?null:Number(max)};
  });
  const rsiGroup=$("[data-technical-field='rsi14']"),rsiMin=rsiGroup?.querySelector('[data-bound="min"]').value,rsiMax=rsiGroup?.querySelector('[data-bound="max"]').value;
  const technical_filters={daily_trend:$("#trend-daily")?.value||"any",weekly_trend:$("#trend-weekly")?.value||"any",monthly_trend:$("#trend-monthly")?.value||"any",pivot_zone:$("#pivot-zone")?.value||"any",near_pivot_level:$("#near-pivot")?.value||"none",pivot_tolerance_pct:Number($("#pivot-tolerance")?.value||.5),volume_daily_above_ma9:Boolean($("#volume-daily-ma9")?.checked),volume_monthly_above_ma9:Boolean($("#volume-monthly-ma9")?.checked)};
  if(rsiMin!==""||rsiMax!=="")technical_filters.rsi14={min:rsiMin===""?null:Number(rsiMin),max:rsiMax===""?null:Number(rsiMax)};
  state.analysisLimit=Number($("#analysis-limit")?.value||50);
  const valuation_flags={below_graham:Boolean($("#below-graham")?.checked),below_barsi_6pct:Boolean($("#below-barsi")?.checked),below_relative_value:Boolean($("#below-relative")?.checked),below_economic_value:Boolean($("#below-economic")?.checked),logic:$("#valuation-logic")?.value||"all"};
  if($("#valuation-min-upside")?.value!=="")valuation_flags.minimum_upside_pct=Number($("#valuation-min-upside").value);
  const valuation_assumptions={relative_peers:{minimum_peers:5,winsor_limits:[0.10,0.90]}};
  if(valuation_flags.below_economic_value&&analysisType()==="stock")valuation_assumptions.economic_value={use_ttm_dividend:Boolean($("#economic-use-ttm")?.checked),margin_of_safety_pct:Number($("#economic-margin")?.value||20),scenarios:{conservative:{required_return_pct:Number($("#economic-conservative-return")?.value),growth_pct:Number($("#economic-conservative-growth")?.value)},base:{required_return_pct:Number($("#economic-base-return")?.value),growth_pct:Number($("#economic-base-growth")?.value)},optimistic:{required_return_pct:Number($("#economic-optimistic-return")?.value),growth_pct:Number($("#economic-optimistic-growth")?.value)}}};
  return {asset_type:analysisType(),fundamental_filters,score_filters,valuation_flags,valuation_assumptions,technical_filters,trend_period:Number($("#trend-period")?.value||21),pivot_timeframe:$("#pivot-timeframe")?.value||"daily",include_technical_columns:true,limit:state.analysisLimit,company_sizes:$("#company-sizes")?[...$("#company-sizes").selectedOptions].map(option=>option.value):[],ibov_membership:$("#ibov-membership")?.value||"any"};
}

function validateAnalysisRequest(request) {
  const flags=request.valuation_flags||{};
  const selected=["below_graham","below_barsi_6pct","below_relative_value","below_economic_value"].filter(key=>flags[key]);
  if(!nullable(flags.minimum_upside_pct)&&!selected.length)throw new Error("Selecione ao menos uma metodologia antes de exigir um potencial mínimo.");
  if(!nullable(flags.minimum_upside_pct)&&Number(flags.minimum_upside_pct)<0)throw new Error("O potencial mínimo deve ser zero ou positivo.");
  if(!flags.below_economic_value||request.asset_type!=="stock")return;
  const economic=request.valuation_assumptions?.economic_value||{};
  if(!economic.use_ttm_dividend)throw new Error("Para usar o valor econômico nesta tela, confirme o uso do provento dos últimos 12 meses como D0.");
  for(const [name,label] of [["conservative","Conservador"],["base","Base"],["optimistic","Otimista"]]){
    const scenario=economic.scenarios?.[name]||{},required=Number(scenario.required_return_pct),growth=Number(scenario.growth_pct);
    if(!Number.isFinite(required)||!Number.isFinite(growth)||required<=growth)throw new Error(`No cenário ${label}, o retorno exigido precisa ser maior que o crescimento.`);
  }
}

function revealSelectedValuationColumns(request) {
  const type=analysisType(),columns=orderedAnalysisColumns(type,analysisColumns(type)),active=new Set(visibleAnalysisColumns(type,columns).map(column=>column.id));
  const economicColumns={stock:["economic","economic_upside"],etf:["nav","nav_upside"],bdr:["parity","parity_upside"],future:["carry","basis"]}[type]||[];
  const map={below_graham:["graham","graham_upside"],below_barsi_6pct:["barsi","barsi_upside"],below_relative_value:["relative","relative_upside"],below_economic_value:economicColumns};
  Object.entries(map).forEach(([flag,ids])=>{if(request.valuation_flags?.[flag])ids.forEach(id=>active.add(id));});
  state.visibleColumns[type]=columns.filter(column=>column.always||active.has(column.id)).map(column=>column.id);
  persistVisibleColumns();
}

function renderCustomPresetButtons() {
  const root=$("#custom-preset-buttons"); if(!root)return;
  root.innerHTML=state.analysisCustom.map(item=>`<button class="preset-button" data-custom-filter-id="${esc(item.id)}">${esc(item.name)}</button>`).join("");
  const access=state.session?.access||{},allowed=Number(access.custom_filter_limit||0)>0&&["stock","fii","etf","bdr","future"].includes(analysisType());
  $("#custom-filter-controls").classList.toggle("hidden",!allowed);
  $("#custom-filter-usage").textContent=allowed?`${state.analysisCustomUsage.used} de ${state.analysisCustomUsage.limit} análise(s) personalizada(s) utilizada(s).`:"";
  updateCustomFilterControls();
}

function updateCustomFilterControls() {
  const current=state.currentCustomFilter;
  if(!$("#save-custom-filter"))return;
  $("#save-custom-filter").textContent=current?"Salvar alterações da análise personalizada":"Gravar análise personalizada";
  $("#delete-custom-filter").classList.toggle("hidden",!current);
  if(current&&$("#custom-filter-name"))$("#custom-filter-name").value=current.name||"";
}

async function loadAnalysisCatalog(type, force=false) {
  const needPresets=force||!state.analysisCatalog[type];
  const needCustom=Number(state.session?.access?.custom_filter_limit||0)>0&&(force||!state.analysisCustomCache[type]);
  const presetPromise=needPresets?api(`/screen/presets?asset_type=${type}`,{cacheTtlMs:300000,bypassCache:force}):Promise.resolve(null);
  const customPromise=needCustom?api(`/screen/custom-filters?asset_type=${type}`,{cacheTtlMs:120000,bypassCache:force}).catch(()=>({items:[],used:0,limit:0})):Promise.resolve(null);
  const presetPayload=await presetPromise;
  if(presetPayload){
    state.analysisCatalog[type]=Object.fromEntries((presetPayload.items||[]).map(item=>[item.id,item]));
    state.analysisColumnCatalog[type]=presetPayload.columns||null;
  }
  const applyCustom=custom=>{
    if(custom){state.analysisCustomCache[type]=custom.items||[];state.analysisCustomUsageCache[type]={used:custom.used||0,limit:custom.limit||0};}
    if(type!==analysisType())return;
    state.analysisCustom=state.analysisCustomCache[type]||[];
    state.analysisCustomUsage=state.analysisCustomUsageCache[type]||{used:0,limit:Number(state.session?.access?.custom_filter_limit||0)};
    renderCustomPresetButtons();
  };
  applyCustom(null);
  if(force)applyCustom(await customPromise);
  else if(needCustom)customPromise.then(applyCustom).catch(()=>{});
}

function prefetchAnalysisCatalogs(){
  const queue=["stock","fii","etf","bdr","future"].filter(type=>!state.analysisCatalog[type]);
  const next=()=>{
    const type=queue.shift();if(!type)return;
    api(`/screen/presets?asset_type=${type}`,{cacheTtlMs:300000}).then(payload=>{
      state.analysisCatalog[type]=Object.fromEntries((payload.items||[]).map(item=>[item.id,item]));
      state.analysisColumnCatalog[type]=payload.columns||null;
    }).catch(()=>{}).finally(()=>scheduleIdleTask(next,2200));
  };
  scheduleIdleTask(next,1000);
}

function markActiveAnalysis({presetId=null,custom=null}={}) {
  state.currentCustomFilter=custom;
  if(presetId)state.analysisPreset=presetId;
  $$("#analysis-preset-row .preset-button").forEach(button=>button.classList.toggle("active",presetId?button.dataset.presetId===presetId:button.dataset.customFilterId===custom?.id));
  const preset=state.analysisCatalog[analysisType()]?.[presetId],label=custom?.name||preset?.name||"Ajustes livres";
  $("#active-analysis-summary").textContent=`${label} • ${custom?"análise personalizada":preset?.active_variant==="owner"?"configuração administrativa ativa":"critérios originais do sistema"}`;
  if($("#custom-filter-name"))$("#custom-filter-name").value=custom?.name||"";
  updateCustomFilterControls();
}

async function selectSystemPreset(presetId) {
  const item=state.analysisCatalog[analysisType()]?.[presetId]; if(!item)return;
  fillAnalysisForm(item.configuration);markActiveAnalysis({presetId});await loadAnalysisResults();
}

async function selectCustomFilter(filterId) {
  const item=state.analysisCustom.find(row=>row.id===filterId);if(!item)return;
  fillAnalysisForm(normalizedConfiguration(item));markActiveAnalysis({custom:item});await applyAdvancedFilters(false);
}

async function saveCustomFilter() {
  const current=state.currentCustomFilter,name=$("#custom-filter-name").value.trim();
  if(!name){toast("Informe um nome para a análise personalizada.","error");$("#custom-filter-name").focus();return;}
  const method=current?"PUT":"POST",path=current?`/screen/custom-filters/${current.id}`:"/screen/custom-filters";
  const filters=analysisRequestFromForm();try{validateAnalysisRequest(filters);}catch(error){toast(error.message,"error");return;}
  const body=current?{name,filters}:{asset_type:analysisType(),name,filters};
  try {const saved=await api(path,{method,body:JSON.stringify(body)});await loadAnalysisCatalog(analysisType(),true);state.currentCustomFilter=state.analysisCustom.find(item=>item.id===saved.id)||saved;markActiveAnalysis({custom:state.currentCustomFilter});toast(current?"Alterações salvas.":"Análise personalizada gravada.","success");}
  catch(error){toast(error.message,"error");}
}

async function deleteCustomFilter() {
  const current=state.currentCustomFilter;if(!current)return;
  if(!confirm(`Excluir a análise personalizada "${current.name}"?`))return;
  try {await api(`/screen/custom-filters/${current.id}`,{method:"DELETE"});state.currentCustomFilter=null;await loadAnalysisCatalog(analysisType(),true);await selectSystemPreset("default");toast("Análise excluída.","success");}
  catch(error){toast(error.message,"error");}
}

async function loadAnalysis() {
  if(!$("#fundamental-filters")?.childElementCount)renderFilterInputs();
  const panelStarted=performance.now(),hadCached=state.analysisResultCache.has(analysisResultCacheKey(analysisType()));
  if(state.tabs.analysisMode==="guide"){renderIndicatorGuide();return;}
  $("#analysis-list-workspace").classList.remove("hidden");$("#analysis-guide").classList.add("hidden");
  const type=analysisType(),analysisTab=state.tabs.analysis,navigationSerial=state.navigationSerial;
  const now=Date.now();
  if(now-state.analysisUpdateCheckedAt>60000){
    state.analysisUpdateCheckedAt=now;
    api("/market-dashboard/updates",{cacheTtlMs:60000}).then(updatePayload=>{
      state.marketEnvelope=state.marketEnvelope||{};state.marketEnvelope.updates={...(state.marketEnvelope.updates||{}),...(updatePayload.updates||{})};
      if(state.view==="analysis"&&$("#analysis-update-status"))$("#analysis-update-status").innerHTML=marketUpdatePanel(["fundamentals","technical_daily","technical_intraday"],"Atualizações dos dados de análise");
      const ensureGroups=["catalog","fundamentals","technical_daily","technical_intraday"].filter(group=>["unavailable","stale","failed"].includes(updatePayload.updates?.[group]?.status));
      if(ensureGroups.length&&Date.now()-state.analysisEnsureSentAt>300000){
        state.analysisEnsureSentAt=Date.now();
        scheduleNavigationTask(()=>Promise.all(ensureGroups.map(group=>api(`/market-dashboard/groups/${encodeURIComponent(group)}/ensure`,{method:"POST",invalidateCache:false}))).catch(()=>{}),1500,navigationSerial);
      }
    }).catch(()=>{if(state.view==="analysis"&&$("#analysis-update-status"))$("#analysis-update-status").innerHTML='<div class="notice warning">O estado das atualizações não pôde ser consultado agora. Os dados disponíveis continuam acessíveis.</div>';});
  } else if($("#analysis-update-status")) {
    $("#analysis-update-status").innerHTML=marketUpdatePanel(["fundamentals","technical_daily","technical_intraday"],"Atualizações dos dados de análise");
  }
  try {
    await loadAnalysisCatalog(type);
    if(!navigationIsCurrent(navigationSerial,"analysis","analysis",analysisTab)||type!==analysisType())return;
    if(state.analysisLoadedType!==type){
      state.analysisLoadedType=type;state.currentCustomFilter=null;state.analysisPreset="default";
      if(!restoreAnalysisFormState(analysisTab)){fillAnalysisForm(state.analysisCatalog[type]?.default?.configuration||{});markActiveAnalysis({presetId:"default"});}
    }
  } catch(error){toast(`Configuração dos filtros: ${error.message}`,"error");}
  updateFilterAvailability();
  await loadAnalysisResults();
  if(navigationIsCurrent(navigationSerial,"analysis","analysis",analysisTab))reportPanelPerformance("analysis",panelStarted,{cacheState:hadCached?"warm":"cold"});
}

function analysisResultCacheKey(type) {
  return [type,state.currentCustomFilter?.id||"system",state.analysisPreset,state.analysisLimit].join("|");
}

async function loadAnalysisResults(force=false) {
  const root = $("#analysis-table");
  const type = analysisType();
  const analysisTab=state.tabs.analysis;
  const navigationSerial=state.navigationSerial;
  const requestSerial=++state.analysisRequestSerial;
  const cacheKey=analysisResultCacheKey(type),cached=state.analysisResultCache.get(cacheKey);
  if(!force&&cached&&Date.now()-cached.savedAt<ANALYSIS_CACHE_TTL_MS){
    state.analysisRows=cached.rows;renderAnalysisRows(cached.rows);
    if(cached.rows?.some(row=>row.backtest_leaders_pending))enrichAnalysisRowsInBackground(cached.rows,{type,analysisTab,cacheKey,requestSerial,navigationSerial});
    markPanelFresh("analysis",analysisTab);
    return;
  }
  if(cached?.rows?.length){state.analysisRows=cached.rows;renderAnalysisRows(cached.rows);root.insertAdjacentHTML("afterbegin",'<div class="notice info analysis-refreshing">Atualizando a lista em segundo plano…</div>');}
  else root.innerHTML = loadingCards(6);
  try {
    let rows, warnings=[];
    const presetItem=state.analysisCatalog[type]?.[state.analysisPreset];
    if (state.currentCustomFilter) {
      const payload=await api(`/screen/db/custom/${state.currentCustomFilter.id}?limit=${state.analysisLimit}`,{requestKey:"analysis"});rows=payload.rows||payload;warnings=payload?.meta?.warnings||[];
    } else if (type === "stock") rows = await api(`/screen/db/stocks/${state.analysisPreset}?limit=${state.analysisLimit}`, {requestKey:"analysis"});
    else if (type === "fii") rows = await api(`/screen/db/fiis/${state.analysisPreset}?limit=${state.analysisLimit}`, {requestKey:"analysis"});
    else if(presetItem?.active_variant==="owner") {
      const configuration={...(presetItem.configuration||{}),asset_type:type,limit:state.analysisLimit};
      const payload=await api("/screen/advanced",{method:"POST",requestKey:"analysis",body:JSON.stringify(configuration),invalidateCache:false});rows=payload.rows||payload;warnings=payload?.meta?.warnings||[];
    }
    else if(state.analysisPreset==="default") rows=await api(`/screen/db/universe/${type}?limit=${state.analysisLimit}`,{requestKey:"analysis"});
    else {
      const configuration={...(state.analysisCatalog[type]?.[state.analysisPreset]?.configuration||{}),asset_type:type,limit:state.analysisLimit};
      const payload=await api("/screen/advanced",{method:"POST",requestKey:"analysis",body:JSON.stringify(configuration),invalidateCache:false});rows=payload.rows||payload;warnings=payload?.meta?.warnings||[];
    }
    if (type === "stock") rows.sort((a,b)=>(Number(b.graham_upside_pct)||-Infinity)-(Number(a.graham_upside_pct)||-Infinity));
    else rows.sort((a,b)=>String(a.ticker).localeCompare(String(b.ticker)));
    if(!navigationIsCurrent(navigationSerial,"analysis","analysis",analysisTab)||state.tabs.analysisMode!=="list"||type!==analysisType()||requestSerial!==state.analysisRequestSerial||cacheKey!==analysisResultCacheKey(type))return;
    const primaryRows=state.session?.access?.can_view_backtests?rows.map(row=>({...row,backtest_leaders_pending:true})):rows;
    state.analysisRows = primaryRows;
    setBoundedCache(state.analysisResultCache,cacheKey,{savedAt:Date.now(),rows:primaryRows},ANALYSIS_RESULT_CACHE_LIMIT);
    state.analysisLastUpdatedAt[type]=Date.now();
    renderAnalysisRows(primaryRows);
    markPanelFresh("analysis",analysisTab);
    if(warnings.length)toast(warnings.join(" "),"warning");
    enrichAnalysisRowsInBackground(rows,{type,analysisTab,cacheKey,requestSerial,navigationSerial});
  } catch (error) {
    if(error.name==="AbortError"||state.view!=="analysis"||type!==analysisType()||requestSerial!==state.analysisRequestSerial)return;
    if(cached?.rows?.length){state.analysisRows=cached.rows;renderAnalysisRows(cached.rows);root.insertAdjacentHTML("afterbegin",'<div class="notice warning analysis-refreshing">Não foi possível renovar a lista agora. Exibindo a última consulta concluída.</div>');}
    else root.innerHTML = errorState(error, "analysis");
  }
}

function enrichAnalysisRowsInBackground(rows,{type,analysisTab,cacheKey,requestSerial,navigationSerial}){
  if(!state.session?.access?.can_view_backtests||!rows?.length)return;
  enrichBacktestLeaders(rows).then(enrichedRows=>{
    if(!navigationIsCurrent(navigationSerial,"analysis","analysis",analysisTab)||state.tabs.analysisMode!=="list"||type!==analysisType()||requestSerial!==state.analysisRequestSerial||cacheKey!==analysisResultCacheKey(type))return;
    state.analysisRows=enrichedRows;
    setBoundedCache(state.analysisResultCache,cacheKey,{savedAt:Date.now(),rows:enrichedRows},ANALYSIS_RESULT_CACHE_LIMIT);
    if(!patchAnalysisBacktestCells(enrichedRows))renderAnalysisRows(enrichedRows);
  }).catch(()=>{});
}

async function enrichBacktestLeaders(rows) {
  if (!state.session?.access?.can_view_backtests || !rows?.length) return rows || [];
  const tickers=rows.slice(0,100).map(row=>row.ticker).filter(Boolean).join(",");
  try {
    const payload=await api(`/backtests/leaderboard?per_asset=3&tickers=${encodeURIComponent(tickers)}`,{requestKey:"analysis-backtests",cacheTtlMs:60000});
    return rows.map(row=>{
      const leaders=payload.items?.[row.ticker]||[];
      return {...row,backtest_leaders_pending:false,backtest_leaders:leaders,best_signal:leaders[0]?.current_signal,best_strategy:leaders[0]?.strategy_name};
    });
  } catch(error) {
    if(error.name!=="AbortError") toast("Os sinais dos backtests serão exibidos assim que o catálogo estiver disponível.");
    return rows.map(row=>({...row,backtest_leaders_pending:false}));
  }
}

function signalLabel(value) {
  return ({buy:"Comprar",sell:"Vender",neutral:"Neutro",compra:"Comprar",venda:"Vender"})[String(value||"").toLowerCase()]||"—";
}

function backtestLeadersCell(row) {
  if(row.backtest_leaders_pending)return '<span class="secondary-loading"><span class="loading-dot" aria-hidden="true"></span> Carregando sinais…</span>';
  const leaders=(row.backtest_leaders||[]).slice(0,3);
  if(!leaders.length)return '<span class="status-chip status-empty" title="Nenhum resultado oficial distinto foi materializado para este ativo.">Sem resultado oficial</span>';
  return `<div class="backtest-leader-stack">${leaders.map((leader,index)=>`<div><span class="leader-rank">${index+1}</span><span><strong>${esc(leader.strategy_name||leader.strategy_id||"Estratégia")}</strong><small>${nullable(leader.ranking_score)?"":`Pontuação ${number(leader.ranking_score,1)}`}</small></span><span class="pill signal-${esc(leader.current_signal||"neutral")}">${signalLabel(leader.current_signal)}</span></div>`).join("")}</div>`;
}

function backtestLeaderCell(row,index) {
  if(row.backtest_leaders_pending)return '<span class="secondary-loading"><span class="loading-dot" aria-hidden="true"></span> Carregando…</span>';
  const leader=(row.backtest_leaders||[])[index];
  if(!leader)return '<span class="status-chip status-empty" title="Nenhum resultado oficial distinto foi materializado nesta posição.">Sem resultado oficial</span>';
  return `<div class="backtest-leader-single"><strong>${esc(leader.strategy_name||leader.strategy_id||"Estratégia")}</strong><span class="pill signal-${esc(leader.current_signal||"neutral")}">${signalLabel(leader.current_signal)}</span><small>${nullable(leader.ranking_score)?"Sem pontuação":`Pontuação ${number(leader.ranking_score,1)}`}</small></div>`;
}

function renderIndicatorGuide() {
  $("#analysis-count").textContent="";
  $("#analysis-list-workspace").classList.add("hidden");
  const root=$("#analysis-guide");root.classList.remove("hidden");
  const indicators=[...filterDefinitions.fundamental.map(([,label,description])=>({label,description})),
    {label:"Número de Graham",description:"Raiz quadrada de 22,5 × lucro por ação × valor patrimonial por ação. É uma referência conservadora para ações com lucro e patrimônio positivos, não um preço justo universal."},
    {label:"Preço-teto por dividend yield-alvo",description:"Proventos por ação dos últimos 12 meses divididos pela taxa-alvo explícita de 6%. Não é chamado de Bazin quando não há normalização histórica dos proventos."},
    {label:"Valuation relativo por pares",description:"Compara ações do mesmo setor, FIIs do mesmo segmento, ETFs pelo prêmio/desconto ao NAV na mesma moeda e BDRs pelo P/VP no mesmo setor ou indústria. Exige ao menos cinco pares e reduz o efeito de extremos antes dos cenários."},
    {label:"Valor econômico por classe",description:"Ações usam Gordon somente com D0 e três cenários explícitos. ETFs usam NAV por cota informado ou recuperado do prêmio/desconto. BDRs usam paridade apenas com lastro, câmbio e razão verificados. Futuros usam ativo à vista, carrego e vencimento do contrato frontal. Sem o insumo próprio, aparece N/D."},
    {label:"Potencial mínimo (%)",description:"Valorização mínima exigida entre a referência calculada e o preço atual: 100 × (valor de referência ÷ preço atual − 1). Se ficar vazio, o filtro exige apenas preço abaixo da referência. Com Todos, cada método deve atingir o mínimo; com Qualquer, basta um."},
    {label:"RSI 14",description:"Compara ganhos e perdas em 14 pregões pelo suavizamento de Wilder; extremos merecem contexto, não são ordem automática."},
    {label:"Tendências",description:"Alta quando o preço atual está acima da média simples de 20 ou 21 períodos. Semanas e meses em formação são excluídos."},
    {label:"Pivô, suportes e resistências",description:"PP=(máxima+mínima+fechamento)/3. R1=2×PP−mínima; S1=2×PP−máxima; R2/S2 usam a amplitude; R3/S3 usam os extremos e o PP."},
    {label:"Volume / média 9",description:"Compara o volume atual com a média simples dos nove períodos concluídos anteriores, separadamente no diário e no mensal."},
  ];
  const notes=filterDefinitions.scores.map(([,label,description])=>({label,description}));
  root.innerHTML=`<div class="guide-intro data-card"><div class="card-section"><p class="eyebrow">Base de consulta</p><h2>Como interpretar filtros, indicadores e notas</h2><p>Os filtros reduzem o universo; eles não substituem a análise do investidor. Campos sem dado não passam por um critério ativo, evitando aprovação artificial.</p></div></div>
    <div class="guide-grid">${sectionCard("Indicadores e filtros",`<div class="guide-list">${indicators.map(item=>`<details><summary>${esc(item.label)}</summary><p>${esc(item.description)}</p></details>`).join("")}</div>`,"Passe o mouse sobre o ? nos filtros para consultar estas definições")}${sectionCard("Notas de 0 a 100",`<div class="guide-list">${notes.map(item=>`<details><summary>${esc(item.label)}</summary><p>${esc(item.description)}</p></details>`).join("")}</div>`,"As notas usam somente componentes disponíveis e registram a cobertura dos dados")}</div>
    ${sectionCard("Como a Nota ALB é formada",`<div class="score-profile-grid"><article><strong>Empresas em geral</strong><span>Qualidade 25% • Valor 25% • Crescimento 15% • Técnica 10% • Risco 15% • Liquidez 10%</span></article><article><strong>Bancos</strong><span>Qualidade 30% • Valor 25% • Crescimento 10% • Técnica 10% • Risco 15% • Liquidez 10%</span></article><article><strong>Seguradoras</strong><span>Qualidade 28% • Valor 24% • Crescimento 13% • Técnica 10% • Risco 15% • Liquidez 10%</span></article><article><strong>Utilities</strong><span>Qualidade 25% • Valor 25% • Crescimento 10% • Técnica 10% • Risco 20% • Liquidez 10%</span></article><article><strong>FIIs</strong><span>Qualidade 25% • Valor 30% • Técnica 10% • Risco 20% • Liquidez 15%</span></article></div><div class="notice info" style="margin-top:14px">Se uma parte estiver sem dados, os pesos disponíveis são normalizados. A qualidade dos dados informa a cobertura para que a nota nunca pareça mais precisa do que realmente é.</div>`)}`;
}

function analysisColumns(type) {
  const common=[
    {id:"ticker",label:"Ativo",always:true,render:r=>`<span class="ticker-cell">${esc(r.ticker)}</span><br><small>${esc(r.name||"")}</small>`},
    {id:"price",label:"Preço",render:r=>money(r.price)},
    {id:"backtest_1",label:"1º backtest",render:r=>backtestLeaderCell(r,0)},
    {id:"backtest_2",label:"2º backtest",render:r=>backtestLeaderCell(r,1)},
    {id:"backtest_3",label:"3º backtest",render:r=>backtestLeaderCell(r,2)},
  ];
  const access=state.session?.access||{},alb=Boolean(access.can_use_alb_analysis),canGraham=Boolean(access.can_use_graham_valuation||alb),canDividend=Boolean(access.can_use_dividend_ceiling||alb),canRelative=Boolean(access.can_use_relative_valuation||alb),canEconomic=Boolean(access.can_use_economic_valuation||alb);
  const valuationCell=(row,family,valueField)=>{const result=row.valuation_methods?.[family]||{};if(result.status&&result.status!=="valid")return `<span class="status-chip status-na" title="${esc(result.reason||"Esta metodologia não se aplica ou não possui dados suficientes.")}">N/D</span>`;const scenarios=result.scenarios||{},scenarioItems=[["conservative","C"],["base","B"],["optimistic","O"]].filter(([key])=>!nullable(scenarios[key]?.value));return `<span class="valuation-base-value">${money(result.value??row[valueField])}</span>${scenarioItems.length?`<small class="valuation-mini-scenarios">${scenarioItems.map(([key,label])=>`${label}: ${money(scenarios[key].value)}`).join(" • ")}</small>`:""}`;};
  const upsideCell=(row,family,valueField)=>{const result=row.valuation_methods?.[family]||{};if(result.status&&result.status!=="valid")return "—";const value=result.upside_pct??row[valueField];return `<span class="${variationClass(value)}">${pct(value,true)}</span>`;};
  if(type==="stock") {
    return [common[0],
    {id:"sector",label:"Setor",render:r=>esc(r.sector_label||r.classification||"—")},
    {id:"company_size",label:"Porte",render:r=>esc(r.company_size_label||"—")},
    {id:"in_ibov",label:"IBOV",render:r=>nullable(r.in_ibov)?"—":r.in_ibov?"Sim":"Não"},common[1],
    {id:"pe",label:"P/L",render:r=>number(r.pe)},{id:"pbv",label:"P/VP",render:r=>number(r.pbv)},
    {id:"dy",label:"DY",render:r=>pct(r.dy??r.dividend_yield_pct)},{id:"roe",label:"ROE",render:r=>pct(r.roe??r.roe_pct)},
    {id:"graham",label:"Número de Graham",render:r=>valuationCell(r,"graham_reference","graham_number")},{id:"graham_upside",label:"Potencial Graham",render:r=>upsideCell(r,"graham_reference","graham_upside_pct")},
    {id:"barsi",label:"Preço-teto DY-alvo",render:r=>valuationCell(r,"dividend_yield_ceiling","dividend_yield_ceiling_value")},{id:"barsi_upside",label:"Potencial DY-alvo",render:r=>upsideCell(r,"dividend_yield_ceiling","dividend_yield_ceiling_upside_pct")},
    {id:"relative",label:"Valor relativo",render:r=>valuationCell(r,"relative_peers","relative_peers_value")},{id:"relative_upside",label:"Potencial relativo",render:r=>upsideCell(r,"relative_peers","relative_peers_upside_pct")},
    {id:"economic",label:"Valor econômico",render:r=>valuationCell(r,"economic_value","economic_value")},{id:"economic_upside",label:"Potencial econômico",render:r=>upsideCell(r,"economic_value","economic_value_upside_pct")},
    {id:"alb",label:"Nota ALB",render:r=>number(r.alb_score,1)},
    {id:"trend_daily",label:"Tendência alta",render:r=>r.trend_daily==="up"?"Sim":r.trend_daily==="down"?"Não":"—"},
    {id:"rsi",label:"RSI 14",render:r=>number(r.rsi14_screen)},
    ...["s3","s2","s1","pp","r1","r2","r3"].map(id=>({id,label:id==="pp"?"Pivô":id.toUpperCase(),render:r=>money(r[id])})),
    {id:"volume_daily",label:"Volume/Média 9 diário",render:r=>nullable(r.volume_daily_ratio)?"—":`${number(Number(r.volume_daily_ratio)*100,0)}%`},
    {id:"volume_monthly",label:"Volume/Média 9 mensal",render:r=>nullable(r.volume_monthly_ratio)?"—":`${number(Number(r.volume_monthly_ratio)*100,0)}%`},
    ...common.slice(2),
    ].filter(column=>!(["graham","graham_upside"].includes(column.id)&&!canGraham)&&!(["barsi","barsi_upside"].includes(column.id)&&!canDividend)&&!(["relative","relative_upside"].includes(column.id)&&!canRelative)&&!(["economic","economic_upside"].includes(column.id)&&!canEconomic));
  }
  if(type==="fii") return [common[0],{id:"segment",label:"Segmento",render:r=>esc(r.segment_label||r.classification||"—")},common[1],{id:"pbv",label:"P/VP",render:r=>number(r.pbv)},{id:"dy",label:"DY",render:r=>pct(r.dy??r.dividend_yield_pct)},{id:"ffo",label:"FFO yield",render:r=>pct(r.ffo_yield??r.ffo_yield_pct)},{id:"vacancy",label:"Vacância",render:r=>pct(r.vacancy??r.vacancy_pct)},{id:"barsi",label:"Preço-teto DY-alvo",render:r=>valuationCell(r,"dividend_yield_ceiling","dividend_yield_ceiling_value")},{id:"barsi_upside",label:"Potencial DY-alvo",render:r=>upsideCell(r,"dividend_yield_ceiling","dividend_yield_ceiling_upside_pct")},{id:"relative",label:"Valor relativo",render:r=>valuationCell(r,"relative_peers","relative_peers_value")},{id:"relative_upside",label:"Potencial relativo",render:r=>upsideCell(r,"relative_peers","relative_peers_upside_pct")},{id:"rsi",label:"RSI 14",render:r=>number(r.rsi14_screen)},...common.slice(2)].filter(column=>!(["barsi","barsi_upside"].includes(column.id)&&!canDividend)&&!(["relative","relative_upside"].includes(column.id)&&!canRelative));
  if(type==="etf") return [common[0],common[1],{id:"nav",label:"NAV por cota",render:r=>valuationCell(r,"economic_value","economic_value")},{id:"nav_upside",label:"Desconto/potencial ao NAV",render:r=>upsideCell(r,"economic_value","economic_value_upside_pct")},{id:"premium",label:"Prêmio/desconto informado",render:r=>pct(r.nav_discount_premium_pct,true)},{id:"expense",label:"Taxa de administração",render:r=>pct(r.expense_ratio_pct)},{id:"relative",label:"Referência pelos pares",render:r=>valuationCell(r,"relative_peers","relative_peers_value")},{id:"relative_upside",label:"Potencial relativo",render:r=>upsideCell(r,"relative_peers","relative_peers_upside_pct")},{id:"rsi",label:"RSI 14",render:r=>number(r.rsi14_screen)},...common.slice(2)].filter(column=>!(["nav","nav_upside"].includes(column.id)&&!canEconomic)&&!(["relative","relative_upside"].includes(column.id)&&!canRelative));
  if(type==="bdr") return [common[0],{id:"sector",label:"Setor",render:r=>esc(r.sector_label||r.sector||"—")},common[1],{id:"pbv",label:"P/VP informado",render:r=>number(r.pbv)},{id:"relative",label:"Referência P/VP dos pares",render:r=>valuationCell(r,"relative_peers","relative_peers_value")},{id:"relative_upside",label:"Potencial relativo",render:r=>upsideCell(r,"relative_peers","relative_peers_upside_pct")},{id:"parity",label:"Paridade com o lastro",render:r=>valuationCell(r,"economic_value","economic_value")},{id:"parity_upside",label:"Potencial pela paridade",render:r=>upsideCell(r,"economic_value","economic_value_upside_pct")},{id:"rsi",label:"RSI 14",render:r=>number(r.rsi14_screen)},...common.slice(2)].filter(column=>!(["relative","relative_upside"].includes(column.id)&&!canRelative)&&!(["parity","parity_upside"].includes(column.id)&&!canEconomic));
  if(type==="future") return [common[0],common[1],{id:"front",label:"Contrato frontal",render:r=>esc(r.front_contract||"—")},{id:"expiry",label:"Vencimento",render:r=>esc(r.expiration_date||"—")},{id:"spot",label:"Ativo à vista",render:r=>r.underlying_ticker?`${esc(r.underlying_ticker)} • ${money(r.underlying_spot_price)}`:"—"},{id:"carry",label:"Preço teórico",render:r=>valuationCell(r,"economic_value","economic_value")},{id:"basis",label:"Potencial / basis",render:r=>upsideCell(r,"economic_value","economic_value_upside_pct")},{id:"rsi",label:"RSI 14",render:r=>number(r.rsi14_screen)},...common.slice(2)].filter(column=>!(["carry","basis"].includes(column.id)&&!canEconomic));
  return [common[0],{id:"category",label:"Categoria",render:r=>esc(r.asset_type_label||r.classification||"—")},common[1],{id:"signal",label:"Sinal",render:r=>esc(r.signal_tv||"—")},{id:"rsi",label:"RSI 14",render:r=>number(r.rsi14_screen)},{id:"technical",label:"Nota técnica",render:r=>number(r.technical_score,1)},...common.slice(2)];
}

function expandBacktestColumnIds(values){
  return [...new Set((values||[]).flatMap(id=>id==="best_signal"?["backtest_1","backtest_2","backtest_3"]:[id]))];
}

function orderedAnalysisColumns(type,columns){
  const podium=["backtest_1","backtest_2","backtest_3"];
  const fallback={stock:["ticker","sector","price","pe","pbv","dy","roe","graham_upside","barsi","relative",...podium],fii:["ticker","segment","price","pbv","dy","ffo","vacancy","barsi","relative",...podium],etf:["ticker","price","nav","nav_upside","premium","relative",...podium],bdr:["ticker","sector","price","pbv","relative","relative_upside",...podium],future:["ticker","price","front","expiry","spot","carry","basis",...podium]};
  const preferred=expandBacktestColumnIds(state.analysisColumnCatalog[type]?.columns||state.analysisColumnCatalog[type]?.factory_columns||fallback[type]||[]);
  const byId=new Map(columns.map(column=>[column.id,column])),ordered=[];
  preferred.forEach(id=>{const column=byId.get(id);if(column){ordered.push(column);byId.delete(id);}});
  columns.forEach(column=>{if(byId.has(column.id)){ordered.push(column);byId.delete(column.id);}});
  return ordered;
}

function visibleAnalysisColumns(type, columns) {
  const podium=["backtest_1","backtest_2","backtest_3"];
  const defaults={stock:["ticker","sector","price","pe","pbv","dy","roe","graham_upside","barsi","relative",...podium],fii:["ticker","segment","price","pbv","dy","ffo","vacancy","barsi","relative",...podium],etf:["ticker","price","nav","nav_upside","premium","relative",...podium],bdr:["ticker","sector","price","pbv","relative","relative_upside",...podium],future:["ticker","price","front","expiry","spot","carry","basis",...podium]};
  const ordered=orderedAnalysisColumns(type,columns);
  const saved=expandBacktestColumnIds(state.visibleColumns[type]);
  const platformDefault=expandBacktestColumnIds(state.analysisColumnCatalog[type]?.columns||defaults[type]||ordered.map(column=>column.id));
  const active=new Set(saved.length?saved:platformDefault);
  return ordered.filter(column=>column.always||active.has(column.id));
}

function analysisSortValue(row,columnId){
  const direct={
    ticker:row.ticker,sector:row.sector_label||row.classification||row.sector,segment:row.segment_label||row.classification,
    company_size:row.company_size_label,in_ibov:row.in_ibov,price:row.price,pe:row.pe,pbv:row.pbv,
    dy:row.dy??row.dividend_yield_pct,roe:row.roe??row.roe_pct,ffo:row.ffo_yield??row.ffo_yield_pct,
    vacancy:row.vacancy??row.vacancy_pct,alb:row.alb_score,rsi:row.rsi14_screen,front:row.front_contract,
    expiry:row.expiration_date,premium:row.nav_discount_premium_pct,expense:row.expense_ratio_pct,
    volume_daily:row.volume_daily_ratio,volume_monthly:row.volume_monthly_ratio,trend_daily:row.trend_daily,
  };
  if(columnId.startsWith("backtest_"))return (row.backtest_leaders||[])[Number(columnId.slice(-1))-1]?.ranking_score??null;
  const valuationMap={
    graham:["graham_reference","graham_number"],graham_upside:["graham_reference","graham_upside_pct"],
    barsi:["dividend_yield_ceiling","dividend_yield_ceiling_value"],barsi_upside:["dividend_yield_ceiling","dividend_yield_ceiling_upside_pct"],
    relative:["relative_peers","relative_peers_value"],relative_upside:["relative_peers","relative_peers_upside_pct"],
    economic:["economic_value","economic_value"],economic_upside:["economic_value","economic_value_upside_pct"],
    nav:["economic_value","economic_value"],nav_upside:["economic_value","economic_value_upside_pct"],
    parity:["economic_value","economic_value"],parity_upside:["economic_value","economic_value_upside_pct"],
    carry:["economic_value","economic_value"],basis:["economic_value","economic_value_upside_pct"],
  };
  if(valuationMap[columnId]){const [family,fallback]=valuationMap[columnId];const result=row.valuation_methods?.[family]||{};return columnId.includes("upside")||columnId==="basis"||columnId==="nav_upside"||columnId==="parity_upside"?result.upside_pct??row[fallback]:result.value??row[fallback];}
  return Object.hasOwn(direct,columnId)?direct[columnId]:row[columnId];
}

function sortedAnalysisRows(rows,type=analysisType()){
  const sort=state.analysisSort[type];if(!sort?.column)return [...rows];
  const direction=sort.direction==="desc"?-1:1;
  return [...rows].sort((left,right)=>{
    const a=analysisSortValue(left,sort.column),b=analysisSortValue(right,sort.column);
    if(nullable(a)&&nullable(b))return String(left.ticker).localeCompare(String(right.ticker));
    if(nullable(a))return 1;if(nullable(b))return -1;
    const comparison=typeof a==="number"||typeof b==="number"?Number(a)-Number(b):String(a).localeCompare(String(b),"pt-BR",{numeric:true,sensitivity:"base"});
    return comparison*direction;
  });
}

function renderAnalysisRows(rows) {
  $("#analysis-count").textContent = `${rows.length} ativo${rows.length===1?"":"s"}`;
  if (!rows.length) { $("#analysis-table").innerHTML='<div class="empty-state"><strong>Nenhum ativo passou pelos filtros</strong><span class="status-chip status-empty">Sem resultado</span><p>Abra os ajustes para ampliar ou alterar os critérios.</p></div>'; return; }
  const type = analysisType();
  const displayRows=sortedAnalysisRows(rows,type),sort=state.analysisSort[type]||{};
  const allColumns=orderedAnalysisColumns(type,analysisColumns(type)), columns=visibleAnalysisColumns(type,allColumns);
  const active=new Set(columns.map(column=>column.id));
  const picker=`<details class="column-picker"><summary>Colunas visíveis</summary><div>${allColumns.filter(column=>!column.always).map(column=>`<label class="check"><input type="checkbox" data-column-id="${column.id}" ${active.has(column.id)?"checked":""}> ${esc(column.label)}</label>`).join("")}<button type="button" class="button ghost compact wide-action" data-reset-personal-columns="${esc(type)}">Usar padrão da plataforma</button></div></details>`;
  const density=`<div class="table-density" role="group" aria-label="Densidade da tabela"><button type="button" class="button ghost compact ${state.analysisDensity==="comfortable"?"active":""}" data-analysis-density="comfortable">Confortável</button><button type="button" class="button ghost compact ${state.analysisDensity==="compact"?"active":""}" data-analysis-density="compact">Compacta</button></div>`;
  $("#analysis-table").innerHTML = `<div class="table-toolbar"><div class="table-toolbar-main">${picker}${density}</div><span class="table-freshness"><span class="status-chip status-updated">Atualizado</span> ${esc(relativeUpdateLabel(state.analysisLastUpdatedAt[type]||Date.now()))}</span><span>Clique em um ativo para abrir todos os dados.</span></div><div class="table-scroll"><table class="analysis-data-table density-${esc(state.analysisDensity)}"><thead><tr>${columns.map(c=>`<th data-column-id="${esc(c.id)}" aria-sort="${sort.column===c.id?(sort.direction==="desc"?"descending":"ascending"):"none"}"><button type="button" class="table-sort ${sort.column===c.id?"active":""}" data-analysis-sort="${esc(c.id)}" aria-label="Ordenar por ${esc(c.label)}">${esc(c.label)}<span aria-hidden="true">${sort.column===c.id?(sort.direction==="desc"?"↓":"↑"):"↕"}</span></button></th>`).join("")}</tr></thead><tbody>${displayRows.map(r=>`<tr data-ticker="${esc(r.ticker)}">${columns.map(c=>`<td data-column-id="${esc(c.id)}">${c.render(r)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function patchAnalysisBacktestCells(rows) {
  const body=$("#analysis-table tbody");
  if(!body)return false;
  const renderedRows=[...body.querySelectorAll("tr[data-ticker]")];
  if(renderedRows.length!==rows.length)return false;
  const byTicker=new Map(renderedRows.map(element=>[element.dataset.ticker,element]));
  for(const row of rows){
    const element=byTicker.get(String(row.ticker||""));
    if(!element)return false;
    ["backtest_1","backtest_2","backtest_3"].forEach((columnId,index)=>{
      const cell=element.querySelector(`td[data-column-id="${columnId}"]`);
      if(cell)cell.innerHTML=backtestLeaderCell(row,index);
    });
  }
  return true;
}

async function applyAdvancedFilters(showToast=true) {
  const request=analysisRequestFromForm();
  try{validateAnalysisRequest(request);}catch(error){toast(error.message,"error");return;}
  const type=analysisType(),analysisTab=state.tabs.analysis,navigationSerial=state.navigationSerial,requestSerial=++state.analysisRequestSerial;
  revealSelectedValuationColumns(request);
  if(!state.currentCustomFilter){const label=state.analysisCatalog[analysisType()]?.[state.analysisPreset]?.name||"Análise";$("#active-analysis-summary").textContent=`${label} • ajustes temporários`;}
  $("#analysis-table").innerHTML=loadingCards(6);
  try {
    const payload=await api("/screen/advanced",{method:"POST",requestKey:"analysis",body:JSON.stringify(request),invalidateCache:false});
    const rows=payload.rows||payload;
    if(!navigationIsCurrent(navigationSerial,"analysis","analysis",analysisTab)||type!==analysisType()||requestSerial!==state.analysisRequestSerial)return;
    const primaryRows=state.session?.access?.can_view_backtests?rows.map(row=>({...row,backtest_leaders_pending:true})):rows;
    state.analysisRows=primaryRows;state.analysisLastUpdatedAt[type]=Date.now();renderAnalysisRows(primaryRows);
    const warnings=payload?.meta?.warnings||[];
    if(warnings.length) toast(warnings.join(" "),"warning");
    else if(showToast) toast(`${rows.length} ativo(s) após os ajustes.`,"success");
    if(state.session?.access?.can_view_backtests)enrichBacktestLeaders(rows).then(enrichedRows=>{
      if(!navigationIsCurrent(navigationSerial,"analysis","analysis",analysisTab)||type!==analysisType()||requestSerial!==state.analysisRequestSerial)return;
      state.analysisRows=enrichedRows;if(!patchAnalysisBacktestCells(enrichedRows))renderAnalysisRows(enrichedRows);
    }).catch(()=>{});
  } catch(error) { if(error.name!=="AbortError"&&state.view==="analysis"&&type===analysisType()&&requestSerial===state.analysisRequestSerial) $("#analysis-table").innerHTML=errorState(error,"analysis"); }
}

async function openAsset(ticker,{historyMode="push"}={}) {
  const dialog=$("#asset-dialog"), content=$("#asset-dialog-content");
  state.currentAssetTicker=String(ticker||"").toUpperCase();
  syncNavigationUrl(historyMode);
  const requestSerial=++state.assetRequestSerial;
  content.innerHTML=loadingCards(4); dialog.showModal();
  try {
    const data=await api(`/assets/${encodeURIComponent(ticker)}`,{requestKey:"asset-detail",cacheTtlMs:120000});
    if(requestSerial!==state.assetRequestSerial||!dialog.open)return;
    const a=data.asset||{}, f=data.fundamentals||{}, t=data.technical||{}, d=data.derived||{}, tech=data.technical_analysis||{}, scores=data.scores||{}, leaders=data.backtests||[];
    const valuationLabels={graham_reference:"Número de Graham",dividend_yield_ceiling:"Preço-teto por DY-alvo",relative_peers:"Valuation relativo",economic_value:"Valor econômico"};
    const valuationStatus=result=>result.status==="not_applicable"?"Não se aplica":result.status==="valid"?"Calculado":"Dados insuficientes";
    const valuationReason=result=>({requires_positive_eps_and_bvps:"Exige lucro e patrimônio por ação positivos.",dividend_per_share_ttm_required:"Exige proventos válidos dos últimos 12 meses.",normalized_dividend_per_share_required:"Exige um dividendo D0 explícito; nenhum valor foi presumido.",three_explicit_scenarios_required:"Exige os três cenários completos.",etf_nav_or_premium_required:"A fonte ainda não informou NAV por cota nem prêmio/desconto ao NAV.",insufficient_etf_nav_peers:"Ainda não há ETFs comparáveis suficientes com prêmio/desconto ao NAV.",bdr_book_value_or_pbv_required:"A fonte ainda não informou P/VP ou valor patrimonial deste BDR.",insufficient_bdr_pbv_peers:"Ainda não há BDRs suficientes do mesmo setor ou indústria com P/VP válido.",bdr_peer_classification_required:"O BDR ainda não tem setor ou indústria confiável para formar o grupo de comparação.",bdr_underlying_price_fx_and_ratio_required:"A paridade exige preço do ativo-lastro, câmbio e razão verificada do programa de BDR.",future_spot_carry_and_expiry_required:"O preço teórico exige ativo à vista, taxa de carregamento e vencimento do contrato frontal."})[result.reason]||result.reason||"Os insumos próprios desta metodologia ainda não estão disponíveis.";
    const valuationMethods=d.valuation_methods||{};
    const valuationCards=Object.entries(valuationMethods).map(([family,result])=>metricCard(result.label||valuationLabels[family]||family,result.status==="valid"?money(result.value):valuationStatus(result),result.status==="valid"?`Potencial ${pct(result.upside_pct,true)}`:"Sem estimativa artificial",result.upside_pct)).join("");
    const valuationDetail=Object.entries(valuationMethods).map(([family,result])=>{
      const scenarios=Object.entries(result.scenarios||{});
      const scenarioBody=scenarios.length?`<div class="detail-list">${scenarios.map(([name,item])=>{const assumptions=item.assumptions||{},premises=!nullable(assumptions.required_return_pct)?`<small>Retorno ${pct(assumptions.required_return_pct)} • crescimento ${pct(assumptions.growth_pct)}${nullable(assumptions.margin_of_safety_pct)?"":` • margem ${pct(assumptions.margin_of_safety_pct)}`}</small>`:"";return `<div><span>${esc(({conservative:"Conservador",base:"Base",optimistic:"Otimista"})[name]||name)}${premises}</span><strong>${money(item.value)} <small>${pct(item.upside_pct,true)}</small></strong></div>`;}).join("")}</div>`:"";
      const audit=[result.metadata?.source,result.metadata?.as_of?`dados de ${dateTime(result.metadata.as_of)}`:null].filter(Boolean).join(" • ");
      return `<article class="valuation-method-card"><div><strong>${esc(result.label||valuationLabels[family]||family)}</strong><span class="pill">${esc(valuationStatus(result))}</span></div>${result.status==="valid"?`<p>Referência base: <strong>${money(result.value)}</strong> • potencial ${pct(result.upside_pct,true)}</p>`:`<p>${esc(valuationReason(result))} O sistema não criou uma estimativa artificial.</p>`}${scenarioBody}${!nullable(result.quality?.coverage_pct)?`<small>Cobertura: ${pct(result.quality.coverage_pct)} • amostra: ${number(result.quality.sample_size||0,0)}</small>`:""}${audit?`<small>${esc(audit)}</small>`:""}</article>`;
    }).join("");
    const fundamentals=[
      ["P/L",f.pe],["P/VP",f.pbv],["EV/EBITDA",f.ev_ebitda],["Dividend yield (%)",f.dividend_yield_pct],
      ["ROE (%)",f.roe_pct],["ROIC (%)",f.roic_pct],["Margem EBIT (%)",f.ebit_margin_pct],["Margem líquida (%)",f.net_margin_pct],
      ["Liquidez corrente",f.current_ratio],["Dívida bruta/patrimônio",f.gross_debt_to_equity],["Dívida líq./EBITDA",f.net_debt_to_ebitda],
      ["CAGR receita 5a (%)",f.revenue_cagr_5y_pct],["CAGR lucro 5a (%)",f.earnings_cagr_5y_pct],["Liquidez diária",f.daily_liquidity??t.daily_liquidity],
    ].filter(([,value])=>!nullable(value));
    const pivotRows=["s3","s2","s1","pp","r1","r2","r3"].map(key=>({label:key==="pp"?"Pivô central":key.startsWith("s")?`Suporte ${key.slice(1)}`:`Resistência ${key.slice(1)}`,value:tech[key]}));
    const leaderTable=leaders.length?marketTable(leaders,[
      {label:"Estratégia",render:r=>`<strong>${esc(r.strategy_name||r.strategy_id)}</strong>`},
      {label:"Sinal atual",render:r=>`<span class="pill signal-${esc(r.current_signal||"neutral")}">${signalLabel(r.current_signal)}</span>`},
      {label:"Pontuação",render:r=>number(r.ranking_score,1)},
      {label:"Retorno",render:r=>pct(r.metrics?.total_return_pct,true),className:r=>variationClass(r.metrics?.total_return_pct)},
    ]):'<div class="empty-state compact"><strong>Sem catálogo oficial para este ativo</strong>Os três melhores resultados aparecerão após a rodada oficial.</div>';
    content.innerHTML=`<div class="asset-dialog-header"><p class="eyebrow">${esc(a.asset_type_label||a.asset_type||"Ativo")}</p><h2 class="asset-title">${esc(a.ticker)} • ${esc(a.name||"")}</h2><p class="asset-subtitle">${esc(a.sector_label||a.classification||"")} ${a.company_size_label?`• ${esc(a.company_size_label)}`:""}</p></div>
      <div class="metric-grid asset-summary">${metricCard("Preço",money(f.price??t.close))}${valuationCards}${metricCard("Sinal do melhor backtest",signalLabel(leaders[0]?.current_signal),leaders[0]?.strategy_name||"")}</div>
      <div class="asset-detail-grid">
        ${sectionCard("Indicadores fundamentalistas",fundamentals.length?`<div class="detail-list">${fundamentals.map(([label,value])=>`<div><span>${esc(label)}</span><strong>${number(value,2)}</strong></div>`).join("")}</div>`:'<div class="empty-state compact">Sem dados fundamentalistas recentes.</div>')}
        ${valuationDetail?sectionCard("Metodologias de valor",`<div class="valuation-method-list">${valuationDetail}</div>`,`Somente métodos autorizados são exibidos; N/D nunca é convertido em preço estimado.`):""}
        ${sectionCard("Análise técnica",`<div class="metric-grid mini">${metricCard("RSI 14",number(tech.rsi14??t.rsi14))}${metricCard("Tendência diária",tech.trend_daily==="up"?"Alta":tech.trend_daily==="down"?"Baixa":"—")}${metricCard("Volume diário / média 9",nullable(tech.volume_daily_ratio)?"—":pct(Number(tech.volume_daily_ratio)*100))}${metricCard("Volume mensal / média 9",nullable(tech.volume_monthly_ratio)?"—":pct(Number(tech.volume_monthly_ratio)*100))}</div><div class="detail-list pivot-list">${pivotRows.map(row=>`<div><span>${esc(row.label)}</span><strong>${money(row.value)}</strong></div>`).join("")}</div><small class="formula-note">Pivôs calculados pela máxima, mínima e fechamento do último período concluído.</small>`)}
        ${sectionCard("Notas do ativo",`<div class="detail-list">${Object.entries({"Qualidade":scores.quality_score,"Valor":scores.value_score,"Crescimento":scores.growth_score,"Técnica":scores.technical_score,"Risco":scores.risk_score,"Liquidez":scores.liquidity_score,"ALB":scores.alb_score,"Qualidade dos dados":scores.data_quality_score}).map(([label,value])=>`<div><span>${esc(label)}</span><strong>${number(value,1)}</strong></div>`).join("")}</div>`)}
        ${sectionCard("3 melhores backtests e sinal atual",leaderTable,"Ordenados pela consistência dos resultados oficiais")}
      </div>`;
  } catch(error) { if(error.name!=="AbortError"&&requestSerial===state.assetRequestSerial&&dialog.open)content.innerHTML=errorState(error); }
}

  window.FDIFeatures=window.FDIFeatures||{};
  window.FDIFeatures.analysis={
    filterDefinitions,
    renderFilterInputs,updateFilterAvailability,resetAdvancedFilters,analysisType,
    fillAnalysisForm,analysisRequestFromForm,validateAnalysisRequest,markActiveAnalysis,
    prefetchAnalysisCatalogs,selectSystemPreset,selectCustomFilter,saveCustomFilter,
    deleteCustomFilter,loadAnalysis,renderAnalysisRows,analysisColumns,
    orderedAnalysisColumns,applyAdvancedFilters,openAsset
  };
})();
