"use strict";

const BASE_PATH = location.pathname === "/testefdi" || location.pathname.startsWith("/testefdi/") ? "/testefdi" : "";
const LANDING_PATH = `${BASE_PATH}/`;
const PLATFORM_PATH = `${BASE_PATH}/plataforma/`;
const ANALYSIS_CACHE_TTL_MS = 300000;
const NEWS_NAVIGATION_CACHE_TTL_MS = 15000;
const ADMIN_NAVIGATION_CACHE_TTL_MS = 30000;
const PANEL_REVALIDATE_DELAY_MS = 80;
const PANEL_SURFACE_LIMIT = 36;
const READ_CACHE_LIMIT = 192;
const ANALYSIS_RESULT_CACHE_LIMIT = 24;
const PANEL_FRESHNESS_MS = Object.freeze({
  dashboard:60000,
  analysis:120000,
  portfolio:120000,
  finances:120000,
  backtests:60000,
  admin:30000,
});

const state = {
  session: null,
  view: "dashboard",
  tabs: { dashboard: "overview", analysis: "stocks", analysisMode: "list", portfolio: "positions", finances: "monthly", backtests: "history", admin: "levels" },
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
  analysisColumnCatalog: {},
  analysisLoadedType: null,
  analysisCustom: [],
  analysisCustomCache: {},
  analysisCustomUsageCache: {},
  analysisCustomUsage: {used:0,limit:0},
  currentCustomFilter: null,
  analysisLimit: 50,
  analysisResultCache: new Map(),
  analysisRequestSerial: 0,
  navigationSerial: 0,
  portfolioListRequestSerial: 0,
  portfolioRequestSerial: 0,
  financeRequestSerial: 0,
  backtestRequestSerial: 0,
  adminRequestSerial: 0,
  assetRequestSerial: 0,
  analysisUpdateCheckedAt: 0,
  analysisEnsureSentAt: 0,
  refreshEnsureSentAt: {},
  readCache: new Map(),
  readRequests: new Map(),
  curveYears: 10,
  curveHistory: [],
  curveHistoryCount: 1,
  curveHistoryLoading: false,
  curveHistoryLoaded: false,
  visibleColumns: JSON.parse(localStorage.getItem("fdi-visible-columns") || "{}"),
  visibleColumnsStorageKey: "fdi-visible-columns",
  portfolios: [],
  portfolioId: null,
  portfolioAllocationType: null,
  portfolioAllocationHierarchy: null,
  portfolioNewsMode: "portfolio",
  recommendationCategory: "all",
  newsRefreshTimer: null,
  alertCatalog: null,
  alertData: null,
  alertSuggestionTimer: null,
  adminUsersOffset: 0,
  adminUsersQuery: "",
  adminUsersStatus: "",
  adminUsersLevel: "",
  financeMonth: new Date().toISOString().slice(0,7),
  officialBacktestJobs: new Map(),
  backtestCatalog: null,
  requestControllers: new Map(),
  navigationTimers: new Set(),
  emailLoginAddress: "",
  portalAdmin: null,
  adminAnalysisSettings: null,
  adminAnalysisType: "stock",
  panelSurfaceCache: new Map(),
  panelFreshness: new Map(),
  viewScroll: new Map(),
  analysisFormState: new Map(),
  analysisLastUpdatedAt: {},
  analysisSort: {},
  analysisDensity: localStorage.getItem("fdi-analysis-density") === "compact" ? "compact" : "comfortable",
  navigationStorageKey: "fdi-last-navigation",
  currentAssetTicker: null,
  applyingHistory: false,
  lastNavigationKind: "initial",
  dashboardCheckedAt: 0,
};


const FEATURE_ASSET_VERSION="1.23.8-r1b";
const FEATURE_SCRIPT_PATHS={
  analysis:`${BASE_PATH}/ui-assets/feature-analysis.js?v=${FEATURE_ASSET_VERSION}`,
  portfolio:`${BASE_PATH}/ui-assets/feature-portfolio.js?v=${FEATURE_ASSET_VERSION}`,
  backtests:`${BASE_PATH}/ui-assets/feature-backtests.js?v=${FEATURE_ASSET_VERSION}`,
  finances:`${BASE_PATH}/ui-assets/feature-finances.js?v=${FEATURE_ASSET_VERSION}`,
  admin:`${BASE_PATH}/ui-assets/feature-admin.js?v=${FEATURE_ASSET_VERSION}`,
};
const FEATURE_BY_VIEW={analysis:"analysis",portfolio:"portfolio",backtests:"backtests",finances:"finances",admin:"admin"};
const featureLoads=new Map();
window.FDIFeatures=window.FDIFeatures||{};

function loadFeature(name){
  if(window.FDIFeatures[name])return Promise.resolve(window.FDIFeatures[name]);
  if(featureLoads.has(name))return featureLoads.get(name);
  const source=FEATURE_SCRIPT_PATHS[name];
  if(!source)return Promise.reject(new Error(`Módulo desconhecido: ${name}`));
  const pending=new Promise((resolve,reject)=>{
    const script=document.createElement("script");
    script.src=source;script.async=true;script.dataset.feature=name;
    script.onload=()=>{
      const loaded=window.FDIFeatures[name];
      if(loaded)resolve(loaded);
      else reject(new Error(`O módulo ${name} não foi registrado.`));
    };
    script.onerror=()=>reject(new Error(`Não foi possível carregar o módulo ${name}.`));
    document.head.append(script);
  }).catch(error=>{featureLoads.delete(name);throw error;});
  featureLoads.set(name,pending);
  return pending;
}

async function invokeFeature(name,method,...args){
  const loaded=await loadFeature(name),handler=loaded?.[method];
  if(typeof handler!=="function")throw new Error(`A função ${method} não está disponível no módulo ${name}.`);
  return handler(...args);
}

function prefetchFeature(name){scheduleIdleTask(()=>loadFeature(name).catch(()=>{}),2400);}

async function loadFeaturePanel(name,method,selector,args=[]){
  const root=$(selector);
  if(root&&!root.childElementCount)root.innerHTML=loadingCards(4);
  try{return await invokeFeature(name,method,...args);}
  catch(error){if(root)root.innerHTML=errorState(error);else toast(error.message,"error");return null;}
}

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

const CACHE_TAG_PREFIXES = [
  ["/portfolios",["portfolio"]],["/alerts",["portfolio"]],["/investor-events/dividends",["portfolio"]],
  ["/finances",["finances"]],["/backtests",["backtests","analysis"]],
  ["/screen",["analysis"]],["/assets",["analysis"]],["/search",["analysis"]],
  ["/market-dashboard",["dashboard","analysis"]],["/prices",["dashboard","portfolio","analysis"]],
  ["/access",["admin","session"]],["/admin/portal",["admin","portal"]],["/admin",["admin"]],
  ["/news",["portfolio"]],["/insights",["portfolio"]],["/session",["session"]],
];

function cacheTagsForPath(path){
  const clean=String(path||"").split("?",1)[0];
  const matched=CACHE_TAG_PREFIXES.filter(([prefix])=>clean.startsWith(prefix)).flatMap(([,tags])=>tags);
  return [...new Set(matched.length?matched:["shared"])];
}

function setBoundedCache(cache,key,value,limit){
  if(cache.has(key))cache.delete(key);
  cache.set(key,value);
  while(cache.size>limit)cache.delete(cache.keys().next().value);
  return value;
}

function panelFreshnessKey(group,tab=state.tabs[group]){
  return panelSurfaceKey(group,tab);
}

function markPanelFresh(group,tab=state.tabs[group]){
  state.panelFreshness.set(panelFreshnessKey(group,tab),Date.now());
}

function panelNeedsRevalidation(group,tab=state.tabs[group]){
  const savedAt=Number(state.panelFreshness.get(panelFreshnessKey(group,tab))||0);
  return !savedAt||Date.now()-savedAt>=Number(PANEL_FRESHNESS_MS[group]||60000);
}

function invalidatePanelFreshness(tags){
  const requested=new Set((Array.isArray(tags)?tags:[tags]).filter(Boolean));
  for(const key of state.panelFreshness.keys()){
    const group=String(key).split(":",1)[0];
    if(requested.has("all")||requested.has(group))state.panelFreshness.delete(key);
  }
}

function invalidateApplicationCache(tags){
  const requested=new Set((Array.isArray(tags)?tags:[tags]).filter(Boolean));
  if(!requested.size)return;
  for(const [path,item] of state.readCache.entries()){
    const itemTags=item.tags||cacheTagsForPath(path);
    if(itemTags.some(tag=>requested.has(tag)||requested.has("all")))state.readCache.delete(path);
  }
  const groupTags={dashboard:"dashboard",analysis:"analysis",portfolio:"portfolio",finances:"finances",backtests:"backtests",admin:"admin"};
  for(const key of state.panelSurfaceCache.keys()){
    const group=String(key).split(":",1)[0];
    if(requested.has("all")||requested.has(groupTags[group]))state.panelSurfaceCache.delete(key);
  }
  if(requested.has("all")||requested.has("analysis")||requested.has("backtests"))state.analysisResultCache.clear();
  if(requested.has("all")||requested.has("admin")){state.adminAnalysisSettings=null;state.portalAdmin=null;}
  invalidatePanelFreshness([...requested]);
}

const panelSurfaceRoots={
  dashboard:"#dashboard-tab-content",analysis:"#analysis-table",portfolio:"#portfolio-tab-content",
  finances:"#finances-tab-content",backtests:"#backtests-tab-content",admin:"#admin-tab-content",
};

function panelSurfaceKey(group,tab=state.tabs[group]){
  if(group==="portfolio")return `${group}:${state.portfolioId||"none"}:${tab}`;
  if(group==="finances")return `${group}:${state.financeMonth}:${tab}`;
  return `${group}:${tab}`;
}

