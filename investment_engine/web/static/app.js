"use strict";

const state = {
  session: null,
  view: "dashboard",
  tabs: { dashboard: "overview", analysis: "stocks", portfolio: "positions", backtests: "history", admin: "users" },
  market: null,
  marketEnvelope: null,
  analysisRows: [],
  analysisPreset: "default",
  portfolios: [],
  portfolioId: null,
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

async function api(path, options = {}) {
  const key = options.requestKey;
  if (key) {
    state.requestControllers.get(key)?.abort();
    const controller = new AbortController();
    state.requestControllers.set(key, controller);
    options.signal = controller.signal;
    delete options.requestKey;
  }
  const request = { credentials: "same-origin", ...options };
  request.headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const response = await fetch(path, request);
  if (response.status === 401) {
    showLogin();
    throw new Error("Sua sessão expirou. Entre novamente.");
  }
  let body = null;
  try { body = await response.json(); } catch (_) { body = null; }
  if (!response.ok) {
    const detail = body?.detail;
    const readable = typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `HTTP ${response.status}`;
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
  const sp = marketMetric(data, "S&P 500");
  const dolar = (data.fx || []).find(item => item.label === "Dólar / Real");
  const selic = data.selic || {};
  $("#market-summary").innerHTML = [
    metricCard("IBOV", ibov ? `${number(ibov.current, 0)} pts` : "—", "Brasil", ibov?.variations?.["1d"]),
    metricCard("S&P 500", sp ? `${number(sp.current, 0)} pts` : "—", "Estados Unidos", sp?.variations?.["1d"]),
    metricCard("Dólar / Real", dolar ? money(dolar.current) : "—", "Câmbio", dolar?.variations?.["1d"]),
    metricCard("Selic atual", pct(selic.current), "Meta anual • Banco Central"),
  ].join("");
  const generated = data.generated_at || state.marketEnvelope?.finished_at;
  $("#market-updated").textContent = generated ? `Atualizado em ${dateTime(generated)}` : "Atualização em segundo plano";
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
    root.innerHTML = `<div class="panel-grid">${sectionCard("Brasil", marketTable(data.quoted?.brazil, marketColumns), "Índices e variações")}${sectionCard("Inflação", inflation, "Brasil e Estados Unidos")}</div>`;
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
    root.innerHTML = `<div class="panel-grid">${sectionCard("Selic e projeções Focus", selicCards, "Taxas anuais")}${sectionCard("Renda fixa brasileira", fixed, "Somente rentabilidades anual e mensal")}${sectionCard("Treasuries dos EUA", yields, `Spread 10a − 2a: ${pct(rates.spread_10y_2y)}`, {url:rates.url,label:rates.source})}${sectionCard("Rentabilidade de T-Bonds", bonds, "ETFs usados como proxies líquidos")}</div><div class="notice info" style="margin-top:16px"><strong>Para que serve o spread?</strong> ${esc(rates.spread_explanation || "Compara juros longos e curtos e ajuda a interpretar a inclinação da curva americana.")}</div>`;
  } else if (tab === "global") {
    root.innerHTML = `<div class="panel-grid">${sectionCard("Bolsas globais", marketTable(data.quoted?.global, marketColumns))}${sectionCard("Risco e dólar", marketTable(data.quoted?.risk, marketColumns))}${sectionCard("Commodities", marketTable(data.quoted?.commodities, marketColumns))}</div>`;
  } else if (tab === "crypto") {
    const crypto = marketTable(data.crypto || [], [
      {label:"Ativo",render:r=>`<strong>${esc(r.label)}</strong>`}, {label:"Em dólar",render:r=>money(r.value_usd,"USD")},
      {label:"Em real",render:r=>`${money(r.value_brl,"BRL")}${r.brl_derived_from_fx ? '<br><small>Convertido pelo câmbio atual</small>':""}`},
      ...[["1d","1 dia"],["1w","1 semana"],["1m","1 mês"],["1y","1 ano"]].map(([key,label])=>({label,render:r=>pct(r.variations?.[key],true),className:r=>variationClass(r.variations?.[key])})),
    ]);
    root.innerHTML = `<div class="panel-grid">${sectionCard("Criptoativos", crypto)}${sectionCard("Câmbio", marketTable(data.fx, marketColumns))}</div>`;
  } else if (tab === "curve") {
    root.innerHTML = renderCurve(data.curve || {});
  } else if (tab === "calendar") {
    const rows = (data.calendar || []).map(item => ({...item, important:item.highlight === "super_wednesday"}));
    root.innerHTML = sectionCard("Próximas datas importantes", marketTable(rows, [
      {label:"Data",render:r=>`<strong>${dateOnly(r.date)}</strong>`},{label:"Evento",render:r=>`${esc(r.event)}${r.important?'<br><span class="pill warning">SUPER QUARTA</span>':""}`},
      {label:"Categoria",render:r=>esc(r.category)},{label:"Horário",render:r=>esc(r.time || "—")},{label:"Observação",render:r=>esc(r.observation || "—")},
    ]));
  } else if (tab === "headlines") {
    loadHeadlines();
  }
}

function renderCurve(curve) {
  const points = curve.points || [];
  if (!points.length) return errorState("A fonte oficial ainda não retornou os pontos da curva.", "market");
  const usable = points.filter(p => !nullable(p.nominal_rate) || !nullable(p.real_rate));
  const width = 900, height = 250, pad = 18;
  const maxX = Math.max(...usable.map(p => Number(p.years) || 0), 1);
  const values = usable.flatMap(p => [p.nominal_rate,p.real_rate]).filter(v => !nullable(v)).map(Number);
  const minY = Math.min(...values), maxY = Math.max(...values);
  const x = p => pad + (Number(p.years) / maxX) * (width - pad * 2);
  const y = value => height - pad - ((Number(value) - minY) / Math.max(maxY-minY,.1)) * (height-pad*2);
  const path = key => usable.filter(p=>!nullable(p[key])).map((p,i)=>`${i?"L":"M"}${x(p).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
  const svg = `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Curva de juros"><path d="${path("nominal_rate")}" fill="none" stroke="#0b5d4b" stroke-width="3"/><path d="${path("real_rate")}" fill="none" stroke="#c79b3b" stroke-width="3"/>${usable.filter((_,i)=>i%Math.ceil(usable.length/10)===0).map(p=>`<text x="${x(p)}" y="${height}" font-size="11" text-anchor="middle" fill="#67756f">${number(p.years,1)}a</text>`).join("")}</svg>`;
  return sectionCard("Curva de juros brasileira", `<div class="chart">${svg}</div><div class="chart-legend"><span><i class="legend-dot" style="background:#0b5d4b"></i>Prefixada nominal</span><span><i class="legend-dot" style="background:#c79b3b"></i>Juro real IPCA</span><span>Referência: ${dateOnly(curve.as_of)}</span></div>`, "Estrutura a termo até o maior prazo disponível", {url:curve.url,label:curve.source});
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
  const list = items.length ? `<div class="headline-list">${items.map((item,index)=>`<a class="headline" href="${esc(item.url)}" target="_blank" rel="noopener"><span class="headline-number">${String(index+1).padStart(2,"0")}</span><span><strong>${esc(item.title)}</strong><small>${esc(item.source)}</small></span><small>${item.published_at ? dateTime(item.published_at) : ""}</small></a>`).join("")}</div>` : '<div class="empty-state"><strong>Nenhuma manchete disponível agora</strong>As fontes serão consultadas novamente em até uma hora.</div>';
  $("#dashboard-tab-content").innerHTML = sectionCard("5 principais manchetes de economia", list, "Atualização automática a cada hora");
}

const filterDefinitions = {
  fundamental: [
    ["pe","P/L"],["pbv","P/VP"],["dividend_yield_pct","Dividend yield (%)"],["roe_pct","ROE (%)"],
    ["roic_pct","ROIC (%)"],["ebit_margin_pct","Margem EBIT (%)"],["net_margin_pct","Margem líquida (%)"],["current_ratio","Liquidez corrente"],
    ["net_debt_to_ebitda","Dívida líq./EBITDA"],["daily_liquidity","Liquidez diária"],["ffo_yield_pct","FFO yield (%)"],["vacancy_pct","Vacância (%)"],
  ],
  technical: [["rsi14","RSI 14"]],
};

function renderFilterInputs() {
  $("#fundamental-filters").innerHTML = filterDefinitions.fundamental.map(([key,label]) => `<div class="field" data-filter-field="${key}"><label>${esc(label)}</label><div style="display:grid;grid-template-columns:1fr 1fr;gap:5px"><input type="number" step="any" data-bound="min" placeholder="Mín."><input type="number" step="any" data-bound="max" placeholder="Máx."></div></div>`).join("");
  $("#technical-filters").innerHTML = `${filterDefinitions.technical.map(([key,label]) => `<div class="field" data-technical-field="${key}"><label>${esc(label)}</label><div style="display:grid;grid-template-columns:1fr 1fr;gap:5px"><input type="number" step="any" data-bound="min" placeholder="Mín."><input type="number" step="any" data-bound="max" placeholder="Máx."></div></div>`).join("")}<div class="field"><label>Tendência diária</label><select id="trend-daily"><option value="any">Qualquer</option><option value="up">Alta</option><option value="down">Baixa</option></select></div><div class="field"><label>Tendência semanal</label><select id="trend-weekly"><option value="any">Qualquer</option><option value="up">Alta</option><option value="down">Baixa</option></select></div><button id="apply-advanced-filters" class="button primary" style="align-self:end">Aplicar ajustes</button>`;
}

function analysisType() {
  return ({stocks:"stock",fiis:"fii",etfs:"etf",bdrs:"bdr",futures:"future"})[state.tabs.analysis];
}

async function loadAnalysis() {
  const root = $("#analysis-table");
  root.innerHTML = loadingCards(6);
  const type = analysisType();
  try {
    let rows;
    if (type === "stock") rows = await api(`/screen/db/stocks/${state.analysisPreset}?limit=50`, {requestKey:"analysis"});
    else if (type === "fii") rows = await api(`/screen/db/fiis/${state.analysisPreset}?limit=50`, {requestKey:"analysis"});
    else {
      const all = await api("/screen/db/universe/other_b3?limit=1200", {requestKey:"analysis"});
      rows = all.filter(item => item.asset_type === type);
    }
    if (type === "stock") rows.sort((a,b)=>(Number(b.graham_upside_pct)||-Infinity)-(Number(a.graham_upside_pct)||-Infinity));
    else rows.sort((a,b)=>String(a.ticker).localeCompare(String(b.ticker)));
    state.analysisRows = rows;
    renderAnalysisRows(rows);
  } catch (error) { root.innerHTML = errorState(error, "analysis"); }
}

function renderAnalysisRows(rows) {
  $("#analysis-count").textContent = `${rows.length} ativo${rows.length===1?"":"s"}`;
  if (!rows.length) { $("#analysis-table").innerHTML='<div class="empty-state"><strong>Nenhum ativo passou pelos filtros</strong>Abra os ajustes para ampliar ou alterar os critérios.</div>'; return; }
  const type = analysisType();
  let columns;
  if (type === "stock") columns = [
    ["Ativo",r=>`<span class="ticker-cell">${esc(r.ticker)}</span><br><small>${esc(r.name||"")}</small>`],
    ["Setor",r=>esc(r.sector_label||r.classification||"—")],["Preço",r=>money(r.price)],["P/L",r=>number(r.pe)],["P/VP",r=>number(r.pbv)],
    ["DY",r=>pct(r.dy)],["ROE",r=>pct(r.roe)],["Graham",r=>money(r.graham_number)],["Potencial Graham",r=>`<span class="${variationClass(r.graham_upside_pct)}">${pct(r.graham_upside_pct,true)}</span>`],["Nota ALB",r=>number(r.alb_score,1)],
  ];
  else if (type === "fii") columns = [["Ativo",r=>`<span class="ticker-cell">${esc(r.ticker)}</span><br><small>${esc(r.name||"")}</small>`],["Segmento",r=>esc(r.segment_label||r.classification||"—")],["Preço",r=>money(r.price)],["P/VP",r=>number(r.pbv)],["DY",r=>pct(r.dy)],["FFO yield",r=>pct(r.ffo_yield)],["Vacância",r=>pct(r.vacancy)],["Nota ALB",r=>number(r.alb_score,1)]];
  else columns = [["Ativo",r=>`<span class="ticker-cell">${esc(r.ticker)}</span><br><small>${esc(r.name||"")}</small>`],["Categoria",r=>esc(r.asset_type_label||r.classification||"—")],["Preço",r=>money(r.price)],["Sinal",r=>esc(r.signal_tv||"—")],["RSI 14",r=>number(r.rsi14_screen)],["Nota técnica",r=>number(r.technical_score,1)]];
  $("#analysis-table").innerHTML = `<div class="table-scroll"><table><thead><tr>${columns.map(c=>`<th>${esc(c[0])}</th>`).join("")}</tr></thead><tbody>${rows.map(r=>`<tr data-ticker="${esc(r.ticker)}">${columns.map(c=>`<td>${c[1](r)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

async function applyAdvancedFilters() {
  const fundamental_filters = {};
  $$("[data-filter-field]").forEach(group => {
    const min=group.querySelector('[data-bound="min"]').value, max=group.querySelector('[data-bound="max"]').value;
    if (min!=="" || max!=="") fundamental_filters[group.dataset.filterField] = {min:min===""?null:Number(min),max:max===""?null:Number(max)};
  });
  const rsiGroup = $("[data-technical-field='rsi14']");
  const rsiMin=rsiGroup?.querySelector('[data-bound="min"]').value, rsiMax=rsiGroup?.querySelector('[data-bound="max"]').value;
  const technical_filters={daily_trend:$("#trend-daily").value,weekly_trend:$("#trend-weekly").value,monthly_trend:"any",pivot_zone:"any",near_pivot_level:"none",pivot_tolerance_pct:.5};
  if (rsiMin!=="" || rsiMax!=="") technical_filters.rsi14={min:rsiMin===""?null:Number(rsiMin),max:rsiMax===""?null:Number(rsiMax)};
  const asset_type = ["stock","fii"].includes(analysisType()) ? analysisType() : "other_b3";
  $("#analysis-table").innerHTML=loadingCards(6);
  try {
    const rows=await api("/screen/advanced",{method:"POST",body:JSON.stringify({asset_type,fundamental_filters,score_filters:{},valuation_flags:{},technical_filters,trend_period:21,pivot_timeframe:"daily",include_technical_columns:true,limit:100})});
    state.analysisRows=rows; renderAnalysisRows(rows); toast("Filtros aplicados.","success");
  } catch(error) { $("#analysis-table").innerHTML=errorState(error,"analysis"); }
}

async function openAsset(ticker) {
  const dialog=$("#asset-dialog"), content=$("#asset-dialog-content");
  content.innerHTML=loadingCards(4); dialog.showModal();
  try {
    const data=await api(`/assets/${encodeURIComponent(ticker)}`);
    const a=data.asset||{}, f=data.fundamentals||{}, t=data.technical||{};
    content.innerHTML=`<p class="eyebrow">${esc(a.asset_type||"Ativo")}</p><h2 class="asset-title">${esc(a.ticker)} • ${esc(a.name||"")}</h2><p class="asset-subtitle">${esc(a.sector_label||a.classification||"")}</p><div class="metric-grid">${metricCard("Preço",money(f.price??t.close))}${metricCard("P/L",number(f.pe))}${metricCard("P/VP",number(f.pbv))}${metricCard("Dividend yield",pct(f.dividend_yield_pct))}${metricCard("ROE",pct(f.roe_pct))}${metricCard("RSI 14",number(t.rsi14))}${metricCard("Retorno 12 meses",pct(t.return_12m_pct,true))}${metricCard("Liquidez diária",money(f.daily_liquidity??t.daily_liquidity))}</div>`;
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

async function renderPortfolioTab() {
  const root=$("#portfolio-tab-content"), tab=state.tabs.portfolio;
  root.innerHTML=loadingCards(5);
  try {
    if (tab==="positions") {
      const data=await api(`/portfolios/${state.portfolioId}`);
      const positions=data.positions||data.items||[];
      const summary=data.summary||{};
      const cards=`<div class="metric-grid summary-grid">${metricCard("Patrimônio",money(summary.total_value??data.total_value))}${metricCard("Posições",String(positions.length))}${metricCard("Caixa",money(data.portfolio?.cash_balance))}${metricCard("Alocação",pct(summary.invested_pct))}</div>`;
      root.innerHTML=cards+sectionCard("Posições",marketTable(positions,[{label:"Ativo",render:r=>`<span class="ticker-cell">${esc(r.ticker)}</span>`},{label:"Quantidade",render:r=>number(r.quantity,0)},{label:"Preço médio",render:r=>money(r.average_price)},{label:"Preço atual",render:r=>money(r.current_price)},{label:"Valor",render:r=>money(r.market_value??(Number(r.quantity)*Number(r.current_price)))},{label:"Setor",render:r=>esc(r.classification||r.sector||"—")} ]));
    } else if (tab==="news") {
      const cache=await api(`/insights/news/cache/portfolios/${state.portfolioId}`);
      const data=cache.data||{};
      const groups=data.assets||data.items||[];
      root.innerHTML=sectionCard("Notícias da carteira",groups.length?groups.map(group=>`<div class="card-section"><div class="card-heading"><h3>${esc(group.ticker||group.label||"Ativo")}</h3></div><div class="headline-list">${(group.items||group.news||[]).map((item,i)=>`<a class="headline" href="${esc(item.url)}" target="_blank" rel="noopener"><span class="headline-number">${i+1}</span><span><strong>${esc(item.title)}</strong><small>${esc(item.source||"")}</small></span></a>`).join("")}</div></div>`).join(""):'<div class="empty-state"><strong>Notícias sendo preparadas</strong>A primeira consulta do dia é feita automaticamente em segundo plano.</div>',"Até 3 notícias relevantes por ativo");
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
  root.innerHTML=`<div class="notice info" style="margin-bottom:14px">B3: monitoramento em dias úteis, das 10h às 18h, a cada 5 minutos. Outros mercados: a cada 30 minutos.</div>${sectionCard("Alertas ativos",marketTable(active,[{label:"Ativo",render:r=>`<strong>${esc(r.symbol)}</strong>`},{label:"Acima de",render:r=>money(r.price_above)},{label:"Abaixo de",render:r=>money(r.price_below)},{label:"Variação positiva",render:r=>pct(r.change_positive_pct)},{label:"Variação negativa",render:r=>pct(r.change_negative_pct)},{label:"Status",render:r=>`<span class="pill">${esc(r.status||"ativo")}</span>`}]),`Limite autorizado: ${data.limit??access.alert_asset_limit} ativos`)}`;
  $("#notification-count").textContent=active.length;
  $("#notification-count").classList.toggle("hidden",!active.length);
}

async function loadBacktests() {
  const root=$("#backtests-tab-content"),tab=state.tabs.backtests; root.innerHTML=loadingCards(6);
  try {
    if(tab==="history") {
      const rows=await api("/backtests/runs?limit=100",{requestKey:"backtests"});
      rows.sort((a,b)=>new Date(b.created_at)-new Date(a.created_at));
      root.innerHTML=sectionCard("Últimos 100 backtests",marketTable(rows,[{label:"Data e hora",render:r=>dateTime(r.created_at)},{label:"Ativo",render:r=>`<span class="ticker-cell">${esc(r.ticker||"—")}</span>`},{label:"Estratégia",render:r=>esc(r.strategy_name||r.strategy_id||"—")},{label:"Retorno",render:r=>pct(r.metrics?.total_return_pct??r.return_pct,true),className:r=>variationClass(r.metrics?.total_return_pct??r.return_pct)},{label:"Status",render:r=>`<span class="pill">${esc(r.status||"—")}</span>`}]));
    } else if(tab==="study") {
      const data=await api("/backtests/study?limit=5"); const rows=data.items||data.ranking||[];
      root.innerHTML=sectionCard("Estratégias mais consistentes",marketTable(rows,[{label:"Posição",render:(r)=>`<strong>${esc(r.position||r.rank||"—")}</strong>`},{label:"Estratégia",render:r=>esc(r.strategy_name||r.name||r.strategy_id)},{label:"Pontuação",render:r=>number(r.score??r.points,1)},{label:"Presença no top 3",render:r=>number(r.top_three_count??r.top3_count,0)}]),"Ranking ponderado por posição, recorrência e qualidade da amostra");
    } else if(tab==="official") {
      const rows=await api("/backtests/batch/jobs?limit=30");
      root.innerHTML=sectionCard("Rodadas oficiais",marketTable(rows,[{label:"Criado em",render:r=>dateTime(r.created_at)},{label:"Identificador",render:r=>esc(r.id)},{label:"Ativos",render:r=>number((r.requested_tickers||r.tickers||[]).length,0)},{label:"Progresso",render:r=>`${number(r.completed_assets||0,0)} / ${number(r.total_assets||(r.requested_tickers||[]).length,0)}`},{label:"Status",render:r=>`<span class="pill ${r.status==="failed"?"danger":""}">${esc(r.status)}</span>`}]));
    } else {
      const catalog=await api("/backtests/strategies");
      root.innerHTML=sectionCard("Executar backtest",`<form id="backtest-form" class="filter-grid"><div class="field"><label>Ativo</label><input name="ticker" required placeholder="PETR4"></div><div class="field"><label>Estratégia</label><select name="strategy_id">${(catalog.strategies||[]).map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")}</select></div><div class="field"><label>Período</label><select name="period">${Object.entries(catalog.periods||{}).map(([id,label])=>`<option value="${esc(id)}" ${id==="5y"?"selected":""}>${esc(label)}</option>`).join("")}</select></div><button class="button primary" type="submit" style="align-self:end">Executar</button></form><div id="backtest-result" style="margin-top:16px"></div>`,"O resultado é salvo no histórico desta conta");
    }
  } catch(error) { root.innerHTML=errorState(error,"backtests"); }
}

async function runBacktest(form) {
  const result=$("#backtest-result"); result.innerHTML=loadingCards(4);
  const values=Object.fromEntries(new FormData(form));
  try {
    const data=await api("/backtests/run",{method:"POST",body:JSON.stringify({ticker:values.ticker.trim().toUpperCase(),asset_type:"stock",strategy_id:values.strategy_id,period:values.period,initial_capital:10000,fee_pct:.03,slippage_pct:.05,risk_free_rate_pct:0,params:{},filters:{},persist:true})});
    const metrics=data.metrics||{};
    result.innerHTML=`<div class="metric-grid">${metricCard("Retorno",pct(metrics.total_return_pct??data.return_pct,true))}${metricCard("CAGR",pct(metrics.cagr_pct??metrics.cagr,true))}${metricCard("Sharpe",number(metrics.sharpe_ratio??metrics.sharpe))}${metricCard("Drawdown máximo",pct(metrics.max_drawdown_pct??metrics.max_drawdown,true))}</div>`;
    toast("Backtest concluído e salvo.","success");
  } catch(error) { result.innerHTML=errorState(error); }
}

async function loadAdmin() {
  const root=$("#admin-tab-content"); root.innerHTML=loadingCards(6);
  try {
    if(state.tabs.admin==="users") {
      const users=await api("/access/users");
      root.innerHTML=sectionCard("Usuários e permissões",marketTable(users,[{label:"Usuário",render:r=>`<strong>${esc(r.display_name||r.email)}</strong><br><small>${esc(r.email)}</small>`},{label:"Perfil",render:r=>esc(r.role)},{label:"Status",render:r=>`<span class="pill">${esc(r.status)}</span>`},{label:"Carteira",render:r=>r.can_view_portfolio?"Sim":"Não"},{label:"Backtests",render:r=>r.can_run_backtests?"Executa":r.can_view_backtests?"Consulta":"Não"},{label:"Alertas",render:r=>number(r.alert_asset_limit||0,0)}]));
    } else {
      const [health,db]=await Promise.all([api("/health"),api("/health/db")]);
      root.innerHTML=`<div class="metric-grid">${metricCard("Aplicação",health.status==="ok"?"Operacional":"Atenção",`Versão ${health.version}`)}${metricCard("Banco de dados",db.status==="ok"?"Conectado":"Indisponível",db.database||"")}${metricCard("Hospedagem","Oracle Cloud","Produção")}${metricCard("Domínio","HTTPS ativo","Conexão segura")}</div>`;
    }
  } catch(error) { root.innerHTML=errorState(error); }
}

function loadCurrentView() {
  if(state.view==="dashboard") { renderDashboardTab(); if(!state.market) loadMarket(); }
  else if(state.view==="analysis") loadAnalysis();
  else if(state.view==="portfolio") loadPortfolios();
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
  $$(".tabs").forEach(tabs=>tabs.addEventListener("click",event=>{const button=event.target.closest(".tab");if(button)activateTab(tabs.dataset.tabs,button.dataset.tab);}));
  $("#refresh-market").addEventListener("click",()=>loadMarket(true));
  $("#logout-button").addEventListener("click",async()=>{try{await api("/logout",{method:"POST"});location.href="/";}catch(error){toast(error.message,"error");}});
  $("#global-search").addEventListener("input",event=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>runSearch(event.target.value),220);});
  document.addEventListener("keydown",event=>{if(event.key==="/"&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)){event.preventDefault();$("#global-search").focus();}});
  document.addEventListener("click",event=>{
    const result=event.target.closest("[data-search-item]"); if(result){try{chooseSearchResult(JSON.parse(result.dataset.searchItem));}catch(_){}}
    const ticker=event.target.closest("tr[data-ticker]")?.dataset.ticker;if(ticker)openAsset(ticker);
    const retry=event.target.closest("[data-retry]")?.dataset.retry;if(retry){if(retry==="market")loadMarket(true);else loadCurrentView();}
    const linked=event.target.closest("[data-view-link]");if(linked)setView(linked.dataset.viewLink,linked.dataset.tabLink||null);
    if(!event.target.closest(".global-search-wrap"))$("#search-results").classList.add("hidden");
  });
  $("#close-asset-dialog").addEventListener("click",()=>$("#asset-dialog").close());
  $("#asset-dialog").addEventListener("click",event=>{if(event.target===$("#asset-dialog"))$("#asset-dialog").close();});
  $$(".preset-button").forEach(button=>button.addEventListener("click",()=>{
    const map={padrao:"default",cnpi:"cnpi",alb:"alb"}; if(!map[button.dataset.preset]){toast("Seus filtros personalizados ficam vinculados à sua conta.");return;}
    state.analysisPreset=map[button.dataset.preset]; $$(".preset-button").forEach(b=>b.classList.toggle("active",b===button)); loadAnalysis();
  }));
  $("#apply-advanced-filters").addEventListener("click",applyAdvancedFilters);
  document.addEventListener("change",event=>{if(event.target.id==="portfolio-selector"){state.portfolioId=event.target.value;renderPortfolioTab();}});
  document.addEventListener("submit",event=>{if(event.target.id==="backtest-form"){event.preventDefault();runBacktest(event.target);}});
}

async function initialize() {
  renderFilterInputs(); bindEvents();
  try {
    const session=await api("/session/me");
    if(!session.authenticated){showLogin();return;}
    state.session=session; configureAccess(); showApp(); loadMarket();
  } catch(error) { showLogin(); toast(error.message,"error"); }
}

document.addEventListener("DOMContentLoaded",initialize);
