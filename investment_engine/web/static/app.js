"use strict";

const BASE_PATH = location.pathname === "/testefdi" || location.pathname.startsWith("/testefdi/") ? "/testefdi" : "";

const state = {
  session: null,
  view: "dashboard",
  tabs: { dashboard: "overview", analysis: "stocks", portfolio: "positions", backtests: "history", admin: "users" },
  market: null,
  marketEnvelope: null,
  analysisRows: [],
  analysisPreset: "default",
  analysisLimit: 50,
  curveYears: 10,
  visibleColumns: JSON.parse(localStorage.getItem("fdi-visible-columns") || "{}"),
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
  const usable = points.filter(p => (!state.curveYears || Number(p.years) <= state.curveYears) && (!nullable(p.nominal_rate) || !nullable(p.real_rate)));
  if (!usable.length) return errorState("Não há vértices disponíveis para esse período.", "market");
  const width = 900, height = 250, pad = 18;
  const maxX = Math.max(...usable.map(p => Number(p.years) || 0), 1);
  const values = usable.flatMap(p => [p.nominal_rate,p.real_rate]).filter(v => !nullable(v)).map(Number);
  const minY = Math.min(...values), maxY = Math.max(...values);
  const x = p => pad + (Number(p.years) / maxX) * (width - pad * 2);
  const y = value => height - pad - ((Number(value) - minY) / Math.max(maxY-minY,.1)) * (height-pad*2);
  const path = key => usable.filter(p=>!nullable(p[key])).map((p,i)=>`${i?"L":"M"}${x(p).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
  const svg = `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Curva de juros"><path d="${path("nominal_rate")}" fill="none" stroke="#0b5d4b" stroke-width="3"/><path d="${path("real_rate")}" fill="none" stroke="#c79b3b" stroke-width="3"/>${usable.filter((_,i)=>i%Math.ceil(usable.length/10)===0).map(p=>`<text x="${x(p)}" y="${height}" font-size="11" text-anchor="middle" fill="#67756f">${number(p.years,1)}a</text>`).join("")}</svg>`;
  const periods = [[1,"1 ano"],[2,"2 anos"],[5,"5 anos"],[10,"10 anos"],[20,"20 anos"],[30,"30 anos"],[0,"Máximo"]];
  const controls = `<div class="chart-periods" role="group" aria-label="Período da curva">${periods.map(([years,label])=>`<button class="button ${state.curveYears===years?"primary":"secondary"}" data-curve-years="${years}">${label}</button>`).join("")}</div>`;
  return sectionCard("Curva de juros brasileira", `${controls}<div class="chart">${svg}</div><div class="chart-legend"><span><i class="legend-dot" style="background:#0b5d4b"></i>Prefixada nominal</span><span><i class="legend-dot" style="background:#c79b3b"></i>Juro real IPCA</span><span>Referência: ${dateOnly(curve.as_of)}</span></div>`, "Escolha o horizonte; a curva oficial da ANBIMA permanece disponível até o maior prazo publicado", {url:curve.url,label:curve.source});
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
    ["price","Preço"],["pe","P/L"],["pbv","P/VP"],["dividend_yield_pct","Dividend yield (%)"],
    ["ev_ebitda","EV/EBITDA"],["ebit_margin_pct","Margem EBIT (%)"],["net_margin_pct","Margem líquida (%)"],
    ["current_ratio","Liquidez corrente"],["roe_pct","ROE (%)"],["roic_pct","ROIC (%)"],
    ["gross_debt_to_equity","Dívida bruta/patrimônio"],["net_debt_to_ebitda","Dívida líquida/EBITDA"],
    ["revenue_cagr_5y_pct","CAGR receita 5a (%)"],["earnings_cagr_5y_pct","CAGR lucro 5a (%)"],
    ["daily_liquidity","Liquidez diária"],["ffo_yield_pct","FFO yield (%)"],["cap_rate_pct","Cap rate (%)"],
    ["vacancy_pct","Vacância física (%)"],["financial_vacancy_pct","Vacância financeira (%)"],["ltv_pct","LTV (%)"],
  ],
  scores: [["quality_score","Qualidade"],["value_score","Valor"],["growth_score","Crescimento"],["technical_score","Técnica"],["risk_score","Risco"],["liquidity_score","Liquidez"],["alb_score","Nota ALB"],["data_quality_score","Qualidade dos dados"]],
};

