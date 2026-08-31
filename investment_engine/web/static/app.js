"use strict";

const BASE_PATH = location.pathname === "/testefdi" || location.pathname.startsWith("/testefdi/") ? "/testefdi" : "";

const state = {
  session: null,
  view: "dashboard",
  tabs: { dashboard: "overview", analysis: "stocks", analysisMode: "list", portfolio: "positions", finances: "monthly", backtests: "history", admin: "users" },
  market: null,
  marketEnvelope: null,
  comparison: null,
  comparisonLoading: false,
  comparisonYears: 5,
  comparisonCustom: false,
  comparisonCustomFrom: "",
  comparisonCustomTo: "",
  comparisonSelected: ["CDI","IBOV","IFIX"],
  comparisonBaseMode: "common",
  analysisRows: [],
  analysisPreset: "default",
  analysisCatalog: {},
  analysisLoadedType: null,
  analysisCustom: [],
  analysisCustomCache: {},
  analysisCustomUsageCache: {},
  analysisCustomUsage: {used:0,limit:0},
  currentCustomFilter: null,
  analysisLimit: 50,
  curveYears: 10,
  curveHistory: [],
  curveHistoryCount: 1,
  curveHistoryLoading: false,
  curveHistoryLoaded: false,
  visibleColumns: JSON.parse(localStorage.getItem("fdi-visible-columns") || "{}"),
  portfolios: [],
  portfolioId: null,
  financeMonth: new Date().toISOString().slice(0,7),
  officialBacktestJobs: new Map(),
  requestControllers: new Map(),
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
const nullable = (value) => value === null || value === undefined || value === "";
const number = (value, digits = 2) => nullable(value) || Number.isNaN(Number(value)) ? "—" : Number(value).toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const money = (value, currency = "BRL") => nullable(value) ? "—" : Number(value).toLocaleString("pt-BR", { style: "currency", currency, maximumFractionDigits: currency === "BRL" ? 2 : 2 });
const pct = (value, signed = false) => nullable(value) ? "—" : `${signed && Number(value) > 0 ? "+" : ""}${number(value, 2)}%`;
const dateTime = (value) => nullable(value) ? "—" : new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
const dateOnly = (value) => nullable(value) ? "—" : new Date(`${String(value).slice(0,10)}T12:00:00`).toLocaleDateString("pt-BR");
const variationClass = (value) => nullable(value) ? "" : Number(value) >= 0 ? "positive" : "negative";

function toast(message, type = "") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  $("#toast-region").append(node);
  setTimeout(() => node.remove(), 5200);
}

function readableApiError(detail,status){
  const code=typeof detail==="string"?detail:"";
  const messages={
    permission_required:"Este recurso não está liberado para a sua conta.",
    portfolio_not_found:"A carteira solicitada não foi encontrada.",
    custom_investment_not_found:"O investimento não foi encontrado ou já foi arquivado.",
    finance_transaction_not_found:"O lançamento não foi encontrado ou já foi arquivado.",
    invalid_finance_category:"A categoria não corresponde ao tipo de lançamento escolhido.",
    invalid_finance_status:"A situação não corresponde ao tipo de lançamento escolhido.",
    invalid_competence_month:"O mês informado é inválido.",
    unsupported_or_duplicate_ticker:"Use o código principal do ativo. Mercados fracionários e códigos temporários não são cadastrados separadamente.",
    active_personal_backtest_exists:"Já existe uma análise em processamento. Aguarde a conclusão.",
  };
  if(typeof detail==="object"&&detail?.permission_required)return messages.permission_required;
  if(messages[code])return messages[code];
  if(status>=500)return "O serviço está temporariamente indisponível. Seus dados foram preservados; tente novamente em instantes.";
  if(status===404)return "A informação solicitada não foi encontrada.";
  if(status===422)return "Revise os campos informados e tente novamente.";
  return code||`Não foi possível concluir a solicitação (HTTP ${status}).`;
}

async function api(path, options = {}) {
  const requestOptions = {...options};
  const key = requestOptions.requestKey;
  let controller = null;
  if (key) {
    state.requestControllers.get(key)?.abort();
    controller = new AbortController();
    state.requestControllers.set(key, controller);
    requestOptions.signal = controller.signal;
    delete requestOptions.requestKey;
  }
  const request = { credentials: "same-origin", ...requestOptions };
  request.headers = { "Content-Type": "application/json", ...(requestOptions.headers || {}) };
  let response;
  try {
    response = await fetch(`${BASE_PATH}${path}`, request);
  } finally {
    if (key && state.requestControllers.get(key) === controller) state.requestControllers.delete(key);
  }
  if (response.status === 401) {
    showLogin();
    throw new Error("Sua sessão expirou. Entre novamente.");
  }
  let body = null;
  try { body = await response.json(); } catch (_) { body = null; }
  if (!response.ok) {
    const detail = body?.detail;
    const readable = readableApiError(detail,response.status);
    throw new Error(readable);
  }
  return body;
}

function showLogin() {
  $("#app-shell").classList.add("hidden");
  $("#login-view").classList.remove("hidden");
}

function showApp() {
  $("#login-view").classList.add("hidden");
  $("#app-shell").classList.remove("hidden");
}

function configureAccess() {
  const { user, access } = state.session;
  $("#profile-name").textContent = user.name || user.email;
  $("#profile-role").textContent = access.is_owner ? "Administrador master" : access.status === "approved" ? "Acesso aprovado" : "Acesso visitante";
  const avatar = $("#profile-avatar");
  avatar.textContent = (user.name || user.email || "U").slice(0, 1).toUpperCase();
  if (user.picture) avatar.innerHTML = `<img src="${esc(user.picture)}" alt="">`;
  $$(".owner-only").forEach(node => node.classList.toggle("hidden", !access.is_owner));
  $$(".permission-study").forEach(node => node.classList.toggle("hidden", !access.can_view_backtest_studies));
  const navRules = {
    analysis: access.can_view_market,
    portfolio: access.can_view_portfolio,
    finances: access.can_view_finances,
    backtests: access.can_view_backtests,
    admin: access.is_owner,
  };
  Object.entries(navRules).forEach(([view, allowed]) => {
    const item = $(`.nav-item[data-view="${view}"]`);
    if (item) item.classList.toggle("hidden", !allowed);
  });
}

function setView(view, tab = null) {
  state.view = view;
  if (tab) state.tabs[view] = tab;
  $$(".view").forEach(node => node.classList.toggle("active", node.id === `view-${view}`));
  $$(".nav-item").forEach(node => node.classList.toggle("active", node.dataset.view === view));
  document.body.classList.remove("mobile-nav-open");
  if (tab) activateTab(view, tab, false);
  loadCurrentView();
}

function activateTab(group, tab, load = true) {
  state.tabs[group] = tab;
  $$(`.tabs[data-tabs="${group}"] .tab`).forEach(node => node.classList.toggle("active", node.dataset.tab === tab));
  if (load) loadCurrentView();
}

function loadingCards(count = 4) {
  return `<div class="loading-grid">${Array.from({length: count}, () => '<div class="skeleton"></div>').join("")}</div>`;
}

function errorState(error, retry = "") {
  return `<div class="data-card error-state"><strong>Não foi possível carregar este painel.</strong><span>${esc(error?.message || error)}</span>${retry ? `<div style="margin-top:14px"><button class="button secondary" data-retry="${esc(retry)}">Tentar novamente</button></div>` : ""}</div>`;
}

function metricCard(label, value, meta = "", variation = null) {
  return `<article class="metric-card"><div class="metric-label"><span>${esc(label)}</span>${nullable(variation) ? "" : `<span class="${variationClass(variation)}">${pct(variation, true)}</span>`}</div><strong class="metric-value">${value}</strong><span class="metric-meta">${esc(meta)}</span></article>`;
}

function marketMetric(data, label) {
  return Object.values(data?.quoted || {}).flat().find(item => item.label === label) || null;
}

function renderMarketSummary() {
  const data = state.market || {};
  const ibov = marketMetric(data, "IBOV");
  const ipca = (data.inflation || []).find(item => item.label === "IPCA");
  const dolar = (data.fx || []).find(item => item.label === "Dólar / Real");
  const selic = data.selic || {};
  $("#market-summary").innerHTML = [
    metricCard("IBOV", ibov ? `${number(ibov.current, 0)} pts` : "—", "Brasil", ibov?.variations?.["1d"]),
    metricCard("IPCA • 12 meses", pct(ipca?.value_12m), `Referência ${dateOnly(ipca?.as_of)} • IBGE`),
    metricCard("Dólar / Real", dolar ? money(dolar.current) : "—", "Câmbio", dolar?.variations?.["1d"]),
    metricCard("Selic atual", pct(selic.current), "Meta anual • Banco Central"),
  ].join("");
  const generated = data.generated_at || state.marketEnvelope?.finished_at;
  $("#market-updated").textContent = generated ? `Atualização mais recente em ${dateTime(generated)}` : "Atualização em segundo plano";
}

const updateStatusLabels={updated:"Atualizado",partial:"Atualização parcial",stale:"Desatualizado",queued:"Na fila",running:"Atualizando",failed:"Falhou",unavailable:"Aguardando dados"};
function marketUpdatePanel(keys, title="Atualizações deste painel") {
  const updates=state.marketEnvelope?.updates||{};
  const rows=keys.map(key=>updates[key]).filter(Boolean);
  if(!rows.length)return "";
  const completed=rows.map(row=>row.last_updated_at).filter(Boolean).sort();
  const next=rows.map(row=>row.next_update_at).filter(Boolean).sort();
  const active=rows.some(row=>["queued","running"].includes(row.status));
  const failed=rows.some(row=>row.status==="failed");
  const partial=rows.some(row=>row.status==="partial");
  const status=active?"Atualizando em segundo plano":failed||partial?"Uma fonte requer atenção":"Dados disponíveis";
  const details=rows.map(row=>`<div class="update-detail-row"><span><strong>${esc(row.label)}</strong><small>${esc(row.source||"")}${row.warnings?.length?` • ${row.warnings.length} item(ns) preservado(s) da atualização anterior`:""}</small></span><span><span class="pill ${["failed","stale","partial"].includes(row.status)?"warning":""}">${esc(updateStatusLabels[row.status]||row.status)}</span><small>${row.last_updated_at?dateTime(row.last_updated_at):"Ainda não atualizada"}${row.next_update_at?` • próxima ${dateTime(row.next_update_at)}`:""}</small></span></div>`).join("");
  return `<div class="update-panel"><div class="update-summary"><span><strong>${esc(title)}</strong><small>${completed.length?`Mais recente: ${dateTime(completed[completed.length-1])}`:"Primeira atualização pendente"}${next.length?` • próxima rodada: ${dateTime(next[0])}`:""}</small></span><span><small>${esc(status)}</small><button class="button secondary compact" data-refresh-groups="${esc(keys.join(","))}" ${active?"disabled":""}>Atualizar agora</button></span></div><details class="update-details"><summary>Detalhes das fontes</summary>${details}</details></div>`;
}
function recordedUpdatePanel(title,lastUpdated,description="") {
  return `<div class="update-panel"><div class="update-summary"><span><strong>${esc(title)}</strong><small>${lastUpdated?`Atualização mais recente: ${dateTime(lastUpdated)}`:"Ainda sem atualização registrada"}${description?` • ${esc(description)}`:""}</small></span></div></div>`;
}

