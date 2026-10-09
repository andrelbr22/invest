"use strict";

// Carregado sob demanda pela V1.23.7 R2. O módulo preserva as mesmas
// funções e regras usadas antes no arquivo principal.
(()=>{
function readableConfigurationKey(key) {
  const labels={
    fast:"Período rápido",fast_period:"Período rápido",fast_window:"Média rápida",
    slow:"Período lento",slow_period:"Período lento",slow_window:"Média lenta",
    signal:"Período do sinal",signal_period:"Período do sinal",window:"Período",
    lower:"Limite inferior",upper:"Limite superior",enabled:"Status",direction:"Direção",
    period:"Período da média",mode:"Regra da tendência",slope_lookback:"Intervalo para confirmar a inclinação",
    daily_trend:"Tendência diária",weekly_trend:"Tendência semanal",monthly_trend:"Tendência mensal",
    trend_combination:"Combinação das tendências",adx_min:"ADX mínimo",volume_ratio_min:"Volume mínimo em relação à média",
    rsi_min:"RSI mínimo",rsi_max:"RSI máximo",atr_pct_min:"ATR mínimo",atr_pct_max:"ATR máximo",
    exit_on_filter_failure:"Sair quando um filtro deixar de ser atendido",fundamental_entry:"Fundamentos exigidos para entrada",
    fundamental_exit:"Fundamentos que provocam saída",fundamental_exit_logic:"Combinação das condições de saída",
    fundamental_min_coverage_pct:"Cobertura fundamentalista mínima",fundamental_max_age_days:"Idade máxima dos fundamentos",
    initial_capital:"Capital inicial",fee_pct:"Taxa por operação",slippage_pct:"Slippage estimado",
    risk_free_rate_pct:"Taxa livre de risco",apply_cash_yield:"Remunerar o caixa não investido",
    cash_yield_rate_pct:"Rendimento anual do caixa",fundamental_filters:"Filtros fundamentalistas",
    technical_filters:"Filtros técnicos",mean_total_return_pct:"Retorno total médio",
    mean_cagr_pct:"Retorno anualizado médio (CAGR)",mean_sharpe_ratio:"Índice de Sharpe médio",
    mean_max_drawdown_pct:"Perda máxima média (drawdown)",mean_profit_factor:"Fator de lucro médio",
    mean_win_rate_pct:"Taxa média de acerto",mean_closed_trades:"Média de operações encerradas",
    pe:"P/L",pbv:"P/VP",dividend_yield_pct:"Dividend yield",ev_ebitda:"EV/EBITDA",
    ebit_margin_pct:"Margem EBIT",net_margin_pct:"Margem líquida",current_ratio:"Liquidez corrente",
    roe_pct:"ROE",roic_pct:"ROIC",gross_debt_to_equity:"Dívida bruta / patrimônio",
    net_debt_to_ebitda:"Dívida líquida / EBITDA",revenue_cagr_5y_pct:"Crescimento da receita em 5 anos",
    earnings_cagr_5y_pct:"Crescimento dos lucros em 5 anos",ffo_yield_pct:"FFO yield",
    cap_rate_pct:"Cap rate",vacancy_pct:"Vacância física",financial_vacancy_pct:"Vacância financeira",
    ltv_pct:"LTV",wale_years:"Prazo médio dos contratos (WALE)",daily_liquidity:"Liquidez diária",
    min:"Mínimo",max:"Máximo",
  };
  return labels[key]||String(key||"").replaceAll("_"," ").replace(/^./,letter=>letter.toUpperCase());
}

function readableConfigurationValue(key,value,parentKey="") {
  if(value===null||value===undefined||value==="")return "Não utilizado neste teste";
  if(typeof value==="boolean")return key==="enabled"||key==="apply_cash_yield"?(value?"Ativado":"Desativado"):(value?"Sim":"Não");
  if(typeof value==="number") {
    if(key==="initial_capital")return money(value);
    if(key==="fundamental_max_age_days")return `${number(value,0)} dias`;
    if(["fast","fast_period","fast_window","slow","slow_period","slow_window","signal","signal_period","window","period","slope_lookback"].includes(key))return `${number(value,0)} períodos`;
    if(key==="volume_ratio_min")return `${number(value,2)} × a média`;
    if(String(key).includes("_pct")||String(parentKey).includes("_pct"))return `${number(value,2)}%`;
    return number(value,2);
  }
  const text=String(value);
  const labels={
    up:"Alta",down:"Baixa",none:"Sem filtro",all:"Todas as condições",any:"Qualquer condição",
    majority:"Maioria das condições",price_above:"Preço acima da média móvel",
    sma_rising:"Média móvel simples em alta",price_above_or_sma_rising:"Preço acima da média OU média em alta",
    price_above_and_sma_rising:"Preço acima da média E média em alta",close:"Fechamento",
    low_touch:"Mínima toca a banda",close_reentry:"Fechamento retorna para dentro da banda",
  };
  if(key==="trend_combination")return {all:"Todas as tendências ativas devem concordar",any:"Ao menos uma tendência ativa deve confirmar",majority:"A maioria das tendências ativas deve confirmar"}[text]||readableConfigurationKey(text);
  if(key==="fundamental_exit_logic")return {all:"Todas as condições devem ocorrer",any:"Qualquer condição pode provocar a saída"}[text]||readableConfigurationKey(text);
  return labels[text]||readableConfigurationKey(text);
}

function configurationValue(value,key="",parentKey="") {
  if(Array.isArray(value))return value.length?`<ul class="configuration-list">${value.map(item=>`<li>${configurationValue(item,key,parentKey)}</li>`).join("")}</ul>`:'<span class="muted">Nenhum item configurado.</span>';
  if(value!==null&&typeof value==="object") {
    const nested=Object.entries(value);
    if(!nested.length)return '<span class="muted">Nenhuma condição configurada.</span>';
    return `<dl class="configuration-pairs nested">${nested.map(([nestedKey,nestedValue])=>`<div><dt>${esc(readableConfigurationKey(nestedKey))}</dt><dd>${configurationValue(nestedValue,nestedKey,key||parentKey)}</dd></div>`).join("")}</dl>`;
  }
  return `<span>${esc(readableConfigurationValue(key,value,parentKey))}</span>`;
}

function configurationPairs(values) {
  if(values!==null&&values!==undefined&&typeof values!=="object")return `<p class="configuration-text">${configurationValue(values)}</p>`;
  const entries=Object.entries(values||{});
  if(!entries.length)return '<span class="muted">Nenhuma configuração adicional.</span>';
  return `<dl class="configuration-pairs">${entries.map(([key,value])=>`<div><dt>${esc(readableConfigurationKey(key))}</dt><dd>${configurationValue(value,key)}</dd></div>`).join("")}</dl>`;
}

async function openStudyStrategy(strategyId) {
  const dialog=$("#asset-dialog"),content=$("#asset-dialog-content");
  content.innerHTML=loadingCards(5);dialog.showModal();
  try {
    const data=await api(`/backtests/study/${encodeURIComponent(strategyId)}/configurations`,{cacheTtlMs:60000});
    const configurations=data.items||[];
    content.innerHTML=`<div class="asset-dialog-header"><p class="eyebrow">Estudo de backtests</p><h2 class="asset-title">${esc(data.strategy_name||strategyId)}</h2><p class="asset-subtitle">Todas as configurações oficiais utilizadas nesta estratégia.</p></div>
      <div class="metric-grid">${metricCard("Configurações",number(data.configuration_count||0,0))}${metricCard("Execuções",number(data.run_count||0,0))}${metricCard("Estratégia",esc(strategyId))}</div>
      ${sectionCard("Regras da estratégia",configurationPairs(data.strategy_rules))}
      <div class="study-configurations">${configurations.length?configurations.map(item=>`<details class="study-configuration"><summary><span>Configuração ${number(item.configuration_number,0)}</span><small>${number(item.assets_tested,0)} ativo(s) • nota média ${number(item.mean_ranking_score,1)}</small></summary><div class="study-configuration-body"><div class="study-configuration-grid"><article><h4>Parâmetros da estratégia</h4>${configurationPairs(item.strategy_parameters)}</article><article><h4>Filtros</h4>${configurationPairs(item.filters)}</article><article><h4>Premissas financeiras</h4>${configurationPairs({...item.financial,...item.assumptions})}</article><article><h4>Métricas médias</h4>${configurationPairs(item.mean_metrics)}</article></div><p><strong>Ativos testados:</strong> ${esc((item.tickers||[]).join(", ")||"—")}</p><p><strong>Sinais atuais:</strong> ${esc(Object.entries(item.signal_counts||{}).map(([key,value])=>`${signalLabel(key)}: ${value}`).join(" • ")||"—")}</p></div></details>`).join(""):'<div class="empty-state"><strong>Nenhuma configuração elegível</strong>As configurações aparecerão depois da próxima rodada oficial válida.</div>'}</div>`;
  } catch(error) {content.innerHTML=errorState(error);}
}

const officialStatusLabels = {
  queued:"Na fila", running:"Executando", completed:"Concluído",
  completed_with_errors:"Concluído com avisos", failed:"Falhou", cancelled:"Cancelado",
};

function officialErrorText(item) {
  const code=String(item?.code||"");
  const labels={
    github_worker_failed:"A execução no GitHub foi interrompida antes da conclusão.",
    github_dispatch_failed:"Não foi possível iniciar a nova execução no GitHub.",
    cancelled_by_owner:"A rodada foi cancelada pelo administrador.",
  };
  const stage=String(item?.details?.failure_stage||"");
  if(stage==="prepare_temporary_database") return "O banco temporário da rodada não pôde ser preparado. A correção desta revisão torna a inicialização independente do histórico de migrações da produção.";
  const safe=String(item?.details?.safe_message||"");
  if(safe.includes("HTTP 413")) return "O pacote de resultados ultrapassou o limite de envio. Esta versão passa a entregá-lo em partes menores e repetíveis com segurança.";
  return labels[code]||String(item?.message||item?.error||"Falha não detalhada.");
}

function openOfficialBacktestJob(jobId) {
  const job=state.officialBacktestJobs.get(String(jobId));
  if(!job)return;
  const content=$("#asset-dialog-content"),dialog=$("#asset-dialog");
  const total=Number(job.total_assets||(job.tickers||[]).length||0);
  const processed=Number(job.processed_assets||0);
  const errors=job.errors||[];
  const canRetry=Boolean(state.session?.access?.is_owner&&(job.retry_tickers||[]).length&&["failed","cancelled","completed_with_errors"].includes(job.status));
  content.innerHTML=`<div class="asset-dialog-header"><p class="eyebrow">Rodada oficial</p><h2 class="asset-title">${esc(officialStatusLabels[job.status]||job.status||"—")}</h2><p class="asset-subtitle">${esc(job.id)}</p></div>
    <div class="metric-grid">${metricCard("Ativos concluídos",`${processed} / ${total}`)}${metricCard("Partes recebidas",number(job.received_chunks||0,0))}${metricCard("Execuções concluídas",number(job.completed_runs||0,0))}${metricCard("Execuções com falha",number(job.failed_runs||0,0))}</div>
    ${sectionCard("Andamento",`<p><strong>Início:</strong> ${dateTime(job.started_at||job.created_at)}</p><p><strong>Última atualização:</strong> ${dateTime(job.last_update_at||job.finished_at)}</p><p><strong>Último ativo recebido:</strong> ${esc(job.last_ticker||job.last_chunk_ticker||"—")}${job.last_chunk_count?` • parte ${number(job.last_chunk_index,0)} de ${number(job.last_chunk_count,0)}`:""}</p>`)}
    ${(job.pending_tickers||[]).length?sectionCard("Ativos pendentes",`<p>${esc(job.pending_tickers.join(", "))}</p>`):""}
    ${errors.length?sectionCard("Motivo e orientação",`<div class="notice danger">${errors.map(item=>`<p>${esc(officialErrorText(item))}</p>`).join("")}</div>`):""}
    <div class="dialog-actions">${canRetry?`<button class="button primary" data-retry-official-job="${esc(job.id)}">Reprocessar ativos pendentes ou com falha</button>`:""}<a class="button secondary" href="https://github.com/andrelbr22/invest/actions/workflows/backtests-semanais.yml" target="_blank" rel="noopener">Ver execuções no GitHub</a></div>`;
  dialog.showModal();
}

async function retryOfficialBacktestJob(jobId, button) {
  if(button){button.disabled=true;button.textContent="Solicitando nova execução…";}
  try {
    const result=await api(`/backtests/batch/jobs/${encodeURIComponent(jobId)}/retry`,{method:"POST",body:"{}"});
    $("#asset-dialog").close();
    const destination=result.dispatch?.environment==="production"?"produção":"ambiente de teste";
    toast(`${(result.retry_tickers||result.tickers||[]).length} ativo(s) enviado(s) para nova execução em ${destination}.`,"success");
    await loadBacktests();
  } catch(error) {
    toast(error.message,"error");
    if(button){button.disabled=false;button.textContent="Reprocessar ativos pendentes ou com falha";}
  }
}

function officialRoundLaunchCard(status) {
  const active=status?.active_job;
  const remaining=Math.max(0,Number(status?.remaining_seconds||0));
  const hours=Math.floor(remaining/3600),minutes=Math.ceil((remaining%3600)/60);
  const waitLabel=hours?`${hours}h${minutes?` ${minutes}min`:""}`:`${minutes} min`;
  const explanation=active
    ?`A rodada ${String(active.id||"").slice(0,8)}… ainda está ${officialStatusLabels[active.status]||active.status}.`
    :status?.allowed
      ?"O intervalo mínimo foi cumprido. O botão iniciará a matriz completa no GitHub."
      :`A próxima rodada completa poderá ser iniciada em aproximadamente ${waitLabel}.`;
  return sectionCard("Iniciar rodada oficial completa",`<div class="admin-launch-row"><div><p>${esc(explanation)}</p><small>Disponível somente ao proprietário e nunca antes de 12 horas da rodada oficial anterior.</small></div><button type="button" class="button primary" data-launch-official-backtests ${status?.allowed?"":"disabled"}>Iniciar nova rodada oficial</button></div>`,status?.next_allowed_at?`Próxima liberação: ${dateTime(status.next_allowed_at)}`:"");
}

async function launchOfficialBacktestRound(button) {
  if(!window.confirm("Iniciar uma rodada oficial completa de backtests? A operação usará o catálogo padrão e poderá levar bastante tempo."))return;
  button.disabled=true;button.textContent="Solicitando rodada…";
  try {
    const result=await api("/backtests/batch/official-launch",{method:"POST",body:"{}"});
    toast(`Rodada oficial ${String(result.id||"").slice(0,8)}… enviada ao GitHub.`,"success");
    await loadBacktests();
  } catch(error) {
    toast(error.message,"error");
    await loadBacktests();
  }
}

const backtestParameterLabels={period:"Período",stddev:"Desvios-padrão",rsi_period:"Período do RSI",entry_rsi:"RSI de entrada",exit_rsi:"RSI de saída",trend_period:"Período da tendência",trend_filter_mode:"Filtro de tendência",trend_slope_lookback:"Janela da inclinação",band_trigger:"Gatilho da banda",fast_period:"Média rápida",slow_period:"Média lenta",fast_type:"Tipo da média rápida",slow_type:"Tipo da média lenta",atr_period:"Período do ATR",multiplier:"Multiplicador",lookback:"Janela de observação",skip_recent:"Pregões recentes ignorados",min_absolute_return_pct:"Retorno absoluto mínimo (%)",min_excess_return_pct:"Excesso sobre benchmark (%)",squeeze_lookback:"Janela do squeeze",squeeze_quantile:"Percentil do squeeze",volume_period:"Período do volume",volume_ratio_min:"Volume / média mínimo"};
const backtestChoiceLabels={sma:"Média simples",ema:"Média exponencial",price_above:"Preço acima/abaixo",sma_rising:"Inclinação da média",price_above_and_sma_rising:"Preço e inclinação",price_above_or_sma_rising:"Preço ou inclinação",none:"Sem filtro",close:"Fechamento",low_touch:"Mínima toca a banda",close_reentry:"Retorno para dentro da banda"};

function renderBacktestStrategyParameters(form){
  const root=form?.querySelector("#backtest-strategy-parameters");if(!root)return;
  const selected=[...form.querySelector('[name="strategy_ids"]').selectedOptions].map(option=>option.value);
  const catalog=state.backtestCatalog?.strategies||[];
  root.innerHTML=selected.map(id=>{
    const strategy=catalog.find(item=>item.id===id),schema=strategy?.parameter_schema||{},defaults=strategy?.default_params||{};
    const fields=Object.entries(schema).map(([key,spec])=>{
      const name=`strategy_param__${id}__${key}`,label=backtestParameterLabels[key]||key,value=defaults[key];
      if(spec.type==="choice")return `<div class="field"><label>${esc(label)}</label><select name="${esc(name)}">${(spec.options||[]).map(option=>`<option value="${esc(option)}" ${String(option)===String(value)?"selected":""}>${esc(backtestChoiceLabels[option]||option)}</option>`).join("")}</select></div>`;
      const step=spec.type==="int"?"1":"0.01";
      return `<div class="field"><label>${esc(label)}</label><input type="number" name="${esc(name)}" min="${esc(spec.min)}" max="${esc(spec.max)}" step="${step}" value="${esc(value)}"></div>`;
    }).join("");
    return `<details class="data-card strategy-parameter-card" open><summary><strong>${esc(strategy?.name||id)}</strong></summary><p class="block-hint">${esc(strategy?.rules||"")}</p>${fields?`<div class="filter-grid compact-grid">${fields}</div>`:'<p class="block-hint">Esta estratégia usa parâmetros fixos e auditados; os filtros técnicos gerais continuam disponíveis abaixo.</p>'}</details>`;
  }).join("")||'<div class="notice info">Selecione uma ou mais estratégias para revisar regras e parâmetros antes do envio.</div>';
}

function collectBacktestStrategyParameters(form,strategyIds){
  const result={};
  strategyIds.forEach(id=>{
    const strategy=(state.backtestCatalog?.strategies||[]).find(item=>item.id===id),params={};
    Object.entries(strategy?.parameter_schema||{}).forEach(([key,spec])=>{
      const input=form.querySelector(`[name="strategy_param__${CSS.escape(id)}__${CSS.escape(key)}"]`);if(!input)return;
      params[key]=spec.type==="choice"?input.value:spec.type==="int"?Number.parseInt(input.value,10):Number(input.value);
    });
    result[id]=params;
  });
  return result;
}

async function loadBacktests() {
  const panelStarted=performance.now();
  const root=$("#backtests-tab-content"),tab=state.tabs.backtests,navigationSerial=state.navigationSerial,requestSerial=++state.backtestRequestSerial,panelKey=tab;
  const isCurrent=()=>root.dataset.panelKey===panelKey&&requestSerial===state.backtestRequestSerial&&navigationIsCurrent(navigationSerial,"backtests","backtests",tab);
  const samePanel=root.dataset.panelKey===panelKey&&root.childElementCount>0;root.dataset.panelKey=panelKey;
  let panelSucceeded=false;
  if(!samePanel)root.innerHTML=loadingCards(6);else root.classList.add("panel-refreshing");
  try {
    if(tab==="history") {
      const rows=await api("/backtests/runs?limit=100",{requestKey:"backtests",cacheTtlMs:15000});
      if(!isCurrent())return;
      rows.sort((a,b)=>new Date(b.created_at)-new Date(a.created_at));
      root.innerHTML=recordedUpdatePanel("Histórico de backtests",rows[0]?.created_at,"Atualizado sempre que um teste é concluído")+sectionCard("Últimos 100 backtests",marketTable(rows,[{label:"Data e hora",render:r=>dateTime(r.created_at)},{label:"Ativo",render:r=>`<span class="ticker-cell">${esc(r.ticker||"—")}</span>`},{label:"Estratégia",render:r=>esc(r.strategy_name||r.strategy_id||"—")},{label:"Retorno",render:r=>pct(r.metrics?.total_return_pct??r.return_pct,true),className:r=>variationClass(r.metrics?.total_return_pct??r.return_pct)},{label:"Status",render:r=>`<span class="pill">${esc(r.status||"—")}</span>`}]));
    } else if(tab==="study") {
      const data=await api("/backtests/study?limit=5",{requestKey:"backtests-study",cacheTtlMs:120000});if(!isCurrent())return; const rows=data.items||data.ranking||[];
      root.innerHTML=recordedUpdatePanel("Estudos oficiais",data.generated_at||data.updated_at,"Recalculado a partir das rodadas oficiais")+sectionCard("Estratégias mais consistentes",marketTable(rows,[{label:"Posição",render:(r)=>`<strong>${esc(r.position||r.rank||"—")}</strong>`},{label:"Estratégia",render:r=>`<button class="table-link" data-study-strategy="${esc(r.strategy_id)}">${esc(r.strategy_name||r.name||r.strategy_id)}</button><small class="block-hint">Abrir configurações</small>`},{label:"Pontuação",render:r=>number(r.study_score??r.score??r.points,1)},{label:"Presença no top 3",render:r=>number(r.top_three_count??r.top3_count,0)},{label:"1º lugares",render:r=>number(r.first_places,0)},{label:"Cobertura",render:r=>pct(r.coverage_pct)}]),"Ranking ponderado por recorrência no top 3, posição, qualidade e cobertura. Clique na estratégia para ver todas as variáveis.");
    } else if(tab==="official") {
      const [rows,launchStatus]=await Promise.all([
        api("/backtests/batch/jobs?limit=30",{requestKey:"backtests-official-jobs",cacheTtlMs:30000}),
        api("/backtests/batch/official-launch",{requestKey:"backtests-official-launch",cacheTtlMs:30000}),
      ]);
      if(!isCurrent())return;
      state.officialBacktestJobs=new Map(rows.map(row=>[String(row.id),row]));
      const officialUpdated=rows.map(row=>row.last_update_at||row.finished_at||row.created_at).filter(Boolean).sort().pop();
      root.innerHTML=recordedUpdatePanel("Backtests oficiais",officialUpdated,"Rodada automática aos sábados às 00h01, horário de Brasília")+officialRoundLaunchCard(launchStatus)+sectionCard("Rodadas oficiais",marketTable(rows,[{label:"Criado em",render:r=>dateTime(r.created_at)},{label:"Identificador",render:r=>`<button class="table-link" data-official-job="${esc(r.id)}">${esc(String(r.id).slice(0,8))}…</button>`},{label:"Ativos",render:r=>number((r.requested_tickers||r.tickers||[]).length,0)},{label:"Progresso",render:r=>`${number(r.processed_assets||0,0)} / ${number(r.total_assets||(r.requested_tickers||r.tickers||[]).length,0)}`},{label:"Partes",render:r=>number(r.received_chunks||0,0)},{label:"Status",render:r=>`<span class="pill ${r.status==="failed"?"danger":""}">${esc(officialStatusLabels[r.status]||r.status)}</span>`},{label:"",render:r=>`<button class="button ghost compact" data-official-job="${esc(r.id)}">Detalhes</button>`}]),"Em caso de falha, abra Detalhes e use Reprocessar ativos pendentes ou com falha. O sistema não recalcula entregas já concluídas.");
    } else {
      const [catalog,recentJobs]=await Promise.all([api("/backtests/strategies",{requestKey:"backtests-catalog",cacheTtlMs:300000}),api("/backtests/jobs?limit=5",{requestKey:"backtests-recent",cacheTtlMs:30000})]);
      if(!isCurrent())return;
      const access=state.session.access;state.backtestCatalog=catalog;
      root.innerHTML=sectionCard("Comparar estratégias",`<form id="backtest-form" class="filter-grid backtest-form">
        <div class="field wide-action"><label>Ativos — separe por vírgula ou espaço</label><textarea name="tickers" required rows="3" placeholder="PETR4, VALE3, BBAS3"></textarea><small>Limite autorizado por análise: ${number(access.backtest_asset_limit||0,0)} ativo(s).</small></div>
        <div class="field"><label>Estratégias (até ${number(access.backtest_strategy_limit||0,0)})</label><select name="strategy_ids" multiple size="7" required>${(catalog.strategies||[]).map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")}</select><small>Use Ctrl para selecionar mais de uma.</small></div>
        <div id="backtest-strategy-parameters" class="wide-action strategy-parameters"></div>
        <div class="field"><label>Forma de análise</label><select name="execution_mode"><option value="compare">Comparar separadamente</option><option value="combined">Combinar estratégias</option></select><small>A combinação produz uma única posição.</small></div>
        <div class="field" data-combination-rule hidden><label>Regra da combinação</label><select name="combination_rule"><option value="all">Todas confirmam (E)</option><option value="any">Qualquer uma confirma (OU)</option><option value="majority">Maioria confirma</option></select></div>
        <div class="field"><label>Tipo de ativo</label><select name="asset_type"><option value="stock">Ações</option><option value="fii">FIIs</option><option value="etf">ETFs</option><option value="bdr">BDRs</option><option value="future">Futuros</option></select></div>
        <div class="field"><label>Período</label><select name="period">${Object.entries(catalog.periods||{}).map(([id,label])=>`<option value="${esc(id)}" ${id==="5y"?"selected":""}>${esc(label)}</option>`).join("")}<option value="custom">Personalizado</option></select></div>
        <div class="field" data-backtest-custom-date hidden><label>De</label><input type="date" name="start"></div><div class="field" data-backtest-custom-date hidden><label>Até</label><input type="date" name="end"></div>
        <details class="wide-action"><summary>Filtros técnicos de entrada e saída</summary><p class="block-hint">Cada filtro é aplicado sobre o sinal de todas as estratégias selecionadas, sem antecipar dados futuros.</p><div class="filter-grid compact-grid">
          ${["daily","weekly","monthly"].map((prefix,index)=>`<fieldset class="data-card"><legend>${["Tendência diária","Tendência semanal","Tendência mensal"][index]}</legend><label class="check"><input type="checkbox" name="${prefix}_enabled"> Ativar</label><div class="field"><label>Média móvel</label><select name="${prefix}_ma"><option value="sma:8">MMS 8</option><option value="ema:9">MME 9</option><option value="sma:21" selected>MMS 21</option><option value="sma:50">MMS 50</option><option value="sma:200">MMS 200</option></select></div><div class="field"><label>Direção</label><select name="${prefix}_direction"><option value="up">Alta</option><option value="down">Baixa</option></select></div><div class="field"><label>Condição</label><select name="${prefix}_mode"><option value="price_above">Preço acima/abaixo da média</option><option value="sma_rising">Inclinação da média</option><option value="price_above_and_sma_rising">Preço e inclinação confirmam</option><option value="price_above_or_sma_rising">Preço ou inclinação confirma</option></select></div></fieldset>`).join("")}
          <div class="field"><label>Combinação das tendências</label><select name="trend_combination"><option value="all">Todas confirmam</option><option value="majority">Maioria confirma</option><option value="any">Qualquer uma confirma</option></select></div>
          <div class="field"><label>ADX mínimo</label><input type="number" name="adx_min" min="0" max="100" step="0.1" placeholder="Ex.: 20"></div><div class="field"><label>Volume / média mínimo</label><input type="number" name="volume_ratio_min" min="0.1" max="10" step="0.1" placeholder="Ex.: 1,2"></div>
          <div class="field"><label>Período da média de volume</label><select name="volume_period"><option value="9">9 períodos</option><option value="20" selected>20 períodos</option><option value="50">50 períodos</option></select></div><div class="field"><label>Gráfico do volume</label><select name="volume_timeframe"><option value="daily">Diário</option><option value="weekly">Semanal</option><option value="monthly">Mensal</option></select></div>
          <div class="field"><label>RSI mínimo</label><input type="number" name="rsi_min" min="0" max="100" step="0.1"></div><div class="field"><label>RSI máximo</label><input type="number" name="rsi_max" min="0" max="100" step="0.1"></div>
          <div class="field"><label>ATR mínimo (%)</label><input type="number" name="atr_pct_min" min="0" max="100" step="0.1"></div><div class="field"><label>ATR máximo (%)</label><input type="number" name="atr_pct_max" min="0" max="100" step="0.1"></div>
          <div class="field"><label>MACD</label><select name="macd_condition"><option value="any">Sem filtro</option><option value="above">Acima do sinal</option><option value="below">Abaixo do sinal</option><option value="cross_up">Cruzamento para cima</option><option value="cross_down">Cruzamento para baixo</option></select></div>
          <div class="field"><label>Bollinger %B mínimo</label><input type="number" name="bollinger_percent_b_min" min="-5" max="5" step="0.01"></div><div class="field"><label>Bollinger %B máximo</label><input type="number" name="bollinger_percent_b_max" min="-5" max="5" step="0.01"></div>
          <div class="field"><label>Largura Bollinger mínima</label><input type="number" name="bollinger_bandwidth_min" min="0" max="500" step="0.1"></div><div class="field"><label>Largura Bollinger máxima</label><input type="number" name="bollinger_bandwidth_max" min="0" max="500" step="0.1"></div>
          <div class="field"><label>Força relativa mínima (%)</label><input type="number" name="relative_strength_min" min="-200" max="500" step="0.1"></div><div class="field"><label>Janela da força relativa</label><input type="number" name="relative_strength_lookback" min="20" max="504" step="1" value="126"></div>
          <div class="field"><label>Zona de pivô</label><select name="pivot_zone"><option value="any">Sem filtro</option><option value="below_s3">Abaixo de S3</option><option value="s3_s2">S3–S2</option><option value="s2_s1">S2–S1</option><option value="s1_pp">S1–Pivô</option><option value="pp_r1">Pivô–R1</option><option value="r1_r2">R1–R2</option><option value="r2_r3">R2–R3</option><option value="above_r3">Acima de R3</option></select></div><div class="field"><label>Próximo do nível</label><select name="near_pivot_level"><option value="none">Sem filtro</option><option value="s3">S3</option><option value="s2">S2</option><option value="s1">S1</option><option value="pp">Pivô</option><option value="r1">R1</option><option value="r2">R2</option><option value="r3">R3</option></select></div>
          <div class="field"><label>Tolerância ao pivô (%)</label><input type="number" name="pivot_tolerance_pct" min="0" max="20" step="0.1" value="0.5"></div><div class="field"><label>Liquidez diária mínima (R$)</label><input type="number" name="daily_liquidity_min" min="0" step="1000"></div>
          <label class="check wide-action"><input type="checkbox" name="exit_on_filter_failure"> Encerrar a posição quando os filtros deixarem de ser atendidos</label>
        </div></details>
        <details class="wide-action"><summary>Premissas financeiras</summary><div class="filter-grid compact-grid"><div class="field"><label>Capital inicial</label><input type="number" name="initial_capital" min="1" step="100" value="10000"></div><div class="field"><label>Taxa (%)</label><input type="number" name="fee_pct" min="0" max="5" step="0.01" value="0.03"></div><div class="field"><label>Slippage (%)</label><input type="number" name="slippage_pct" min="0" max="5" step="0.01" value="0.05"></div><div class="field"><label>Taxa livre de risco (% a.a.)</label><input type="number" name="risk_free_rate_pct" min="-20" max="100" step="0.1" value="0"></div><label class="check"><input type="checkbox" name="apply_cash_yield"> Remunerar o caixa</label><div class="field"><label>Rendimento do caixa (% a.a.)</label><input type="number" name="cash_yield_rate_pct" min="-99" max="100" step="0.1" value="0"></div></div></details>
        <button class="button primary wide-action" type="submit">Enviar análise para processamento</button>
      </form><div id="backtest-result" style="margin-top:16px"></div>`+((recentJobs||[]).length?`<div style="margin-top:18px">${sectionCard("Execuções recentes",marketTable(recentJobs,[{label:"Solicitado",render:r=>dateTime(r.created_at)},{label:"Progresso",render:r=>`${number(r.progress_current||0,0)} / ${number(r.progress_total||0,0)}`},{label:"Status",render:r=>`<span class="pill">${esc(r.status)}</span>`}]))}</div>`:""),`Cada envio conta como uma análise diária. Limite: ${access.backtest_daily_limit||0} por dia; até ${access.backtest_strategy_limit||0} estratégia(s); intervalo mínimo de ${access.backtest_cooldown_seconds||60} segundos. A tela permanece livre durante o processamento.`);
      renderBacktestStrategyParameters($("#backtest-form"));
    }
    panelSucceeded=true;
  } catch(error) { if(error.name!=="AbortError"&&isCurrent())root.innerHTML=errorState(error,"backtests"); }
  finally {if(isCurrent()){root.classList.remove("panel-refreshing");reportPanelPerformance("backtests",panelStarted,{success:panelSucceeded,cacheState:samePanel?(panelSucceeded?"warm":"stale"):"cold"});}}
}

async function runBacktest(form) {
  const result=$("#backtest-result"); result.innerHTML=loadingCards(4);
  const formData=new FormData(form), values=Object.fromEntries(formData);
  const tickers=String(values.tickers||"").toUpperCase().split(/[\s,;]+/).map(value=>value.trim()).filter(Boolean);
  const strategy_ids=[...form.querySelector('[name="strategy_ids"]').selectedOptions].map(option=>option.value);
  if(!tickers.length||!strategy_ids.length){result.innerHTML=errorState("Informe ao menos um ativo e uma estratégia.");return;}
  try {
    const numberOrNull=name=>values[name]===""||nullable(values[name])?null:Number(values[name]);
    const trend=prefix=>{const [ma_type,period]=String(values[`${prefix}_ma`]||"sma:21").split(":");return {enabled:Boolean(form.querySelector(`[name="${prefix}_enabled"]`)?.checked),direction:values[`${prefix}_direction`]||"up",ma_type,period:Number(period),mode:values[`${prefix}_mode`]||"price_above",slope_lookback:prefix==="daily"?5:prefix==="weekly"?4:3};};
    const filters={daily_trend:trend("daily"),weekly_trend:trend("weekly"),monthly_trend:trend("monthly"),trend_combination:values.trend_combination||"all",adx_min:numberOrNull("adx_min"),volume_ratio_min:numberOrNull("volume_ratio_min"),volume_period:Number(values.volume_period||20),volume_timeframe:values.volume_timeframe||"daily",rsi_min:numberOrNull("rsi_min"),rsi_max:numberOrNull("rsi_max"),atr_pct_min:numberOrNull("atr_pct_min"),atr_pct_max:numberOrNull("atr_pct_max"),macd_condition:values.macd_condition||"any",bollinger_percent_b_min:numberOrNull("bollinger_percent_b_min"),bollinger_percent_b_max:numberOrNull("bollinger_percent_b_max"),bollinger_bandwidth_min:numberOrNull("bollinger_bandwidth_min"),bollinger_bandwidth_max:numberOrNull("bollinger_bandwidth_max"),relative_strength_min:numberOrNull("relative_strength_min"),relative_strength_lookback:Number(values.relative_strength_lookback||126),pivot_zone:values.pivot_zone||"any",near_pivot_level:values.near_pivot_level||"none",pivot_tolerance_pct:Number(values.pivot_tolerance_pct||.5),daily_liquidity_min:numberOrNull("daily_liquidity_min"),exit_on_filter_failure:Boolean(form.querySelector('[name="exit_on_filter_failure"]')?.checked)};
    const strategy_params=collectBacktestStrategyParameters(form,strategy_ids);
    const payload={tickers,strategy_ids,strategy_params,execution_mode:values.execution_mode,combination_rule:values.combination_rule,asset_type:values.asset_type,period:values.period,start:values.period==="custom"&&values.start?`${values.start}T00:00:00Z`:null,end:values.period==="custom"&&values.end?`${values.end}T23:59:59Z`:null,initial_capital:Number(values.initial_capital||10000),fee_pct:Number(values.fee_pct||0),slippage_pct:Number(values.slippage_pct||0),risk_free_rate_pct:Number(values.risk_free_rate_pct||0),apply_cash_yield:form.querySelector('[name="apply_cash_yield"]')?.checked||false,cash_yield_rate_pct:Number(values.cash_yield_rate_pct||0),filters};
    const data=await api("/backtests/matrix",{method:"POST",body:JSON.stringify(payload)});
    result.innerHTML=sectionCard("Análise na fila",`<div class="notice"><strong>Você pode continuar usando o site.</strong><br>O processamento ocorre em segundo plano.</div><progress max="${data.assets_requested}" value="0" style="width:100%;margin-top:14px"></progress><p class="block-hint">Preparando a análise…</p>`);
    toast("Análise enviada. Você pode continuar navegando.","success");
    await watchBacktestJob(data.job_id,result,data);
  } catch(error) { result.innerHTML=errorState(error); }
}

function renderPersonalBacktestResult(job,submission) {
  const data=job.result||{},rows=data.results||[];
  return sectionCard(data.execution_mode==="combined"?"Resultado da combinação":"Resultado comparativo",marketTable(rows,[
    {label:"Ativo",render:r=>`<strong>${esc(r.ticker||r.requested_ticker)}</strong>`},
    {label:"Estratégia",render:r=>esc(r.strategy_name||r.strategy_id)},
    {label:"Ação agora",render:r=>`<span class="pill signal-${esc(r.action_signal?.status||r.current_signal||"neutral")}">${signalLabel(r.action_signal?.status||r.current_signal)}</span>`},
    {label:"Posição",render:r=>esc(r.position_state?.label||({invested:"Comprado",out:"Fora da posição"})[r.position_state?.status]||"—")},
    {label:"Retorno",render:r=>pct(r.total_return_pct,true),className:r=>variationClass(r.total_return_pct)},
    {label:"CAGR",render:r=>pct(r.cagr_pct??r.cagr,true),className:r=>variationClass(r.cagr_pct??r.cagr)},
    {label:"Sharpe",render:r=>number(r.sharpe_ratio??r.sharpe)},
    {label:"Drawdown",render:r=>pct(r.max_drawdown_pct??r.max_drawdown,true)},
  ]),`${data.assets_requested||submission.assets_requested} ativo(s), ${data.strategies_requested||submission.strategies_requested} estratégia(s) • uso diário ${submission.daily_used}/${submission.daily_limit}`)+(data.failures?.length?`<div class="notice" style="margin-top:12px">${data.failures.length} ativo(s) não puderam ser processados nesta rodada.</div>`:"")+`<p style="margin-top:14px"><a class="button secondary" href="${BASE_PATH}/backtests/jobs/${encodeURIComponent(job.id)}/export.csv">Exportar operações em CSV</a></p>`;
}

async function watchBacktestJob(jobId,result,submission) {
  for(let attempt=0;attempt<3600;attempt+=1) {
    if(!result?.isConnected)return;
    const job=await api(`/backtests/jobs/${encodeURIComponent(jobId)}`);
    const total=Math.max(1,Number(job.progress_total||submission.assets_requested||1));
    const current=Math.min(total,Number(job.progress_current||0));
    if(job.status==="succeeded"){
      result.innerHTML=renderPersonalBacktestResult(job,submission);
      toast("Análise concluída e salva no histórico.","success");return;
    }
    if(job.status==="failed"||job.status==="cancelled"){
      result.innerHTML=errorState(`A análise não foi concluída (${job.last_error_code||job.status}).`);return;
    }
    result.innerHTML=sectionCard("Análise em segundo plano",`<progress max="${total}" value="${current}" style="width:100%"></progress><p><strong>${current} de ${total}</strong> ativo(s)</p><p class="block-hint">${esc(job.message||"Processando…")} Você pode continuar usando as outras áreas.</p>`);
    await new Promise(resolve=>setTimeout(resolve,2000));
  }
  result.innerHTML=errorState("O acompanhamento excedeu o tempo desta tela. Consulte o histórico de execuções.");
}

  window.FDIFeatures=window.FDIFeatures||{};
  window.FDIFeatures.backtests={
    openStudyStrategy,
    openOfficialBacktestJob,
    retryOfficialBacktestJob,
    launchOfficialBacktestRound,
    renderBacktestStrategyParameters,
    loadBacktests,
    runBacktest
  };
})();