function capturePanelSurface(group,tab=state.tabs[group]){
  const root=$(panelSurfaceRoots[group]);
  if(!root?.childElementCount)return false;
  const fragment=document.createDocumentFragment();
  const scrollPositions=[...root.querySelectorAll(".table-scroll")].map(node=>({top:node.scrollTop,left:node.scrollLeft}));
  while(root.firstChild)fragment.append(root.firstChild);
  const dataset={...root.dataset};
  state.panelSurfaceCache.set(panelSurfaceKey(group,tab),{fragment,dataset,scrollPositions,savedAt:Date.now()});
  while(state.panelSurfaceCache.size>PANEL_SURFACE_LIMIT)state.panelSurfaceCache.delete(state.panelSurfaceCache.keys().next().value);
  return true;
}

function restorePanelSurface(group,tab=state.tabs[group]){
  const root=$(panelSurfaceRoots[group]),key=panelSurfaceKey(group,tab),saved=state.panelSurfaceCache.get(key);
  if(!root||!saved)return false;
  state.panelSurfaceCache.delete(key);
  root.replaceChildren(saved.fragment);
  Object.keys(root.dataset).forEach(name=>delete root.dataset[name]);
  Object.assign(root.dataset,saved.dataset||{});
  root.classList.remove("panel-refreshing");
  requestAnimationFrame(()=>[...root.querySelectorAll(".table-scroll")].forEach((node,index)=>{const position=saved.scrollPositions?.[index];if(position){node.scrollTop=position.top;node.scrollLeft=position.left;}}));
  return true;
}

function viewHasRenderedContent(view){
  if(view==="dashboard")return Boolean(state.market&&$(panelSurfaceRoots.dashboard)?.childElementCount);
  return Boolean($(panelSurfaceRoots[view])?.childElementCount);
}

function relativeUpdateLabel(value){
  if(!value)return "Atualização ainda não registrada";
  const seconds=Math.max(0,Math.round((Date.now()-Number(value))/1000));
  if(seconds<10)return "Atualizado agora";
  if(seconds<60)return `Atualizado há ${seconds} s`;
  const minutes=Math.round(seconds/60);if(minutes<60)return `Atualizado há ${minutes} min`;
  const hours=Math.round(minutes/60);return `Atualizado há ${hours} h`;
}

function toast(message, type = "") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  $("#toast-region").append(node);
  setTimeout(() => node.remove(), 5200);
}

const panelRequestKeys={
  dashboard:["market-get","comparison","official-calendar","relevant-facts","headlines"],
  analysis:["analysis","analysis-backtests","asset-detail"],
  portfolio:["portfolios","portfolio-detail","portfolio-catalog","portfolio-news","portfolio-alerts","alert-suggestions","dividends-"],
  finances:["finances","finance-catalog"],
  backtests:["backtests","backtests-"],
  admin:["admin-"],
};

function abortRequestGroups(groups){
  const prefixes=groups.flatMap(group=>panelRequestKeys[group]||[]);
  for(const [key,controller] of state.requestControllers.entries()){
    if(prefixes.some(prefix=>key===prefix||key.startsWith(prefix))){controller.abort();state.requestControllers.delete(key);}
  }
}

function beginNavigation(previousView,nextView){
  state.navigationSerial+=1;
  for(const timer of state.navigationTimers)clearTimeout(timer);
  state.navigationTimers.clear();
  clearTimeout(state.newsRefreshTimer);state.newsRefreshTimer=null;
  clearTimeout(state.alertSuggestionTimer);state.alertSuggestionTimer=null;
  if(typeof searchTimer!=="undefined"){clearTimeout(searchTimer);searchTimer=null;}
  if(previousView)abortRequestGroups([previousView]);
  if(previousView===nextView)abortRequestGroups([nextView]);
  state.requestControllers.get("search")?.abort();
}

function navigationIsCurrent(serial,view,tabGroup=null,tab=null){
  return serial===state.navigationSerial&&state.view===view&&(!tabGroup||state.tabs[tabGroup]===tab);
}

function scheduleIdleTask(callback,timeout=1800){
  if("requestIdleCallback" in window)window.requestIdleCallback(()=>callback(),{timeout});
  else setTimeout(callback,Math.min(timeout,1200));
}

function scheduleNavigationTask(callback,delay,serial=state.navigationSerial){
  const timer=setTimeout(()=>{
    state.navigationTimers.delete(timer);
    if(serial!==state.navigationSerial)return;
    try{Promise.resolve(callback()).catch(()=>{});}catch(_){/* tarefa de interface obsoleta ou opcional */}
  },delay);
  state.navigationTimers.add(timer);
  return timer;
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
    invalid_secondary_email:"Informe um segundo e-mail válido ou deixe o campo vazio.",
    price_alert_limit_not_granted:"Sua conta ainda não possui uma quantidade de ativos liberada para alertas.",
    price_alert_requires_condition:"Preencha ao menos uma condição para este ativo.",
    unsupported_market_alert_symbol:"Escolha um dos ativos disponíveis no catálogo de mercados.",
    b3_alert_asset_not_found:"Este código não está disponível no catálogo principal da B3.",
    alert_email_delivery_not_configured:"O envio de e-mails ainda não foi configurado pelo administrador.",
    price_alert_not_found:"Este alerta não existe mais ou pertence a outra conta.",
    access_level_not_found:"O nível de acesso selecionado não foi encontrado.",
    access_level_is_inactive:"Este nível está inativo e não pode receber novos usuários.",
    access_level_already_exists:"Já existe um nível com esse identificador.",
    owner_permissions_are_permanent:"As permissões do proprietário são permanentes.",
    owner_access_level_is_permanent:"O nível do proprietário é permanente.",
    access_level_required_for_overrides:"Atribua um nível antes de criar ajustes individuais.",
    background_job_not_found:"Este trabalho não está mais disponível na fila.",
    email_login_rate_limited:"Aguarde um minuto antes de solicitar um novo código.",
    email_login_temporarily_limited:"Foram solicitados muitos códigos nesta conexão. Aguarde alguns minutos e tente novamente.",
    email_login_code_invalid_or_expired:"O código é inválido, expirou ou já foi utilizado. Solicite outro se necessário.",
    email_login_delivery_not_configured:"O acesso por e-mail ainda não foi configurado pelo administrador.",
    email_login_delivery_failed:"Não foi possível enviar o código agora. Tente novamente em instantes.",
    portal_page_revision_conflict:"A página foi alterada em outra sessão. Recarregue esta área antes de salvar novamente.",
    portal_book_slug_exists:"Já existe um livro com esse identificador.",
    portal_book_not_found:"Este livro não foi encontrado.",
    portal_media_not_found:"A imagem selecionada não foi encontrada.",
    portal_media_in_use:"Esta imagem ainda está vinculada a um livro.",
    portal_sales_link_limit:"Cada livro aceita no máximo três links de venda.",
    portal_https_url_invalid:"Os links de venda devem começar com https:// e não podem conter credenciais.",
    portal_image_size_invalid:"A imagem deve ter no máximo 4 MB.",
    portal_image_signature_invalid:"O conteúdo da imagem não corresponde ao tipo PNG, JPG ou WebP informado.",
  };
  if(typeof detail==="object"&&detail?.permission_required)return messages.permission_required;
  if(typeof detail==="object"&&detail?.code==="official_batch_cooldown")return `Aguarde até ${dateTime(detail.next_allowed_at)} para iniciar outra rodada oficial completa.`;
  if(typeof detail==="object"&&detail?.price_alert_limit_reached)return `O limite de ${detail.price_alert_limit_reached} ativo(s) com alerta foi atingido.`;
  if(typeof detail==="object"&&detail?.alert_conditions_not_granted)return "Uma das condições escolhidas não está liberada para sua conta.";
  if(code.startsWith("batch_job_active:"))return "Já existe uma rodada oficial em andamento. Aguarde a conclusão.";
  if(messages[code])return messages[code];
  if(status>=500)return "O serviço está temporariamente indisponível. Seus dados foram preservados; tente novamente em instantes.";
  if(status===404)return "A informação solicitada não foi encontrada.";
  if(status===422)return "Revise os campos informados e tente novamente.";
  return code||`Não foi possível concluir a solicitação (HTTP ${status}).`;
}

async function api(path, options = {}) {
  const requestOptions = {...options};
  const cacheTtlMs = Math.max(0, Number(requestOptions.cacheTtlMs || 0));
  const bypassCache = Boolean(requestOptions.bypassCache);
  const invalidateCache = requestOptions.invalidateCache !== false;
  const invalidateTags = requestOptions.invalidateTags || cacheTagsForPath(path);
  delete requestOptions.cacheTtlMs;
  delete requestOptions.bypassCache;
  delete requestOptions.invalidateCache;
  delete requestOptions.invalidateTags;
  const method = String(requestOptions.method || "GET").toUpperCase();
  if (method === "GET" && cacheTtlMs > 0 && !bypassCache) {
    const cached = state.readCache.get(path);
    if (cached && Date.now() - cached.savedAt < cacheTtlMs) return cached.body;
  }
  const key = requestOptions.requestKey;
  const coalesceKey = method === "GET" && !bypassCache ? `${key?`key:${key}`:"path"}:${path}` : null;
  if (coalesceKey && state.readRequests.has(coalesceKey)) return state.readRequests.get(coalesceKey);
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
  const pending = (async()=>{
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
    if (method === "GET" && cacheTtlMs > 0) setBoundedCache(state.readCache,path,{savedAt:Date.now(),body,tags:cacheTagsForPath(path)},READ_CACHE_LIMIT);
    else if (method !== "GET" && invalidateCache) invalidateApplicationCache(invalidateTags);
    return body;
  })();
  if (coalesceKey) state.readRequests.set(coalesceKey,pending);
  try { return await pending; }
  finally { if(coalesceKey&&state.readRequests.get(coalesceKey)===pending)state.readRequests.delete(coalesceKey); }
}