function numericRange(key, label, kind="filter") {
  const attr = kind === "score" ? "data-score-field" : kind === "technical" ? "data-technical-field" : "data-filter-field";
  return `<div class="field" ${attr}="${key}"><label>${esc(label)}</label><div class="range-pair"><input type="number" step="any" data-bound="min" placeholder="Mín."><input type="number" step="any" data-bound="max" placeholder="Máx."></div></div>`;
}

function renderFilterInputs() {
  $("#fundamental-filters").innerHTML = `
    <div class="field"><label>Máximo de ativos: <strong id="analysis-limit-label">${state.analysisLimit}</strong></label><input id="analysis-limit" type="range" min="5" max="100" step="5" value="${state.analysisLimit}"></div>
    <div class="field stock-only-filter"><label>Participação no IBOV</label><select id="ibov-membership"><option value="any">Qualquer</option><option value="inside">Somente no IBOV</option><option value="outside">Fora do IBOV</option></select></div>
    <div class="field stock-only-filter"><label>Porte da empresa</label><select id="company-sizes" multiple size="3"><option value="blue_chip">Blue Chip</option><option value="mid_cap">Middle Cap</option><option value="small_cap">Small Cap</option></select></div>
    <div class="field stock-only-filter"><label>Preços-teto</label><label class="check"><input id="below-graham" type="checkbox"> Abaixo de Graham</label><label class="check"><input id="below-barsi" type="checkbox"> Abaixo do preço-teto de dividendos (6%)</label></div>
    <details class="filter-subgroup" open><summary>Indicadores fundamentalistas</summary><div class="filter-grid">${filterDefinitions.fundamental.map(([key,label])=>numericRange(key,label)).join("")}</div></details>
    <details class="filter-subgroup"><summary>Notas e qualidade</summary><div class="filter-grid">${filterDefinitions.scores.map(([key,label])=>numericRange(key,label,"score")).join("")}</div></details>`;
  $("#technical-filters").innerHTML = `
    ${numericRange("rsi14","RSI 14","technical")}
    <div class="field"><label>Tendência diária</label><select id="trend-daily"><option value="any">Qualquer</option><option value="up">Alta</option><option value="down">Baixa</option></select></div>
    <div class="field"><label>Tendência semanal</label><select id="trend-weekly"><option value="any">Qualquer</option><option value="up">Alta</option><option value="down">Baixa</option></select></div>
    <div class="field"><label>Tendência mensal</label><select id="trend-monthly"><option value="any">Qualquer</option><option value="up">Alta</option><option value="down">Baixa</option></select></div>
    <div class="field"><label>Período dos pivôs</label><select id="pivot-timeframe"><option value="daily">Diário</option><option value="weekly">Semanal</option><option value="monthly">Mensal</option></select></div>
    <div class="field"><label>Zona entre pivôs</label><select id="pivot-zone"><option value="any">Qualquer</option><option value="below_s3">Abaixo de S3</option><option value="s3_s2">S3–S2</option><option value="s2_s1">S2–S1</option><option value="s1_pp">S1–Pivô</option><option value="pp_r1">Pivô–R1</option><option value="r1_r2">R1–R2</option><option value="r2_r3">R2–R3</option><option value="above_r3">Acima de R3</option></select></div>
    <div class="field"><label>Próximo de</label><select id="near-pivot"><option value="none">Sem filtro</option><option value="s3">Suporte 3</option><option value="s2">Suporte 2</option><option value="s1">Suporte 1</option><option value="pp">Pivô</option><option value="r1">Resistência 1</option><option value="r2">Resistência 2</option><option value="r3">Resistência 3</option></select></div>
    <div class="field"><label>Tolerância ao pivô (%)</label><input id="pivot-tolerance" type="number" min="0" max="20" step="0.1" value="0.5"></div>
    <div class="field"><label>Volume acima da média de 9</label><label class="check"><input id="volume-daily-ma9" type="checkbox"> Diário</label><label class="check"><input id="volume-monthly-ma9" type="checkbox"> Mensal</label></div>
    <button id="apply-advanced-filters" class="button primary wide-action">Aplicar ajustes</button>`;
  updateFilterAvailability();
}