function marketTable(items, columns) {
  if (!items?.length) return '<div class="empty-state"><strong>Dados ainda indisponíveis</strong>A atualização ocorre em segundo plano. Os outros painéis continuam utilizáveis.</div>';
  return `<div class="table-scroll"><table><thead><tr>${columns.map(col => `<th>${esc(col.label)}</th>`).join("")}</tr></thead><tbody>${items.map(item => `<tr>${columns.map(col => `<td class="${col.className ? col.className(item) : ""}">${col.render(item)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

const marketColumns = [
  {label:"Indicador", render: row => `<strong>${esc(row.label)}</strong>${row.proxy ? '<br><span class="pill warning">Proxy transparente</span>' : ""}`},
  {label:"Atual", render: row => nullable(row.current) ? "—" : `${number(row.current, row.unit === "pontos" ? 0 : 2)} ${esc(row.unit || "")}`},
  ...[["1d","1 dia"],["1w","1 semana"],["1m","1 mês"],["1y","1 ano"]].map(([key,label]) => ({label, className: row => variationClass(row.variations?.[key]), render: row => pct(row.variations?.[key], true)})),
];

function sectionCard(title, body, subtitle = "", source = null) {
  return `<section class="data-card"><div class="card-section"><div class="card-heading"><div><h2>${esc(title)}</h2>${subtitle ? `<p>${esc(subtitle)}</p>` : ""}</div>${source?.url ? `<a class="source-link" target="_blank" rel="noopener" href="${esc(source.url)}">${esc(source.label || "Fonte")}</a>` : ""}</div>${body}</div></section>`;
}

function renderDashboardTab() {
  const root = $("#dashboard-tab-content");
  const data = state.market;
  if (!data) { root.innerHTML = loadingCards(6); return; }
  const tab = state.tabs.dashboard;
  if (tab === "overview") {
    const inflation = marketTable(data.inflation || [], [
      {label:"Indicador",render:r=>`<strong>${esc(r.label)}</strong>`},
      {label:"Acumulado 12 meses",render:r=>pct(r.value_12m),className:r=>variationClass(r.value_12m)},
      {label:"Referência",render:r=>dateOnly(r.as_of)},
    ]);
    root.innerHTML = `${marketUpdatePanel(["global_markets","macro","fx","selic_current"])}<div class="panel-grid">${sectionCard("Brasil", marketTable(data.quoted?.brazil, marketColumns), "Índices e variações")}${sectionCard("Inflação", inflation, "Brasil e Estados Unidos")}</div>`;
  } else if (tab === "rates") {
    const selic = data.selic || {};
    const projections = [selic.current_year, selic.next_year].filter(Boolean);
    const selicCards = `<div class="metric-grid">${metricCard("Selic atual", pct(selic.current), `Referência ${dateOnly(selic.current_as_of)}`)}${projections.map(item => metricCard(`Selic projetada • ${item.reference_year || ""}`, pct(item.value), `Focus de ${dateOnly(item.survey_date)}`)).join("")}</div><div class="notice info" style="margin-top:13px">${esc(selic.projection_note || "As projeções são medianas do Relatório Focus.")}</div>`;
    const fixed = marketTable(data.fixed_income || [], [
      {label:"Indicador",render:r=>`<strong>${esc(r.label)}</strong>${r.proxy ? `<br><small>${esc(r.proxy_label || "Proxy")}</small>`:""}`},
      {label:"Rentabilidade anual",render:r=>pct(r.annual_return_pct),className:r=>variationClass(r.annual_return_pct)},
      {label:"Rentabilidade mensal",render:r=>pct(r.monthly_return_pct),className:r=>variationClass(r.monthly_return_pct)},
      {label:"Referência",render:r=>dateOnly(r.as_of)},
    ]);
    const rates = data.us_rates || {};
    const yields = marketTable(rates.yields || [], [{label:"Prazo",render:r=>esc(r.maturity)},{label:"Yield anual",render:r=>pct(r.yield_pct)}]);
    const bonds = marketTable(rates.bond_returns || [], [
      {label:"T-Bonds",render:r=>`<strong>${esc(r.label)}</strong><br><small>${esc(r.proxy_label || "")}</small>`},
      {label:"1 mês",render:r=>pct(r.monthly_return_pct,true),className:r=>variationClass(r.monthly_return_pct)},
      {label:"1 ano",render:r=>pct(r.annual_return_pct,true),className:r=>variationClass(r.annual_return_pct)},
    ]);
    root.innerHTML = `${marketUpdatePanel(["selic_current","selic_focus","macro","rates_calendar"])}<div class="panel-grid">${sectionCard("Selic e projeções Focus", selicCards, "Taxas anuais")}${sectionCard("Renda fixa brasileira", fixed, "Somente rentabilidades anual e mensal")}${sectionCard("Treasuries dos EUA", yields, `Spread 10a − 2a: ${pct(rates.spread_10y_2y)}`, {url:rates.url,label:rates.source})}${sectionCard("Rentabilidade de T-Bonds", bonds, "ETFs usados como proxies líquidos")}</div><div class="notice info" style="margin-top:16px"><strong>Para que serve o spread?</strong> ${esc(rates.spread_explanation || "Compara juros longos e curtos e ajuda a interpretar a inclinação da curva americana.")}</div>`;
  } else if (tab === "global") {
    root.innerHTML = `${marketUpdatePanel(["global_markets"])}<div class="global-market-layout"><div class="global-market-main">${sectionCard("Bolsas globais", marketTable(data.quoted?.global, marketColumns))}</div><div class="global-market-stack">${sectionCard("Risco e dólar", marketTable(data.quoted?.risk, marketColumns))}${sectionCard("Commodities", marketTable(data.quoted?.commodities, marketColumns))}</div></div>`;
  } else if (tab === "crypto") {
    const crypto = marketTable(data.crypto || [], [
      {label:"Ativo",render:r=>`<strong>${esc(r.label)}</strong>`}, {label:"Em dólar",render:r=>money(r.value_usd,"USD")},
      {label:"Em real",render:r=>`${money(r.value_brl,"BRL")}${r.brl_derived_from_fx ? '<br><small>Convertido pelo câmbio atual</small>':""}`},
      ...[["1d","1 dia"],["1w","1 semana"],["1m","1 mês"],["1y","1 ano"]].map(([key,label])=>({label,render:r=>pct(r.variations?.[key],true),className:r=>variationClass(r.variations?.[key])})),
    ]);
    root.innerHTML = `${marketUpdatePanel(["crypto","fx"])}<div class="panel-grid">${sectionCard("Criptoativos", crypto)}${sectionCard("Resumo de câmbio", marketTable(data.fx, marketColumns), "Cotações orientadas conforme o nome do par")}</div>`;
  } else if (tab === "curve") {
    root.innerHTML = marketUpdatePanel(["rates_calendar"])+renderCurve(data.curve || {});
    if(!state.curveHistoryLoading&&!state.curveHistoryLoaded)loadCurveHistory();
  } else if (tab === "comparison") {
    if (state.comparison) renderComparison(); else loadComparison();
  } else if (tab === "calendar") {
    const rows = (data.calendar || []).map(item => ({...item, important:item.highlight === "super_wednesday"}));
    root.innerHTML = marketUpdatePanel(["rates_calendar"])+sectionCard("Próximas datas importantes", marketTable(rows, [
      {label:"Data",render:r=>`<strong>${dateOnly(r.date)}</strong>`},{label:"Evento",render:r=>`${esc(r.event)}${r.important?'<br><span class="pill warning">SUPER QUARTA</span>':""}`},
      {label:"Categoria",render:r=>esc(r.category)},{label:"Horário",render:r=>esc(r.time || "—")},{label:"Observação",render:r=>esc(r.observation || "—")},
      {label:"Fonte",render:r=>r.url?`<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.source||"Consultar")}</a>`:esc(r.source||"—")},
    ]));
  } else if (tab === "headlines") {
    loadHeadlines();
  }
}

function renderCurve(curve) {
  const current={reference_date:curve.as_of,points:curve.points||[],curve_type:curve.curve_type,title:curve.title,source:curve.source,url:curve.url};
  if(!current.points.length)return errorState("A fonte oficial ainda não retornou os pontos da curva.","market");
  const history=(state.curveHistory||[]).filter(item=>String(item.reference_date)!==String(current.reference_date));
  const requested=Math.max(1,Number(state.curveHistoryCount||1));
  const series=[current,...history.slice(0,requested-1)].map(item=>({...item,points:(item.points||[]).filter(p=>Number(p.years)<=20&&(!state.curveYears||Number(p.years)<=state.curveYears)&&!nullable(p.nominal_rate))})).filter(item=>item.points.length);
  if(!series.length)return errorState("Não há vértices disponíveis para esse horizonte.","market");
  const width=900,height=320,padLeft=68,padRight=22,padTop=18,padBottom=58;
  const allPoints=series.flatMap(item=>item.points),maxX=Math.max(...allPoints.map(p=>Number(p.years)||0),1);
  const values=allPoints.map(p=>Number(p.nominal_rate)).filter(Number.isFinite),minY=Math.min(...values),maxY=Math.max(...values);
  const x=p=>padLeft+(Number(p.years)/maxX)*(width-padLeft-padRight),y=value=>height-padBottom-((Number(value)-minY)/Math.max(maxY-minY,.1))*(height-padTop-padBottom);
  const colors=["#0b5d4b","#c79b3b","#2775b6","#8c5aa6"],paths=series.map((item,index)=>`<path d="${item.points.map((p,i)=>`${i?"L":"M"}${x(p).toFixed(1)},${y(p.nominal_rate).toFixed(1)}`).join(" ")}" fill="none" stroke="${colors[index]}" stroke-width="${index?2:3}" ${index?'stroke-dasharray="7 4"':""}/>`).join("");
  const currentPoints=series[0].points;
  const circles=currentPoints.map(p=>`<circle cx="${x(p)}" cy="${y(p.nominal_rate)}" r="3" fill="${colors[0]}"><title>${esc(p.contract||`${number(p.years,2)} anos`)} • ${pct(p.nominal_rate)}</title></circle>`).join("");
  const labels=currentPoints.filter((_,i)=>i%Math.max(1,Math.ceil(currentPoints.length/10))===0).map(p=>`<text x="${x(p)}" y="${height-padBottom+19}" font-size="11" text-anchor="middle" fill="#67756f">${number(p.years,1)}a</text>`).join("");
  const yTicks=Array.from({length:5},(_,i)=>minY+(maxY-minY)*(i/4));
  const yGrid=yTicks.map(value=>`<line x1="${padLeft}" x2="${width-padRight}" y1="${y(value)}" y2="${y(value)}" stroke="#e3eae7" stroke-width="1"/><text x="${padLeft-9}" y="${y(value)+4}" font-size="11" text-anchor="end" fill="#67756f">${number(value,2)}%</text>`).join("");
  const axes=`<line x1="${padLeft}" x2="${padLeft}" y1="${padTop}" y2="${height-padBottom}" stroke="#8b9993"/><line x1="${padLeft}" x2="${width-padRight}" y1="${height-padBottom}" y2="${height-padBottom}" stroke="#8b9993"/><text x="${(padLeft+width-padRight)/2}" y="${height-12}" text-anchor="middle" font-size="12" font-weight="700" fill="#46534e">Prazo até o vencimento (anos)</text><text transform="translate(16 ${(padTop+height-padBottom)/2}) rotate(-90)" text-anchor="middle" font-size="12" font-weight="700" fill="#46534e">Taxa anual (%)</text>`;
  const svg=`<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Curvas de juros: prazo em anos no eixo horizontal e taxa anual no eixo vertical">${yGrid}${axes}${paths}${circles}${labels}</svg>`;
  const periods=[[1,"1 ano"],[2,"2 anos"],[5,"5 anos"],[10,"10 anos"],[20,"20 anos"],[0,"Máximo"]];
  const controls=`<div class="curve-controls"><div class="chart-periods" role="group" aria-label="Horizonte da curva">${periods.map(([years,label])=>`<button class="button ${state.curveYears===years?"primary":"secondary"}" data-curve-years="${years}">${label}</button>`).join("")}</div><div class="chart-periods" role="group" aria-label="Comparar curvas anteriores">${[[1,"Somente atual"],[2,"+ 1 anterior"],[4,"+ 3 anteriores"]].map(([count,label])=>`<button class="button ${requested===count?"primary":"secondary"}" data-curve-history-count="${count}">${label}</button>`).join("")}</div></div>`;
  const curveLegend=series.map((item,index)=>`<span><i class="legend-dot" style="background:${colors[index]}"></i>${index?"Curva anterior":"Curva atual"} • ${dateOnly(item.reference_date)}</span>`).join("");
  const method=curve.curve_type==="di_pre"?"Taxa de ajuste DI1 • efetiva anual, base 252 dias úteis":"Taxa prefixada nominal • ETTJ ANBIMA";
  const historyNote=state.curveHistory.length?"As referências diárias ficam preservadas para comparação.":"O histórico começará a ser formado após esta versão registrar as próximas atualizações.";
  return sectionCard(curve.title || "Curva de juros brasileira",`${controls}<div class="chart">${svg}</div><div class="chart-legend">${curveLegend}</div><div class="notice info"><strong>${esc(method)}.</strong> ${esc(historyNote)} ${esc(curve.methodology||"Nenhum vértice é extrapolado.")}</div>`,`Curva de juros futuros • horizonte dos contratos e deslocamento entre datas`,{url:curve.url,label:curve.source});
}

async function loadCurveHistory(){
  state.curveHistoryLoading=true;
  try{state.curveHistory=await api("/market-dashboard/interest-curve/history?limit=12");if(state.tabs.dashboard==="curve")renderDashboardTab();}
  catch(_){state.curveHistory=[];}
  state.curveHistoryLoaded=true;
  state.curveHistoryLoading=false;
}

const comparisonColors = ["#0b5d4b","#c79b3b","#2775b6","#8c5aa6","#d0614c","#3d9a78","#9b7d31","#5267a5","#c24f86","#69766f","#df8437","#3999a3","#7c655c","#22577a","#9a031e","#386641","#7b2cbf","#bc6c25","#0077b6","#6a994e","#ef476f","#118ab2","#8338ec","#fb8500","#495057","#2a9d8f"];

function comparisonDateBounds() {
  const timestamps=(state.comparison?.series||[]).flatMap(item=>(item.points||[]).map(point=>new Date(`${point.date}T12:00:00Z`).getTime())).filter(Number.isFinite);
  if(!timestamps.length)return null;
  return {min:new Date(Math.min(...timestamps)),max:new Date(Math.max(...timestamps))};
}

function isoDay(value) { return value instanceof Date&&!Number.isNaN(value.getTime())?value.toISOString().slice(0,10):""; }

function ensureComparisonCustomDates() {
  const bounds=comparisonDateBounds();
  if(!bounds)return;
  if(!state.comparisonCustomTo)state.comparisonCustomTo=isoDay(bounds.max);
  if(!state.comparisonCustomFrom){
    const start=new Date(bounds.max);
    start.setUTCFullYear(start.getUTCFullYear()-Math.max(1,Number(state.comparisonYears)||5));
    state.comparisonCustomFrom=isoDay(start<bounds.min?bounds.min:start);
  }
}

function comparisonWindow() {
  const bounds=comparisonDateBounds();
  if(!bounds)return null;
  if(state.comparisonCustom){
    const start=new Date(`${state.comparisonCustomFrom}T00:00:00Z`),end=new Date(`${state.comparisonCustomTo}T23:59:59Z`);
    if(!state.comparisonCustomFrom||!state.comparisonCustomTo||Number.isNaN(start.getTime())||Number.isNaN(end.getTime())||start>end)return {...bounds,error:"A data inicial deve ser anterior ou igual à data final."};
    if(state.comparisonCustomFrom<isoDay(bounds.min)||state.comparisonCustomTo>isoDay(bounds.max))return {...bounds,error:`Escolha datas entre ${dateOnly(isoDay(bounds.min))} e ${dateOnly(isoDay(bounds.max))}.`};
    return {min:start,max:end};
  }
  const end=new Date(bounds.max),start=new Date(bounds.max);
  if(state.comparisonYears===.5)start.setUTCMonth(start.getUTCMonth()-6);
  else start.setUTCFullYear(start.getUTCFullYear()-Math.floor(state.comparisonYears));
  return {min:start,max:end};
}

function comparisonTimeTicks(minX,maxX) {
  const day=86400000,spanYears=(maxX-minX)/(365.25*day),ticks=[];
  if(spanYears<=5.1){
    const stepMonths=spanYears<=1.1?1:spanYears<=3.1?3:6;
    const start=new Date(minX),cursor=new Date(Date.UTC(start.getUTCFullYear(),start.getUTCMonth(),1));
    while(cursor.getTime()<minX)cursor.setUTCMonth(cursor.getUTCMonth()+stepMonths);
    while(cursor.getTime()<=maxX){
      const label=cursor.toLocaleDateString("pt-BR",{month:"short",year:"2-digit",timeZone:"UTC"}).replace(".","");
      ticks.push({value:cursor.getTime(),label});cursor.setUTCMonth(cursor.getUTCMonth()+stepMonths);
    }
  }else{
    const stepYears=spanYears>15?2:1,start=new Date(minX),cursor=new Date(Date.UTC(start.getUTCFullYear()+1,0,1));
    while(cursor.getTime()<=maxX){ticks.push({value:cursor.getTime(),label:String(cursor.getUTCFullYear())});cursor.setUTCFullYear(cursor.getUTCFullYear()+stepYears);}
  }
  if(!ticks.length){
    const start=new Date(minX),end=new Date(maxX),format=value=>value.toLocaleDateString("pt-BR",{month:"short",year:"2-digit",timeZone:"UTC"}).replace(".","");
    ticks.push({value:minX,label:format(start)});
    if(maxX-minX>7*day)ticks.push({value:maxX,label:format(end)});
  }
  return ticks;
}

function visibleComparisonSeries() {
  const window=comparisonWindow();
  if(!window||window.error)return [];
  let rows=(state.comparison?.series || []).filter(item=>state.comparisonSelected.includes(item.code)).map(item=>({...item,points:(item.points||[]).filter(point=>{const observed=new Date(`${point.date}T12:00:00Z`);return observed>=window.min&&observed<=window.max;})}));
  if(state.comparisonBaseMode==="common"){
    const starts=rows.filter(item=>item.points.length).map(item=>new Date(`${item.points[0].date}T12:00:00Z`).getTime());
    if(starts.length){const commonStart=Math.max(...starts);rows=rows.map(item=>({...item,points:item.points.filter(point=>new Date(`${point.date}T12:00:00Z`).getTime()>=commonStart)}));}
  }
  return rows.map(item=>{
    const points=item.points;
    if(!points.length)return {...item,points:[]};
    const base=Number(points[0].value)||100;
    return {...item,points:points.map(point=>({...point,value:Number(point.value)/base*100}))};
  });
}