function reportPanelPerformance(panel,started,{success=true,cacheState="cold"}={}){
  const duration=Math.max(0,performance.now()-Number(started||performance.now()));
  const vitals=window.FDIWebVitals?.snapshot?.()||{};
  const width=Math.max(document.documentElement.clientWidth||0,window.innerWidth||0);
  const deviceClass=width<760?"mobile":width<1100?"tablet":"desktop";
  fetch(`${BASE_PATH}/operations/client-performance`,{
    method:"POST",credentials:"same-origin",keepalive:true,
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({
      panel,duration_ms:Math.round(duration*100)/100,success,cache_state:cacheState,
      device_class:deviceClass,navigation_kind:state.lastNavigationKind,tab:state.tabs[panel]||null,
      lcp_ms:vitals.lcp_ms??null,inp_ms:vitals.inp_ms??null,cls:vitals.cls??null,
    }),
  }).catch(()=>{});
}

function safeExternalUrl(value) {
  try { const url=new URL(String(value||"")); return ["http:","https:"].includes(url.protocol)?url.href:"#"; }
  catch (_) { return "#"; }
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
  $("#profile-role").textContent = access.is_owner ? "Administrador master" : access.access_level_name || (access.access_inheritance?"Acesso por nível":"Acesso personalizado");
  const avatar = $("#profile-avatar");
  avatar.textContent = (user.name || user.email || "U").slice(0, 1).toUpperCase();
  if (user.picture) avatar.innerHTML = `<img src="${esc(user.picture)}" alt="">`;
  state.visibleColumnsStorageKey=`fdi-visible-columns:${String(user.email||"anonymous").trim().toLowerCase()}`;
  state.navigationStorageKey=`fdi-last-navigation:${String(user.email||"anonymous").trim().toLowerCase()}`;
  const personalColumns=localStorage.getItem(state.visibleColumnsStorageKey);
  if(personalColumns){try{state.visibleColumns=JSON.parse(personalColumns)||{};}catch(_){state.visibleColumns={};}}
  else {localStorage.setItem(state.visibleColumnsStorageKey,JSON.stringify(state.visibleColumns||{}));}
  $$(".owner-only").forEach(node => node.classList.toggle("hidden", !access.is_owner));
  $$(".permission-study").forEach(node => node.classList.toggle("hidden", !access.can_view_backtest_studies));
  const canAdmin=Boolean(access.is_owner||access.can_manage_users||access.can_sync_market||access.can_manage_portal);
  const navRules = {
    analysis: access.can_view_market,
    portfolio: access.can_view_portfolio,
    finances: access.can_view_finances,
    backtests: access.can_view_backtests,
    admin: canAdmin,
  };
  Object.entries(navRules).forEach(([view, allowed]) => {
    const item = $(`.nav-item[data-view="${view}"]`);
    if (item) item.classList.toggle("hidden", !allowed);
  });
  const adminItem=$('.nav-item[data-view="admin"]');
  if(adminItem)adminItem.classList.toggle("hidden",!canAdmin);
  for(const tab of ["levels","users"]){const node=$(`.tabs[data-tabs="admin"] [data-tab="${tab}"]`);if(node)node.classList.toggle("hidden",!(access.is_owner||access.can_manage_users));}
  for(const tab of ["data","quality"]){const node=$(`.tabs[data-tabs="admin"] [data-tab="${tab}"]`);if(node)node.classList.toggle("hidden",!(access.is_owner||access.can_sync_market));}
  const portalTab=$('.tabs[data-tabs="admin"] [data-tab="portal"]');
  if(portalTab)portalTab.classList.toggle("hidden",!(access.is_owner||access.can_manage_portal));
  for(const tab of ["analysis-settings","jobs","operations","system"]){const node=$(`.tabs[data-tabs="admin"] [data-tab="${tab}"]`);if(node)node.classList.toggle("hidden",!access.is_owner);}
  $$(".admin-nav-group").forEach(group=>group.classList.toggle("hidden",!group.querySelector(".tab:not(.hidden)")));
  if(!access.is_owner&&!access.can_manage_users){
    state.tabs.admin=access.can_manage_portal?"portal":"data";
    activateTab("admin",state.tabs.admin,false);
  }
}

function persistVisibleColumns(){localStorage.setItem(state.visibleColumnsStorageKey,JSON.stringify(state.visibleColumns));}

function emailLoginMessage(message,type=""){
  const node=$("#email-login-message");
  if(!node)return;
  node.textContent=message;
  node.className=`login-message${type?` ${type}`:""}`;
}

async function requestEmailLogin(form){
  const button=form.querySelector('button[type="submit"]');
  const email=String(new FormData(form).get("email")||"").trim().toLowerCase();
  button.disabled=true;
  try{
    await api("/auth/email/request",{method:"POST",body:JSON.stringify({email,next:PLATFORM_PATH}),invalidateCache:false});
    state.emailLoginAddress=email;
    $("#email-login-verify-form")?.classList.remove("hidden");
    emailLoginMessage("Código enviado. Ele vale por 10 minutos e o envio de um novo código invalida o anterior.");
    $("#email-login-code")?.focus();
    let remaining=60;
    const original=button.textContent;
    button.textContent=`Reenviar em ${remaining}s`;
    const timer=setInterval(()=>{
      remaining-=1;
      button.textContent=remaining>0?`Reenviar em ${remaining}s`:"Enviar novo código";
      if(remaining<=0){clearInterval(timer);button.disabled=false;button.textContent="Enviar novo código";}
    },1000);
    setTimeout(()=>{if(!button.isConnected)clearInterval(timer);},61000);
  }catch(error){button.disabled=false;emailLoginMessage(error.message,"error");}
}

async function verifyEmailLogin(form){
  const button=form.querySelector('button[type="submit"]');
  const code=String(new FormData(form).get("code")||"").replace(/\D/g,"");
  const email=state.emailLoginAddress||String($("#email-login-address")?.value||"").trim().toLowerCase();
  button.disabled=true;
  try{
    const result=await api("/auth/email/verify",{method:"POST",body:JSON.stringify({email,code,next:PLATFORM_PATH}),invalidateCache:false});
    emailLoginMessage("Código confirmado. Abrindo a plataforma…");
    location.assign(result.destination||PLATFORM_PATH);
  }catch(error){button.disabled=false;emailLoginMessage(error.message,"error");$("#email-login-code")?.select();}
}

const analysisTypeTabs={stock:"stocks",fii:"fiis",etf:"etfs",bdr:"bdrs",future:"futures"};
const analysisTabTypes=Object.fromEntries(Object.entries(analysisTypeTabs).map(([type,tab])=>[tab,type]));

function navigationStateFromLocation(){
  const params=new URLSearchParams(location.search),view=params.get("view")||null;
  const result={view,tab:params.get("tab")||null,asset:params.get("asset")||null};
  if(view==="analysis")result.tab=analysisTypeTabs[params.get("type")]||result.tab;
  return result;
}

function navigationIsAllowed(view,tab=null){
  const nav=$(`.nav-item[data-view="${CSS.escape(view||"")}"]`);
  if(!nav||nav.classList.contains("hidden"))return false;
  if(!tab)return true;
  const button=$(`.tabs[data-tabs="${CSS.escape(view)}"] [data-tab="${CSS.escape(tab)}"]`);
  return Boolean(button&&!button.classList.contains("hidden"));
}

function persistNavigationState(){
  if(!state.session?.user)return;
  const payload={view:state.view,tabs:state.tabs,financeMonth:state.financeMonth};
  try{localStorage.setItem(state.navigationStorageKey,JSON.stringify(payload));}catch(_){/* armazenamento opcional */}
}

function syncNavigationUrl(mode="push"){
  if(mode==="none"||state.applyingHistory)return;
  const url=new URL(location.href),params=url.searchParams;
  params.set("view",state.view);
  params.delete("type");params.delete("tab");params.delete("mode");
  if(state.view==="analysis"){
    params.set("type",analysisTabTypes[state.tabs.analysis]||"stock");
    if(state.tabs.analysisMode!=="list")params.set("mode",state.tabs.analysisMode);
  }else if(state.tabs[state.view])params.set("tab",state.tabs[state.view]);
  if(state.view==="finances")params.set("month",state.financeMonth);else params.delete("month");
  if(state.currentAssetTicker)params.set("asset",state.currentAssetTicker);else params.delete("asset");
  history[mode==="replace"?"replaceState":"pushState"]({view:state.view,tab:state.tabs[state.view]||null,asset:state.currentAssetTicker},"",url);
  persistNavigationState();
}

function updateNavigationAccessibility(){
  $$(".nav-item[data-view]").forEach(node=>node.setAttribute("aria-current",node.dataset.view===state.view?"page":"false"));
  $$(".tabs[data-tabs]").forEach(container=>{
    container.setAttribute("role","tablist");
    container.querySelectorAll(".tab").forEach(node=>{
      const selected=state.tabs[container.dataset.tabs]===node.dataset.tab;
      node.setAttribute("role","tab");node.setAttribute("aria-selected",String(selected));node.tabIndex=selected?0:-1;
    });
  });
}

function captureAnalysisFormState(tab=state.tabs.analysis){
  if(!$("#analysis-limit")||!state.session)return;
  try{
    state.analysisFormState.set(tab,{
      configuration:analysisRequestFromForm(),preset:state.analysisPreset,
      customFilterId:state.currentCustomFilter?.id||null,limit:state.analysisLimit,
      drawerOpen:Boolean($(".filter-drawer")?.open),
    });
  }catch(_){/* o formulário pode estar sendo reconstruído */}
}

function restoreAnalysisFormState(tab=state.tabs.analysis){
  const saved=state.analysisFormState.get(tab);if(!saved)return false;
  const custom=state.analysisCustom.find(item=>item.id===saved.customFilterId)||null;
  state.analysisLimit=Number(saved.limit||50);fillAnalysisForm(saved.configuration||{});
  markActiveAnalysis(custom?{custom}:{presetId:saved.preset||"default"});
  if($(".filter-drawer"))$(".filter-drawer").open=Boolean(saved.drawerOpen);
  return true;
}

