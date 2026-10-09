"use strict";

const BASE_PATH = location.pathname === "/testefdi" || location.pathname.startsWith("/testefdi/") ? "/testefdi" : "";
const LANDING_PATH = `${BASE_PATH}/`;
const PLATFORM_PATH = `${BASE_PATH}/plataforma/`;
const ANALYSIS_CACHE_TTL_MS = 300000;
const NEWS_NAVIGATION_CACHE_TTL_MS = 15000;
const ADMIN_NAVIGATION_CACHE_TTL_MS = 15000;
const PANEL_REVALIDATE_DELAY_MS = 80;
const PANEL_SURFACE_LIMIT = 36;

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


const FEATURE_ASSET_VERSION="1.23.7-r2";
const FEATURE_SCRIPT_PATHS={
  portfolio:`${BASE_PATH}/ui-assets/feature-portfolio.js?v=${FEATURE_ASSET_VERSION}`,
  backtests:`${BASE_PATH}/ui-assets/feature-backtests.js?v=${FEATURE_ASSET_VERSION}`,
  finances:`${BASE_PATH}/ui-assets/feature-finances.js?v=${FEATURE_ASSET_VERSION}`,
  admin:`${BASE_PATH}/ui-assets/feature-admin.js?v=${FEATURE_ASSET_VERSION}`,
};
const FEATURE_BY_VIEW={portfolio:"portfolio",backtests:"backtests",finances:"finances",admin:"admin"};
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
  portfolio:["portfolios","portfolio-detail","portfolio-catalog","portfolio-news","portfolio-alerts","dividends-"],
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
  const coalesceKey = method === "GET" && !bypassCache && !key ? path : null;
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
    if (method === "GET" && cacheTtlMs > 0) state.readCache.set(path, {savedAt:Date.now(),body,tags:cacheTagsForPath(path)});
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
  if(warm)scheduleNavigationTask(()=>loadCurrentView(),PANEL_REVALIDATE_DELAY_MS);
  else loadCurrentView();
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
    if(restored)scheduleNavigationTask(()=>loadCurrentView(),PANEL_REVALIDATE_DELAY_MS);
    else loadCurrentView();
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
    root.innerHTML=marketUpdatePanel(["official_calendar"])+sectionCard("Agenda oficial do investidor",table,"Eventos econômicos, feriados e eleições renovados anualmente");
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
    root.innerHTML=marketUpdatePanel(["cvm_relevant_facts"])+sectionCard("Fatos relevantes oficiais",content,"Metadados e documentos publicados no sistema IPE da CVM",{url:"https://dados.cvm.gov.br/dataset/cia_aberta-doc-ipe",label:"CVM • Dados Abertos"});
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
  root.innerHTML=marketUpdatePanel(["comparison"])+sectionCard("Comparador histórico",`${selectors}<div class="chart comparison-chart-wrap">${svg}</div><div class="chart-legend">${legend}</div>${sectionCard("Retorno e risco no período",metrics,"Volatilidade anualizada conforme a frequência de cada série")}${unavailable.length?`<div class="notice">Sem dados nesta atualização: ${esc(unavailable.join(", "))}.</div>`:""}<div class="notice info">${esc(payload.note||"Base 100 no início do período selecionado.")} ${state.comparisonBaseMode==="common"?"Todas as linhas começam na primeira data disponível em comum.":"Cada linha usa seu próprio primeiro dado disponível."}</div>`,`Desempenho acumulado • base R$ 100 • ${periodLabel}`);
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
    state.analysisResultCache.set(cacheKey,{savedAt:Date.now(),rows:primaryRows});
    state.analysisLastUpdatedAt[type]=Date.now();
    renderAnalysisRows(primaryRows);
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
    state.analysisResultCache.set(cacheKey,{savedAt:Date.now(),rows:enrichedRows});
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
  $("#apply-advanced-filters").addEventListener("click",applyAdvancedFilters);
  $("#save-custom-filter").addEventListener("click",saveCustomFilter);
  $("#delete-custom-filter").addEventListener("click",deleteCustomFilter);
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
  renderFilterInputs(); bindEvents();
  try {
    const session=await api("/session/me");
    if(!session.authenticated){showLogin();return;}
    state.session=session; configureAccess(); showApp();
    $("#finance-month").value=state.financeMonth;
    updateNavigationAccessibility();
    applyNavigationFromLocation({historyMode:"replace",useStored:!new URLSearchParams(location.search).has("view")});
    if(session.access?.can_view_market)prefetchAnalysisCatalogs();
    if(session.access?.can_view_news_insights)api("/insights/news/refresh-daily",{method:"POST",invalidateCache:false}).catch(()=>{});
  } catch(error) { showLogin(); toast(error.message,"error"); }
}

document.addEventListener("DOMContentLoaded",initialize);