function annualizedVolatility(points){
  if(!points||points.length<3)return null;const returns=[],spans=[];
  for(let index=1;index<points.length;index+=1){const before=Number(points[index-1].value),after=Number(points[index].value);if(before>0&&after>0)returns.push(after/before-1);spans.push(Math.max(1,(new Date(`${points[index].date}T12:00:00Z`)-new Date(`${points[index-1].date}T12:00:00Z`))/86400000));}
  if(returns.length<2)return null;const mean=returns.reduce((sum,value)=>sum+value,0)/returns.length,variance=returns.reduce((sum,value)=>sum+(value-mean)**2,0)/(returns.length-1);const sorted=[...spans].sort((a,b)=>a-b),median=sorted[Math.floor(sorted.length/2)]||1;return Math.sqrt(variance)*Math.sqrt(365/median)*100;
}

function renderComparison() {
  if(state.tabs.dashboard!=="comparison")return;
  const root=$("#dashboard-tab-content"), payload=state.comparison||{}, all=payload.series||[];
  if(!all.length){root.innerHTML=errorState("As séries históricas ainda estão sendo preparadas.");return;}
  const periods=[[.5,"6 meses"],[1,"1 ano"],[2,"2 anos"],[3,"3 anos"],[5,"5 anos"],[10,"10 anos"],[15,"15 anos"],[20,"20 anos"]];
  if(state.comparisonCustom)ensureComparisonCustomDates();
  const bounds=comparisonDateBounds(),minDate=bounds?isoDay(bounds.min):"",maxDate=bounds?isoDay(bounds.max):"";
  const customDates=state.comparisonCustom?`<div class="comparison-date-range"><div class="field"><label for="comparison-from">De</label><input id="comparison-from" type="date" data-comparison-date="from" value="${esc(state.comparisonCustomFrom)}" min="${minDate}" max="${maxDate}"></div><div class="field"><label for="comparison-to">Até</label><input id="comparison-to" type="date" data-comparison-date="to" value="${esc(state.comparisonCustomTo)}" min="${minDate}" max="${maxDate}"></div></div>`:"";
  const selectors=`<div class="comparison-controls"><div class="chart-periods">${periods.map(([years,label])=>`<button class="button ${!state.comparisonCustom&&state.comparisonYears===years?"primary":"secondary"}" data-comparison-years="${years}">${label}</button>`).join("")}<button class="button ${state.comparisonCustom?"primary":"secondary"}" data-comparison-custom="true">Personalizar</button></div>${customDates}<div class="comparison-refresh-row"><span class="chart-periods"><button class="button ${state.comparisonBaseMode==="common"?"primary":"secondary"}" data-comparison-base="common">Início comum</button><button class="button ${state.comparisonBaseMode==="own"?"primary":"secondary"}" data-comparison-base="own">Histórico próprio</button></span><button class="button secondary" data-comparison-refresh="true">Atualizar séries</button></div><div class="series-picker" role="group" aria-label="Indicadores para comparação">${all.map((item,index)=>`<label class="check" title="${esc(item.note||item.source||item.label)}"><input type="checkbox" data-comparison-series="${esc(item.code)}" ${state.comparisonSelected.includes(item.code)?"checked":""} ${item.points?.length?"":"disabled"}><i class="legend-dot" style="background:${comparisonColors[index%comparisonColors.length]}"></i><span>${esc(item.label)}${item.proxy?" <small>proxy</small>":""}</span></label>`).join("")}</div></div>`;
  const selectedWindow=comparisonWindow();
  if(selectedWindow?.error){root.innerHTML=sectionCard("Comparador histórico",selectors+`<div class="notice danger">${esc(selectedWindow.error)}</div>`);return;}
  const selected=visibleComparisonSeries().filter(item=>item.points.length);
  if(!selected.length){root.innerHTML=sectionCard("Comparador histórico",selectors+'<div class="empty-state"><strong>Selecione ao menos uma série disponível</strong>Os dados ausentes não impedem o uso das demais séries.</div>');return;}
  const width=1000,height=360,padX=48,padTop=25,padBottom=42,plotBottom=height-padBottom;
  const timestamps=selected.flatMap(item=>item.points.map(point=>new Date(`${point.date}T12:00:00Z`).getTime()));
  const values=selected.flatMap(item=>item.points.map(point=>Number(point.value))).filter(Number.isFinite);
  const minX=Math.min(...timestamps),maxX=Math.max(...timestamps),minY=Math.min(...values),maxY=Math.max(...values);
  const x=value=>padX+((value-minX)/Math.max(maxX-minX,1))*(width-padX*2);
  const y=value=>plotBottom-((value-minY)/Math.max(maxY-minY,.1))*(plotBottom-padTop);
  const paths=selected.map(item=>{
    const originalIndex=all.findIndex(row=>row.code===item.code),color=comparisonColors[originalIndex%comparisonColors.length];
    const d=item.points.map((point,index)=>`${index?"L":"M"}${x(new Date(`${point.date}T12:00:00Z`).getTime()).toFixed(1)},${y(Number(point.value)).toFixed(1)}`).join(" ");
    return `<path d="${d}" fill="none" stroke="${color}" stroke-width="2.6"/>`;
  }).join("");
  const grid=[0,.25,.5,.75,1].map(position=>{const value=maxY-(maxY-minY)*position,yy=padTop+(plotBottom-padTop)*position;return `<line x1="${padX}" x2="${width-padX}" y1="${yy}" y2="${yy}" stroke="#dfe6e2" stroke-dasharray="5 5"/><text x="${padX-7}" y="${yy+4}" text-anchor="end" font-size="11" fill="#67756f">${number(value,0)}</text>`;}).join("");
  const timeline=comparisonTimeTicks(minX,maxX).map(tick=>`<line x1="${x(tick.value)}" x2="${x(tick.value)}" y1="${padTop}" y2="${plotBottom}" stroke="#edf1ef"/><text x="${x(tick.value)}" y="${height-10}" text-anchor="middle" font-size="11" fill="#67756f">${esc(tick.label)}</text>`).join("");
  const svg=`<svg class="chart-svg comparison-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Comparação histórica rebaseada em 100">${grid}${timeline}<line x1="${padX}" x2="${width-padX}" y1="${plotBottom}" y2="${plotBottom}" stroke="#bfcac5"/>${paths}</svg>`;
  const legend=selected.map(item=>{const originalIndex=all.findIndex(row=>row.code===item.code),points=item.points,last=points[points.length-1],result=Number(last.value)-100;return `<span><i class="legend-dot" style="background:${comparisonColors[originalIndex%comparisonColors.length]}"></i>${esc(item.label)} <strong class="${variationClass(result)}">${pct(result,true)}</strong></span>`;}).join("");
  const unavailable=all.filter(item=>!item.points?.length).map(item=>item.label);
  const periodLabel=state.comparisonCustom?`de ${dateOnly(state.comparisonCustomFrom)} até ${dateOnly(state.comparisonCustomTo)}`:state.comparisonYears===.5?"6 meses":`${state.comparisonYears} ano(s)`;
  const metrics=marketTable(selected.map(item=>{const points=item.points,last=points[points.length-1];return {label:item.label,start:points[0]?.date,end:last?.date,return_pct:Number(last?.value)-100,volatility_pct:annualizedVolatility(points),observations:points.length};}),[{label:"Indicador",render:r=>`<strong>${esc(r.label)}</strong>`},{label:"Início efetivo",render:r=>dateOnly(r.start)},{label:"Fim",render:r=>dateOnly(r.end)},{label:"Retorno",render:r=>pct(r.return_pct,true),className:r=>variationClass(r.return_pct)},{label:"Volatilidade anual",render:r=>pct(r.volatility_pct)},{label:"Observações",render:r=>number(r.observations,0)}]);
  root.innerHTML=marketUpdatePanel(["comparison"])+sectionCard("Comparador histórico",`${selectors}<div class="chart comparison-chart-wrap">${svg}</div><div class="chart-legend">${legend}</div>${sectionCard("Retorno e risco no período",metrics,"Volatilidade anualizada conforme a frequência de cada série")}${unavailable.length?`<div class="notice">Sem dados nesta atualização: ${esc(unavailable.join(", "))}.</div>`:""}<div class="notice info">${esc(payload.note||"Base 100 no início do período selecionado.")} ${state.comparisonBaseMode==="common"?"Todas as linhas começam na primeira data disponível em comum.":"Cada linha usa seu próprio primeiro dado disponível."}</div>`,`Desempenho acumulado • base R$ 100 • ${periodLabel}`);
}

async function loadComparison(force=false,attempt=0) {
  if(state.comparisonLoading&&attempt===0)return;
  state.comparisonLoading=true;
  const root=$("#dashboard-tab-content");
  if(!state.comparison)root.innerHTML=`${loadingCards(6)}<div class="notice info" style="margin-top:14px">Preparando as séries históricas em segundo plano. Você pode continuar usando os outros painéis.</div>`;
  try{
    let payload=await api(force?"/market-dashboard/comparison/refresh":"/market-dashboard/comparison",{method:force?"POST":"GET",requestKey:"comparison"});
    if(payload.update){state.marketEnvelope=state.marketEnvelope||{};state.marketEnvelope.updates={...(state.marketEnvelope.updates||{}),comparison:payload.update};}
    if(payload.data?.series?.length){state.comparison=payload.data;renderComparison();state.comparisonLoading=false;return;}
    if((payload.refreshing||payload.scheduled)&&attempt<40){state.comparisonLoading=false;setTimeout(()=>loadComparison(false,attempt+1),3000);return;}
    root.innerHTML=errorState(payload.error||"As fontes históricas não responderam nesta atualização.");
  }catch(error){if(error.name!=="AbortError")root.innerHTML=errorState(error);}
  state.comparisonLoading=false;
}

async function loadMarket(force = false) {
  if (!state.market) {
    $("#market-summary").innerHTML = loadingCards(4);
    $("#dashboard-tab-content").innerHTML = loadingCards(6);
  }
  try {
    const envelope = await api("/market-dashboard", {requestKey:"market-get"});
    state.marketEnvelope = envelope;
    if (envelope?.data && Object.keys(envelope.data).length) state.market = envelope.data;
    renderMarketSummary(); renderDashboardTab();
    const endpoint = force ? "/market-dashboard/refresh" : "/market-dashboard/ensure";
    const queued = await api(endpoint, {method:"POST"});
    if (queued.scheduled || ["queued","running"].includes(queued.refresh_status)) pollMarket();
    else if (queued.data && Object.keys(queued.data).length) { state.marketEnvelope=queued; state.market=queued.data; renderMarketSummary(); renderDashboardTab(); }
  } catch (error) {
    if (!state.market) $("#dashboard-tab-content").innerHTML = errorState(error, "market");
    toast(`Dados de mercado: ${error.message}`, "error");
  }
}

async function pollMarket(attempt = 0) {
  if (attempt > 35) return;
  await new Promise(resolve => setTimeout(resolve, 2500));
  try {
    const envelope = await api("/market-dashboard");
    if (envelope.data && Object.keys(envelope.data).length) { state.marketEnvelope=envelope; state.market=envelope.data; renderMarketSummary(); renderDashboardTab(); }
    if (["queued","running"].includes(envelope.refresh_status)) pollMarket(attempt+1);
    else if (envelope.refresh_status === "completed") toast("Painel de mercado atualizado.", "success");
  } catch (_) { /* keep stale data visible */ }
}

async function loadHeadlines() {
  const root = $("#dashboard-tab-content");
  root.innerHTML = loadingCards(5);
  try {
    let payload = await api("/market-dashboard/headlines", {requestKey:"headlines"});
    if (payload.data?.items?.length) renderHeadlines(payload);
    else if (payload.refreshing || payload.scheduled) {
      root.innerHTML = `${loadingCards(5)}<div class="notice info" style="margin-top:14px">Buscando as principais manchetes em segundo plano. O restante do site continua disponível.</div>`;
      setTimeout(async () => { try { payload=await api("/market-dashboard/headlines"); renderHeadlines(payload); } catch (_) {} }, 2500);
    } else renderHeadlines(payload);
  } catch (error) { root.innerHTML = errorState(error); }
}

function renderHeadlines(payload) {
  if (state.tabs.dashboard !== "headlines") return;
  const items = payload.data?.items || [];
  const list = items.length ? `<div class="headline-list"><div class="headline headline-header"><span>#</span><span>Manchete e fonte</span><span>Publicada em</span></div>${items.slice(0,10).map((item,index)=>`<a class="headline" href="${esc(item.url)}" target="_blank" rel="noopener"><span class="headline-number">${String(index+1).padStart(2,"0")}</span><span><strong>${esc(item.title)}</strong><small>${esc(item.source)}</small></span><small>${item.published_at ? dateTime(item.published_at) : "Horário não informado"}</small></a>`).join("")}</div>` : '<div class="empty-state"><strong>Nenhuma manchete disponível agora</strong>As fontes serão consultadas novamente em até uma hora.</div>';
  if(payload.update){state.marketEnvelope=state.marketEnvelope||{};state.marketEnvelope.updates={...(state.marketEnvelope.updates||{}),headlines:payload.update};}
  $("#dashboard-tab-content").innerHTML = marketUpdatePanel(["headlines"])+sectionCard("10 principais manchetes de economia", list, "Atualização automática a cada hora");
}

async function refreshMarketGroups(keys) {
  const groups=String(keys||"").split(",").map(value=>value.trim()).filter(Boolean);
  if(!groups.length)return;
  try {
    const results=await Promise.all(groups.map(group=>api(`/market-dashboard/groups/${encodeURIComponent(group)}/refresh`,{method:"POST"})));
    const scheduled=results.filter(result=>result.scheduled).length;
    toast(scheduled?"Atualização solicitada. Os dados atuais permanecerão visíveis.":"Esses dados foram solicitados há menos de 5 minutos.",scheduled?"success":"info");
    setTimeout(()=>loadCurrentView(),2500);
  } catch(error) { toast(error.message,"error"); }
}

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
    <div class="field stock-only-filter"><label>Preços-teto</label><label class="check"><input id="below-graham" type="checkbox"> Abaixo de Graham</label><label class="check"><input id="below-barsi" type="checkbox"> Abaixo do preço-teto de dividendos (6%)</label><small id="valuation-permission-note"></small></div>
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
  const supportsFilters=["stock","fii"].includes(analysisType());
  const access=state.session?.access||{},canEdit=supportsFilters;
  $$("#fundamental-filters input,#fundamental-filters select,#technical-filters input,#technical-filters select,#analysis-limit,#ibov-membership,#company-sizes,#below-graham,#below-barsi").forEach(node=>node.disabled=!canEdit);
  const canGraham=Boolean(access.can_use_graham_valuation||access.can_use_alb_analysis),canDividend=Boolean(access.can_use_dividend_ceiling||access.can_use_alb_analysis);
  if($("#below-graham"))$("#below-graham").disabled=!canEdit||!canGraham;
  if($("#below-barsi"))$("#below-barsi").disabled=!canEdit||!canDividend;
  if($("#valuation-permission-note"))$("#valuation-permission-note").textContent=canGraham&&canDividend?"Filtros de valuation autorizados.":"Graham e preço-teto exigem autorizações específicas; a análise ALB libera ambos.";
  if($("#apply-advanced-filters")) $("#apply-advanced-filters").disabled=!canEdit;
  $$("#analysis-preset-row [data-preset-id]").forEach(node=>{
    const permission=node.dataset.presetId==="cnpi"?"can_use_fdi_analysis":node.dataset.presetId==="alb"?"can_use_alb_analysis":null;
    node.disabled=!supportsFilters||Boolean(permission&&!access[permission]);
    node.title=node.disabled&&permission?"Análise disponível mediante autorização do administrador.":"";
  });
  if($("#analysis-filter-notice")) {
    $("#analysis-filter-notice").textContent=!supportsFilters?"Este tipo de ativo exibe apenas os indicadores aplicáveis ao catálogo.":"Os filtros gerais estão ativos. FDI, ALB, Graham e preço-teto respeitam as autorizações individuais da conta.";
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
  ["below-graham","below-barsi","volume-daily-ma9","volume-monthly-ma9"].forEach(id=>{if($(`#${id}`))$(`#${id}`).checked=false;});
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
  return {asset_type:["stock","fii"].includes(analysisType())?analysisType():"other_b3",fundamental_filters,score_filters,valuation_flags:{below_graham:Boolean($("#below-graham")?.checked),below_barsi_6pct:Boolean($("#below-barsi")?.checked)},technical_filters,trend_period:Number($("#trend-period")?.value||21),pivot_timeframe:$("#pivot-timeframe")?.value||"daily",include_technical_columns:true,limit:state.analysisLimit,company_sizes:$("#company-sizes")?[...$("#company-sizes").selectedOptions].map(option=>option.value):[],ibov_membership:$("#ibov-membership")?.value||"any"};
}