function setView(view, tab = null, {force=false,historyMode="push"} = {}) {
  const sameView=state.view===view;
  const sameTab=!tab||state.tabs[view]===tab;
  if(sameView&&sameTab&&!force){document.body.classList.remove("mobile-nav-open");return false;}
  const previousView=state.view;
  state.viewScroll.set(previousView,window.scrollY);
  beginNavigation(previousView,view);
  state.view = view;
  if (tab) state.tabs[view] = tab;
  $$(".view").forEach(node => node.classList.toggle("active", node.id === `view-${view}`));
  $$(".nav-item").forEach(node => node.classList.toggle("active", node.dataset.view === view));
  document.body.classList.remove("mobile-nav-open");
  if (tab) activateTab(view, tab, false);
  if(view==="analysis")activateTab("analysisMode",state.tabs.analysisMode,false);
  const warm=viewHasRenderedContent(view);
  state.lastNavigationKind=historyMode==="none"?"history":warm?"return":"switch";
  updateNavigationAccessibility();syncNavigationUrl(historyMode);
  requestAnimationFrame(()=>window.scrollTo({top:state.viewScroll.get(view)||0,behavior:"auto"}));
  if(force||!warm)loadCurrentView();
  else if(panelNeedsRevalidation(view))scheduleNavigationTask(()=>loadCurrentView(),PANEL_REVALIDATE_DELAY_MS);
  return true;
}

function activateTab(group, tab, load = true, {force=false,historyMode="push"} = {}) {
  if(load&&state.tabs[group]===tab&&!force)return false;
  const previousTab=state.tabs[group];
  if(load){
    if(group==="analysis")captureAnalysisFormState(previousTab);
    if(panelSurfaceRoots[group])capturePanelSurface(group,previousTab);
    beginNavigation(state.view,state.view);
  }
  state.tabs[group] = tab;
  $$(`.tabs[data-tabs="${group}"] .tab`).forEach(node => node.classList.toggle("active", node.dataset.tab === tab));
  const restored=load&&panelSurfaceRoots[group]?restorePanelSurface(group,tab):false;
  if(load){
    state.lastNavigationKind=historyMode==="none"?"history":restored?"return":"switch";
    updateNavigationAccessibility();syncNavigationUrl(historyMode);
    if(force||!restored)loadCurrentView();
    else if(panelNeedsRevalidation(group,tab))scheduleNavigationTask(()=>loadCurrentView(),PANEL_REVALIDATE_DELAY_MS);
  }
  return true;
}

function loadingCards(count = 4) {
  return `<div class="loading-grid" role="status" aria-live="polite"><span class="sr-only">Carregando dados do painel…</span>${Array.from({length: count}, () => '<div class="skeleton" aria-hidden="true"></div>').join("")}</div>`;
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
    loadOfficialCalendar();
  } else if (tab === "headlines") {
    loadHeadlines();
  } else if (tab === "facts") {
    loadRelevantFacts();
  }
  if(!["comparison","calendar","headlines","facts"].includes(tab))markPanelFresh("dashboard",tab);
}

async function loadOfficialCalendar(){
  const root=$("#dashboard-tab-content"),hadContent=Boolean(root.childElementCount);if(!hadContent)root.innerHTML=loadingCards(5);else root.classList.add("panel-refreshing");
  try{
    const payload=await api("/investor-events/calendar",{requestKey:"official-calendar",cacheTtlMs:120000});
    ensureRefreshGroupIfNeeded("official_calendar",payload.update,!(payload.items||[]).length,()=>loadOfficialCalendar());
    if(state.tabs.dashboard!=="calendar")return;
    const rows=payload.items||[];
    const table=rows.length?marketTable(rows,[
      {label:"Data",render:r=>`<strong>${dateOnly(r.date)}</strong>`},
      {label:"Evento",render:r=>`<strong>${esc(r.title)}</strong>${r.metadata?.conditional?'<br><span class="pill warning">CONDICIONAL</span>':""}`},
      {label:"Categoria",render:r=>esc(r.category)},{label:"Região",render:r=>esc(r.region||"—")},{label:"Horário",render:r=>esc(r.time||"—")},
      {label:"Fonte",render:r=>r.source_url?`<a href="${esc(safeExternalUrl(r.source_url))}" target="_blank" rel="noopener noreferrer">${esc(r.source||"Consultar")}</a>`:esc(r.source||"—")},
    ]):'<div class="empty-state"><strong>Agenda oficial sendo preparada</strong>A atualização ocorre em segundo plano e os dados anteriores nunca são apagados por uma falha de fonte.</div>';
    root.innerHTML=marketUpdatePanel(["official_calendar"])+sectionCard("Agenda oficial do investidor",table,"Eventos econômicos, feriados e eleições renovados anualmente");markPanelFresh("dashboard","calendar");
  }catch(error){if(!hadContent)root.innerHTML=errorState(error,"market");}
  finally{root.classList.remove("panel-refreshing");}
}

async function loadRelevantFacts(){
  const root=$("#dashboard-tab-content"),hadContent=Boolean(root.childElementCount);if(!hadContent)root.innerHTML=loadingCards(5);else root.classList.add("panel-refreshing");
  try{
    const payload=await api("/investor-events/relevant-facts?limit=100",{requestKey:"relevant-facts",cacheTtlMs:120000});
    ensureRefreshGroupIfNeeded("cvm_relevant_facts",payload.update,!(payload.items||[]).length,()=>loadRelevantFacts());
    if(state.tabs.dashboard!=="facts")return;
    const rows=payload.items||[];
    const content=rows.length?`<div class="headline-list"><div class="headline headline-header"><span>#</span><span>Companhia • assunto • ativos</span><span>Entrega</span></div>${rows.map((item,index)=>`<a class="headline" href="${esc(safeExternalUrl(item.document_url))}" target="_blank" rel="noopener noreferrer"><span class="headline-number">${String(index+1).padStart(2,"0")}</span><span><strong>${esc(item.issuer_name)}</strong><small>${esc(item.subject||"Fato relevante")}${(item.tickers||[]).length?` • ${item.tickers.map(esc).join(", ")}`:""}</small></span><small>${dateTime(item.delivered_at)}</small></a>`).join("")}</div>`:'<div class="empty-state"><strong>Fatos relevantes sendo sincronizados</strong>A fonte oficial da CVM será consultada em segundo plano.</div>';
    root.innerHTML=marketUpdatePanel(["cvm_relevant_facts"])+sectionCard("Fatos relevantes oficiais",content,"Metadados e documentos publicados no sistema IPE da CVM",{url:"https://dados.cvm.gov.br/dataset/cia_aberta-doc-ipe",label:"CVM • Dados Abertos"});markPanelFresh("dashboard","facts");
  }catch(error){if(!hadContent)root.innerHTML=errorState(error,"market");}
  finally{root.classList.remove("panel-refreshing");}
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
  root.innerHTML=marketUpdatePanel(["comparison"])+sectionCard("Comparador histórico",`${selectors}<div class="chart comparison-chart-wrap">${svg}</div><div class="chart-legend">${legend}</div>${sectionCard("Retorno e risco no período",metrics,"Volatilidade anualizada conforme a frequência de cada série")}${unavailable.length?`<div class="notice">Sem dados nesta atualização: ${esc(unavailable.join(", "))}.</div>`:""}<div class="notice info">${esc(payload.note||"Base 100 no início do período selecionado.")} ${state.comparisonBaseMode==="common"?"Todas as linhas começam na primeira data disponível em comum.":"Cada linha usa seu próprio primeiro dado disponível."}</div>`,`Desempenho acumulado • base R$ 100 • ${periodLabel}`);markPanelFresh("dashboard","comparison");
}

async function loadComparison(force=false,attempt=0,baselineGeneratedAt=null) {
  if(state.comparisonLoading&&attempt===0)return;
  if(attempt===0&&baselineGeneratedAt===null)baselineGeneratedAt=state.comparison?.generated_at||null;
  state.comparisonLoading=true;
  const root=$("#dashboard-tab-content");
  if(!state.comparison)root.innerHTML=`${loadingCards(6)}<div class="notice info" style="margin-top:14px">Preparando as séries históricas em segundo plano. Você pode continuar usando os outros painéis.</div>`;
  try{
    let payload=await api(force?"/market-dashboard/comparison/refresh":"/market-dashboard/comparison",{method:force?"POST":"GET",requestKey:"comparison",cacheTtlMs:force?0:120000});
    if(!force)ensureRefreshGroupIfNeeded("comparison",payload.update,!payload.data?.series?.length,()=>loadComparison(false));
    if(payload.update){state.marketEnvelope=state.marketEnvelope||{};state.marketEnvelope.updates={...(state.marketEnvelope.updates||{}),comparison:payload.update};}
    const hasSnapshot=Boolean(payload.data?.series?.length);
    if(hasSnapshot){state.comparison=payload.data;renderComparison();}
    if((payload.refreshing||payload.scheduled)&&attempt<120){
      state.comparisonLoading=false;
      scheduleNavigationTask(()=>loadComparison(false,attempt+1,baselineGeneratedAt),3000);
      return;
    }
    if(hasSnapshot){state.comparisonLoading=false;return;}
    if(state.comparison){renderComparison();state.comparisonLoading=false;return;}
    root.innerHTML=errorState(payload.error||"As séries históricas ainda não possuem uma atualização válida.");
  }catch(error){
    if(error.name!=="AbortError"){
      if(state.comparison)renderComparison();
      else root.innerHTML=errorState(error);
    }
  }
  state.comparisonLoading=false;
}