function updateFilterAvailability() {
  $$(".stock-only-filter").forEach(node=>node.classList.toggle("hidden",analysisType()!=="stock"));
}

function resetAdvancedFilters() {
  $$('[data-filter-field] input,[data-score-field] input,[data-technical-field] input').forEach(input=>input.value="");
  ["trend-daily","trend-weekly","trend-monthly"].forEach(id=>{if($(`#${id}`))$(`#${id}`).value="any";});
  if($("#pivot-zone")) $("#pivot-zone").value="any";
  if($("#near-pivot")) $("#near-pivot").value="none";
  ["below-graham","below-barsi","volume-daily-ma9","volume-monthly-ma9"].forEach(id=>{if($(`#${id}`))$(`#${id}`).checked=false;});
  if($("#ibov-membership")) $("#ibov-membership").value="any";
  if($("#company-sizes")) [...$("#company-sizes").options].forEach(option=>option.selected=false);
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
    if (type === "stock") rows = await api(`/screen/db/stocks/${state.analysisPreset}?limit=${state.analysisLimit}`, {requestKey:"analysis"});
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

function analysisColumns(type) {
  const common=[
    {id:"ticker",label:"Ativo",always:true,render:r=>`<span class="ticker-cell">${esc(r.ticker)}</span><br><small>${esc(r.name||"")}</small>`},
    {id:"price",label:"Preço",render:r=>money(r.price)},
    {id:"best_signal",label:"Melhor backtest",render:r=>r.backtest_leaders?.length?`<span class="pill signal-${esc(r.best_signal||"neutral")}">${signalLabel(r.best_signal)}</span><br><small>${esc(r.best_strategy||"")}</small>`:"—"},
  ];
  if(type==="stock") return [common[0],
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
  ];
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

async function applyAdvancedFilters() {
  const fundamental_filters = {};
  $$("[data-filter-field]").forEach(group => {
    const min=group.querySelector('[data-bound="min"]').value, max=group.querySelector('[data-bound="max"]').value;
    if (min!=="" || max!=="") fundamental_filters[group.dataset.filterField] = {min:min===""?null:Number(min),max:max===""?null:Number(max)};
  });
  const score_filters={};
  $$('[data-score-field]').forEach(group=>{
    const min=group.querySelector('[data-bound="min"]').value,max=group.querySelector('[data-bound="max"]').value;
    if(min!==""||max!=="")score_filters[group.dataset.scoreField]={min:min===""?null:Number(min),max:max===""?null:Number(max)};
  });
  const rsiGroup = $("[data-technical-field='rsi14']");
  const rsiMin=rsiGroup?.querySelector('[data-bound="min"]').value, rsiMax=rsiGroup?.querySelector('[data-bound="max"]').value;
  const technical_filters={daily_trend:$("#trend-daily").value,weekly_trend:$("#trend-weekly").value,monthly_trend:$("#trend-monthly").value,pivot_zone:$("#pivot-zone").value,near_pivot_level:$("#near-pivot").value,pivot_tolerance_pct:Number($("#pivot-tolerance").value||.5),volume_daily_above_ma9:$("#volume-daily-ma9").checked,volume_monthly_above_ma9:$("#volume-monthly-ma9").checked};
  if (rsiMin!=="" || rsiMax!=="") technical_filters.rsi14={min:rsiMin===""?null:Number(rsiMin),max:rsiMax===""?null:Number(rsiMax)};
  const asset_type = ["stock","fii"].includes(analysisType()) ? analysisType() : "other_b3";
  state.analysisLimit=Number($("#analysis-limit").value||50);
  const company_sizes=$("#company-sizes")?[...$("#company-sizes").selectedOptions].map(option=>option.value):[];
  const ibov_membership=$("#ibov-membership")?.value||"any";
  const valuation_flags={below_graham:Boolean($("#below-graham")?.checked),below_barsi_6pct:Boolean($("#below-barsi")?.checked)};
  $("#analysis-table").innerHTML=loadingCards(6);
  try {
    const payload=await api("/screen/advanced",{method:"POST",requestKey:"analysis",body:JSON.stringify({asset_type,fundamental_filters,score_filters,valuation_flags,technical_filters,trend_period:21,pivot_timeframe:$("#pivot-timeframe").value,include_technical_columns:true,limit:state.analysisLimit,company_sizes,ibov_membership})});
    const rows=await enrichBacktestLeaders(payload.rows||payload);
    state.analysisRows=rows; renderAnalysisRows(rows); toast(`${rows.length} ativo(s) após os ajustes.`,"success");
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
      const access=state.session.access;
      root.innerHTML=sectionCard("Comparar estratégias",`<form id="backtest-form" class="filter-grid backtest-form">
        <div class="field wide-action"><label>Ativos — separe por vírgula ou espaço</label><textarea name="tickers" required rows="3" placeholder="PETR4, VALE3, BBAS3"></textarea><small>Limite autorizado por análise: ${number(access.backtest_asset_limit||0,0)} ativo(s).</small></div>
        <div class="field"><label>Estratégias (até 3)</label><select name="strategy_ids" multiple size="6" required>${(catalog.strategies||[]).map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")}</select></div>
        <div class="field"><label>Tipo de ativo</label><select name="asset_type"><option value="stock">Ações</option><option value="fii">FIIs</option><option value="etf">ETFs</option><option value="bdr">BDRs</option></select></div>
        <div class="field"><label>Período</label><select name="period">${Object.entries(catalog.periods||{}).map(([id,label])=>`<option value="${esc(id)}" ${id==="5y"?"selected":""}>${esc(label)}</option>`).join("")}</select></div>
        <button class="button primary wide-action" type="submit">Executar e comparar</button>
      </form><div id="backtest-result" style="margin-top:16px"></div>`,`Cada envio conta como uma análise diária. Limite desta conta: ${access.backtest_daily_limit||0} por dia; os resultados ficam salvos no histórico.`);
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
    const data=await api("/backtests/matrix",{method:"POST",body:JSON.stringify({tickers,strategy_ids,asset_type:values.asset_type,period:values.period,initial_capital:10000,fee_pct:.03,slippage_pct:.05,risk_free_rate_pct:0,filters:{}})});
    const rows=data.results||[];
    result.innerHTML=sectionCard("Resultado comparativo",marketTable(rows,[
      {label:"Ativo",render:r=>`<strong>${esc(r.ticker||r.requested_ticker)}</strong>`},
      {label:"Estratégia",render:r=>esc(r.strategy_name||r.strategy_id)},
      {label:"Retorno",render:r=>pct(r.total_return_pct,true),className:r=>variationClass(r.total_return_pct)},
      {label:"CAGR",render:r=>pct(r.cagr_pct??r.cagr,true),className:r=>variationClass(r.cagr_pct??r.cagr)},
      {label:"Sharpe",render:r=>number(r.sharpe_ratio??r.sharpe)},
      {label:"Drawdown",render:r=>pct(r.max_drawdown_pct??r.max_drawdown,true)},
    ]),`${data.assets_requested} ativo(s), ${data.strategies_requested} estratégia(s) • uso diário ${data.daily_used}/${data.daily_limit}`)+(data.failures?.length?`<div class="notice" style="margin-top:12px">${data.failures.length} ativo(s) não puderam ser processados nesta rodada.</div>`:"");
    toast("Comparação concluída e salva no histórico.","success");
  } catch(error) { result.innerHTML=errorState(error); }
}

async function loadAdmin() {
  const root=$("#admin-tab-content"); root.innerHTML=loadingCards(6);
  try {
    if(state.tabs.admin==="users") {
      const users=await api("/access/users");
      const body=`<div class="table-scroll"><table><thead><tr><th>Usuário</th><th>Status</th><th>Executa backtests</th><th>Ativos por análise</th><th>Análises por dia</th><th>Alertas</th><th></th></tr></thead><tbody>${users.map(user=>`<tr data-user-row="${esc(user.email)}"><td><strong>${esc(user.display_name||user.email)}</strong><br><small>${esc(user.email)}</small></td><td>${user.is_owner?'<span class="pill">Permanente</span>':`<select data-user-field="status"><option value="pending" ${user.status==="pending"?"selected":""}>Pendente</option><option value="approved" ${user.status==="approved"?"selected":""}>Aprovado</option><option value="blocked" ${user.status==="blocked"?"selected":""}>Bloqueado</option></select>`}</td><td>${user.is_owner?"Sim":`<label class="check"><input type="checkbox" data-user-field="can_run_backtests" ${user.can_run_backtests?"checked":""}> Permitir</label>`}</td><td>${user.is_owner?"30":`<select data-user-field="backtest_asset_limit">${[0,1,3,5,10,20,30].map(value=>`<option value="${value}" ${Number(user.backtest_asset_limit||0)===value?"selected":""}>${value}</option>`).join("")}</select>`}</td><td>${user.is_owner?"30":`<select data-user-field="backtest_daily_limit">${[0,1,5,10,20,30].map(value=>`<option value="${value}" ${Number(user.backtest_daily_limit||0)===value?"selected":""}>${value}</option>`).join("")}</select>`}</td><td>${number(user.alert_asset_limit||0,0)}</td><td>${user.is_owner?"":`<button class="button secondary" data-save-user="${esc(user.email)}">Salvar</button>`}</td></tr>`).join("")}</tbody></table></div>`;
      root.innerHTML=sectionCard("Usuários e permissões",body,"Os limites de backtest podem ser 1, 3, 5, 10, 20 ou 30 ativos e 1, 5, 10, 20 ou 30 análises por dia.");
    } else if(state.tabs.admin==="data") {
      const summary=await api("/data/catalog-summary");
      const counts=summary.counts||{}, groups=summary.groups||{};
      root.innerHTML=`<div class="metric-grid">${metricCard("Ações",number(groups.stock||0,0),"Ativos ativos")}${metricCard("FIIs",number(groups.fii||0,0),"Fundos imobiliários")}${metricCard("ETFs",number(counts.etf||0,0),"Fundos de índice")}${metricCard("BDRs",number(counts.bdr||0,0),"Recibos negociados na B3")}</div>
        ${sectionCard("Atualizar catálogos",`<div class="action-grid">
          <button class="button secondary" data-market-sync="stock" data-technicals="false">Atualizar Ações</button>
          <button class="button primary" data-market-sync="fii" data-technicals="false">Atualizar FIIs</button>
          <button class="button secondary" data-market-sync="other_b3" data-technicals="true">Atualizar ETFs, BDRs e futuros</button>
          <button class="button ghost" data-market-sync="fii" data-technicals="true">Atualização completa dos FIIs</button>
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
  const payload={
    status:value("status")?.value,
    can_run_backtests:canRun,
    can_view_backtests:canRun,
    backtest_asset_limit:canRun?Number(value("backtest_asset_limit")?.value||1):0,
    backtest_daily_limit:canRun?Number(value("backtest_daily_limit")?.value||1):0,
  };
  try{await api(`/access/users/${encodeURIComponent(email)}`,{method:"PUT",body:JSON.stringify(payload)});toast("Permissões atualizadas.","success");loadAdmin();}
  catch(error){toast(error.message,"error");}
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
  $$(".tabs").forEach(tabs=>tabs.addEventListener("click",event=>{const button=event.target.closest(".tab");if(button){activateTab(tabs.dataset.tabs,button.dataset.tab);if(tabs.dataset.tabs==="analysis")updateFilterAvailability();}}));
  $("#refresh-market").addEventListener("click",()=>loadMarket(true));
  $("#logout-button").addEventListener("click",async()=>{try{await api("/logout",{method:"POST"});location.href=BASE_PATH||"/";}catch(error){toast(error.message,"error");}});
  $("#global-search").addEventListener("input",event=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>runSearch(event.target.value),220);});
  document.addEventListener("keydown",event=>{if(event.key==="/"&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)){event.preventDefault();$("#global-search").focus();}});
  document.addEventListener("click",event=>{
    const result=event.target.closest("[data-search-item]"); if(result){try{chooseSearchResult(JSON.parse(result.dataset.searchItem));}catch(_){}}
    const ticker=event.target.closest("tr[data-ticker]")?.dataset.ticker;if(ticker)openAsset(ticker);
    const retry=event.target.closest("[data-retry]")?.dataset.retry;if(retry){if(retry==="market")loadMarket(true);else loadCurrentView();}
    const linked=event.target.closest("[data-view-link]");if(linked)setView(linked.dataset.viewLink,linked.dataset.tabLink||null);
    const curve=event.target.closest("[data-curve-years]");if(curve){state.curveYears=Number(curve.dataset.curveYears);renderDashboardTab();}
    const saveUser=event.target.closest("[data-save-user]");if(saveUser)saveUserAccess(saveUser.dataset.saveUser);
    const marketSync=event.target.closest("[data-market-sync]");if(marketSync)syncMarketCatalog(marketSync.dataset.marketSync,marketSync.dataset.technicals==="true");
    if(!event.target.closest(".global-search-wrap"))$("#search-results").classList.add("hidden");
  });
  $("#close-asset-dialog").addEventListener("click",()=>$("#asset-dialog").close());
  $("#asset-dialog").addEventListener("click",event=>{if(event.target===$("#asset-dialog"))$("#asset-dialog").close();});
  $$(".preset-button").forEach(button=>button.addEventListener("click",()=>{
    const map={padrao:"default",cnpi:"cnpi",alb:"alb"}; if(!map[button.dataset.preset]){toast("Seus filtros personalizados ficam vinculados à sua conta.");return;}
    state.analysisPreset=map[button.dataset.preset]; resetAdvancedFilters(); $$(".preset-button").forEach(b=>b.classList.toggle("active",b===button)); loadAnalysis();
  }));
  $("#apply-advanced-filters").addEventListener("click",applyAdvancedFilters);
  document.addEventListener("change",event=>{
    if(event.target.id==="portfolio-selector"){state.portfolioId=event.target.value;renderPortfolioTab();}
    if(event.target.id==="analysis-limit"){state.analysisLimit=Number(event.target.value);$("#analysis-limit-label").textContent=state.analysisLimit;}
    if(event.target.matches("[data-column-id]")){
      const type=analysisType(),columns=analysisColumns(type).filter(column=>!column.always);
      state.visibleColumns[type]=columns.filter(column=>$(`[data-column-id="${column.id}"]`)?.checked).map(column=>column.id);
      localStorage.setItem("fdi-visible-columns",JSON.stringify(state.visibleColumns));renderAnalysisRows(state.analysisRows);
    }
  });
  document.addEventListener("submit",event=>{if(event.target.id==="backtest-form"){event.preventDefault();runBacktest(event.target);}});
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