function renderCustomPresetButtons() {
  const root=$("#custom-preset-buttons"); if(!root)return;
  root.innerHTML=state.analysisCustom.map(item=>`<button class="preset-button" data-custom-filter-id="${esc(item.id)}">${esc(item.name)}</button>`).join("");
  const access=state.session?.access||{},allowed=Number(access.custom_filter_limit||0)>0&&["stock","fii"].includes(analysisType());
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
  if(!["stock","fii"].includes(type)) { state.analysisCustom=[]; renderCustomPresetButtons(); return; }
  if(force||!state.analysisCatalog[type]){
    const presetPayload=await api(`/screen/presets?asset_type=${type}`);
    state.analysisCatalog[type]=Object.fromEntries((presetPayload.items||[]).map(item=>[item.id,item]));
  }
  if(Number(state.session?.access?.custom_filter_limit||0)>0&&(force||!state.analysisCustomCache[type])) {
    try {
      const custom=await api(`/screen/custom-filters?asset_type=${type}`);
      state.analysisCustomCache[type]=custom.items||[];state.analysisCustomUsageCache[type]={used:custom.used||0,limit:custom.limit||0};
    } catch(_){state.analysisCustomCache[type]=[];}
  }
  state.analysisCustom=state.analysisCustomCache[type]||[];
  state.analysisCustomUsage=state.analysisCustomUsageCache[type]||{used:0,limit:Number(state.session?.access?.custom_filter_limit||0)};
  renderCustomPresetButtons();
}

function markActiveAnalysis({presetId=null,custom=null}={}) {
  state.currentCustomFilter=custom;
  if(presetId)state.analysisPreset=presetId;
  $$("#analysis-preset-row .preset-button").forEach(button=>button.classList.toggle("active",presetId?button.dataset.presetId===presetId:button.dataset.customFilterId===custom?.id));
  const label=custom?.name||state.analysisCatalog[analysisType()]?.[presetId]?.name||"Ajustes livres";
  $("#active-analysis-summary").textContent=`${label} • ${custom?"análise personalizada":"critérios originais do sistema"}`;
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
  const body=current?{name,filters:analysisRequestFromForm()}:{asset_type:analysisType(),name,filters:analysisRequestFromForm()};
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
  if(state.tabs.analysisMode==="guide"){renderIndicatorGuide();return;}
  $("#analysis-list-workspace").classList.remove("hidden");$("#analysis-guide").classList.add("hidden");
  const type=analysisType();
  try {
    const updatePayload=await api("/market-dashboard/updates");
    state.marketEnvelope=state.marketEnvelope||{};state.marketEnvelope.updates={...(state.marketEnvelope.updates||{}),...(updatePayload.updates||{})};
    if($("#analysis-update-status"))$("#analysis-update-status").innerHTML=marketUpdatePanel(["fundamentals","technical_daily","technical_intraday"],"Atualizações dos dados de análise");
  } catch(_) {
    if($("#analysis-update-status"))$("#analysis-update-status").innerHTML='<div class="notice warning">O estado das atualizações não pôde ser consultado agora. Os dados disponíveis continuam acessíveis.</div>';
  }
  Promise.all(["catalog","fundamentals","technical_daily","technical_intraday"].map(group=>api(`/market-dashboard/groups/${group}/ensure`,{method:"POST"}))).catch(()=>{});
  try {
    await loadAnalysisCatalog(type);
    if(state.analysisLoadedType!==type){state.analysisLoadedType=type;state.currentCustomFilter=null;state.analysisPreset="default";if(["stock","fii"].includes(type))fillAnalysisForm(state.analysisCatalog[type]?.default?.configuration||{});else resetAdvancedFilters();markActiveAnalysis({presetId:"default"});}
  } catch(error){toast(`Configuração dos filtros: ${error.message}`,"error");}
  updateFilterAvailability();
  await loadAnalysisResults();
}

async function loadAnalysisResults() {
  const root = $("#analysis-table");
  root.innerHTML = loadingCards(6);
  const type = analysisType();
  try {
    let rows, warnings=[];
    if (state.currentCustomFilter && ["stock","fii"].includes(type)) {
      const payload=await api(`/screen/db/custom/${state.currentCustomFilter.id}?limit=${state.analysisLimit}`,{requestKey:"analysis"});rows=payload.rows||payload;warnings=payload?.meta?.warnings||[];
    } else if (type === "stock") rows = await api(`/screen/db/stocks/${state.analysisPreset}?limit=${state.analysisLimit}`, {requestKey:"analysis"});
    else if (type === "fii") rows = await api(`/screen/db/fiis/${state.analysisPreset}?limit=${state.analysisLimit}`, {requestKey:"analysis"});
    else {
      const all = await api("/screen/db/universe/other_b3?limit=1200", {requestKey:"analysis"});
      rows = all.filter(item => item.asset_type === type);
    }
    if (type === "stock") rows.sort((a,b)=>(Number(b.graham_upside_pct)||-Infinity)-(Number(a.graham_upside_pct)||-Infinity));
    else rows.sort((a,b)=>String(a.ticker).localeCompare(String(b.ticker)));
    rows = await enrichBacktestLeaders(rows);
    state.analysisRows = rows;
    renderAnalysisRows(rows);
    if(warnings.length)toast(warnings.join(" "),"warning");
  } catch (error) { if (error.name !== "AbortError") root.innerHTML = errorState(error, "analysis"); }
}

async function enrichBacktestLeaders(rows) {
  if (!state.session?.access?.can_view_backtests || !rows?.length) return rows || [];
  const tickers=rows.slice(0,100).map(row=>row.ticker).filter(Boolean).join(",");
  try {
    const payload=await api(`/backtests/leaderboard?per_asset=3&tickers=${encodeURIComponent(tickers)}`,{requestKey:"analysis-backtests"});
    return rows.map(row=>{
      const leaders=payload.items?.[row.ticker]||[];
      return {...row,backtest_leaders:leaders,best_signal:leaders[0]?.current_signal,best_strategy:leaders[0]?.strategy_name};
    });
  } catch(error) {
    if(error.name!=="AbortError") toast("Os sinais dos backtests serão exibidos assim que o catálogo estiver disponível.");
    return rows;
  }
}

function signalLabel(value) {
  return ({buy:"Comprar",sell:"Vender",neutral:"Neutro",compra:"Comprar",venda:"Vender"})[String(value||"").toLowerCase()]||"—";
}

function backtestLeadersCell(row) {
  const leaders=(row.backtest_leaders||[]).slice(0,3);
  if(!leaders.length)return '<span class="muted">Sem dados</span>';
  return `<div class="backtest-leader-stack">${leaders.map((leader,index)=>`<div><span class="leader-rank">${index+1}</span><span><strong>${esc(leader.strategy_name||leader.strategy_id||"Estratégia")}</strong><small>${nullable(leader.ranking_score)?"":`Pontuação ${number(leader.ranking_score,1)}`}</small></span><span class="pill signal-${esc(leader.current_signal||"neutral")}">${signalLabel(leader.current_signal)}</span></div>`).join("")}</div>`;
}

function renderIndicatorGuide() {
  $("#analysis-count").textContent="";
  $("#analysis-list-workspace").classList.add("hidden");
  const root=$("#analysis-guide");root.classList.remove("hidden");
  const indicators=[...filterDefinitions.fundamental.map(([,label,description])=>({label,description})),
    {label:"Preço justo de Graham",description:"Raiz quadrada de 22,5 × lucro por ação × valor patrimonial por ação. Exige lucro e patrimônio positivos."},
    {label:"Preço-teto de dividendos (Barsi/Bazin)",description:"Dividendos anuais por ação divididos pela taxa-alvo de 6%. Serve como referência educacional de renda."},
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
    {id:"best_signal",label:"3 melhores backtests",render:backtestLeadersCell},
  ];
  if(type==="stock") {
    const access=state.session?.access||{},canGraham=Boolean(access.can_use_graham_valuation||access.can_use_alb_analysis),canDividend=Boolean(access.can_use_dividend_ceiling||access.can_use_alb_analysis);
    return [common[0],
    {id:"sector",label:"Setor",render:r=>esc(r.sector_label||r.classification||"—")},
    {id:"company_size",label:"Porte",render:r=>esc(r.company_size_label||"—")},
    {id:"in_ibov",label:"IBOV",render:r=>nullable(r.in_ibov)?"—":r.in_ibov?"Sim":"Não"},common[1],
    {id:"pe",label:"P/L",render:r=>number(r.pe)},{id:"pbv",label:"P/VP",render:r=>number(r.pbv)},
    {id:"dy",label:"DY",render:r=>pct(r.dy??r.dividend_yield_pct)},{id:"roe",label:"ROE",render:r=>pct(r.roe??r.roe_pct)},
    {id:"graham",label:"Graham",render:r=>money(r.graham_number)},{id:"graham_upside",label:"Potencial Graham",render:r=>`<span class="${variationClass(r.graham_upside_pct)}">${pct(r.graham_upside_pct,true)}</span>`},
    {id:"barsi",label:"Preço-teto dividendos",render:r=>money(r.barsi_ceiling_price)},{id:"barsi_upside",label:"Potencial preço-teto",render:r=>pct(r.barsi_upside_pct,true)},
    {id:"alb",label:"Nota ALB",render:r=>number(r.alb_score,1)},
    {id:"trend_daily",label:"Tendência alta",render:r=>r.trend_daily==="up"?"Sim":r.trend_daily==="down"?"Não":"—"},
    {id:"rsi",label:"RSI 14",render:r=>number(r.rsi14_screen)},
    ...["s3","s2","s1","pp","r1","r2","r3"].map(id=>({id,label:id==="pp"?"Pivô":id.toUpperCase(),render:r=>money(r[id])})),
    {id:"volume_daily",label:"Volume/Média 9 diário",render:r=>nullable(r.volume_daily_ratio)?"—":`${number(Number(r.volume_daily_ratio)*100,0)}%`},
    {id:"volume_monthly",label:"Volume/Média 9 mensal",render:r=>nullable(r.volume_monthly_ratio)?"—":`${number(Number(r.volume_monthly_ratio)*100,0)}%`},
    common[2],
    ].filter(column=>!(["graham","graham_upside"].includes(column.id)&&!canGraham)&&!(["barsi","barsi_upside"].includes(column.id)&&!canDividend));
  }
  if(type==="fii") return [common[0],{id:"segment",label:"Segmento",render:r=>esc(r.segment_label||r.classification||"—")},common[1],{id:"pbv",label:"P/VP",render:r=>number(r.pbv)},{id:"dy",label:"DY",render:r=>pct(r.dy??r.dividend_yield_pct)},{id:"ffo",label:"FFO yield",render:r=>pct(r.ffo_yield??r.ffo_yield_pct)},{id:"vacancy",label:"Vacância",render:r=>pct(r.vacancy??r.vacancy_pct)},{id:"rsi",label:"RSI 14",render:r=>number(r.rsi14_screen)},common[2]];
  return [common[0],{id:"category",label:"Categoria",render:r=>esc(r.asset_type_label||r.classification||"—")},common[1],{id:"signal",label:"Sinal",render:r=>esc(r.signal_tv||"—")},{id:"rsi",label:"RSI 14",render:r=>number(r.rsi14_screen)},{id:"technical",label:"Nota técnica",render:r=>number(r.technical_score,1)},common[2]];
}

function visibleAnalysisColumns(type, columns) {
  const defaults={stock:["ticker","sector","price","pe","pbv","dy","roe","graham_upside","barsi","best_signal"],fii:["ticker","segment","price","pbv","dy","ffo","vacancy","best_signal"]};
  const saved=state.visibleColumns[type];
  const active=new Set(Array.isArray(saved)?saved:(defaults[type]||columns.map(column=>column.id)));
  return columns.filter(column=>column.always||active.has(column.id));
}