async function loadMarket(force = false) {
  const panelStarted=performance.now(),hadCached=Boolean(state.market);
  if (!state.market) {
    $("#market-summary").innerHTML = loadingCards(4);
    $("#dashboard-tab-content").innerHTML = loadingCards(6);
  }
  try {
    const envelope = await api("/market-dashboard", {requestKey:"market-get"});
    state.marketEnvelope = envelope;
    if (envelope?.data && Object.keys(envelope.data).length) state.market = envelope.data;
    state.dashboardCheckedAt = Date.now();
    renderMarketSummary(); renderDashboardTab();
    if (!force) {
      // The scheduler owns routine refreshes. Access fallback remains active
      // only when a required snapshot is unavailable, stale or failed. This
      // avoids a write on every navigation without losing self-recovery when
      // the scheduler is disabled (staging) or temporarily unavailable.
      const requiredGroups=["selic_current","selic_focus","macro","global_markets","rates_calendar","crypto","fx"];
      const needsEnsure=requiredGroups.some(key=>["unavailable","stale","failed"].includes(envelope.updates?.[key]?.status));
      if(!needsEnsure){if(["queued","running"].includes(envelope.refresh_status))pollMarket();reportPanelPerformance("dashboard",panelStarted,{cacheState:hadCached?"warm":"cold"});return;}
    }
    const endpoint=force?"/market-dashboard/refresh":"/market-dashboard/ensure";
    const queued = await api(endpoint, {method:"POST",invalidateCache:false});
    if (queued.scheduled || ["queued","running"].includes(queued.refresh_status)) pollMarket();
    else if (queued.data && Object.keys(queued.data).length) { state.marketEnvelope=queued; state.market=queued.data; renderMarketSummary(); renderDashboardTab(); }
    reportPanelPerformance("dashboard",panelStarted,{cacheState:hadCached?"warm":"cold"});
  } catch (error) {
    if (error.name === "AbortError") return;
    if (!state.market) $("#dashboard-tab-content").innerHTML = errorState(error, "market");
    toast(`Dados de mercado: ${error.message}`, "error");
    reportPanelPerformance("dashboard",panelStarted,{success:false,cacheState:hadCached?"stale":"cold"});
  }
}

function pollMarket(attempt = 0, navigationSerial = state.navigationSerial) {
  if (attempt > 35 || !navigationIsCurrent(navigationSerial,"dashboard")) return;
  scheduleNavigationTask(async()=>{
    try {
      const envelope = await api("/market-dashboard");
      if(!navigationIsCurrent(navigationSerial,"dashboard"))return;
      if (envelope.data && Object.keys(envelope.data).length) { state.marketEnvelope=envelope; state.market=envelope.data; renderMarketSummary(); renderDashboardTab(); }
      if (["queued","running"].includes(envelope.refresh_status)) pollMarket(attempt+1,navigationSerial);
      else if (envelope.refresh_status === "completed") toast("Painel de mercado atualizado.", "success");
    } catch (_) { /* keep stale data visible */ }
  },2500,navigationSerial);
}

async function loadHeadlines() {
  const root = $("#dashboard-tab-content");
  const hadContent=Boolean(root.childElementCount);
  if(!hadContent)root.innerHTML=loadingCards(5);else root.classList.add("panel-refreshing");
  try {
    let payload = await api("/market-dashboard/headlines", {requestKey:"headlines",cacheTtlMs:120000});
    ensureRefreshGroupIfNeeded("headlines",payload.update,!payload.data?.items?.length,()=>loadHeadlines());
    if (payload.data?.items?.length) renderHeadlines(payload);
    else if (payload.refreshing || payload.scheduled) {
      root.innerHTML = `${loadingCards(5)}<div class="notice info" style="margin-top:14px">Buscando as principais manchetes em segundo plano. O restante do site continua disponível.</div>`;
      scheduleNavigationTask(async () => { try { payload=await api("/market-dashboard/headlines"); renderHeadlines(payload); } catch (_) {} }, 2500);
    } else renderHeadlines(payload);
  } catch (error) { if(!hadContent)root.innerHTML = errorState(error); }
  finally { root.classList.remove("panel-refreshing"); }
}

function renderHeadlines(payload) {
  if (state.tabs.dashboard !== "headlines") return;
  const items = payload.data?.items || [];
  const list = items.length ? `<div class="headline-list"><div class="headline headline-header"><span>#</span><span>Manchete e fonte</span><span>Publicada em</span></div>${items.slice(0,10).map((item,index)=>`<a class="headline" href="${esc(item.url)}" target="_blank" rel="noopener"><span class="headline-number">${String(index+1).padStart(2,"0")}</span><span><strong>${esc(item.title)}</strong><small>${esc(item.source)}</small></span><small>${item.published_at ? dateTime(item.published_at) : "Horário não informado"}</small></a>`).join("")}</div>` : '<div class="empty-state"><strong>Nenhuma manchete disponível agora</strong>As fontes serão consultadas novamente em até uma hora.</div>';
  if(payload.update){state.marketEnvelope=state.marketEnvelope||{};state.marketEnvelope.updates={...(state.marketEnvelope.updates||{}),headlines:payload.update};}
  $("#dashboard-tab-content").innerHTML = marketUpdatePanel(["headlines"])+sectionCard("10 principais manchetes de economia", list, "Atualização automática a cada hora");
  markPanelFresh("dashboard","headlines");
}

async function refreshMarketGroups(keys) {
  const groups=String(keys||"").split(",").map(value=>value.trim()).filter(Boolean);
  if(!groups.length)return;
  try {
    if(groups.some(group=>["catalog","fundamentals","technical_daily","technical_intraday"].includes(group)))state.analysisResultCache.clear();
    const results=await Promise.all(groups.map(group=>api(`/market-dashboard/groups/${encodeURIComponent(group)}/refresh`,{method:"POST"})));
    const scheduled=results.filter(result=>result.scheduled).length;
    toast(scheduled?"Atualização solicitada. Os dados atuais permanecerão visíveis.":"Esses dados foram solicitados há menos de 5 minutos.",scheduled?"success":"info");
    scheduleNavigationTask(()=>loadCurrentView(),2500);
  } catch(error) { toast(error.message,"error"); }
}

function ensureRefreshGroupIfNeeded(group,update,missing,onReady,endpoint=null){
  const status=String(update?.status||"").toLowerCase();
  if(!missing&&!['unavailable','stale','failed'].includes(status))return false;
  if(['queued','running'].includes(status))return false;
  const now=Date.now(),last=Number(state.refreshEnsureSentAt[group]||0);
  if(now-last<300000)return false;
  state.refreshEnsureSentAt[group]=now;
  api(endpoint||`/market-dashboard/groups/${encodeURIComponent(group)}/ensure`,{method:"POST",invalidateCache:false})
    .then(result=>{
      if(result?.scheduled)scheduleNavigationTask(()=>{
        invalidateApplicationCache(cacheTagsForPath(endpoint||`/market-dashboard/groups/${encodeURIComponent(group)}`));
        onReady?.();
      },3000);
    })
    .catch(()=>{});
  return true;
}

function loadedAnalysisMethod(method){
  const handler=window.FDIFeatures.analysis?.[method];
  return typeof handler==="function"?handler:null;
}
function analysisType(){return analysisTabTypes[state.tabs.analysis]||"stock";}
function renderFilterInputs(...args){return loadedAnalysisMethod("renderFilterInputs")?.(...args);}
function updateFilterAvailability(...args){return loadedAnalysisMethod("updateFilterAvailability")?.(...args);}
function fillAnalysisForm(...args){return loadedAnalysisMethod("fillAnalysisForm")?.(...args);}
function analysisRequestFromForm(...args){return loadedAnalysisMethod("analysisRequestFromForm")?.(...args)||{};}
function validateAnalysisRequest(...args){const handler=loadedAnalysisMethod("validateAnalysisRequest");if(!handler)throw new Error("O módulo de análises ainda está sendo carregado.");return handler(...args);}
function markActiveAnalysis(...args){return loadedAnalysisMethod("markActiveAnalysis")?.(...args);}
function analysisColumns(...args){return loadedAnalysisMethod("analysisColumns")?.(...args)||[];}
function orderedAnalysisColumns(...args){return loadedAnalysisMethod("orderedAnalysisColumns")?.(...args)||[];}
function renderAnalysisRows(...args){return loadedAnalysisMethod("renderAnalysisRows")?.(...args);}
async function prefetchAnalysisCatalogs(...args){const feature=await loadFeature("analysis");return feature.prefetchAnalysisCatalogs(...args);}
async function selectSystemPreset(...args){return invokeFeature("analysis","selectSystemPreset",...args);}
async function selectCustomFilter(...args){return invokeFeature("analysis","selectCustomFilter",...args);}
async function saveCustomFilter(...args){return invokeFeature("analysis","saveCustomFilter",...args);}
async function deleteCustomFilter(...args){return invokeFeature("analysis","deleteCustomFilter",...args);}
async function loadAnalysis(...args){return loadFeaturePanel("analysis","loadAnalysis","#analysis-table",args);}
async function applyAdvancedFilters(...args){return invokeFeature("analysis","applyAdvancedFilters",...args);}
async function openAsset(...args){return invokeFeature("analysis","openAsset",...args);}
async function loadPortfolios(...args){return loadFeaturePanel("portfolio","loadPortfolios","#portfolio-tab-content",args);}
async function renderPortfolioTab(...args){return loadFeaturePanel("portfolio","renderPortfolioTab","#portfolio-tab-content",args);}
async function refreshPortfolioNews(...args){return invokeFeature("portfolio","refreshPortfolioNews",...args);}
async function refreshRecommendationNews(...args){return invokeFeature("portfolio","refreshRecommendationNews",...args);}
async function renderAlertSuggestions(...args){return invokeFeature("portfolio","renderAlertSuggestions",...args);}
async function setAlertStatus(...args){return invokeFeature("portfolio","setAlertStatus",...args);}
async function editPriceAlert(...args){return invokeFeature("portfolio","editPriceAlert",...args);}
async function sendAlertTestEmail(...args){return invokeFeature("portfolio","sendAlertTestEmail",...args);}
async function savePriceAlert(...args){return invokeFeature("portfolio","savePriceAlert",...args);}
async function saveAlertPreferences(...args){return invokeFeature("portfolio","saveAlertPreferences",...args);}
async function refreshPortfolioPrices(...args){return invokeFeature("portfolio","refreshPortfolioPrices",...args);}
async function showPortfolioAllocationType(...args){return invokeFeature("portfolio","showPortfolioAllocationType",...args);}
async function updateCustomInvestmentValue(...args){return invokeFeature("portfolio","updateCustomInvestmentValue",...args);}
async function deleteCustomInvestment(...args){return invokeFeature("portfolio","deleteCustomInvestment",...args);}
async function deletePortfolioPosition(...args){return invokeFeature("portfolio","deletePortfolioPosition",...args);}
async function saveCustomInvestment(...args){return invokeFeature("portfolio","saveCustomInvestment",...args);}
async function savePortfolioPosition(...args){return invokeFeature("portfolio","savePortfolioPosition",...args);}
async function saveCustomInvestmentValue(...args){return invokeFeature("portfolio","saveCustomInvestmentValue",...args);}