function renderAnalysisRows(rows) {
  $("#analysis-count").textContent = `${rows.length} ativo${rows.length===1?"":"s"}`;
  if (!rows.length) { $("#analysis-table").innerHTML='<div class="empty-state"><strong>Nenhum ativo passou pelos filtros</strong>Abra os ajustes para ampliar ou alterar os critérios.</div>'; return; }
  const type = analysisType();
  const allColumns=analysisColumns(type), columns=visibleAnalysisColumns(type,allColumns);
  const active=new Set(columns.map(column=>column.id));
  const picker=`<details class="column-picker"><summary>Colunas visíveis</summary><div>${allColumns.filter(column=>!column.always).map(column=>`<label class="check"><input type="checkbox" data-column-id="${column.id}" ${active.has(column.id)?"checked":""}> ${esc(column.label)}</label>`).join("")}</div></details>`;
  $("#analysis-table").innerHTML = `<div class="table-toolbar">${picker}<span>Clique em um ativo para abrir todos os dados.</span></div><div class="table-scroll"><table><thead><tr>${columns.map(c=>`<th>${esc(c.label)}</th>`).join("")}</tr></thead><tbody>${rows.map(r=>`<tr data-ticker="${esc(r.ticker)}">${columns.map(c=>`<td>${c.render(r)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

async function applyAdvancedFilters(showToast=true) {
  const request=analysisRequestFromForm();
  if(!state.currentCustomFilter){const label=state.analysisCatalog[analysisType()]?.[state.analysisPreset]?.name||"Análise";$("#active-analysis-summary").textContent=`${label} • ajustes temporários`;}
  $("#analysis-table").innerHTML=loadingCards(6);
  try {
    const payload=await api("/screen/advanced",{method:"POST",requestKey:"analysis",body:JSON.stringify(request)});
    const rows=await enrichBacktestLeaders(payload.rows||payload);
    state.analysisRows=rows; renderAnalysisRows(rows);
    const warnings=payload?.meta?.warnings||[];
    if(warnings.length) toast(warnings.join(" "),"warning");
    else if(showToast) toast(`${rows.length} ativo(s) após os ajustes.`,"success");
  } catch(error) { if(error.name!=="AbortError") $("#analysis-table").innerHTML=errorState(error,"analysis"); }
}

async function openAsset(ticker) {
  const dialog=$("#asset-dialog"), content=$("#asset-dialog-content");
  content.innerHTML=loadingCards(4); dialog.showModal();
  try {
    const data=await api(`/assets/${encodeURIComponent(ticker)}`);
    const a=data.asset||{}, f=data.fundamentals||{}, t=data.technical||{}, d=data.derived||{}, tech=data.technical_analysis||{}, scores=data.scores||{}, leaders=data.backtests||[];
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
      <div class="metric-grid asset-summary">${metricCard("Preço",money(f.price??t.close))}${metricCard("Potencial Graham",pct(d.graham_upside_pct,true),`Preço justo ${money(d.graham_number)}`)}${metricCard("Preço-teto dividendos",money(d.barsi_ceiling_price),`Potencial ${pct(d.barsi_upside_pct,true)}`)}${metricCard("Sinal do melhor backtest",signalLabel(leaders[0]?.current_signal),leaders[0]?.strategy_name||"")}</div>
      <div class="asset-detail-grid">
        ${sectionCard("Indicadores fundamentalistas",fundamentals.length?`<div class="detail-list">${fundamentals.map(([label,value])=>`<div><span>${esc(label)}</span><strong>${number(value,2)}</strong></div>`).join("")}</div>`:'<div class="empty-state compact">Sem dados fundamentalistas recentes.</div>')}
        ${sectionCard("Análise técnica",`<div class="metric-grid mini">${metricCard("RSI 14",number(tech.rsi14??t.rsi14))}${metricCard("Tendência diária",tech.trend_daily==="up"?"Alta":tech.trend_daily==="down"?"Baixa":"—")}${metricCard("Volume diário / média 9",nullable(tech.volume_daily_ratio)?"—":pct(Number(tech.volume_daily_ratio)*100))}${metricCard("Volume mensal / média 9",nullable(tech.volume_monthly_ratio)?"—":pct(Number(tech.volume_monthly_ratio)*100))}</div><div class="detail-list pivot-list">${pivotRows.map(row=>`<div><span>${esc(row.label)}</span><strong>${money(row.value)}</strong></div>`).join("")}</div><small class="formula-note">Pivôs calculados pela máxima, mínima e fechamento do último período concluído.</small>`)}
        ${sectionCard("Notas do ativo",`<div class="detail-list">${Object.entries({"Qualidade":scores.quality_score,"Valor":scores.value_score,"Crescimento":scores.growth_score,"Técnica":scores.technical_score,"Risco":scores.risk_score,"Liquidez":scores.liquidity_score,"ALB":scores.alb_score,"Qualidade dos dados":scores.data_quality_score}).map(([label,value])=>`<div><span>${esc(label)}</span><strong>${number(value,1)}</strong></div>`).join("")}</div>`)}
        ${sectionCard("3 melhores backtests e sinal atual",leaderTable,"Ordenados pela consistência dos resultados oficiais")}
      </div>`;
  } catch(error) { content.innerHTML=errorState(error); }
}

async function loadPortfolios() {
  const root=$("#portfolio-tab-content"); root.innerHTML=loadingCards(5);
  try {
    state.portfolios=await api("/portfolios",{requestKey:"portfolios"});
    if (!state.portfolios.length) { root.innerHTML='<div class="data-card empty-state"><strong>Você ainda não criou uma carteira</strong>A criação estará disponível aqui para contas com permissão de edição.</div>'; return; }
    if (!state.portfolioId || !state.portfolios.some(p=>p.id===state.portfolioId)) state.portfolioId=state.portfolios[0].id;
    $("#portfolio-selector-wrap").innerHTML=`<select id="portfolio-selector" class="button secondary">${state.portfolios.map(p=>`<option value="${esc(p.id)}" ${p.id===state.portfolioId?"selected":""}>${esc(p.name)}</option>`).join("")}</select>`;
    await renderPortfolioTab();
  } catch(error) { root.innerHTML=errorState(error,"portfolio"); }
}

function allocationDonut(items) {
  const rows=(items||[]).filter(item=>Number(item.value)>0);
  if(!rows.length)return '<div class="empty-state"><strong>Composição ainda vazia</strong>Cadastre posições ou investimentos para visualizar a distribuição.</div>';
  const colors=["#0b5d4b","#c79b3b","#4f7cac","#9b5de5","#e07a5f","#2a9d8f","#6c757d","#f4a261"];
  let cursor=0;const stops=rows.map((item,index)=>{const start=cursor;cursor+=Number(item.weight_pct||0);return `${colors[index%colors.length]} ${start}% ${cursor}%`;});
  return `<div class="allocation-visual"><div class="allocation-donut" style="background:conic-gradient(${stops.join(",")})"><span>${money(rows.reduce((sum,item)=>sum+Number(item.value||0),0))}</span></div><div class="allocation-legend">${rows.map((item,index)=>`<div><i class="legend-dot" style="background:${colors[index%colors.length]}"></i><span>${esc(item.label)}</span><strong>${pct(item.weight_pct)}</strong></div>`).join("")}</div></div>`;
}

async function renderPortfolioTab() {
  const root=$("#portfolio-tab-content"), tab=state.tabs.portfolio;
  root.innerHTML=loadingCards(5);
  try {
    if (tab==="positions") {
      const data=await api(`/portfolios/${state.portfolioId}`);
      const positions=data.positions||data.items||[];
      const summary=data.summary||{};
      const cards=`<div class="metric-grid summary-grid">${metricCard("Patrimônio",money(data.consolidated_summary?.total_value??data.consolidated_summary?.known_total_value??summary.market_value))}${metricCard("Posições",String(positions.length))}${metricCard("Outros investimentos",money(data.custom_summary?.current_value||0))}${metricCard("Caixa",money(data.portfolio?.cash_balance))}</div>`;
      const priceDates=positions.map(item=>item.current_price_as_of).filter(Boolean).sort();
      const priceUpdate=data.price_update||{};
      const quoteUpdate=`<div class="update-panel"><div class="update-summary"><span><strong>Cotações da carteira</strong><small>${priceDates.length?`Mais recente: ${dateTime(priceDates[priceDates.length-1])}`:"Nenhuma cotação disponível"} • ${esc(priceUpdate.source||"Yahoo Finance")}${priceUpdate.next_update_at?` • próxima ${dateTime(priceUpdate.next_update_at)}`:""}</small></span><span><span class="pill ${["failed","stale","partial"].includes(priceUpdate.status)?"warning":""}">${esc(updateStatusLabels[priceUpdate.status]||priceUpdate.status||"Sob demanda")}</span><button class="button secondary compact" data-portfolio-prices-refresh="${esc(state.portfolioId)}">Atualizar agora</button></span></div></div>`;
      const positionForm=state.session.access.can_write_portfolio?`<details class="data-card"><summary><strong>Adicionar ou atualizar posição</strong></summary><form id="portfolio-position-form" class="filter-grid" style="margin-top:16px"><div class="field"><label>Código do ativo</label><input name="ticker" required maxlength="24" placeholder="PETR4"></div><div class="field"><label>Tipo</label><select name="asset_type"><option value="stock">Ação</option><option value="fii">FII</option><option value="etf">ETF</option><option value="bdr">BDR</option><option value="future">Futuro</option><option value="crypto">Cripto</option><option value="other">Outro</option></select></div><div class="field"><label>Quantidade total</label><input name="quantity" type="number" min="0" step="0.000001" required></div><div class="field"><label>Preço médio</label><input name="average_price" type="number" min="0" step="0.000001"></div><div class="field"><label>Meta na carteira (%)</label><input name="target_weight_pct" type="number" min="0" max="100" step="0.01" value="0"></div><div class="field"><label>Categoria opcional</label><input name="classification_override" maxlength="120" placeholder="Ex.: Renda variável"></div><div class="field"><label>Setor</label><input name="sector_override" maxlength="120" placeholder="Ex.: Financeiro"></div><div class="field"><label>Segmento</label><input name="segment_override" maxlength="120" placeholder="Ex.: Bancos"></div><button class="button primary wide-action" type="submit">Salvar posição</button></form></details>`:"";
      const positionTable=marketTable(positions,[{label:"Ativo",render:r=>`<span class="ticker-cell">${esc(r.ticker)}</span>`},{label:"Quantidade",render:r=>Number(r.quantity||0).toLocaleString("pt-BR",{maximumFractionDigits:6})},{label:"Preço médio",render:r=>money(r.average_price)},{label:"Preço atual",render:r=>`${money(r.current_price)}${r.current_price_as_of?`<br><small>${dateTime(r.current_price_as_of)} • ${esc(r.price_source||"")}</small>`:""}`},{label:"Valor",render:r=>money(r.market_value??(Number(r.quantity)*Number(r.current_price)))},{label:"Peso / meta",render:r=>`${pct(r.current_weight_pct)}<br><small>meta ${pct(r.effective_target_weight_pct??r.target_weight_pct)}</small>`},{label:"Rebalanceamento",render:r=>nullable(r.rebalance_value)?"—":`<strong class="${variationClass(r.rebalance_value)}">${Number(r.rebalance_value)>=0?"Comprar":"Reduzir"} ${money(Math.abs(Number(r.rebalance_value)))}</strong>${nullable(r.rebalance_quantity)?"":`<br><small>aprox. ${number(Math.abs(Number(r.rebalance_quantity)),0)} unidade(s)</small>`}`},{label:"Setor / segmento",render:r=>`${esc(r.sector||r.classification||"—")}<br><small>${esc(r.segment||"—")}</small>`},{label:"",render:r=>state.session.access.can_write_portfolio?`<button class="button ghost compact danger" data-delete-position="${esc(r.ticker)}">Remover</button>`:""}]);
      root.innerHTML=quoteUpdate+cards+sectionCard("Posições",positionTable,"Sugestão matemática baseada nas metas informadas; não constitui recomendação de investimento.")+positionForm;
    } else if (tab==="allocation") {
      const [data,catalog]=await Promise.all([api(`/portfolios/${state.portfolioId}`),api(`/portfolios/${state.portfolioId}/custom-investments/catalog`)]);
      const rows=data.custom_investments||[],summary=data.consolidated_summary||{},today=new Date().toISOString().slice(0,10);
      const form=state.session.access.can_write_portfolio?`<details class="data-card" ${rows.length?"":"open"}><summary><strong>Adicionar investimento sem ticker</strong></summary><form id="custom-investment-form" class="filter-grid" style="margin-top:16px"><div class="field"><label>Tipo</label><select name="category" required>${catalog.map(item=>`<option value="${esc(item.id)}">${esc(item.label)}</option>`).join("")}</select></div><div class="field"><label>Nome do investimento</label><input name="name" required maxlength="200" placeholder="Ex.: CDB Banco X 110% CDI"></div><div class="field"><label>Instituição</label><input name="institution" maxlength="160" placeholder="Banco ou corretora"></div><div class="field"><label>Setor</label><input name="sector" maxlength="120" placeholder="Ex.: Renda fixa"></div><div class="field"><label>Segmento</label><input name="segment" maxlength="120" placeholder="Ex.: Bancário pós-fixado"></div><div class="field"><label>Data da aplicação</label><input type="date" name="application_date" required value="${today}"></div><div class="field"><label>Vencimento (opcional)</label><input type="date" name="maturity_date"></div><div class="field"><label>Valor aplicado</label><input type="number" name="invested_value" min="0.01" step="0.01" required></div><div class="field"><label>Valor atual</label><input type="number" name="current_value" min="0" step="0.01" required></div><div class="field"><label>Data do valor atual</label><input type="date" name="current_value_as_of" required value="${today}"></div><div class="field"><label>Indexador / referência</label><input name="benchmark" maxlength="80" placeholder="Ex.: 110% do CDI"></div><div class="field"><label>Liquidez</label><input name="liquidity" maxlength="120" placeholder="Ex.: no vencimento ou D+1"></div><div class="field wide-action"><label>Observações</label><textarea name="notes" rows="2"></textarea></div><button class="button primary wide-action" type="submit">Salvar investimento</button></form></details>`:"";
      root.innerHTML=`<div class="metric-grid summary-grid">${metricCard("Patrimônio conhecido",money(summary.known_total_value))}${metricCard("Investimentos sem ticker",money(data.custom_summary?.current_value||0),`${rows.length} cadastro(s)`)}${metricCard("Valor aplicado",money(data.custom_summary?.invested_value||0))}${metricCard("Variação",pct(data.custom_summary?.variation_pct,true))}</div>${sectionCard("Composição consolidada",allocationDonut(data.consolidated_allocation||[]),summary.allocation_complete?"Valores de mercado e valores informados manualmente":"Composição parcial: existe posição sem cotação")}${sectionCard("Renda fixa, fundos e outros",marketTable(rows,[{label:"Investimento",render:r=>`<strong>${esc(r.name)}</strong><br><small>${esc(r.category_label)}</small>`},{label:"Setor / segmento",render:r=>`${esc(r.sector||"—")}<br><small>${esc(r.segment||"—")}</small>`},{label:"Instituição",render:r=>esc(r.institution||"—")},{label:"Aplicação",render:r=>dateOnly(r.application_date)},{label:"Vencimento",render:r=>dateOnly(r.maturity_date)},{label:"Aplicado",render:r=>money(r.invested_value)},{label:"Atual",render:r=>`${money(r.current_value)}<br><small>${dateOnly(r.current_value_as_of)}</small>`},{label:"Variação",render:r=>pct(r.variation_pct,true),className:r=>variationClass(r.variation_pct)},{label:"",render:r=>state.session.access.can_write_portfolio?`<span class="row-actions"><button class="button ghost compact" data-update-custom-investment="${esc(r.id)}" data-current-value="${esc(r.current_value)}">Atualizar valor</button><button class="button ghost compact danger" data-delete-custom-investment="${esc(r.id)}">Arquivar</button></span>`:""}]),"O histórico preserva cada valor informado por data")}${form}`;
    } else if (tab==="news") {
      const cache=await api(`/insights/news/cache/portfolios/${state.portfolioId}`);
      const data=cache.data||{};
      const groups=data.assets||data.items||[];
      const newsUpdate=`<div class="update-panel"><div class="update-summary"><span><strong>Notícias da carteira</strong><small>${cache.finished_at?`Atualizadas em ${dateTime(cache.finished_at)}`:"Primeira atualização pendente"}</small></span><button class="button secondary compact" data-portfolio-news-refresh="${esc(state.portfolioId)}" ${["queued","running"].includes(cache.status)?"disabled":""}>Atualizar agora</button></div></div>`;
      root.innerHTML=newsUpdate+sectionCard("Notícias da carteira",groups.length?groups.map(group=>`<div class="card-section"><div class="card-heading"><h3>${esc(group.ticker||group.label||"Ativo")}</h3></div><div class="headline-list">${(group.items||group.news||[]).map((item,i)=>`<a class="headline" href="${esc(item.url)}" target="_blank" rel="noopener"><span class="headline-number">${i+1}</span><span><strong>${esc(item.title)}</strong><small>${esc(item.source||"")}</small></span></a>`).join("")}</div></div>`).join(""):'<div class="empty-state"><strong>Notícias sendo preparadas</strong>A primeira consulta do dia é feita automaticamente em segundo plano.</div>',"Até 3 notícias relevantes por ativo");
      api("/insights/news/refresh-daily",{method:"POST"}).catch(()=>{});
    } else {
      await renderAlerts(root);
    }
  } catch(error) { root.innerHTML=errorState(error); }
}

async function renderAlerts(root) {
  const access=state.session.access;
  if (!access.can_use_price_alerts) { root.innerHTML='<div class="data-card empty-state"><strong>Alertas não liberados para esta conta</strong>O administrador pode conceder um limite de 1, 3, 5 ou 10 ativos.</div>'; return; }
  const data=await api("/alerts");
  const active=data.active||data.alerts||[];
  root.innerHTML=`<div class="notice info" style="margin-bottom:14px">B3: monitoramento em dias úteis, das 10h às 18h, a cada 5 minutos. Outros mercados: a cada 10 minutos, com candles de 5 minutos.</div>${sectionCard("Alertas ativos",marketTable(active,[{label:"Ativo",render:r=>`<strong>${esc(r.symbol)}</strong>`},{label:"Acima de",render:r=>money(r.price_above)},{label:"Abaixo de",render:r=>money(r.price_below)},{label:"Variação positiva",render:r=>pct(r.change_positive_pct)},{label:"Variação negativa",render:r=>pct(r.change_negative_pct)},{label:"Última verificação",render:r=>r.last_checked_at?dateTime(r.last_checked_at):"—"},{label:"Status",render:r=>`<span class="pill">${esc(r.status||"ativo")}</span>`}]),`Limite autorizado: ${data.limit??access.alert_asset_limit} ativos`)}`;
  $("#notification-count").textContent=active.length;
  $("#notification-count").classList.toggle("hidden",!active.length);
}

async function refreshPortfolioNews(portfolioId) {
  try {
    const result=await api(`/insights/news/cache/portfolios/${encodeURIComponent(portfolioId)}/refresh`,{method:"POST"});
    toast(result.scheduled===false?"As notícias já estão sendo atualizadas.":"Atualização das notícias solicitada.",result.scheduled===false?"info":"success");
    setTimeout(()=>renderPortfolioTab(),2500);
  } catch(error) { toast(error.message,"error"); }
}

async function saveCustomInvestment(form) {
  const values=Object.fromEntries(new FormData(form));
  for(const key of ["invested_value","current_value"])values[key]=Number(values[key]);
  for(const key of ["maturity_date","institution","sector","segment","benchmark","liquidity","notes"])if(!values[key])values[key]=null;
  try{await api(`/portfolios/${encodeURIComponent(state.portfolioId)}/custom-investments`,{method:"POST",body:JSON.stringify(values)});toast("Investimento salvo.","success");renderPortfolioTab();}
  catch(error){toast(error.message,"error");}
}

async function savePortfolioPosition(form){
  const values=Object.fromEntries(new FormData(form)),ticker=String(values.ticker||"").trim().toUpperCase();
  const payload={asset_type:values.asset_type,stage:"position",quantity:Number(values.quantity||0),average_price:values.average_price?Number(values.average_price):null,target_weight_pct:Number(values.target_weight_pct||0),classification_override:values.classification_override||null,sector_override:values.sector_override||null,segment_override:values.segment_override||null,notes:null};
  try{await api(`/portfolios/${encodeURIComponent(state.portfolioId)}/positions/${encodeURIComponent(ticker)}`,{method:"PUT",body:JSON.stringify(payload)});toast("Posição salva e alocação recalculada.","success");renderPortfolioTab();}
  catch(error){toast(error.message,"error");}
}

async function deletePortfolioPosition(button){
  if(!window.confirm(`Remover ${button.dataset.deletePosition} desta carteira?`))return;
  try{await api(`/portfolios/${encodeURIComponent(state.portfolioId)}/positions/${encodeURIComponent(button.dataset.deletePosition)}`,{method:"DELETE"});toast("Posição removida.","success");renderPortfolioTab();}
  catch(error){toast(error.message,"error");}
}

async function updateCustomInvestmentValue(button) {
  const dialog=$("#custom-value-dialog"),form=$("#custom-value-form");
  form.elements.investment_id.value=button.dataset.updateCustomInvestment;
  form.elements.current_value.value=button.dataset.currentValue||"";
  form.elements.current_value_as_of.value=new Date().toISOString().slice(0,10);
  dialog.showModal();
}

async function saveCustomInvestmentValue(form){
  const values=Object.fromEntries(new FormData(form)),value=Number(values.current_value);
  if(!Number.isFinite(value)||value<0){toast("Informe um valor válido.","error");return;}
  try{await api(`/portfolios/${encodeURIComponent(state.portfolioId)}/custom-investments/${encodeURIComponent(values.investment_id)}`,{method:"PATCH",body:JSON.stringify({current_value:value,current_value_as_of:values.current_value_as_of})});$("#custom-value-dialog").close();toast("Valor e histórico atualizados.","success");renderPortfolioTab();}
  catch(error){toast(error.message,"error");}
}

async function deleteCustomInvestment(button) {
  if(!window.confirm("Arquivar este investimento? O histórico será preservado."))return;
  try{await api(`/portfolios/${encodeURIComponent(state.portfolioId)}/custom-investments/${encodeURIComponent(button.dataset.deleteCustomInvestment)}`,{method:"DELETE"});toast("Investimento arquivado.","success");renderPortfolioTab();}
  catch(error){toast(error.message,"error");}
}

async function refreshPortfolioPrices(portfolioId) {
  try {
    const result=await api(`/portfolios/${encodeURIComponent(portfolioId)}/refresh-prices`,{method:"POST"});
    toast(result.scheduled?"Atualização das cotações solicitada.":"As cotações foram solicitadas há menos de 5 minutos.",result.scheduled?"success":"info");
    setTimeout(()=>renderPortfolioTab(),3000);
  } catch(error) { toast(error.message,"error"); }
}

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
    const data=await api(`/backtests/study/${encodeURIComponent(strategyId)}/configurations`);
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
    <div class="dialog-actions">${canRetry?`<button class="button primary" data-retry-official-job="${esc(job.id)}">Repetir somente os ativos pendentes</button>`:""}<a class="button secondary" href="https://github.com/andrelbr22/invest/actions/workflows/backtests-semanais.yml" target="_blank" rel="noopener">Ver execuções no GitHub</a></div>`;
  dialog.showModal();
}

async function retryOfficialBacktestJob(jobId, button) {
  if(button){button.disabled=true;button.textContent="Solicitando nova execução…";}
  try {
    const result=await api(`/backtests/batch/jobs/${encodeURIComponent(jobId)}/retry`,{method:"POST",body:"{}"});
    $("#asset-dialog").close();
    toast(`${(result.retry_tickers||result.tickers||[]).length} ativo(s) enviado(s) para nova execução no ambiente de teste.`,"success");
    await loadBacktests();
  } catch(error) {
    toast(error.message,"error");
    if(button){button.disabled=false;button.textContent="Repetir somente os ativos pendentes";}
  }
}

async function loadBacktests() {
  const root=$("#backtests-tab-content"),tab=state.tabs.backtests; root.innerHTML=loadingCards(6);
  try {
    if(tab==="history") {
      const rows=await api("/backtests/runs?limit=100",{requestKey:"backtests"});
      rows.sort((a,b)=>new Date(b.created_at)-new Date(a.created_at));
      root.innerHTML=recordedUpdatePanel("Histórico de backtests",rows[0]?.created_at,"Atualizado sempre que um teste é concluído")+sectionCard("Últimos 100 backtests",marketTable(rows,[{label:"Data e hora",render:r=>dateTime(r.created_at)},{label:"Ativo",render:r=>`<span class="ticker-cell">${esc(r.ticker||"—")}</span>`},{label:"Estratégia",render:r=>esc(r.strategy_name||r.strategy_id||"—")},{label:"Retorno",render:r=>pct(r.metrics?.total_return_pct??r.return_pct,true),className:r=>variationClass(r.metrics?.total_return_pct??r.return_pct)},{label:"Status",render:r=>`<span class="pill">${esc(r.status||"—")}</span>`}]));
    } else if(tab==="study") {
      const data=await api("/backtests/study?limit=5"); const rows=data.items||data.ranking||[];
      root.innerHTML=recordedUpdatePanel("Estudos oficiais",data.generated_at||data.updated_at,"Recalculado a partir das rodadas oficiais")+sectionCard("Estratégias mais consistentes",marketTable(rows,[{label:"Posição",render:(r)=>`<strong>${esc(r.position||r.rank||"—")}</strong>`},{label:"Estratégia",render:r=>`<button class="table-link" data-study-strategy="${esc(r.strategy_id)}">${esc(r.strategy_name||r.name||r.strategy_id)}</button><small class="block-hint">Abrir configurações</small>`},{label:"Pontuação",render:r=>number(r.study_score??r.score??r.points,1)},{label:"Presença no top 3",render:r=>number(r.top_three_count??r.top3_count,0)},{label:"1º lugares",render:r=>number(r.first_places,0)},{label:"Cobertura",render:r=>pct(r.coverage_pct)}]),"Ranking ponderado por recorrência no top 3, posição, qualidade e cobertura. Clique na estratégia para ver todas as variáveis.");
    } else if(tab==="official") {
      const rows=await api("/backtests/batch/jobs?limit=30");
      state.officialBacktestJobs=new Map(rows.map(row=>[String(row.id),row]));
      const officialUpdated=rows.map(row=>row.last_update_at||row.finished_at||row.created_at).filter(Boolean).sort().pop();
      root.innerHTML=recordedUpdatePanel("Backtests oficiais",officialUpdated,"Rodada automática aos sábados às 00h01, horário de Brasília")+sectionCard("Rodadas oficiais",marketTable(rows,[{label:"Criado em",render:r=>dateTime(r.created_at)},{label:"Identificador",render:r=>`<button class="table-link" data-official-job="${esc(r.id)}">${esc(String(r.id).slice(0,8))}…</button>`},{label:"Ativos",render:r=>number((r.requested_tickers||r.tickers||[]).length,0)},{label:"Progresso",render:r=>`${number(r.processed_assets||0,0)} / ${number(r.total_assets||(r.requested_tickers||r.tickers||[]).length,0)}`},{label:"Partes",render:r=>number(r.received_chunks||0,0)},{label:"Status",render:r=>`<span class="pill ${r.status==="failed"?"danger":""}">${esc(officialStatusLabels[r.status]||r.status)}</span>`},{label:"",render:r=>`<button class="button ghost compact" data-official-job="${esc(r.id)}">Detalhes</button>`}]),"A entrega de cada ativo é fracionada em partes pequenas. Uma interrupção pode ser retomada sem duplicar resultados.");
    } else {
      const [catalog,recentJobs]=await Promise.all([api("/backtests/strategies"),api("/backtests/jobs?limit=5")]);
      const access=state.session.access;
      root.innerHTML=sectionCard("Comparar estratégias",`<form id="backtest-form" class="filter-grid backtest-form">
        <div class="field wide-action"><label>Ativos — separe por vírgula ou espaço</label><textarea name="tickers" required rows="3" placeholder="PETR4, VALE3, BBAS3"></textarea><small>Limite autorizado por análise: ${number(access.backtest_asset_limit||0,0)} ativo(s).</small></div>
        <div class="field"><label>Estratégias (até ${number(access.backtest_strategy_limit||0,0)})</label><select name="strategy_ids" multiple size="7" required>${(catalog.strategies||[]).map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")}</select><small>Use Ctrl para selecionar mais de uma.</small></div>
        <div class="field"><label>Forma de análise</label><select name="execution_mode"><option value="compare">Comparar separadamente</option><option value="combined">Combinar estratégias</option></select><small>A combinação produz uma única posição.</small></div>
        <div class="field" data-combination-rule hidden><label>Regra da combinação</label><select name="combination_rule"><option value="all">Todas confirmam (E)</option><option value="any">Qualquer uma confirma (OU)</option><option value="majority">Maioria confirma</option></select></div>
        <div class="field"><label>Tipo de ativo</label><select name="asset_type"><option value="stock">Ações</option><option value="fii">FIIs</option><option value="etf">ETFs</option><option value="bdr">BDRs</option></select></div>
        <div class="field"><label>Período</label><select name="period">${Object.entries(catalog.periods||{}).map(([id,label])=>`<option value="${esc(id)}" ${id==="5y"?"selected":""}>${esc(label)}</option>`).join("")}<option value="custom">Personalizado</option></select></div>
        <div class="field" data-backtest-custom-date hidden><label>De</label><input type="date" name="start"></div><div class="field" data-backtest-custom-date hidden><label>Até</label><input type="date" name="end"></div>
        <details class="wide-action"><summary>Filtros técnicos de entrada e saída</summary><p class="block-hint">Cada filtro é aplicado sobre o sinal de todas as estratégias selecionadas, sem antecipar dados futuros.</p><div class="filter-grid compact-grid">
          ${["daily","weekly","monthly"].map((prefix,index)=>`<fieldset class="data-card"><legend>${["Tendência diária","Tendência semanal","Tendência mensal"][index]}</legend><label class="check"><input type="checkbox" name="${prefix}_enabled"> Ativar</label><div class="field"><label>Média móvel</label><select name="${prefix}_ma"><option value="sma:8">MMS 8</option><option value="ema:9">MME 9</option><option value="sma:21" selected>MMS 21</option><option value="sma:50">MMS 50</option><option value="sma:200">MMS 200</option></select></div><div class="field"><label>Direção</label><select name="${prefix}_direction"><option value="up">Alta</option><option value="down">Baixa</option></select></div><div class="field"><label>Condição</label><select name="${prefix}_mode"><option value="price_above">Preço acima/abaixo da média</option><option value="sma_rising">Inclinação da média</option><option value="price_above_and_sma_rising">Preço e inclinação confirmam</option><option value="price_above_or_sma_rising">Preço ou inclinação confirma</option></select></div></fieldset>`).join("")}
          <div class="field"><label>Combinação das tendências</label><select name="trend_combination"><option value="all">Todas confirmam</option><option value="majority">Maioria confirma</option><option value="any">Qualquer uma confirma</option></select></div>
          <div class="field"><label>ADX mínimo</label><input type="number" name="adx_min" min="0" max="100" step="0.1" placeholder="Ex.: 20"></div><div class="field"><label>Volume / média mínimo</label><input type="number" name="volume_ratio_min" min="0.1" max="10" step="0.1" placeholder="Ex.: 1,2"></div>
          <div class="field"><label>RSI mínimo</label><input type="number" name="rsi_min" min="0" max="100" step="0.1"></div><div class="field"><label>RSI máximo</label><input type="number" name="rsi_max" min="0" max="100" step="0.1"></div>
          <div class="field"><label>ATR mínimo (%)</label><input type="number" name="atr_pct_min" min="0" max="100" step="0.1"></div><div class="field"><label>ATR máximo (%)</label><input type="number" name="atr_pct_max" min="0" max="100" step="0.1"></div>
          <label class="check wide-action"><input type="checkbox" name="exit_on_filter_failure"> Encerrar a posição quando os filtros deixarem de ser atendidos</label>
        </div></details>
        <details class="wide-action"><summary>Premissas financeiras</summary><div class="filter-grid compact-grid"><div class="field"><label>Capital inicial</label><input type="number" name="initial_capital" min="1" step="100" value="10000"></div><div class="field"><label>Taxa (%)</label><input type="number" name="fee_pct" min="0" max="5" step="0.01" value="0.03"></div><div class="field"><label>Slippage (%)</label><input type="number" name="slippage_pct" min="0" max="5" step="0.01" value="0.05"></div><div class="field"><label>Taxa livre de risco (% a.a.)</label><input type="number" name="risk_free_rate_pct" min="-20" max="100" step="0.1" value="0"></div><label class="check"><input type="checkbox" name="apply_cash_yield"> Remunerar o caixa</label><div class="field"><label>Rendimento do caixa (% a.a.)</label><input type="number" name="cash_yield_rate_pct" min="-99" max="100" step="0.1" value="0"></div></div></details>
        <button class="button primary wide-action" type="submit">Enviar análise para processamento</button>
      </form><div id="backtest-result" style="margin-top:16px"></div>`+((recentJobs||[]).length?`<div style="margin-top:18px">${sectionCard("Execuções recentes",marketTable(recentJobs,[{label:"Solicitado",render:r=>dateTime(r.created_at)},{label:"Progresso",render:r=>`${number(r.progress_current||0,0)} / ${number(r.progress_total||0,0)}`},{label:"Status",render:r=>`<span class="pill">${esc(r.status)}</span>`}]))}</div>`:""),`Cada envio conta como uma análise diária. Limite: ${access.backtest_daily_limit||0} por dia; até ${access.backtest_strategy_limit||0} estratégia(s); intervalo mínimo de ${access.backtest_cooldown_seconds||60} segundos. A tela permanece livre durante o processamento.`);
    }
  } catch(error) { root.innerHTML=errorState(error,"backtests"); }
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
    const filters={daily_trend:trend("daily"),weekly_trend:trend("weekly"),monthly_trend:trend("monthly"),trend_combination:values.trend_combination||"all",adx_min:numberOrNull("adx_min"),volume_ratio_min:numberOrNull("volume_ratio_min"),rsi_min:numberOrNull("rsi_min"),rsi_max:numberOrNull("rsi_max"),atr_pct_min:numberOrNull("atr_pct_min"),atr_pct_max:numberOrNull("atr_pct_max"),exit_on_filter_failure:Boolean(form.querySelector('[name="exit_on_filter_failure"]')?.checked)};
    const payload={tickers,strategy_ids,execution_mode:values.execution_mode,combination_rule:values.combination_rule,asset_type:values.asset_type,period:values.period,start:values.period==="custom"&&values.start?`${values.start}T00:00:00Z`:null,end:values.period==="custom"&&values.end?`${values.end}T23:59:59Z`:null,initial_capital:Number(values.initial_capital||10000),fee_pct:Number(values.fee_pct||0),slippage_pct:Number(values.slippage_pct||0),risk_free_rate_pct:Number(values.risk_free_rate_pct||0),apply_cash_yield:form.querySelector('[name="apply_cash_yield"]')?.checked||false,cash_yield_rate_pct:Number(values.cash_yield_rate_pct||0),filters};
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

function financeCategoryBars(rows,total) {
  if(!(rows||[]).length)return '<div class="empty-state compact"><strong>Nenhuma despesa neste mês</strong>Os grupos aparecerão à medida que você fizer lançamentos.</div>';
  const maximum=Math.max(...rows.map(row=>Number(row.value||0)),1);
  return `<div class="finance-bars">${rows.map(row=>`<div class="finance-bar-row"><span>${esc(row.category)}</span><div><i style="width:${Math.max(2,Number(row.value||0)/maximum*100)}%"></i></div><strong>${money(row.value)}</strong></div>`).join("")}</div><small>Total previsto e realizado: ${money(total)}</small>`;
}

function financeBudgetTable(rows) {
  return marketTable(rows||[],[
    {label:"Categoria",render:r=>`<strong>${esc(r.category)}</strong>`},
    {label:"Limite",render:r=>money(r.limit_value)},
    {label:"Usado",render:r=>money(r.used_value)},
    {label:"Consumo",render:r=>`<span class="pill ${Number(r.used_pct)>100?"danger":""}">${pct(r.used_pct)}</span>`},
  ]);
}

function financeTransactionTable(rows,canWrite) {
  const statusLabels={planned:"Previsto",paid:"Pago",received:"Recebido",overdue:"Atrasado"};
  return marketTable(rows||[],[
    {label:"Data",render:r=>dateOnly(r.transaction_date)},
    {label:"Descrição",render:r=>`<strong>${esc(r.description)}</strong><br><small>${esc(r.category)}${r.institution?` • ${esc(r.institution)}`:""}</small>`},
    {label:"Tipo",render:r=>r.kind==="income"?"Receita":"Despesa"},
    {label:"Valor",render:r=>money(r.amount),className:r=>r.kind==="income"?"positive":"negative"},
    {label:"Status",render:r=>`<span class="pill ${r.status==="overdue"?"danger":""}">${esc(statusLabels[r.status]||r.status)}</span>`},
    {label:"",render:r=>canWrite?`<span class="row-actions">${["paid","received"].includes(r.status)?"":`<button class="button ghost compact" data-set-finance-status="${esc(r.id)}" data-finance-kind="${esc(r.kind)}">${r.kind==="income"?"Marcar recebido":"Marcar pago"}</button>`}<button class="button ghost compact danger" data-delete-finance="${esc(r.id)}">Arquivar</button></span>`:""},
  ]);
}

async function loadFinances() {
  const root=$("#finances-tab-content"),monthInput=$("#finance-month");
  if(monthInput&&!monthInput.value)monthInput.value=state.financeMonth;
  root.innerHTML=loadingCards(5);
  try {
    const [data,catalog]=await Promise.all([
      api(`/finances/summary?month=${encodeURIComponent(state.financeMonth)}`,{requestKey:"finances"}),
      api("/finances/catalog"),
    ]);
    const access=state.session.access,tab=state.tabs.finances,transactions=data.transactions||[];
    if(tab==="monthly"){
      const expenseTotal=(data.expense_by_category||[]).reduce((sum,row)=>sum+Number(row.value||0),0);
      root.innerHTML=`<div class="metric-grid summary-grid">${metricCard("Receitas recebidas",money(data.realized?.income),"Realizado")}${metricCard("Despesas pagas",money(data.realized?.expense),"Realizado")}${metricCard("Saldo realizado",money(data.realized?.balance),"Entradas menos saídas",data.realized?.balance)}${metricCard("Saldo previsto",money(data.forecast?.balance),"Inclui lançamentos pendentes",data.forecast?.balance)}</div><div class="finance-overview-grid">${sectionCard("Despesas por categoria",financeCategoryBars(data.expense_by_category||[],expenseTotal),`Competência ${state.financeMonth}`)}${sectionCard("Orçamento do mês",(data.budgets||[]).length?financeBudgetTable(data.budgets):'<div class="empty-state compact"><strong>Orçamento ainda não definido</strong>Use a aba Orçamento para criar limites por categoria.</div>')}</div>${sectionCard("Lançamentos mais recentes",financeTransactionTable(transactions.slice(0,8),access.can_write_finances),data.updated_at?`Atualizado em ${dateTime(data.updated_at)}`:"Sem lançamentos")}`;
    }else if(tab==="transactions"){
      const options=(kind)=>(catalog.categories?.[kind]||[]).map(item=>`<option data-finance-category-kind="${kind}" ${kind==="income"?"hidden disabled":""}>${esc(item)}</option>`).join("");
      const form=access.can_write_finances?`<details class="data-card" open><summary><strong>Novo lançamento</strong></summary><form id="finance-transaction-form" class="filter-grid" style="margin-top:16px"><div class="field"><label>Tipo</label><select name="kind"><option value="expense">Despesa</option><option value="income">Receita</option></select></div><div class="field"><label>Categoria</label><select name="category">${options("expense")}${options("income")}</select></div><div class="field"><label>Descrição</label><input name="description" required maxlength="200"></div><div class="field"><label>Valor</label><input name="amount" type="number" min="0.01" step="0.01" required></div><div class="field"><label>Data</label><input name="transaction_date" type="date" value="${new Date().toISOString().slice(0,10)}" required></div><div class="field"><label>Situação</label><select name="status"><option value="planned">Previsto</option><option value="paid" data-finance-status-kind="expense">Pago</option><option value="received" data-finance-status-kind="income" hidden disabled>Recebido</option><option value="overdue">Atrasado</option></select></div><div class="field"><label>Instituição</label><input name="institution" maxlength="120"></div><div class="field"><label>Forma de pagamento</label><input name="payment_method" maxlength="80"></div><div class="field wide-action"><label>Observações</label><textarea name="notes" rows="2"></textarea></div><button class="button primary wide-action" type="submit">Salvar lançamento</button></form></details>`:"";
      root.innerHTML=form+sectionCard("Planilha mensal",financeTransactionTable(transactions,access.can_write_finances),`${transactions.length} lançamento(s) em ${state.financeMonth}`);
    }else{
      const current=new Map((data.budgets||[]).map(row=>[row.category,Number(row.limit_value||0)]));
      const fields=(catalog.categories?.expense||[]).map(category=>`<div class="field"><label>${esc(category)}</label><input type="number" min="0" step="0.01" name="${esc(category)}" value="${current.get(category)||""}" placeholder="Sem limite"></div>`).join("");
      root.innerHTML=`${sectionCard("Acompanhamento",(data.budgets||[]).length?financeBudgetTable(data.budgets):'<div class="empty-state compact">Nenhum limite definido.</div>',"O consumo inclui despesas previstas e pagas")}${access.can_write_finances?`<form id="finance-budget-form" class="data-card filter-grid" style="margin-top:16px">${fields}<button class="button primary wide-action" type="submit">Salvar orçamento de ${esc(state.financeMonth)}</button></form>`:""}`;
    }
  }catch(error){root.innerHTML=errorState(error,"finances");}
}

async function saveFinanceTransaction(form){
  const values=Object.fromEntries(new FormData(form));values.amount=Number(values.amount);values.competence_month=state.financeMonth;
  try{await api("/finances/transactions",{method:"POST",body:JSON.stringify(values)});toast("Lançamento salvo.","success");loadFinances();}
  catch(error){toast(error.message,"error");}
}

async function saveFinanceBudget(form){
  const values={};new FormData(form).forEach((value,key)=>{values[key]=Number(value||0);});
  try{await api("/finances/budgets",{method:"PUT",body:JSON.stringify({competence_month:state.financeMonth,values})});toast("Orçamento atualizado.","success");loadFinances();}
  catch(error){toast(error.message,"error");}
}

async function setFinanceStatus(button){
  const status=button.dataset.financeKind==="income"?"received":"paid";
  try{await api(`/finances/transactions/${encodeURIComponent(button.dataset.setFinanceStatus)}`,{method:"PATCH",body:JSON.stringify({status})});toast("Situação atualizada.","success");loadFinances();}
  catch(error){toast(error.message,"error");}
}

async function archiveFinanceTransaction(button){
  if(!window.confirm("Arquivar este lançamento? O registro continuará preservado no banco."))return;
  try{await api(`/finances/transactions/${encodeURIComponent(button.dataset.deleteFinance)}`,{method:"DELETE"});toast("Lançamento arquivado.","success");loadFinances();}
  catch(error){toast(error.message,"error");}
}

async function loadAdmin() {
  const root=$("#admin-tab-content"); root.innerHTML=loadingCards(6);
  try {
    if(state.tabs.admin==="users") {
      const users=await api("/access/users");
      const body=`<div class="table-scroll"><table><thead><tr><th>Usuário e análises</th><th>Status</th><th>Finanças</th><th>Executa backtests</th><th>Ativos</th><th>Estratégias</th><th>Análises/dia</th><th>Alertas</th><th></th></tr></thead><tbody>${users.map(user=>`<tr data-user-row="${esc(user.email)}"><td><strong>${esc(user.display_name||user.email)}</strong><br><small>${esc(user.email)}</small>${user.is_owner?'<div class="permission-grid"><span class="pill">Acesso integral</span></div>':`<div class="permission-grid"><label class="check"><input type="checkbox" data-user-field="can_use_fdi_analysis" ${user.can_use_fdi_analysis?"checked":""}> FDI</label><label class="check"><input type="checkbox" data-user-field="can_use_alb_analysis" ${user.can_use_alb_analysis?"checked":""}> ALB</label><label class="check"><input type="checkbox" data-user-field="can_use_graham_valuation" ${user.can_use_graham_valuation?"checked":""}> Graham</label><label class="check"><input type="checkbox" data-user-field="can_use_dividend_ceiling" ${user.can_use_dividend_ceiling?"checked":""}> Preço-teto</label></div>`}</td><td>${user.is_owner?'<span class="pill">Permanente</span>':`<select data-user-field="status"><option value="pending" ${user.status==="pending"?"selected":""}>Pendente</option><option value="approved" ${user.status==="approved"?"selected":""}>Aprovado</option><option value="blocked" ${user.status==="blocked"?"selected":""}>Bloqueado</option></select>`}</td><td>${user.is_owner?"Leitura e escrita":`<label class="check"><input type="checkbox" data-user-field="can_view_finances" ${user.can_view_finances?"checked":""}> Ver</label><label class="check"><input type="checkbox" data-user-field="can_write_finances" ${user.can_write_finances?"checked":""}> Editar</label>`}</td><td>${user.is_owner?"Sim":`<label class="check"><input type="checkbox" data-user-field="can_run_backtests" ${user.can_run_backtests?"checked":""}> Permitir</label>`}</td><td>${user.is_owner?"10":`<select data-user-field="backtest_asset_limit">${[0,1,3,5,10].map(value=>`<option value="${value}" ${Number(user.backtest_asset_limit||0)===value?"selected":""}>${value}</option>`).join("")}</select>`}</td><td>${user.is_owner?"5":`<select data-user-field="backtest_strategy_limit">${[0,1,2,3,5].map(value=>`<option value="${value}" ${Number(user.backtest_strategy_limit||0)===value?"selected":""}>${value}</option>`).join("")}</select>`}</td><td>${user.is_owner?"20":`<select data-user-field="backtest_daily_limit">${[0,1,5,10,20].map(value=>`<option value="${value}" ${Number(user.backtest_daily_limit||0)===value?"selected":""}>${value}</option>`).join("")}</select>`}</td><td>${number(user.alert_asset_limit||0,0)}</td><td>${user.is_owner?"":`<button class="button secondary" data-save-user="${esc(user.email)}">Salvar</button>`}</td></tr>`).join("")}</tbody></table></div>`;
      root.innerHTML=sectionCard("Usuários e permissões",body,"Níveis disponíveis: 1, 3, 5 ou 10 ativos; 1, 2, 3 ou 5 estratégias; e 1, 5, 10 ou 20 solicitações por dia. Toda conta respeita intervalo mínimo de 60 segundos.");
    } else if(state.tabs.admin==="data") {
      const [summary,updatePayload]=await Promise.all([api("/data/catalog-summary"),api("/market-dashboard/updates")]);
      state.marketEnvelope=state.marketEnvelope||{};state.marketEnvelope.updates={...(state.marketEnvelope.updates||{}),...(updatePayload.updates||{})};
      const counts=summary.counts||{}, groups=summary.groups||{};
      root.innerHTML=`${marketUpdatePanel(["catalog","fundamentals","technical_daily","technical_intraday"],"Atualizações do catálogo e análises")}<div class="metric-grid">${metricCard("Ações",number(groups.stock||0,0),"Ativos ativos")}${metricCard("FIIs",number(groups.fii||0,0),"Fundos imobiliários")}${metricCard("ETFs",number(counts.etf||0,0),"Fundos de índice")}${metricCard("BDRs",number(counts.bdr||0,0),"Recibos negociados na B3")}</div>
        ${sectionCard("Atualizar catálogos",`<div class="action-grid">
          <button class="button secondary" data-refresh-groups="catalog">Atualizar catálogo</button>
          <button class="button primary" data-refresh-groups="fundamentals">Atualizar fundamentos e notas</button>
          <button class="button secondary" data-refresh-groups="technical_daily">Atualizar indicadores técnicos</button>
          <button class="button ghost" data-refresh-groups="technical_intraday">Atualizar ativos relevantes</button>
        </div><div id="market-sync-status" class="notice hidden" style="margin-top:14px"></div>`,`A atualização simples cria ou renova o catálogo rapidamente. A atualização completa também consulta indicadores técnicos e pode levar mais tempo.`)}`;
    } else {
      const [health,db]=await Promise.all([api("/health"),api("/health/db")]);
      root.innerHTML=`<div class="metric-grid">${metricCard("Aplicação",health.status==="ok"?"Operacional":"Atenção",`Versão ${health.version}`)}${metricCard("Banco de dados",db.status==="ok"?"Conectado":"Indisponível",db.database||"")}${metricCard("Hospedagem","Oracle Cloud","Produção")}${metricCard("Domínio","HTTPS ativo","Conexão segura")}</div>`;
    }
  } catch(error) { root.innerHTML=errorState(error); }
}

async function syncMarketCatalog(assetType, includeTechnicals) {
  const status=$("#market-sync-status");
  const buttons=$$("[data-market-sync]");
  buttons.forEach(button=>button.disabled=true);
  if(status){status.classList.remove("hidden");status.textContent="Atualizando o catálogo…";}
  try {
    const result=await api("/data/sync-market",{method:"POST",body:JSON.stringify({asset_type:assetType,include_technicals:includeTechnicals})});
    toast(`Catálogo atualizado: ${number(result.catalog_count||0,0)} ativo(s).`,"success");
    await loadAdmin();
  } catch(error) {
    if(status){status.textContent=error.message;status.classList.remove("hidden");}
    toast(error.message,"error");
    buttons.forEach(button=>button.disabled=false);
  }
}

async function saveUserAccess(email) {
  const row=$(`[data-user-row="${CSS.escape(email)}"]`);
  if(!row)return;
  const value=name=>row.querySelector(`[data-user-field="${name}"]`);
  const canRun=Boolean(value("can_run_backtests")?.checked);
  const canViewFinances=Boolean(value("can_view_finances")?.checked);
  const canWriteFinances=Boolean(value("can_write_finances")?.checked);
  const payload={
    status:value("status")?.value,
    can_use_fdi_analysis:Boolean(value("can_use_fdi_analysis")?.checked),
    can_use_alb_analysis:Boolean(value("can_use_alb_analysis")?.checked),
    can_use_graham_valuation:Boolean(value("can_use_graham_valuation")?.checked),
    can_use_dividend_ceiling:Boolean(value("can_use_dividend_ceiling")?.checked),
    can_view_finances:canViewFinances||canWriteFinances,
    can_write_finances:canWriteFinances,
    can_run_backtests:canRun,
    can_view_backtests:canRun,
    backtest_asset_limit:canRun?Number(value("backtest_asset_limit")?.value||1):0,
    backtest_daily_limit:canRun?Number(value("backtest_daily_limit")?.value||1):0,
    backtest_strategy_limit:canRun?Number(value("backtest_strategy_limit")?.value||1):0,
    backtest_cooldown_seconds:60,
  };
  try{await api(`/access/users/${encodeURIComponent(email)}`,{method:"PUT",body:JSON.stringify(payload)});toast("Permissões atualizadas.","success");loadAdmin();}
  catch(error){toast(error.message,"error");}
}

function loadCurrentView() {
  if(state.view==="dashboard") { renderDashboardTab(); if(!state.market) loadMarket(); }
  else if(state.view==="analysis") loadAnalysis();
  else if(state.view==="portfolio") loadPortfolios();
  else if(state.view==="finances") loadFinances();
  else if(state.view==="backtests") loadBacktests();
  else if(state.view==="admin") loadAdmin();
}

let searchTimer;
async function runSearch(query) {
  const root=$("#search-results");
  if(query.trim().length<1) { root.classList.add("hidden"); root.innerHTML=""; return; }
  try {
    const data=await api(`/search?q=${encodeURIComponent(query.trim())}`,{requestKey:"search"});
    const items=data.items||[];
    root.innerHTML=items.length?items.map(item=>`<button class="search-result" data-search-item='${esc(JSON.stringify(item))}'><strong>${esc(item.symbol)}</strong><span>${esc(item.label)}</span><small>${esc(item.asset_type)}</small></button>`).join(""):'<div class="empty-state" style="padding:18px"><strong>Nenhum resultado</strong>Revise o código ou nome.</div>';
    root.classList.remove("hidden");
  } catch(error) { if(error.name!=="AbortError") root.innerHTML=`<div class="error-state" style="padding:18px">${esc(error.message)}</div>`; }
}

function chooseSearchResult(item) {
  $("#search-results").classList.add("hidden"); $("#global-search").value="";
  if(item.area==="analysis") { setView("analysis",item.panel); openAsset(item.symbol); }
  else {
    setView("dashboard",item.target_tab||"overview");
    toast(`${item.label} aberto no Painel de Mercado.`,"success");
  }
}

function bindEvents() {
  $("#primary-nav").addEventListener("click", event=>{ const button=event.target.closest("[data-view]"); if(button) setView(button.dataset.view); });
  $("#collapse-sidebar").addEventListener("click",()=>document.body.classList.toggle("sidebar-collapsed"));
  $("#mobile-menu").addEventListener("click",()=>document.body.classList.toggle("mobile-nav-open"));
  $$(".tabs").forEach(tabs=>tabs.addEventListener("click",event=>{const button=event.target.closest(".tab");if(button){activateTab(tabs.dataset.tabs,button.dataset.tab);if(tabs.dataset.tabs==="analysis")updateFilterAvailability();}}));
  $("#refresh-market").addEventListener("click",()=>loadMarket(true));
  $("#logout-button").addEventListener("click",async()=>{try{await api("/logout",{method:"POST"});location.href=BASE_PATH||"/";}catch(error){toast(error.message,"error");}});
  $("#global-search").addEventListener("input",event=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>runSearch(event.target.value),220);});
  document.addEventListener("keydown",event=>{if(event.key==="/"&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)){event.preventDefault();$("#global-search").focus();}});
  document.addEventListener("click",event=>{
    const refreshGroupsButton=event.target.closest("[data-refresh-groups]");if(refreshGroupsButton){refreshMarketGroups(refreshGroupsButton.dataset.refreshGroups);return;}
    const portfolioNewsButton=event.target.closest("[data-portfolio-news-refresh]");if(portfolioNewsButton){refreshPortfolioNews(portfolioNewsButton.dataset.portfolioNewsRefresh);return;}
    const portfolioPricesButton=event.target.closest("[data-portfolio-prices-refresh]");if(portfolioPricesButton){refreshPortfolioPrices(portfolioPricesButton.dataset.portfolioPricesRefresh);return;}
    const updateCustom=event.target.closest("[data-update-custom-investment]");if(updateCustom){updateCustomInvestmentValue(updateCustom);return;}
    const deleteCustom=event.target.closest("[data-delete-custom-investment]");if(deleteCustom){deleteCustomInvestment(deleteCustom);return;}
    const deletePosition=event.target.closest("[data-delete-position]");if(deletePosition){deletePortfolioPosition(deletePosition);return;}
    if(event.target.closest("[data-close-custom-value]")){$("#custom-value-dialog").close();return;}
    const setFinance=event.target.closest("[data-set-finance-status]");if(setFinance){setFinanceStatus(setFinance);return;}
    const deleteFinance=event.target.closest("[data-delete-finance]");if(deleteFinance){archiveFinanceTransaction(deleteFinance);return;}
    const result=event.target.closest("[data-search-item]"); if(result){try{chooseSearchResult(JSON.parse(result.dataset.searchItem));}catch(_){}}
    const ticker=event.target.closest("tr[data-ticker]")?.dataset.ticker;if(ticker)openAsset(ticker);
    const retry=event.target.closest("[data-retry]")?.dataset.retry;if(retry){if(retry==="market")loadMarket(true);else loadCurrentView();}
    const linked=event.target.closest("[data-view-link]");if(linked)setView(linked.dataset.viewLink,linked.dataset.tabLink||null);
    const curve=event.target.closest("[data-curve-years]");if(curve){state.curveYears=Number(curve.dataset.curveYears);renderDashboardTab();}
    const curveHistory=event.target.closest("[data-curve-history-count]");if(curveHistory){state.curveHistoryCount=Number(curveHistory.dataset.curveHistoryCount);renderDashboardTab();}
    const comparisonPeriod=event.target.closest("[data-comparison-years]");if(comparisonPeriod){state.comparisonYears=Number(comparisonPeriod.dataset.comparisonYears);state.comparisonCustom=false;renderComparison();}
    const comparisonCustom=event.target.closest("[data-comparison-custom]");if(comparisonCustom){state.comparisonCustom=true;ensureComparisonCustomDates();renderComparison();}
    const comparisonBase=event.target.closest("[data-comparison-base]");if(comparisonBase){state.comparisonBaseMode=comparisonBase.dataset.comparisonBase;renderComparison();}
    const comparisonRefresh=event.target.closest("[data-comparison-refresh]");if(comparisonRefresh){state.comparison=null;loadComparison(true);}
    const saveUser=event.target.closest("[data-save-user]");if(saveUser)saveUserAccess(saveUser.dataset.saveUser);
    const marketSync=event.target.closest("[data-market-sync]");if(marketSync)syncMarketCatalog(marketSync.dataset.marketSync,marketSync.dataset.technicals==="true");
    const preset=event.target.closest("[data-preset-id]");if(preset)selectSystemPreset(preset.dataset.presetId);
    const customPreset=event.target.closest("[data-custom-filter-id]");if(customPreset)selectCustomFilter(customPreset.dataset.customFilterId);
    const studyStrategy=event.target.closest("[data-study-strategy]");if(studyStrategy)openStudyStrategy(studyStrategy.dataset.studyStrategy);
    const officialJob=event.target.closest("[data-official-job]");if(officialJob)openOfficialBacktestJob(officialJob.dataset.officialJob);
    const retryOfficial=event.target.closest("[data-retry-official-job]");if(retryOfficial)retryOfficialBacktestJob(retryOfficial.dataset.retryOfficialJob,retryOfficial);
    if(!event.target.closest(".global-search-wrap"))$("#search-results").classList.add("hidden");
  });
  $("#close-asset-dialog").addEventListener("click",()=>$("#asset-dialog").close());
  $("#asset-dialog").addEventListener("click",event=>{if(event.target===$("#asset-dialog"))$("#asset-dialog").close();});
  $("#apply-advanced-filters").addEventListener("click",applyAdvancedFilters);
  $("#save-custom-filter").addEventListener("click",saveCustomFilter);
  $("#delete-custom-filter").addEventListener("click",deleteCustomFilter);
  document.addEventListener("change",event=>{
    if(event.target.matches('#finance-transaction-form [name="kind"]')){
      const kind=event.target.value,form=event.target.form;
      form.querySelectorAll("[data-finance-category-kind]").forEach(option=>{const active=option.dataset.financeCategoryKind===kind;option.hidden=!active;option.disabled=!active;});
      form.querySelector('[name="category"]').value=form.querySelector(`[data-finance-category-kind="${kind}"]`)?.value||"";
      form.querySelectorAll("[data-finance-status-kind]").forEach(option=>{const active=option.dataset.financeStatusKind===kind;option.hidden=!active;option.disabled=!active;});
      form.querySelector('[name="status"]').value="planned";
    }
    if(event.target.matches('#backtest-form [name="execution_mode"]')){
      const combined=event.target.value==="combined";
      const field=event.target.form?.querySelector("[data-combination-rule]");if(field)field.hidden=!combined;
    }
    if(event.target.matches('#backtest-form [name="period"]')){
      const custom=event.target.value==="custom";
      event.target.form?.querySelectorAll("[data-backtest-custom-date]").forEach(field=>field.hidden=!custom);
    }
    if(event.target.id==="portfolio-selector"){state.portfolioId=event.target.value;renderPortfolioTab();}
    if(event.target.id==="finance-month"){state.financeMonth=event.target.value;loadFinances();}
    if(event.target.id==="analysis-limit"){state.analysisLimit=Number(event.target.value);$("#analysis-limit-label").textContent=state.analysisLimit;}
    if(event.target.matches("[data-comparison-series]")){
      state.comparisonSelected=$$("[data-comparison-series]:checked").map(input=>input.dataset.comparisonSeries);
      renderComparison();
    }
    if(event.target.matches("[data-comparison-date]")){
      if(event.target.dataset.comparisonDate==="from")state.comparisonCustomFrom=event.target.value;
      else state.comparisonCustomTo=event.target.value;
      renderComparison();
    }
    if(event.target.matches("[data-column-id]")){
      const type=analysisType(),columns=analysisColumns(type).filter(column=>!column.always);
      state.visibleColumns[type]=columns.filter(column=>$(`[data-column-id="${column.id}"]`)?.checked).map(column=>column.id);
      localStorage.setItem("fdi-visible-columns",JSON.stringify(state.visibleColumns));renderAnalysisRows(state.analysisRows);
    }
  });
  document.addEventListener("submit",event=>{if(event.target.id==="backtest-form"){event.preventDefault();runBacktest(event.target);}if(event.target.id==="portfolio-position-form"){event.preventDefault();savePortfolioPosition(event.target);}if(event.target.id==="custom-investment-form"){event.preventDefault();saveCustomInvestment(event.target);}if(event.target.id==="custom-value-form"){event.preventDefault();saveCustomInvestmentValue(event.target);}if(event.target.id==="finance-transaction-form"){event.preventDefault();saveFinanceTransaction(event.target);}if(event.target.id==="finance-budget-form"){event.preventDefault();saveFinanceBudget(event.target);}});
}

async function initialize() {
  const login=$("#login-view a[href='/login']");
  if(login) login.href=BASE_PATH?`/login?next=${encodeURIComponent(BASE_PATH+"/")}`:"/login";
  if(BASE_PATH){document.body.classList.add("staging-mode");document.body.insertAdjacentHTML("afterbegin",'<div class="staging-banner">AMBIENTE DE TESTE • nenhuma alteração será publicada na página oficial sem aprovação</div>');}
  renderFilterInputs(); bindEvents();
  try {
    const session=await api("/session/me");
    if(!session.authenticated){showLogin();return;}
    state.session=session; configureAccess(); showApp(); loadMarket();
  } catch(error) { showLogin(); toast(error.message,"error"); }
}

document.addEventListener("DOMContentLoaded",initialize);