async function openStudyStrategy(...args){return invokeFeature("backtests","openStudyStrategy",...args);}
async function openOfficialBacktestJob(...args){return invokeFeature("backtests","openOfficialBacktestJob",...args);}
async function retryOfficialBacktestJob(...args){return invokeFeature("backtests","retryOfficialBacktestJob",...args);}
async function launchOfficialBacktestRound(...args){return invokeFeature("backtests","launchOfficialBacktestRound",...args);}
async function renderBacktestStrategyParameters(...args){return invokeFeature("backtests","renderBacktestStrategyParameters",...args);}
async function loadBacktests(...args){return loadFeaturePanel("backtests","loadBacktests","#backtests-tab-content",args);}
async function runBacktest(...args){return invokeFeature("backtests","runBacktest",...args);}

async function loadFinances(...args){return loadFeaturePanel("finances","loadFinances","#finances-tab-content",args);}
async function saveFinanceTransaction(...args){return invokeFeature("finances","saveFinanceTransaction",...args);}
async function saveFinanceBudget(...args){return invokeFeature("finances","saveFinanceBudget",...args);}
async function setFinanceStatus(...args){return invokeFeature("finances","setFinanceStatus",...args);}
async function archiveFinanceTransaction(...args){return invokeFeature("finances","archiveFinanceTransaction",...args);}

const accessPermissionSections=[
  {title:"Mercado e análises",items:[["can_view_market","Ver Painel de Mercado"],["can_use_advanced_filters","Usar filtros avançados"],["can_use_fdi_analysis","Análise FDI"],["can_use_alb_analysis","Análise ALB"],["can_use_graham_valuation","Número de Graham"],["can_use_dividend_ceiling","Preço-teto por dividendos"],["can_use_relative_valuation","Valuation relativo"],["can_use_economic_valuation","Valor econômico"]]},
  {title:"Carteira, notícias e alertas",items:[["can_view_portfolio","Ver carteiras"],["can_write_portfolio","Editar carteiras"],["can_view_news_insights","Notícias e recomendações"],["can_use_price_alerts","Usar alertas"],["can_alert_price_above","Preço acima"],["can_alert_price_below","Preço abaixo"],["can_alert_change_positive","Variação positiva"],["can_alert_change_negative","Variação negativa"]]},
  {title:"Finanças e backtests",items:[["can_view_finances","Ver finanças"],["can_write_finances","Editar finanças"],["can_view_backtests","Ver backtests"],["can_run_backtests","Executar backtests"],["can_refresh_backtest_signals","Atualizar sinais"],["can_view_backtest_studies","Ver estudos"]]},
  {title:"Administração",items:[["can_sync_market","Atualizar dados e qualidade"],["can_manage_users","Gerenciar usuários e níveis"],["can_manage_portal","Editar página inicial e livros"]]},
];
const accessLimitDefinitions=[
  {key:"custom_filter_limit",label:"Análises personalizadas",values:[0,1,2,3]},
  {key:"alert_asset_limit",label:"Ativos com alertas",values:[0,1,3,5,10]},
  {key:"backtest_asset_limit",label:"Ativos por backtest",values:[0,1,3,5,10]},
  {key:"backtest_strategy_limit",label:"Estratégias combinadas",values:[0,1,2,3,5]},
  {key:"backtest_daily_limit",label:"Backtests por dia",values:[0,1,5,10,20]},
  {key:"backtest_cooldown_seconds",label:"Intervalo mínimo (segundos)",values:[60,120,300,600,1800,3600]},
];
const adminRefreshGroups=[
  {key:"selic_current",section:"Juros e macro",frequency:"06h e 13h"},{key:"selic_focus",section:"Juros e macro",frequency:"Diária, 04h"},{key:"macro",section:"Juros e macro",frequency:"Diária, 04h"},{key:"rates_calendar",section:"Juros e macro",frequency:"06h e 13h"},
  {key:"global_markets",section:"Mercados",frequency:"06h e 13h"},{key:"crypto",section:"Mercados",frequency:"A cada 30 min"},{key:"fx",section:"Mercados",frequency:"A cada 2 horas"},
  {key:"headlines",section:"Notícias e históricos",frequency:"A cada hora"},{key:"comparison",section:"Notícias e históricos",frequency:"Diária, 05h"},{key:"ibov_portfolio",section:"Notícias e históricos",frequency:"Dias úteis, 08h15"},
  {key:"catalog",section:"Catálogo e análises",frequency:"Dias úteis, 08h30"},{key:"fundamentals",section:"Catálogo e análises",frequency:"Dias úteis, 19h"},{key:"technical_daily",section:"Catálogo e análises",frequency:"Dias úteis, 18h15"},{key:"technical_intraday",section:"Catálogo e análises",frequency:"Pregão, a cada 15 min"},{key:"current_metrics",section:"Catálogo e análises",frequency:"Diária, 20h40"},
  {key:"portfolio_dividends",section:"Eventos oficiais",frequency:"Dias úteis, 07h20 e 19h20"},{key:"cvm_relevant_facts",section:"Eventos oficiais",frequency:"Diária, 07h40"},{key:"official_calendar",section:"Eventos oficiais",frequency:"Diária, 03h20"},{key:"ima_history",section:"Eventos oficiais",frequency:"Dias úteis, 21h30"},
  {key:"alb_monitor",section:"Qualidade",frequency:"Dias úteis, 19h40"},{key:"data_quality",section:"Qualidade",frequency:"Diária, 20h10"},
  {key:"operations_retention",section:"Operação",frequency:"Diária, 02h50"},
];

async function loadAdmin(...args){return loadFeaturePanel("admin","loadAdmin","#admin-tab-content",args);}
async function renderAdminAnalysisSettings(...args){return invokeFeature("admin","renderAdminAnalysisSettings",...args);}
async function saveAdminPreset(...args){return invokeFeature("admin","saveAdminPreset",...args);}
async function resetAdminPreset(...args){return invokeFeature("admin","resetAdminPreset",...args);}
async function saveAdminColumns(...args){return invokeFeature("admin","saveAdminColumns",...args);}
async function resetAdminColumns(...args){return invokeFeature("admin","resetAdminColumns",...args);}
async function moveAdminColumn(...args){return invokeFeature("admin","moveAdminColumn",...args);}
async function deletePortalBook(...args){return invokeFeature("admin","deletePortalBook",...args);}
async function movePortalBook(...args){return invokeFeature("admin","movePortalBook",...args);}
async function savePortalPage(...args){return invokeFeature("admin","savePortalPage",...args);}
async function savePortalBook(...args){return invokeFeature("admin","savePortalBook",...args);}
async function saveAccessLevel(...args){return invokeFeature("admin","saveAccessLevel",...args);}
async function createAccessLevel(...args){return invokeFeature("admin","createAccessLevel",...args);}
async function saveUserLevel(...args){return invokeFeature("admin","saveUserLevel",...args);}
async function bulkAssignAccessLevel(...args){return invokeFeature("admin","bulkAssignAccessLevel",...args);}
async function clearUserOverrides(...args){return invokeFeature("admin","clearUserOverrides",...args);}
async function runAlertMonitorNow(...args){return invokeFeature("admin","runAlertMonitorNow",...args);}
async function retryAdminJob(...args){return invokeFeature("admin","retryAdminJob",...args);}
async function applyAdminUserFilters(...args){return invokeFeature("admin","applyAdminUserFilters",...args);}
async function changeAdminUsersPage(...args){return invokeFeature("admin","changeAdminUsersPage",...args);}
async function syncMarketCatalog(...args){return invokeFeature("admin","syncMarketCatalog",...args);}
async function saveUserAccess(...args){return invokeFeature("admin","saveUserAccess",...args);}

function dividendEventLabel(value){return ({dividend:"Dividendo",jcp:"Juros sobre capital próprio",income:"Rendimento",capital_return:"Restituição de capital",cash_distribution:"Provento em dinheiro"})[value]||value||"Provento";}

async function renderPortfolioDividends(root){
  const panelKey=root.dataset.panelKey;
  const query=new URLSearchParams({portfolio_id:state.portfolioId,limit:"1000"});
  const payload=await api(`/investor-events/dividends?${query}`,{requestKey:`dividends-${state.portfolioId}`,cacheTtlMs:120000});
  if(root.dataset.panelKey!==panelKey||state.view!=="portfolio"||state.tabs.portfolio!=="dividends")return;
  ensureRefreshGroupIfNeeded("portfolio_dividends",payload.update,!(payload.items||[]).length,()=>renderPortfolioDividends(root),"/investor-events/dividends/ensure");
  const rows=payload.items||[],known=rows.filter(item=>!nullable(item.estimated_gross_amount));
  const estimated=known.reduce((sum,item)=>sum+Number(item.estimated_gross_amount||0),0);
  const table=rows.length?marketTable(rows,[
    {label:"Ativo",render:r=>`<strong>${esc(r.ticker)}</strong><br><small>${esc(r.portfolio_name||"")}</small>`},
    {label:"Tipo",render:r=>esc(dividendEventLabel(r.event_type))},
    {label:"Data-com",render:r=>dateOnly(r.last_cum_date)},{label:"Data-ex",render:r=>dateOnly(r.ex_date)},{label:"Pagamento",render:r=>dateOnly(r.payment_date)},
    {label:"Valor por unidade",render:r=>nullable(r.amount)?"—":money(r.amount,r.currency||"BRL")},
    {label:"Quantidade atual",render:r=>nullable(r.quantity)?"—":number(r.quantity,4)},
    {label:"Total indicativo",render:r=>nullable(r.estimated_gross_amount)?"—":money(r.estimated_gross_amount,r.currency||"BRL")},
    {label:"Fonte",render:r=>r.source_url?`<a href="${esc(safeExternalUrl(r.source_url))}" target="_blank" rel="noopener noreferrer">${esc(r.source)}</a>`:esc(r.source||"—")},
  ]):'<div class="empty-state"><strong>Nenhum provento confirmado no período</strong>A consulta usa somente eventos oficiais dos ativos desta carteira.</div>';
  const update=payload.update||{};
  root.innerHTML=`<div class="metric-grid summary-grid">${metricCard("Eventos",number(rows.length,0),"No período consultado")}${metricCard("Total indicativo",money(estimated),`${known.length} evento(s) com valor e posição`) }${metricCard("Fonte","B3","Empresas Listadas")}${metricCard("Última atualização",update.last_updated_at?dateTime(update.last_updated_at):"Preparando",update.status||"")}</div>${sectionCard("Calendário oficial de proventos",table,payload.gross_amount_note||"Valores brutos e indicativos; confirme na corretora.")}`;
}

function loadCurrentView() {
  if(state.view==="dashboard") {
    renderDashboardTab();
    if(!state.market||Date.now()-state.dashboardCheckedAt>60000)loadMarket(false);
  }
  else if(state.view==="analysis") loadAnalysis();
  else if(state.view==="portfolio") loadPortfolios();
  else if(state.view==="finances") loadFinances();
  else if(state.view==="backtests") loadBacktests();
  else if(state.view==="admin") loadAdmin();
}

let searchTimer;
async function runSearch(query) {
  const root=$("#search-results");
  const normalized=query.trim();
  if(normalized.length<1) { state.requestControllers.get("search")?.abort();state.requestControllers.delete("search");root.classList.add("hidden"); root.innerHTML=""; return; }
  try {
    const data=await api(`/search?q=${encodeURIComponent(normalized)}`,{requestKey:"search"});
    if(String($("#global-search")?.value||"").trim()!==normalized)return;
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
  const primaryNav=$("#primary-nav");
  primaryNav.addEventListener("click", event=>{ const button=event.target.closest("[data-view]"); if(button) setView(button.dataset.view); });
  const prefetchFromNavigation=event=>{const button=event.target.closest?.("[data-view]"),feature=FEATURE_BY_VIEW[button?.dataset.view];if(feature)prefetchFeature(feature);};
  primaryNav.addEventListener("pointerover",prefetchFromNavigation,{passive:true});
  primaryNav.addEventListener("focusin",prefetchFromNavigation);
  $("#collapse-sidebar").addEventListener("click",()=>document.body.classList.toggle("sidebar-collapsed"));
  $("#mobile-menu").addEventListener("click",()=>document.body.classList.toggle("mobile-nav-open"));
  $$(".tabs").forEach(tabs=>tabs.addEventListener("click",event=>{const button=event.target.closest(".tab");if(button&&activateTab(tabs.dataset.tabs,button.dataset.tab)&&tabs.dataset.tabs==="analysis")updateFilterAvailability();}));
  $$(".tabs").forEach(tabs=>tabs.addEventListener("keydown",event=>{
    if(!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Home","End"].includes(event.key))return;
    const visible=$$(".tab:not(.hidden):not([disabled])",tabs);if(!visible.length)return;
    const current=Math.max(0,visible.indexOf(document.activeElement));
    const next=event.key==="Home"?0:event.key==="End"?visible.length-1:(current+(["ArrowRight","ArrowDown"].includes(event.key)?1:-1)+visible.length)%visible.length;
    event.preventDefault();visible[next].focus();visible[next].click();
  }));
  $("#refresh-market").addEventListener("click",()=>loadMarket(true));
  $("#logout-button").addEventListener("click",async()=>{try{await api("/logout",{method:"POST"});location.href=LANDING_PATH;}catch(error){toast(error.message,"error");}});
  $("#global-search").addEventListener("input",event=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>runSearch(event.target.value),220);});
  document.addEventListener("keydown",event=>{if(event.key==="/"&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)){event.preventDefault();$("#global-search").focus();}});
  document.addEventListener("click",event=>{
    const applyAdvanced=event.target.closest("#apply-advanced-filters");if(applyAdvanced){applyAdvancedFilters();return;}
    const saveCustom=event.target.closest("#save-custom-filter");if(saveCustom){saveCustomFilter();return;}
    const deleteCustomFilterButton=event.target.closest("#delete-custom-filter");if(deleteCustomFilterButton){deleteCustomFilter();return;}
    const refreshGroupsButton=event.target.closest("[data-refresh-groups]");if(refreshGroupsButton){if(refreshGroupsButton.hasAttribute("data-confirm-all-updates")&&!window.confirm(`Enfileirar agora as ${adminRefreshGroups.length} rotinas de atualização? Os dados atuais continuarão disponíveis durante o processamento.`))return;refreshMarketGroups(refreshGroupsButton.dataset.refreshGroups);return;}
    const portfolioNewsButton=event.target.closest("[data-portfolio-news-refresh]");if(portfolioNewsButton){refreshPortfolioNews(portfolioNewsButton.dataset.portfolioNewsRefresh);return;}
    const newsMode=event.target.closest("[data-portfolio-news-mode]");if(newsMode){const mode=newsMode.dataset.portfolioNewsMode;if(state.portfolioNewsMode!==mode){state.portfolioNewsMode=mode;renderPortfolioTab();}return;}
    const recommendationCategory=event.target.closest("[data-recommendation-category]");if(recommendationCategory){const category=recommendationCategory.dataset.recommendationCategory;if(state.recommendationCategory!==category){state.recommendationCategory=category;renderPortfolioTab();}return;}
    const recommendationRefresh=event.target.closest("[data-recommendation-news-refresh]");if(recommendationRefresh){refreshRecommendationNews(recommendationRefresh.dataset.recommendationNewsRefresh);return;}
    const alertSuggestion=event.target.closest("[data-alert-suggestion]");if(alertSuggestion){const input=$("#alert-symbol");if(input){input.value=alertSuggestion.dataset.alertSuggestion;$("#alert-symbol-suggestions")?.classList.add("hidden");}return;}
    const alertStatus=event.target.closest("[data-alert-status]");if(alertStatus){setAlertStatus(alertStatus);return;}
    const editAlert=event.target.closest("[data-edit-alert]");if(editAlert){editPriceAlert(editAlert.dataset.editAlert);return;}
    const alertTest=event.target.closest("[data-alert-test-email]");if(alertTest){sendAlertTestEmail(alertTest);return;}
    const saveUserLevelButton=event.target.closest("[data-save-user-level]");if(saveUserLevelButton){saveUserLevel(saveUserLevelButton.dataset.saveUserLevel);return;}
    const clearOverrides=event.target.closest("[data-clear-user-overrides]");if(clearOverrides){clearUserOverrides(clearOverrides.dataset.clearUserOverrides);return;}
    if(event.target.closest("[data-bulk-assign-level]")){bulkAssignAccessLevel();return;}
    const usersPage=event.target.closest("[data-admin-users-page]");if(usersPage){changeAdminUsersPage(usersPage.dataset.adminUsersPage);return;}
    const runMonitor=event.target.closest("[data-run-alert-monitor]");if(runMonitor){runAlertMonitorNow(runMonitor);return;}
    const retryJob=event.target.closest("[data-retry-admin-job]");if(retryJob){retryAdminJob(retryJob);return;}
    const resetAdminPresetButton=event.target.closest("[data-reset-admin-preset]");if(resetAdminPresetButton){resetAdminPreset(resetAdminPresetButton);return;}
    const resetAdminColumnsButton=event.target.closest("[data-reset-admin-columns]");if(resetAdminColumnsButton){resetAdminColumns(resetAdminColumnsButton.dataset.resetAdminColumns);return;}
    const moveAdminColumnButton=event.target.closest("[data-move-admin-column]");if(moveAdminColumnButton){moveAdminColumn(moveAdminColumnButton);return;}
    if(event.target.closest("[data-reload-admin-jobs]")){loadAdmin(true);return;}
    if(event.target.closest("[data-reload-admin-operations]")){loadAdmin(true);return;}
    if(event.target.closest("[data-reload-admin-quality]")){loadAdmin(true);return;}
    const deletePortal=event.target.closest("[data-portal-book-delete]");if(deletePortal){deletePortalBook(deletePortal.dataset.portalBookDelete);return;}
    const movePortal=event.target.closest("[data-portal-book-move]");if(movePortal){movePortalBook(movePortal.dataset.portalBookId,movePortal.dataset.portalBookMove);return;}
    const portfolioPricesButton=event.target.closest("[data-portfolio-prices-refresh]");if(portfolioPricesButton){refreshPortfolioPrices(portfolioPricesButton.dataset.portfolioPricesRefresh);return;}
    const allocationType=event.target.closest("[data-allocation-type]");if(allocationType){showPortfolioAllocationType(allocationType.dataset.allocationType);return;}
    if(event.target.closest("[data-allocation-close]")){showPortfolioAllocationType(null);return;}
    const resetPersonalColumns=event.target.closest("[data-reset-personal-columns]");if(resetPersonalColumns){delete state.visibleColumns[resetPersonalColumns.dataset.resetPersonalColumns];persistVisibleColumns();renderAnalysisRows(state.analysisRows);toast("Colunas restauradas para o padrão da plataforma.","success");return;}
    const densityButton=event.target.closest("[data-analysis-density]");if(densityButton){state.analysisDensity=densityButton.dataset.analysisDensity;localStorage.setItem("fdi-analysis-density",state.analysisDensity);renderAnalysisRows(state.analysisRows);return;}
    const sortButton=event.target.closest("[data-analysis-sort]");if(sortButton){const type=analysisType(),column=sortButton.dataset.analysisSort,current=state.analysisSort[type]||{};state.analysisSort[type]={column,direction:current.column===column&&current.direction==="asc"?"desc":"asc"};renderAnalysisRows(state.analysisRows);return;}
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
    const comparisonRefresh=event.target.closest("[data-comparison-refresh]");if(comparisonRefresh){loadComparison(true);}
    const saveUser=event.target.closest("[data-save-user]");if(saveUser)saveUserAccess(saveUser.dataset.saveUser);
    const marketSync=event.target.closest("[data-market-sync]");if(marketSync)syncMarketCatalog(marketSync.dataset.marketSync,marketSync.dataset.technicals==="true");
    const preset=event.target.closest("[data-preset-id]");if(preset)selectSystemPreset(preset.dataset.presetId);
    const customPreset=event.target.closest("[data-custom-filter-id]");if(customPreset)selectCustomFilter(customPreset.dataset.customFilterId);
    const studyStrategy=event.target.closest("[data-study-strategy]");if(studyStrategy)openStudyStrategy(studyStrategy.dataset.studyStrategy);
    const launchOfficial=event.target.closest("[data-launch-official-backtests]");if(launchOfficial){launchOfficialBacktestRound(launchOfficial);return;}
    const officialJob=event.target.closest("[data-official-job]");if(officialJob)openOfficialBacktestJob(officialJob.dataset.officialJob);
    const retryOfficial=event.target.closest("[data-retry-official-job]");if(retryOfficial)retryOfficialBacktestJob(retryOfficial.dataset.retryOfficialJob,retryOfficial);
    if(!event.target.closest(".global-search-wrap"))$("#search-results").classList.add("hidden");
  });
  const closeAssetDialog=({historyMode="replace"}={})=>{state.assetRequestSerial+=1;state.requestControllers.get("asset-detail")?.abort();state.requestControllers.delete("asset-detail");state.currentAssetTicker=null;if($("#asset-dialog").open)$("#asset-dialog").close();syncNavigationUrl(historyMode);};
  $("#close-asset-dialog").addEventListener("click",closeAssetDialog);
  $("#asset-dialog").addEventListener("click",event=>{if(event.target===$("#asset-dialog"))closeAssetDialog();});
  $("#asset-dialog").addEventListener("close",()=>{state.assetRequestSerial+=1;state.requestControllers.get("asset-detail")?.abort();state.requestControllers.delete("asset-detail");if(state.currentAssetTicker){state.currentAssetTicker=null;syncNavigationUrl("replace");}});
  document.addEventListener("change",event=>{
    if(event.target.id==="admin-analysis-type"){state.adminAnalysisType=event.target.value;renderAdminAnalysisSettings($("#admin-tab-content"));return;}
    if(event.target.id==="alert-market-scope"){const input=$("#alert-symbol");if(input)input.value="";renderAlertSuggestions("");}
    if(event.target.id==="below-economic"&&event.target.checked&&analysisType()==="stock"){const details=$("#economic-assumptions");if(details){details.open=true;details.scrollIntoView({behavior:"smooth",block:"nearest"});}}
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
    if(event.target.matches('#backtest-form [name="strategy_ids"]'))renderBacktestStrategyParameters(event.target.form);
    if(event.target.matches('#backtest-form [name="period"]')){
      const custom=event.target.value==="custom";
      event.target.form?.querySelectorAll("[data-backtest-custom-date]").forEach(field=>field.hidden=!custom);
    }
    if(event.target.id==="portfolio-selector"){state.portfolioId=event.target.value;state.portfolioAllocationType=null;state.portfolioAllocationHierarchy=null;renderPortfolioTab();}
    if(event.target.id==="finance-month"){capturePanelSurface("finances",state.tabs.finances);state.financeMonth=event.target.value;syncNavigationUrl("replace");restorePanelSurface("finances",state.tabs.finances);loadFinances();}
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
      const type=analysisType(),columns=orderedAnalysisColumns(type,analysisColumns(type)).filter(column=>!column.always);
      state.visibleColumns[type]=columns.filter(column=>$(`[data-column-id="${column.id}"]`)?.checked).map(column=>column.id);
      persistVisibleColumns();renderAnalysisRows(state.analysisRows);
    }
  });
  document.addEventListener("input",event=>{if(event.target.id==="alert-symbol")renderAlertSuggestions(event.target.value);});
  document.addEventListener("keydown",event=>{const slice=event.target.closest?.("[data-allocation-type]");if(slice&&(event.key==="Enter"||event.key===" ")){event.preventDefault();showPortfolioAllocationType(slice.dataset.allocationType);}});
  document.addEventListener("submit",event=>{if(event.target.id==="email-login-request-form"){event.preventDefault();requestEmailLogin(event.target);}if(event.target.id==="email-login-verify-form"){event.preventDefault();verifyEmailLogin(event.target);}if(event.target.id==="backtest-form"){event.preventDefault();runBacktest(event.target);}if(event.target.id==="portfolio-position-form"){event.preventDefault();savePortfolioPosition(event.target);}if(event.target.id==="custom-investment-form"){event.preventDefault();saveCustomInvestment(event.target);}if(event.target.id==="custom-value-form"){event.preventDefault();saveCustomInvestmentValue(event.target);}if(event.target.id==="finance-transaction-form"){event.preventDefault();saveFinanceTransaction(event.target);}if(event.target.id==="finance-budget-form"){event.preventDefault();saveFinanceBudget(event.target);}if(event.target.id==="price-alert-form"){event.preventDefault();savePriceAlert(event.target);}if(event.target.id==="alert-preference-form"){event.preventDefault();saveAlertPreferences(event.target);}if(event.target.id==="portal-page-form"){event.preventDefault();savePortalPage(event.target);}if(event.target.matches("[data-portal-book-form]")){event.preventDefault();savePortalBook(event.target);}if(event.target.matches("[data-access-level-form]")){event.preventDefault();saveAccessLevel(event.target);}if(event.target.id==="create-access-level-form"){event.preventDefault();createAccessLevel(event.target);}if(event.target.id==="admin-user-filter-form"){event.preventDefault();applyAdminUserFilters(event.target);}if(event.target.matches("[data-admin-preset-form]")){event.preventDefault();saveAdminPreset(event.target);}if(event.target.matches("[data-admin-columns-form]")){event.preventDefault();saveAdminColumns(event.target);}});
  window.addEventListener("popstate",()=>applyNavigationFromLocation({historyMode:"none"}));
}

function storedNavigation(){
  try{return JSON.parse(localStorage.getItem(state.navigationStorageKey)||"null");}catch(_){return null;}
}

function applyNavigationFromLocation({historyMode="replace",useStored=false}={}){
  const fromUrl=navigationStateFromLocation(),saved=useStored?storedNavigation():null;
  let view=fromUrl.view||saved?.view||"dashboard";
  let tab=fromUrl.tab||saved?.tabs?.[view]||state.tabs[view];
  if(view==="analysis"){
    tab=fromUrl.tab||saved?.tabs?.analysis||"stocks";
    const mode=new URLSearchParams(location.search).get("mode")||saved?.tabs?.analysisMode;
    if(["list","guide"].includes(mode))state.tabs.analysisMode=mode;
  }
  if(view==="finances"){
    const month=new URLSearchParams(location.search).get("month")||saved?.financeMonth;
    if(/^\d{4}-\d{2}$/.test(month||"")){state.financeMonth=month;if($("#finance-month"))$("#finance-month").value=month;}
  }
  if(!navigationIsAllowed(view,tab)){view="dashboard";tab=state.tabs.dashboard;}
  state.applyingHistory=true;
  try{
    setView(view,tab,{force:true,historyMode:"none"});
    const requestedAsset=fromUrl.asset;
    if(requestedAsset&&view==="analysis")scheduleNavigationTask(()=>openAsset(requestedAsset,{historyMode:"none"}),120);
    else if($("#asset-dialog")?.open){state.currentAssetTicker=null;$("#asset-dialog").close();}
  }finally{state.applyingHistory=false;}
  syncNavigationUrl(historyMode);
}

async function initialize() {
  const login=$("#platform-login");
  if(login) login.href=`${BASE_PATH}/login?next=${encodeURIComponent(PLATFORM_PATH)}`;
  if(BASE_PATH){document.body.classList.add("staging-mode");document.body.insertAdjacentHTML("afterbegin",'<div class="staging-banner">AMBIENTE DE TESTE • nenhuma alteração será publicada na página oficial sem aprovação</div>');}
  bindEvents();
  try {
    const session=await api("/session/me");
    if(!session.authenticated){showLogin();return;}
    state.session=session; configureAccess(); showApp();
    $("#finance-month").value=state.financeMonth;
    updateNavigationAccessibility();
    applyNavigationFromLocation({historyMode:"replace",useStored:!new URLSearchParams(location.search).has("view")});
    if(session.access?.can_view_news_insights)api("/insights/news/refresh-daily",{method:"POST",invalidateCache:false}).catch(()=>{});
  } catch(error) { showLogin(); toast(error.message,"error"); }
}

document.addEventListener("DOMContentLoaded",initialize);
