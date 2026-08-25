import math
import os
import html
from datetime import date, datetime, timedelta, timezone
import pandas as pd
import requests
import streamlit as st
from investment_engine.ui_helpers import format_brl_price_input, parse_brl_price_input
from investment_engine.core.screening.universe import (
    BESST_LABELS,
    COMPANY_SIZE_LABELS,
    apply_universe_subfilters,
    filter_rows_by_tickers,
    universe_tickers,
)
from investment_engine.core.strategies.presets import FII_STRATEGIES, STOCK_STRATEGIES
from investment_engine.integrations.github_actions import (
    GitHubActionsError,
    cancel_workflow_run,
    dispatch_official_backtests,
    list_workflow_runs,
)

st.set_page_config(
    page_title="Formação do Investidor",
    page_icon=":material/school:",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"Get help": None, "Report a Bug": None, "About": None},
)

st.markdown("""
<style>
    /* Mantém o cabeçalho estrutural para o controle da barra lateral, enquanto
       remove os elementos técnicos e a identificação visual da plataforma. */
    header[data-testid="stHeader"] {
        background:rgba(248,251,250,.96); border-bottom:1px solid rgba(20,103,78,.08);
        backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
    }
    #MainMenu,
    [data-testid="stToolbar"],
    [data-testid="stStatusWidget"],
    [data-testid="stDecoration"],
    .stDeployButton,
    footer {display:none !important; visibility:hidden !important;}
    .block-container {padding-top: 4rem; padding-bottom: 2rem; max-width: 1500px;}
    .block-container h1 {font-size:2rem; line-height:1.12; margin:.15rem 0 .2rem;}
    .block-container h2 {font-size:1.38rem; margin:.35rem 0 .15rem;}
    .block-container h3 {font-size:1.12rem; margin:.3rem 0 .1rem;}
    .block-container [data-testid="stVerticalBlock"] {gap:.55rem;}
    .block-container [data-testid="stHorizontalBlock"] {gap:.65rem;}
    .block-container [data-testid="stAlert"] {padding:.55rem .75rem; border-radius:.7rem;}
    .block-container [data-testid="stExpander"] {
        border:1px solid rgba(20,103,78,.14); border-radius:.8rem;
        background:rgba(248,252,250,.72); overflow:hidden;
    }
    .block-container [data-testid="stExpander"] details > summary {
        padding:.25rem .55rem; color:#244f42; font-weight:650;
    }
    .block-container [data-testid="stExpander"] details[open] > summary {
        background:rgba(222,243,234,.48); border-bottom:1px solid rgba(20,103,78,.10);
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f4faf7 0%, #edf6f2 52%, #f8fbfa 100%);
        border-right: 1px solid rgba(20, 103, 78, .14);
        box-shadow: 8px 0 30px rgba(21, 77, 60, .035);
    }
    section[data-testid="stSidebar"][aria-expanded="true"] {width:20rem !important; min-width:20rem !important; max-width:20rem !important;}
    section[data-testid="stSidebar"][aria-expanded="true"] > div {width:20rem !important; min-width:20rem !important; max-width:20rem !important;}
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {padding-top: .55rem;}
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap: .55rem;}
    .ie-brand {
        display:flex; align-items:center; gap:.8rem; padding:.35rem .05rem 1rem;
        border-bottom:1px solid rgba(20,103,78,.12); margin-bottom:.15rem;
    }
    .ie-brand-mark {
        width:46px; height:46px; flex:0 0 46px; display:grid; place-items:center;
        color:#fff; font-weight:800; font-size:1rem; letter-spacing:-.04em;
        border-radius:14px; background:linear-gradient(145deg,#168765,#0b634b);
        box-shadow:0 8px 18px rgba(18,126,94,.22);
    }
    .ie-brand-title {font-size:1rem; line-height:1.15; font-weight:750; color:#133f33;}
    .ie-brand-subtitle {font-size:.72rem; color:#658078; margin-top:.2rem; letter-spacing:.02em;}
    .ie-account-card {
        padding:.85rem; border:1px solid rgba(20,103,78,.13); border-radius:14px;
        background:rgba(255,255,255,.76); box-shadow:0 5px 16px rgba(36,77,65,.045);
    }
    .ie-account-row {display:flex; align-items:center; gap:.7rem; min-width:0;}
    .ie-avatar {
        width:38px; height:38px; flex:0 0 38px; display:grid; place-items:center;
        border-radius:50%; color:#12684f; font-weight:750; font-size:.8rem;
        background:#dff3ea; border:1px solid rgba(18,104,79,.13);
    }
    .ie-account-copy {min-width:0; flex:1;}
    .ie-account-name {font-size:.86rem; font-weight:700; color:#173e34; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
    .ie-account-email {font-size:.68rem; color:#71847e; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin-top:.1rem;}
    .ie-account-meta {display:flex; align-items:center; justify-content:space-between; gap:.4rem; margin-top:.65rem;}
    .ie-profile-badge {
        display:inline-flex; align-items:center; border-radius:999px; padding:.2rem .48rem;
        color:#17664f; background:#e1f3eb; font-size:.66rem; font-weight:650;
    }
    .ie-approved {font-size:.66rem; color:#54736a;}
    .ie-engine-card {
        display:flex; align-items:center; gap:.7rem; padding:.72rem .82rem; margin-top:.1rem;
        border-radius:13px; color:#174f3e; background:linear-gradient(135deg,#d8f2e5,#cdebdc);
        border:1px solid rgba(24,128,94,.09);
    }
    .ie-status-dot {width:9px; height:9px; border-radius:50%; flex:0 0 9px; background:#14a36f; box-shadow:0 0 0 4px rgba(20,163,111,.13);}
    .ie-engine-title {font-size:.78rem; font-weight:700; line-height:1.15;}
    .ie-engine-version {font-size:.66rem; opacity:.72; margin-top:.12rem;}
    .ie-menu-title {font-size:.68rem; font-weight:750; color:#698078; letter-spacing:.1em; margin:1rem 0 .15rem;}
    section[data-testid="stSidebar"] div[role="radiogroup"] {gap:.55rem; width:100%;}
    section[data-testid="stSidebar"] div[role="radiogroup"] label {
        position:relative; width:100%; min-height:49px; box-sizing:border-box;
        display:flex; align-items:center; margin:0; padding:.7rem .82rem;
        border:1px solid rgba(33,91,73,.14); border-radius:13px;
        color:#2a4a40; background:rgba(255,255,255,.58);
        box-shadow:0 2px 8px rgba(36,77,65,.025);
        transition:background .16s ease,border-color .16s ease,box-shadow .16s ease,transform .16s ease;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
        border-color:rgba(20,126,92,.28); background:#fff; transform:translateX(2px);
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
        color:#0f6249; font-weight:700; border-color:rgba(17,137,98,.32);
        background:linear-gradient(135deg,#e0f5eb,#d5efe3);
        box-shadow:0 6px 15px rgba(26,121,91,.10);
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked)::before {
        content:""; position:absolute; left:-1px; top:10px; bottom:10px; width:4px;
        border-radius:0 6px 6px 0; background:#13966b;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] input[type="radio"] {
        position:absolute; opacity:0; width:1px; height:1px;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:focus-visible) {
        outline:3px solid rgba(20,139,99,.22); outline-offset:2px;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] [data-testid="stMarkdownContainer"] p {
        margin:0; font-size:.82rem; line-height:1.25;
    }
    section[data-testid="stSidebar"] [data-testid="stButton"] button {
        width:100%; min-height:40px; border-radius:11px; border-color:rgba(33,91,73,.16);
        color:#36584e; background:rgba(255,255,255,.58);
    }
    section[data-testid="stSidebar"] [data-testid="stButton"] button:hover {
        color:#0e684c; border-color:rgba(20,126,92,.28); background:#fff;
    }
    .ie-sidebar-footer {
        margin-top:1.05rem; padding-top:.8rem; border-top:1px solid rgba(20,103,78,.12);
        color:#7a8c86; font-size:.65rem; text-align:center; letter-spacing:.02em;
    }
    div[data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,.20); border-radius: .75rem; padding: .5rem .72rem;
        background: rgba(128,128,128,.035);
    }
    div[data-testid="stMetric"] [data-testid="stMetricLabel"] {font-size:.74rem;}
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {font-size:1.35rem;}
    div[data-testid="stDataFrame"] {border-radius: .75rem; overflow: hidden;}
    .ie-compact-summary {
        display:flex; align-items:center; gap:.55rem; flex-wrap:wrap;
        margin:.15rem 0 .45rem; padding:.58rem .72rem; border-radius:.8rem;
        border:1px solid rgba(20,103,78,.13); background:linear-gradient(135deg,#f5fbf8,#eef8f3);
    }
    .ie-compact-summary-title {font-size:.72rem; font-weight:750; color:#315a4d; margin-right:.1rem;}
    .ie-filter-chip {
        display:inline-flex; align-items:center; min-height:24px; padding:.18rem .52rem;
        border-radius:999px; background:#dff2e9; color:#17634d; font-size:.68rem; font-weight:650;
        border:1px solid rgba(20,111,82,.10);
    }
    .ie-filter-chip-muted {background:#edf1ef; color:#65736e;}
    .ie-section-hint {font-size:.7rem; color:#6b8179; margin:-.15rem 0 .2rem;}
    @media (max-width: 768px) {
        .block-container {padding-top:4.35rem; padding-left:1rem; padding-right:1rem;}
        .block-container h1 {font-size:1.72rem; line-height:1.16;}
    }
</style>
""",unsafe_allow_html=True)

CURRENT_USER_EMAIL=""
CURRENT_USER_NAME=""
PERMISSIONS={}
MARKET_ASSET_TYPES={"Ações":"stock","FIIs":"fii","Demais Ativos B3":"other_b3"}

def _env_flag(name,default=False):
    return os.getenv(name,"true" if default else "false").strip().lower() in {"1","true","yes","on"}

def _protect_private_beta():
    global CURRENT_USER_EMAIL,CURRENT_USER_NAME
    if not _env_flag("APP_AUTH_REQUIRED",False):
        return
    try:
        logged_in=bool(getattr(st.user,"is_logged_in",False))
    except Exception:
        logged_in=False
    if not logged_in:
        st.title("🔐 Formação do Investidor")
        st.write("Este ambiente está em beta privado. Entre com uma conta autorizada para continuar.")
        if st.button("Entrar com Google",type="primary",use_container_width=True):
            try:
                st.login()
            except Exception:
                st.error("A autenticação ainda não foi configurada neste servidor.")
        st.stop()
    email=str(getattr(st.user,"email","") or "").strip().lower()
    CURRENT_USER_EMAIL=email
    CURRENT_USER_NAME=str(getattr(st.user,"name","") or getattr(st.user,"given_name","") or "").strip()

_protect_private_beta()

DEFAULT_API=os.getenv("INVESTMENT_API_URL","http://127.0.0.1:8000").rstrip("/")
if _env_flag("SHOW_API_SELECTOR",True):
    API=st.sidebar.text_input("Investment Engine API",DEFAULT_API).rstrip("/")
else:
    API=DEFAULT_API

def _request(method,path,params=None,json=None,timeout=120):
    try:
        headers={"X-App-User-Email":CURRENT_USER_EMAIL} if CURRENT_USER_EMAIL else {}
        r=requests.request(method,f"{API}{path}",params=params,json=json,headers=headers,timeout=timeout)
        r.raise_for_status(); return r.json(),None
    except requests.RequestException as exc:
        detail=getattr(exc.response,"text",None) if getattr(exc,"response",None) is not None else None
        return None,(detail or str(exc))

def api_get(path,params=None):return _request("GET",path,params=params)
def api_post(path,json=None,timeout=180):return _request("POST",path,json=json,timeout=timeout)
def api_put(path,json=None,timeout=120):return _request("PUT",path,json=json,timeout=timeout)
def api_patch(path,json=None,timeout=120):return _request("PATCH",path,json=json,timeout=timeout)
def api_delete(path,timeout=120):return _request("DELETE",path,timeout=timeout)

def can(permission):return bool(PERMISSIONS.get(permission,False))


def _render_sidebar_identity(health):
    display_name=CURRENT_USER_NAME or (CURRENT_USER_EMAIL.split("@",1)[0] if CURRENT_USER_EMAIL else "Ambiente local")
    name_parts=[part for part in display_name.replace("."," ").split() if part]
    initials="".join(part[0] for part in name_parts[:2]).upper() or "FI"
    role_labels={"owner":"Proprietário","admin":"Administrador","member":"Membro","visitor":"Visitante"}
    status_labels={"approved":"Acesso aprovado","pending":"Aguardando aprovação","blocked":"Acesso bloqueado"}
    role=role_labels.get(PERMISSIONS.get("role"),"Usuário")
    status=status_labels.get(PERMISSIONS.get("status"),"Acesso local")
    version=html.escape(str(health.get("version") or "?"))
    st.sidebar.markdown(f"""
<div class="ie-brand">
  <div class="ie-brand-mark">FI</div>
  <div><div class="ie-brand-title">Formação do Investidor</div><div class="ie-brand-subtitle">Investment Engine</div></div>
</div>
<div class="ie-account-card">
  <div class="ie-account-row">
    <div class="ie-avatar">{html.escape(initials)}</div>
    <div class="ie-account-copy">
      <div class="ie-account-name">{html.escape(display_name)}</div>
      <div class="ie-account-email">{html.escape(CURRENT_USER_EMAIL or "Execução local")}</div>
    </div>
  </div>
  <div class="ie-account-meta"><span class="ie-profile-badge">{html.escape(role)}</span><span class="ie-approved">{html.escape(status)}</span></div>
</div>
<div class="ie-engine-card">
  <span class="ie-status-dot"></span>
  <div><div class="ie-engine-title">Motor operacional</div><div class="ie-engine-version">Versão {version}</div></div>
</div>
""",unsafe_allow_html=True)
    if CURRENT_USER_EMAIL and st.sidebar.button("↪  Sair da conta",key="app_logout",use_container_width=True):
        st.logout()
    st.sidebar.markdown('<div class="ie-menu-title">MENU PRINCIPAL</div>',unsafe_allow_html=True)


def _private_setting(name,default=""):
    """Lê uma configuração do servidor sem exibi-la nem enviá-la ao navegador."""
    try:
        value=st.secrets.get(name,os.getenv(name,default))
    except Exception:
        value=os.getenv(name,default)
    return str(value or "").strip()


def _reset_market_refinements(asset_type,reason="O universo de ativos foi alterado."):
    """Clear dependent filters before Streamlit rebuilds their widgets."""
    st.session_state[f"market_strategy_ref_{asset_type}"]="preset:all"
    st.session_state[f"market_table_ticker_{asset_type}"]=""
    st.session_state["advanced_screen_result"]=None
    st.session_state[f"market_scope_notice_{asset_type}"]=reason


def _clear_market_subfilters(asset_type):
    """Restore every dependent subfilter without changing the base universe."""
    st.session_state[f"market_subfilter_size_enabled_{asset_type}"]=False
    st.session_state[f"market_subfilter_size_values_{asset_type}"]=[]
    st.session_state[f"market_subfilter_ibov_enabled_{asset_type}"]=False
    st.session_state[f"market_subfilter_ibov_value_{asset_type}"]="inside"
    st.session_state[f"market_subfilter_class_enabled_{asset_type}"]=False


def _change_market_base_universe(asset_type):
    _clear_market_subfilters(asset_type)
    _reset_market_refinements(
        asset_type,
        "O universo principal foi alterado; os subfiltros e refinamentos anteriores foram removidos.",
    )


def _restore_full_market(asset_type):
    st.session_state[f"market_universe_mode_{asset_type}"]="all"
    _clear_market_subfilters(asset_type)
    _reset_market_refinements(asset_type,"O universo completo foi restaurado e os refinamentos anteriores foram removidos.")


def _change_market_asset_class():
    asset_type=MARKET_ASSET_TYPES.get(st.session_state.get("market_asset_class","Ações"),"stock")
    st.session_state[f"market_universe_mode_{asset_type}"]="all"
    _clear_market_subfilters(asset_type)
    st.session_state[f"market_strategy_ref_{asset_type}"]="preset:default"
    st.session_state[f"market_table_ticker_{asset_type}"]=""
    st.session_state["advanced_screen_result"]=None
    st.session_state["analysis_payload_v14"]=None
    st.session_state[f"market_scope_notice_{asset_type}"]="O tipo de ativo foi alterado; a lista Padrão deste mercado foi carregada."


def _initialize_market_panel():
    """Open the market area in the documented stock/default-analysis state."""
    asset_type="stock"
    st.session_state["market_asset_class"]="Ações"
    st.session_state[f"market_universe_mode_{asset_type}"]="all"
    _clear_market_subfilters(asset_type)
    st.session_state[f"market_strategy_ref_{asset_type}"]="preset:default"
    st.session_state[f"market_result_limit_{asset_type}"]=50
    st.session_state[f"market_table_ticker_{asset_type}"]=""
    st.session_state[f"market_analysis_revision_{asset_type}"]=int(st.session_state.get(f"market_analysis_revision_{asset_type}",0))+1
    st.session_state["advanced_screen_result"]=None
    st.session_state["analysis_payload_v14"]=None


def _select_market_analysis(asset_type,strategy_ref):
    """Select an analysis and recreate its editor from the preset's saved defaults."""
    st.session_state[f"market_strategy_ref_{asset_type}"]=strategy_ref
    st.session_state[f"market_table_ticker_{asset_type}"]=""
    st.session_state[f"market_analysis_revision_{asset_type}"]=int(st.session_state.get(f"market_analysis_revision_{asset_type}",0))+1
    st.session_state["advanced_screen_result"]=None


def _analysis_filter_defaults(asset_type,strategy_ref,custom_by_id):
    if strategy_ref.startswith("custom:"):
        item=custom_by_id.get(strategy_ref.split(":",1)[1]) or {}
        return dict(item.get("filters") or {})
    if not strategy_ref.startswith("preset:") or strategy_ref=="preset:all":
        return {}
    strategy_id=strategy_ref.split(":",1)[1]
    strategies=STOCK_STRATEGIES if asset_type=="stock" else FII_STRATEGIES
    selected=strategies.get(strategy_id)
    return selected.filters.model_dump() if selected else {}


def _graham_sort_key(row):
    value=row.get("graham_upside_pct")
    try:return (value is not None,float(value))
    except (TypeError,ValueError):return (False,float("-inf"))


def _navigate_to(module):
    st.session_state["main_navigation"]=module


def _remember_market_backtest_selection(tickers,label):
    clean=[]
    for ticker in tickers or []:
        value=str(ticker or "").strip().upper()
        if value and value not in clean:clean.append(value)
    source_label=str(label or "Mercado e análise")
    st.session_state["market_backtest_selection_stock"]={
        "tickers":clean[:100],"total":len(clean),"label":source_label,
        "signature":source_label+"|"+",".join(clean[:100]),
    }
    return clean


def _send_market_selection_to_official_batch(tickers,label):
    clean=[]
    for ticker in tickers or []:
        value=str(ticker or "").strip().upper()
        if value and value not in clean:clean.append(value)
    st.session_state["official_batch_selected_tickers"]=clean[:100]
    st.session_state["official_batch_selection_source"]={
        "label":str(label or "Mercado e análise"),"count":len(clean),
    }
    st.session_state["official_batch_market_signature_applied"]=str(label or "Mercado e análise")+"|"+",".join(clean[:100])
    st.session_state["main_navigation"]="access"


def _set_official_batch_selection(tickers,label):
    _send_market_selection_to_official_batch(tickers,label)
    st.session_state["main_navigation"]="access"

def br_money(v):
    if v is None or (isinstance(v,float) and math.isnan(v)):return "N/D"
    return f"R$ {float(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")

def br_num(v,digits=1,suffix=""):
    if v is None or (isinstance(v,float) and math.isnan(v)):return "N/D"
    return f"{float(v):.{digits}f}".replace(".",",")+suffix

def br_datetime(value):
    if not value:return "N/D"
    try:
        timestamp=pd.Timestamp(value)
        if timestamp.tzinfo is None:timestamp=timestamp.tz_localize("UTC")
        return timestamp.tz_convert("America/Sao_Paulo").strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)

def _datetime_sort_value(value):
    try:
        timestamp=pd.Timestamp(value)
        if pd.isna(timestamp):return -1
        if timestamp.tzinfo is None:timestamp=timestamp.tz_localize("UTC")
        return int(timestamp.tz_convert("UTC").value)
    except Exception:
        return -1

def score_label(v):
    if v is None:return "N/D"
    if v>=85:return "Excelente"
    if v>=70:return "Bom"
    if v>=55:return "Moderado"
    if v>=40:return "Fraco"
    return "Muito fraco"

def render_score_card(name,value,coverage=None):
    st.metric(name,br_num(value,1))
    st.caption(score_label(value)+(f" • cobertura {br_num(coverage,0,'%')}" if coverage is not None else ""))

def _pct(v):
    return "N/D" if v is None else br_num(v,1,"%")


def _compact_summary(title,items,muted_items=None):
    """Render the current context without exposing the complete configuration panel."""
    chips=[]
    for item in items or []:
        if item not in (None,""):
            chips.append(f'<span class="ie-filter-chip">{html.escape(str(item))}</span>')
    for item in muted_items or []:
        if item not in (None,""):
            chips.append(f'<span class="ie-filter-chip ie-filter-chip-muted">{html.escape(str(item))}</span>')
    st.markdown(
        '<div class="ie-compact-summary">'
        f'<span class="ie-compact-summary-title">{html.escape(str(title))}</span>'
        +"".join(chips)+"</div>",
        unsafe_allow_html=True,
    )


def _backtest_filter_summary(filters):
    trend_labels={"daily_trend":"Diária","weekly_trend":"Semanal","monthly_trend":"Mensal"}
    technical_labels={
        "adx_min":"ADX","volume_ratio_min":"Volume","rsi_min":"RSI","rsi_max":"RSI",
        "atr_pct_min":"ATR","atr_pct_max":"ATR",
    }
    active_trends=[label for key,label in trend_labels.items() if (filters.get(key) or {}).get("enabled")]
    active_technical=sorted({label for key,label in technical_labels.items() if filters.get(key) is not None})
    fundamental_count=len(filters.get("fundamental_entry") or {})+len(filters.get("fundamental_exit") or {})
    items=[]
    if active_trends:items.append("Tendência: "+", ".join(active_trends))
    if active_technical:items.append("Confirmação: "+", ".join(active_technical))
    if fundamental_count:items.append(f"Fundamentos: {fundamental_count} regra(s)")
    if filters.get("exit_on_filter_failure"):items.append("Saída ao falhar filtro")
    return items or ["Sem filtros adicionais"]


def _active_range(enabled, min_value=None, max_value=None):
    if not enabled:
        return None
    out={}
    if min_value is not None:out["min"]=float(min_value)
    if max_value is not None:out["max"]=float(max_value)
    return out


def render_advanced_screener(
    asset_type,allowed_tickers=None,universe_label="Universo completo",
    initial_filters=None,form_instance="default",compact=False,
):
    initial_filters=dict(initial_filters or {})
    def seeded(name,fallback):
        value=initial_filters.get(name)
        return float(value) if value is not None else float(fallback)
    def enabled(*names):
        return any(initial_filters.get(name) is not None for name in names)

    if compact:st.markdown("#### Ajustar indicadores desta análise")
    else:st.subheader("Screener configurável — Fundamentalista + Técnico")
    st.caption(f"Universo atual: {universe_label}. Ative somente as regras que quiser. Filtros ativos são combinados por E (AND): o ativo precisa satisfazer todos eles. N/D nunca passa por um filtro ativo.")
    market_name={"stock":"Ações","fii":"FIIs","other_b3":"Demais Ativos B3"}.get(asset_type,"Ativos")
    if "advanced_screen_result" not in st.session_state:st.session_state.advanced_screen_result=None

    with st.form(f"advanced_screen_form_{asset_type}_{form_instance}"):
        st.markdown(f"#### Indicadores Fundamentalistas — {market_name}")
        st.caption("Ative, desative ou altere os limites abaixo. Ao clicar novamente no botão da análise, os valores originais daquele método são restaurados.")
        fundamental={}
        if asset_type=="stock":
            c1,c2,c3,c4=st.columns(4)
            use_pe=c1.checkbox("Usar P/L",value=enabled("pe_min","pe_max")); pe_min=c1.number_input("P/L mínimo",value=seeded("pe_min",0),step=0.5); pe_max=c1.number_input("P/L máximo",value=seeded("pe_max",15),step=0.5)
            use_pbv=c2.checkbox("Usar P/VP",value=enabled("pbv_max")); pbv_max=c2.number_input("P/VP máximo",value=seeded("pbv_max",2),step=0.1)
            use_dy=c3.checkbox("Usar Dividend Yield",value=enabled("dividend_yield_min")); dy_min=c3.number_input("DY mínimo (%)",value=seeded("dividend_yield_min",4),step=0.5)
            use_liq=c4.checkbox("Usar liquidez diária",value=enabled("daily_liquidity_min")); liq_min=c4.number_input("Liquidez diária mínima (R$)",value=seeded("daily_liquidity_min",1000000),step=100000.0,format="%.0f")

            c1,c2,c3,c4=st.columns(4)
            use_roe=c1.checkbox("Usar ROE",value=enabled("roe_min")); roe_min=c1.number_input("ROE mínimo (%)",value=seeded("roe_min",10),step=1.0)
            use_roic=c2.checkbox("Usar ROIC",value=enabled("roic_min")); roic_min=c2.number_input("ROIC mínimo (%)",value=seeded("roic_min",8),step=1.0)
            use_ebit=c3.checkbox("Usar margem EBIT",value=enabled("ebit_margin_min")); ebit_min=c3.number_input("Margem EBIT mínima (%)",value=seeded("ebit_margin_min",8),step=1.0)
            use_net=c4.checkbox("Usar margem líquida",value=enabled("net_margin_min")); net_min=c4.number_input("Margem líquida mínima (%)",value=seeded("net_margin_min",5),step=1.0)

            c1,c2,c3,c4=st.columns(4)
            use_ev=c1.checkbox("Usar EV/EBITDA",value=enabled("ev_ebitda_max")); ev_max=c1.number_input("EV/EBITDA máximo",value=seeded("ev_ebitda_max",10),step=0.5)
            use_debt=c2.checkbox("Usar dívida bruta/PL",value=enabled("gross_debt_to_equity_max")); debt_max=c2.number_input("Dívida bruta/PL máxima",value=seeded("gross_debt_to_equity_max",1.5),step=0.1)
            use_ndebt=c3.checkbox("Usar dívida líquida/EBITDA",value=enabled("net_debt_to_ebitda_max")); ndebt_max=c3.number_input("Dív. líquida/EBITDA máxima",value=seeded("net_debt_to_ebitda_max",3),step=0.25)
            use_cr=c4.checkbox("Usar liquidez corrente",value=enabled("current_ratio_min")); cr_min=c4.number_input("Liquidez corrente mínima",value=seeded("current_ratio_min",1),step=0.1)

            c1,c2=st.columns(2)
            use_rev=c1.checkbox("Usar CAGR receita 5 anos",value=enabled("revenue_cagr_5y_min")); rev_min=c1.number_input("CAGR receita mínimo (%)",value=seeded("revenue_cagr_5y_min",5),step=1.0)
            use_earn=c2.checkbox("Usar CAGR lucro 5 anos",value=enabled("earnings_cagr_5y_min")); earn_min=c2.number_input("CAGR lucro mínimo (%)",value=seeded("earnings_cagr_5y_min",5),step=1.0)

            fundamental={
                "pe":_active_range(use_pe,pe_min,pe_max), "pbv":_active_range(use_pbv,None,pbv_max),
                "dividend_yield_pct":_active_range(use_dy,dy_min,None), "daily_liquidity":_active_range(use_liq,liq_min,None),
                "roe_pct":_active_range(use_roe,roe_min,None), "roic_pct":_active_range(use_roic,roic_min,None),
                "ebit_margin_pct":_active_range(use_ebit,ebit_min,None), "net_margin_pct":_active_range(use_net,net_min,None),
                "ev_ebitda":_active_range(use_ev,None,ev_max), "gross_debt_to_equity":_active_range(use_debt,None,debt_max),
                "net_debt_to_ebitda":_active_range(use_ndebt,None,ndebt_max), "current_ratio":_active_range(use_cr,cr_min,None),
                "revenue_cagr_5y_pct":_active_range(use_rev,rev_min,None), "earnings_cagr_5y_pct":_active_range(use_earn,earn_min,None),
            }
        elif asset_type=="fii":
            c1,c2,c3,c4=st.columns(4)
            use_pbv=c1.checkbox("Usar P/VP",value=enabled("pbv_min","pbv_max")); pbv_min=c1.number_input("P/VP mínimo",value=seeded("pbv_min",0.5),step=0.05); pbv_max=c1.number_input("P/VP máximo",value=seeded("pbv_max",1.1),step=0.05)
            use_dy=c2.checkbox("Usar Dividend Yield",value=enabled("dividend_yield_min")); dy_min=c2.number_input("DY mínimo (%)",value=seeded("dividend_yield_min",7),step=0.5)
            use_ffo=c3.checkbox("Usar FFO Yield",value=enabled("ffo_yield_min")); ffo_min=c3.number_input("FFO Yield mínimo (%)",value=seeded("ffo_yield_min",5),step=0.5)
            use_cap=c4.checkbox("Usar Cap Rate",value=enabled("cap_rate_min")); cap_min=c4.number_input("Cap Rate mínimo (%)",value=seeded("cap_rate_min",5),step=0.5)
            c1,c2,c3,c4=st.columns(4)
            use_vac=c1.checkbox("Usar vacância física",value=enabled("vacancy_max")); vac_max=c1.number_input("Vacância máxima (%)",value=seeded("vacancy_max",10),step=1.0)
            use_fvac=c2.checkbox("Usar vacância financeira",value=enabled("financial_vacancy_max")); fvac_max=c2.number_input("Vacância financeira máxima (%)",value=seeded("financial_vacancy_max",10),step=1.0)
            use_ltv=c3.checkbox("Usar LTV",value=enabled("ltv_max")); ltv_max=c3.number_input("LTV máximo (%)",value=seeded("ltv_max",40),step=1.0)
            use_wale=c4.checkbox("Usar WALE",value=enabled("wale_min")); wale_min=c4.number_input("WALE mínimo (anos)",value=seeded("wale_min",2),step=0.5)
            use_liq=st.checkbox("Usar liquidez diária do FII",value=enabled("daily_liquidity_min")); liq_min=st.number_input("Liquidez diária mínima (R$)",value=seeded("daily_liquidity_min",500000),step=100000.0,format="%.0f")
            fundamental={
                "pbv":_active_range(use_pbv,pbv_min,pbv_max), "dividend_yield_pct":_active_range(use_dy,dy_min,None),
                "ffo_yield_pct":_active_range(use_ffo,ffo_min,None), "cap_rate_pct":_active_range(use_cap,cap_min,None),
                "vacancy_pct":_active_range(use_vac,None,vac_max), "financial_vacancy_pct":_active_range(use_fvac,None,fvac_max),
                "ltv_pct":_active_range(use_ltv,None,ltv_max), "wale_years":_active_range(use_wale,wale_min,None),
                "daily_liquidity":_active_range(use_liq,liq_min,None),
            }
        else:
            st.info("Para ETFs, BDRs e futuros, os filtros empresariais e imobiliários incompatíveis ficam ocultos. Esta tela usa somente liquidez e indicadores técnicos comparáveis.")
            use_liq=st.checkbox("Usar liquidez diária",value=enabled("daily_liquidity_min"))
            liq_min=st.number_input("Liquidez diária mínima (R$)",value=seeded("daily_liquidity_min",500000),step=100000.0,format="%.0f")
            fundamental={"daily_liquidity":_active_range(use_liq,liq_min,None)}
        fundamental={k:v for k,v in fundamental.items() if v is not None}

        st.markdown("##### Valuation e scores fundamentalistas")
        score_filters={}
        if asset_type=="other_b3":
            below_graham=False; below_barsi=False; score_enabled=False
            st.caption("Oculto nesta categoria: Graham, Bazin/Barsi, ALB, Quality, Value e Growth. Esses modelos dependem de fundamentos de empresa ou FII.")
        else:
            v1,v2,v3=st.columns(3)
            below_graham=v1.checkbox("Preço abaixo do Graham",value=bool(initial_filters.get("require_below_graham")),disabled=asset_type!="stock")
            below_barsi=v2.checkbox("Preço abaixo do Teto Bazin/Barsi (6%)",value=bool(initial_filters.get("require_below_dividend_target")))
            score_enabled=v3.checkbox("Filtrar também por scores")
        if score_enabled:
            q1,q2,q3,q4=st.columns(4)
            alb=q1.number_input("ALB mínimo",min_value=0.0,max_value=100.0,value=55.0,step=5.0)
            quality=q2.number_input("Quality mínimo",min_value=0.0,max_value=100.0,value=50.0,step=5.0)
            value=q3.number_input("Value mínimo",min_value=0.0,max_value=100.0,value=50.0,step=5.0)
            dataq=q4.number_input("Data Quality mínimo",min_value=0.0,max_value=100.0,value=70.0,step=5.0)
            q1,q2,q3=st.columns(3)
            technical_score=q1.number_input("Technical mínimo",min_value=0.0,max_value=100.0,value=45.0,step=5.0)
            risk_score=q2.number_input("Risk mínimo",min_value=0.0,max_value=100.0,value=45.0,step=5.0)
            liquidity_score=q3.number_input("Liquidity mínimo",min_value=0.0,max_value=100.0,value=40.0,step=5.0)
            score_filters={"alb_score":{"min":alb},"quality_score":{"min":quality},"value_score":{"min":value},"data_quality_score":{"min":dataq},"technical_score":{"min":technical_score},"risk_score":{"min":risk_score},"liquidity_score":{"min":liquidity_score}}

        st.markdown("#### Indicadores Técnicos")
        st.caption("Tendências diária, semanal e mensal, RSI 14 e Pivot Points podem ser combinados com os fundamentos acima.")
        t1,t2,t3,t4=st.columns(4)
        trend_choices=[20,21] if asset_type=="other_b3" else [21,20]
        trend_period=t1.selectbox("Período das médias",trend_choices,help="Para Demais Ativos B3, 20 aproveita o snapshot técnico do catálogo. Com histórico local, 21 também pode ser usado.")
        trend_labels={"any":"Sem filtro","up":"🟢 Alta","down":"🔴 Baixa"}
        daily=t2.selectbox("Tendência diária",list(trend_labels),format_func=lambda x:trend_labels[x])
        weekly=t3.selectbox("Tendência semanal",list(trend_labels),format_func=lambda x:trend_labels[x])
        monthly=t4.selectbox("Tendência mensal",list(trend_labels),format_func=lambda x:trend_labels[x])

        r1c,r2c=st.columns(2)
        use_rsi=r1c.checkbox("Filtrar RSI (14)")
        rsi_min=r1c.number_input("RSI mínimo",min_value=0.0,max_value=100.0,value=30.0,step=1.0)
        rsi_max=r1c.number_input("RSI máximo",min_value=0.0,max_value=100.0,value=70.0,step=1.0)
        pivot_tf_label=r2c.selectbox("Período-base dos Pivot Points",["Diário","Semanal","Mensal"],help="Os níveis usam sempre o período anterior já encerrado.")
        pivot_tf={"Diário":"daily","Semanal":"weekly","Mensal":"monthly"}[pivot_tf_label]

        zone_labels={
            "any":"Sem filtro por faixa", "below_s3":"Abaixo de S3", "s3_s2":"Entre S3 e S2", "s2_s1":"Entre S2 e S1",
            "s1_pp":"Entre S1 e PP", "pp_r1":"Entre PP e R1", "r1_r2":"Entre R1 e R2", "r2_r3":"Entre R2 e R3", "above_r3":"Acima de R3",
        }
        p1,p2,p3=st.columns(3)
        pivot_zone=p1.selectbox("Faixa atual do preço",list(zone_labels),format_func=lambda x:zone_labels[x])
        near_labels={"none":"Sem proximidade","s3":"Próximo de S3","s2":"Próximo de S2","s1":"Próximo de S1","pp":"Próximo do PP","r1":"Próximo de R1","r2":"Próximo de R2","r3":"Próximo de R3"}
        near_level=p2.selectbox("Proximidade de nível",list(near_labels),format_func=lambda x:near_labels[x])
        tolerance=p3.number_input("Tolerância da proximidade (%)",min_value=0.0,max_value=20.0,value=0.5,step=0.1)

        with st.popover("Ver fórmulas de Pivot"):
            st.markdown("""
- **PP** = (Máxima + Mínima + Fechamento) / 3
- **R1** = (2 × PP) − Mínima
- **S1** = (2 × PP) − Máxima
- **R2** = PP + (Máxima − Mínima)
- **S2** = PP − (Máxima − Mínima)
- **R3** = Máxima + 2 × (PP − Mínima)
- **S3** = Mínima − 2 × (Máxima − PP)

Para não usar informação ainda incompleta, a referência é sempre o **dia/semana/mês anterior encerrado**.
""")
        limit=st.slider("Máximo de resultados do screener avançado",10,300,100,10)
        submitted=st.form_submit_button("🔎 Aplicar análise ajustada",type="primary")

    if submitted:
        tech={"daily_trend":daily,"weekly_trend":weekly,"monthly_trend":monthly,"pivot_zone":pivot_zone,"near_pivot_level":near_level,"pivot_tolerance_pct":tolerance}
        if use_rsi:tech["rsi14"]={"min":rsi_min,"max":rsi_max}
        payload={
            "asset_type":asset_type,"fundamental_filters":fundamental,"score_filters":score_filters,
            "valuation_flags":{"below_graham":bool(below_graham),"below_barsi_6pct":bool(below_barsi)},
            "technical_filters":tech,"trend_period":trend_period,"pivot_timeframe":pivot_tf,
            "include_technical_columns":True,"limit":limit,
            "allowed_tickers":list(allowed_tickers) if allowed_tickers is not None else None,
        }
        with st.spinner("Aplicando fundamentos, scores, tendências e pivôs..."):
            result,e=api_post("/screen/advanced",payload,timeout=240)
        if e:st.error(f"Screener avançado não concluído: {e}")
        else:
            result=dict(result or {})
            result["_analysis_context"]=str(form_instance)
            st.session_state.advanced_screen_result=result

    result=st.session_state.get("advanced_screen_result")
    if result and compact:
        meta=result.get("meta") or {}
        st.success(
            f"Análise ajustada aplicada: {int(meta.get('returned') or 0)} ativo(s) aprovado(s) "
            f"dentro de {universe_label}. A tabela principal abaixo foi atualizada."
        )
        if meta.get("technical_filter_active") and meta.get("technical_history_missing",0)>0:
            st.warning(f"{meta.get('technical_history_missing',0)} ativo(s) não possuíam histórico suficiente para os indicadores técnicos ativos.")
        return result
    if result:
        meta=result.get("meta") or {}; rows=result.get("rows") or []
        st.caption(f"Resultado calculado dentro de: **{universe_label}**.")
        a,b,c,d=st.columns(4)
        initial_filter_label="Após liquidez" if asset_type=="other_b3" else "Após fundamentos/scores"
        a.metric("Universo",meta.get("universe_count",0)); b.metric(initial_filter_label,meta.get("fundamental_candidates",0)); c.metric("Resultado final",meta.get("returned",0)); d.metric("Sem histórico técnico",meta.get("technical_history_missing",0))
        if meta.get("technical_filter_active") and meta.get("technical_history_missing",0)>0:
            st.warning("Alguns ativos não possuem histórico local suficiente para filtros técnicos/pivôs. Para ampliar a cobertura, carregue o histórico do universo.")
            if asset_type=="other_b3":
                st.caption("Para ETF ou BDR, abra a Análise individual e use ‘Carregar histórico deste ativo’. Futuros exigem uma série contínua própria.")
            else:
                st.code(f"python scripts/ingest_prices.py --all --type {asset_type} --range 3y")
        if not rows:
            if asset_type=="stock" and PERMISSIONS.get("is_owner"):
                _remember_market_backtest_selection([],f"Screener avançado • {universe_label}")
            st.info("Nenhum ativo satisfez simultaneamente todos os filtros ativados.")
        else:
            df=pd.DataFrame(rows)
            rename={
                "ticker":"Ticker","name":"Nome","asset_type_label":"Tipo","company_size_label":"Porte","sector_label":"Setor","segment_label":"Segmento","classification":"Categoria","price":"Preço","graham_number":"Preço Justo Graham","graham_upside_pct":"Potencial Graham %","pe":"P/L","pbv":"P/VP","dividend_yield_pct":"DY %","roe_pct":"ROE %","roic_pct":"ROIC %","ebit_margin_pct":"Margem EBIT %","net_margin_pct":"Margem Líquida %","ev_ebitda":"EV/EBITDA","gross_debt_to_equity":"Dív. Bruta/PL","net_debt_to_ebitda":"Dív. Líq./EBITDA","current_ratio":"Liq. Corrente","revenue_cagr_5y_pct":"CAGR Receita %","earnings_cagr_5y_pct":"CAGR Lucro %","ffo_yield_pct":"FFO Yield %","cap_rate_pct":"Cap Rate %","vacancy_pct":"Vacância %","ltv_pct":"LTV %","wale_years":"WALE","daily_liquidity":"Liquidez diária","alb_score":"ALB","quality_score":"Quality","value_score":"Value","growth_score":"Growth","technical_score":"Technical","risk_score":"Risk","liquidity_score":"Liquidity","data_quality_score":"Data Quality","trend_daily":"Tend. Dia","trend_weekly":"Tend. Sem.","trend_monthly":"Tend. Mês","sma_daily":"Média Dia","sma_weekly":"Média Sem.","sma_monthly":"Média Mês","rsi14_screen":"RSI 14","pp":"PP","s1":"S1","s2":"S2","s3":"S3","r1":"R1","r2":"R2","r3":"R3","pivot_zone":"Faixa Pivot","pivot_reference":"Referência Pivot",
            }
            view=df.rename(columns=rename)
            preferred=[c for c in ["Ticker","Nome","Tipo","Porte","Categoria","Setor","Segmento","Preço","Preço Justo Graham","Potencial Graham %","P/L","P/VP","DY %","ROE %","ROIC %","FFO Yield %","Cap Rate %","Vacância %","Liquidez diária","ALB","Quality","Value","Technical","Risk","Liquidity","Tend. Dia","Tend. Sem.","Tend. Mês","Média Dia","Média Sem.","Média Mês","RSI 14","S3","S2","S1","PP","R1","R2","R3","Faixa Pivot","Referência Pivot"] if c in view.columns]
            st.dataframe(view[preferred],hide_index=True,use_container_width=True,height=520)
            st.caption("Tendência = preço atual acima/abaixo da média simples do período escolhido. Sem histórico suficiente, o filtro técnico ativo reprova o ativo em vez de assumir zero.")
            if asset_type=="stock" and PERMISSIONS.get("is_owner"):
                advanced_tickers=_remember_market_backtest_selection(
                    [row.get("ticker") for row in rows],f"Screener avançado • {universe_label}",
                )
                if advanced_tickers:
                    st.button(
                        f"🧪 Gerar backtests oficiais destes {min(len(advanced_tickers),100)} ativo(s)",
                        key="advanced_to_official_backtests",type="primary",use_container_width=True,
                        on_click=_send_market_selection_to_official_batch,
                        args=(advanced_tickers,f"Screener avançado • {universe_label}"),
                    )
                    if len(advanced_tickers)>100:st.caption("O lote administrativo aceita no máximo 100 ativos; serão levados os 100 primeiros desta tabela.")
    return result


def _optional_filter_number(label,key,initial=None,default=0.0,min_value=-1000000000.0,max_value=1000000000.0,step=0.5):
    enabled=st.checkbox(f"Usar {label}",value=initial is not None,key=f"{key}_enabled")
    value=st.number_input(label,min_value=float(min_value),max_value=float(max_value),value=float(initial if initial is not None else default),step=float(step),key=f"{key}_value",disabled=not enabled)
    return float(value) if enabled else None


def _set_quantity_state(key, *, delta=0, minimum=0, exact=None):
    """Update a quantity from a Streamlit callback, before widgets are rendered."""
    current=int(float(st.session_state.get(key,minimum) or 0))
    st.session_state[key]=max(int(minimum),int(exact) if exact is not None else current+int(delta))


def _merge_purchase_position(existing_quantity,existing_average_price,purchase_quantity,purchase_price):
    """Consolidate a purchase without depending on a newly deployed helper module."""
    old_quantity=float(existing_quantity or 0)
    bought_quantity=float(purchase_quantity or 0)
    bought_price=float(purchase_price or 0)
    if old_quantity<0 or bought_quantity<=0 or bought_price<=0:
        raise ValueError("Quantidade e preço da compra devem ser maiores que zero.")
    new_quantity=old_quantity+bought_quantity
    if old_quantity>0 and existing_average_price is not None:
        new_average=((old_quantity*float(existing_average_price))+(bought_quantity*bought_price))/new_quantity
    else:
        new_average=bought_price
    return new_quantity,new_average


def _quantity_adjustment_buttons(quantity_key,key_prefix,*,disabled=False):
    """Render fixed portfolio adjustments without a separate step selector."""
    columns=st.columns(5)
    for column,amount in zip(columns,(100,50,10,5,1)):
        column.button(
            f"(+{amount})",key=f"{key_prefix}_plus_{amount}",use_container_width=True,
            disabled=disabled,on_click=_set_quantity_state,
            kwargs={"key":quantity_key,"delta":amount,"minimum":0},
        )
        column.button(
            f"(-{amount})",key=f"{key_prefix}_minus_{amount}",use_container_width=True,
            disabled=disabled,on_click=_set_quantity_state,
            kwargs={"key":quantity_key,"delta":-amount,"minimum":0},
        )


@st.fragment
def _quantity_control(label,quantity_key,key_prefix,*,initial_value=100,reset_key=None,disabled=False):
    """Fast local quantity editor: button clicks rerun only this fragment."""
    if reset_key and st.session_state.pop(reset_key,False):
        st.session_state[quantity_key]=int(initial_value)
    if quantity_key not in st.session_state:
        st.session_state[quantity_key]=int(initial_value)
    st.number_input(label,min_value=0,step=100,format="%d",key=quantity_key,disabled=disabled)
    _quantity_adjustment_buttons(quantity_key,key_prefix,disabled=disabled)
    return int(st.session_state.get(quantity_key,0) or 0)


def _custom_filter_editor(asset_type,prefix,initial=None):
    initial=initial or {}
    values={}
    if asset_type=="stock":
        c1,c2=st.columns(2)
        with c1:
            values["roe_min"]=_optional_filter_number("ROE mínimo (%)",f"{prefix}_roe",initial.get("roe_min"),0,-100,200,1)
            values["net_margin_min"]=_optional_filter_number("Margem líquida mínima (%)",f"{prefix}_net",initial.get("net_margin_min"),0,-100,200,1)
            values["ebit_margin_min"]=_optional_filter_number("Margem EBIT mínima (%)",f"{prefix}_ebit",initial.get("ebit_margin_min"),0,-100,200,1)
            values["revenue_cagr_5y_min"]=_optional_filter_number("CAGR de receita 5a mínimo (%)",f"{prefix}_cagr",initial.get("revenue_cagr_5y_min"),0,-100,300,1)
            values["pe_min"]=_optional_filter_number("P/L mínimo",f"{prefix}_pe_min",initial.get("pe_min"),0,-100,1000,0.5)
            values["pe_max"]=_optional_filter_number("P/L máximo",f"{prefix}_pe_max",initial.get("pe_max"),15,-100,1000,0.5)
        with c2:
            values["pbv_max"]=_optional_filter_number("P/VP máximo",f"{prefix}_pbv",initial.get("pbv_max"),2,-100,100,0.1)
            values["dividend_yield_min"]=_optional_filter_number("Dividend Yield mínimo (%)",f"{prefix}_dy",initial.get("dividend_yield_min"),4,0,100,0.5)
            values["ev_ebitda_max"]=_optional_filter_number("EV/EBITDA máximo",f"{prefix}_ev",initial.get("ev_ebitda_max"),10,-100,1000,0.5)
            values["gross_debt_to_equity_max"]=_optional_filter_number("Dívida bruta/PL máxima",f"{prefix}_debt",initial.get("gross_debt_to_equity_max"),1,0,100,0.1)
            values["current_ratio_min"]=_optional_filter_number("Liquidez corrente mínima",f"{prefix}_current",initial.get("current_ratio_min"),1,0,100,0.1)
            values["daily_liquidity_min"]=_optional_filter_number("Liquidez diária mínima (R$)",f"{prefix}_liq",initial.get("daily_liquidity_min"),1000000,0,100000000000,100000)
        values["require_below_graham"]=st.checkbox("Exigir preço abaixo do valor de Graham",value=bool(initial.get("require_below_graham")),key=f"{prefix}_graham")
    else:
        c1,c2=st.columns(2)
        with c1:
            values["pbv_max"]=_optional_filter_number("P/VP máximo",f"{prefix}_pbv",initial.get("pbv_max"),1,0,100,0.05)
            values["dividend_yield_min"]=_optional_filter_number("Dividend Yield mínimo (%)",f"{prefix}_dy",initial.get("dividend_yield_min"),8,0,100,0.5)
            values["ffo_yield_min"]=_optional_filter_number("FFO Yield mínimo (%)",f"{prefix}_ffo",initial.get("ffo_yield_min"),6,-100,100,0.5)
        with c2:
            values["cap_rate_min"]=_optional_filter_number("Cap Rate mínimo (%)",f"{prefix}_cap",initial.get("cap_rate_min"),6,-100,100,0.5)
            values["vacancy_max"]=_optional_filter_number("Vacância máxima (%)",f"{prefix}_vac",initial.get("vacancy_max"),10,0,100,0.5)
            values["daily_liquidity_min"]=_optional_filter_number("Liquidez diária mínima (R$)",f"{prefix}_liq",initial.get("daily_liquidity_min"),500000,0,100000000000,100000)
        values["require_below_dividend_target"]=st.checkbox("Exigir preço abaixo do teto por dividendos",value=bool(initial.get("require_below_dividend_target")),key=f"{prefix}_divtarget")
    return values


def render_custom_filter_manager(asset_type,payload):
    limit=int((payload or {}).get("limit") or 0); used=int((payload or {}).get("used") or 0)
    items=(payload or {}).get("items") or []
    with st.expander("🧑 Meus filtros personalizados",expanded=False):
        st.caption(f"Você utiliza {used} de {limit} configuração(ões) permitida(s). O limite vale para Ações e FIIs somados.")
        create_tab,edit_tab=st.tabs(["Criar novo","Alterar ou excluir"])
        with create_tab:
            if used>=limit:
                st.warning("Seu limite de filtros personalizados foi atingido. Exclua um filtro ou peça ao administrador para ampliar o limite.")
            else:
                name=st.text_input("Nome (opcional)",value="",placeholder="Em branco: usa seu nome e acrescenta (1), (2)... se necessário",key=f"custom_new_name_{asset_type}")
                values=_custom_filter_editor(asset_type,f"custom_new_{asset_type}")
                if st.button("Salvar novo filtro",type="primary",key=f"custom_create_{asset_type}"):
                    _,err=api_post("/screen/custom-filters",{"asset_type":asset_type,"name":name or None,"filters":values})
                    if err:st.error(f"Não foi possível salvar: {err}")
                    else:st.success("Filtro personalizado salvo."); st.rerun()
        with edit_tab:
            if not items:
                st.info("Nenhum filtro personalizado deste mercado.")
            else:
                by_id={item["id"]:item for item in items}
                chosen=st.selectbox("Filtro",list(by_id),format_func=lambda x:by_id[x]["name"],key=f"custom_edit_choice_{asset_type}")
                current=by_id[chosen]
                edit_name=st.text_input("Nome",value=current["name"],key=f"custom_edit_name_{asset_type}_{chosen}")
                values=_custom_filter_editor(asset_type,f"custom_edit_{asset_type}_{chosen}",current.get("filters") or {})
                a,b=st.columns(2)
                if a.button("Salvar alterações",type="primary",key=f"custom_update_{asset_type}_{chosen}",use_container_width=True):
                    _,err=api_put(f"/screen/custom-filters/{chosen}",{"name":edit_name,"filters":values})
                    if err:st.error(f"Não foi possível salvar: {err}")
                    else:st.success("Filtro atualizado."); st.rerun()
                if b.button("Excluir filtro",key=f"custom_delete_{asset_type}_{chosen}",use_container_width=True):
                    _,err=api_delete(f"/screen/custom-filters/{chosen}")
                    if err:st.error(f"Não foi possível excluir: {err}")
                    else:st.success("Filtro excluído."); st.rerun()


def _panel_number(value,unit=None,currency=None):
    if value is None:return "N/D"
    try:value=float(value)
    except (TypeError,ValueError):return "N/D"
    if currency=="BRL" or unit=="R$":return f"R$ {value:,.2f}".replace(",","X").replace(".",",").replace("X",".")
    if currency=="USD" or unit=="USD":return f"US$ {value:,.2f}".replace(",","X").replace(".",",").replace("X",".")
    if unit=="%":return f"{value:.2f}%".replace(".",",")
    return f"{value:,.2f}".replace(",","X").replace(".",",").replace("X",".")


def _panel_delta(value):
    if value is None:return None
    try:return f"{float(value):+.2f}%".replace(".",",")
    except (TypeError,ValueError):return None


def _variation_frame(items,include_current=True):
    rows=[]
    for item in items or []:
        variations=item.get("variations") or {}
        row={"Indicador":item.get("label") or item.get("ticker") or "Indicador"}
        if include_current:
            row["Atual"]=_panel_number(item.get("current"),item.get("unit"),item.get("currency"))
        row.update({"1 dia":variations.get("1d"),"1 semana":variations.get("1w"),"1 mês":variations.get("1m"),"1 ano":variations.get("1y")})
        if item.get("proxy"):
            row["Observação"]=f"Proxy: {item.get('proxy_label') or item.get('ticker')}"
        rows.append(row)
    return pd.DataFrame(rows)


def _show_variation_table(items,include_current=True,key=None):
    frame=_variation_frame(items,include_current=include_current)
    if frame.empty:
        st.info("Dados temporariamente indisponíveis para este grupo.")
        return
    configs={column:st.column_config.NumberColumn(column,format="%.2f%%") for column in ("1 dia","1 semana","1 mês","1 ano")}
    st.dataframe(frame,use_container_width=True,hide_index=True,column_config=configs,key=key)


def _render_market_dashboard_data(payload):
    data=(payload or {}).get("data") or {}
    status=(payload or {}).get("refresh_status") or (payload or {}).get("status")
    has_data=bool(data)
    top_left,top_right=st.columns([4,1])
    with top_left:
        generated=data.get("generated_at")
        if generated:
            try:
                stamp=pd.to_datetime(generated,utc=True).tz_convert("America/Sao_Paulo").strftime("%d/%m/%Y %H:%M")
            except Exception:stamp=str(generated)
            st.caption(f"Última consolidação: {stamp}. Os horários e fechamentos podem variar conforme cada mercado.")
        elif status in {"queued","running"}:
            st.info("O primeiro retrato do dia está sendo preparado em segundo plano. Esta página se atualizará automaticamente.")
        else:
            st.info("O retrato de mercado ainda não foi gerado hoje.")
    with top_right:
        if st.button("🔄 Atualizar agora",use_container_width=True,key="refresh_market_dashboard"):
            result,error=api_post("/market-dashboard/refresh",timeout=15)
            if error:st.error(f"Não foi possível iniciar a atualização: {error}")
            else:
                st.toast("Atualização iniciada em segundo plano.")
                st.rerun(scope="fragment")
    if status in {"queued","running"} and has_data:
        st.info("Atualização em andamento. Enquanto isso, o último retrato válido continua disponível.")
    if not has_data:return

    selic=data.get("selic") or {}
    quoted=data.get("quoted") or {}
    brazil=quoted.get("brazil") or []
    ibov=next((item for item in brazil if item.get("label")=="IBOV"),{})
    fx=data.get("fx") or []
    usdbrl=next((item for item in fx if item.get("label")=="Dólar / Real"),{})
    c1,c2,c3,c4,c5=st.columns(5)
    c1.metric("Selic atual",_panel_number(selic.get("current"),"%"))
    projection_help=selic.get("projection_note") or "Mediana da Selic no Relatório Focus, usada como referência para o CDI projetado."
    c2.metric(f"CDI projetado • fim de {date.today().year}",_panel_number((selic.get("current_year") or {}).get("value"),"%"),help=projection_help)
    c3.metric(f"CDI projetado • fim de {date.today().year+1}",_panel_number((selic.get("next_year") or {}).get("value"),"%"),help=projection_help)
    c4.metric("IBOV",_panel_number(ibov.get("current")),_panel_delta((ibov.get("variations") or {}).get("1d")))
    c5.metric("Dólar / Real",_panel_number(usdbrl.get("current"),"R$","BRL"),_panel_delta((usdbrl.get("variations") or {}).get("1d")))

    st.subheader("🇧🇷 Brasil")
    fixed_income=data.get("fixed_income") or []
    left,right=st.columns([1.05,1.45])
    with left:
        st.markdown("**Juros e renda fixa**")
        _show_variation_table(fixed_income,key="market_dashboard_fixed_income")
        st.caption("IMA-B e IRF-M usam proxies negociados somente quando o histórico público do índice não permite calcular todas as janelas. O proxy é sempre identificado.")
    with right:
        st.markdown("**Bolsa brasileira**")
        _show_variation_table(brazil,key="market_dashboard_brazil")

    curve=data.get("curve") or {}
    points=curve.get("points") or []
    with st.expander("📈 Curva de juros brasileira — gráfico, intervalo e tabela",expanded=True):
        if not points:
            st.info("A curva oficial da ANBIMA não respondeu nesta atualização.")
        else:
            years=[float(point.get("years") or 0) for point in points]
            minimum,maximum=min(years),max(years)
            selected=st.slider("Intervalo de vencimentos (anos)",min_value=float(minimum),max_value=float(maximum),value=(float(minimum),float(maximum)),step=0.25,key="market_curve_year_range") if maximum>minimum else (minimum,maximum)
            filtered=[point for point in points if selected[0]<=float(point.get("years") or 0)<=selected[1]]
            chart=pd.DataFrame(filtered).rename(columns={"years":"Anos","nominal_rate":"Prefixada","real_rate":"Juro real (IPCA)","implied_inflation":"Inflação implícita"})
            available=[column for column in ("Prefixada","Juro real (IPCA)","Inflação implícita") if column in chart and chart[column].notna().any()]
            if available:st.line_chart(chart.set_index("Anos")[available],use_container_width=True)
            search=st.text_input("Localizar prazo",placeholder="Ex.: 2 anos ou 504 dias úteis",key="market_curve_search")
            table=chart.rename(columns={"business_days":"Dias úteis"})
            if search:
                digits=re.findall(r"\d+(?:[.,]\d+)?",search)
                if digits:
                    number=float(digits[0].replace(",","."))
                    target="Dias úteis" if "dia" in search.lower() else "Anos"
                    table=table.iloc[(table[target]-number).abs().argsort()[:8]]
            columns=[column for column in ("Dias úteis","Anos","Prefixada","Juro real (IPCA)","Inflação implícita") if column in table]
            st.dataframe(table[columns],use_container_width=True,hide_index=True,column_config={column:st.column_config.NumberColumn(column,format="%.2f%%") for column in columns if column not in {"Dias úteis","Anos"}})
            st.caption(f"Fonte: {curve.get('source','ANBIMA')} • referência: {curve.get('as_of') or 'data mais recente disponível'}")

    st.subheader("🌍 Mercados internacionais")
    global_tab,risk_tab,commodities_tab=st.tabs(["🌐 Bolsas","Volatilidade, dólar e juros","Ouro, prata e petróleo"])
    with global_tab:_show_variation_table(quoted.get("global") or [],key="market_dashboard_global")
    with risk_tab:
        _show_variation_table(quoted.get("risk") or [],key="market_dashboard_risk")
        rates=data.get("us_rates") or {}
        a,b,c=st.columns(3)
        a.metric("Treasury EUA • 2 anos",_panel_number(rates.get("two_year"),"%"))
        b.metric("Treasury EUA • 10 anos",_panel_number(rates.get("ten_year"),"%"))
        c.metric("Spread 10a - 2a",_panel_number(rates.get("spread_10y_2y"),"%"))
    with commodities_tab:_show_variation_table(quoted.get("commodities") or [],key="market_dashboard_commodities")

    st.subheader("₿ Criptoativos, câmbio e inflação")
    crypto_tab,fx_tab,inflation_tab=st.tabs(["Criptoativos","Câmbio","Inflação em 12 meses"])
    with crypto_tab:
        crypto=data.get("crypto") or []
        columns=st.columns(max(1,len(crypto)))
        for column,item in zip(columns,crypto):
            variations=item.get("variations") or {}
            column.metric(f"{item.get('label')} • USD",_panel_number(item.get("value_usd"),"USD","USD"),_panel_delta(variations.get("1d")))
            column.metric(f"{item.get('label')} • BRL",_panel_number(item.get("value_brl"),"R$","BRL"))
        _show_variation_table([{"label":item.get("label"),"current":item.get("value_usd"),"unit":"USD","currency":"USD","variations":item.get("variations") or {}} for item in crypto],key="market_dashboard_crypto")
    with fx_tab:_show_variation_table(fx,key="market_dashboard_fx")
    with inflation_tab:
        inflation=data.get("inflation") or []
        columns=st.columns(max(1,len(inflation)))
        for column,item in zip(columns,inflation):column.metric(item.get("label"),_panel_number(item.get("value_12m"),"%"),help=f"Fonte: {item.get('source','N/D')} • referência: {item.get('as_of') or 'N/D'}")

    st.subheader("🗓️ Próximas datas importantes")
    calendar=data.get("calendar") or []
    if calendar:
        calendar_frame=pd.DataFrame(calendar).rename(columns={"category":"Categoria","event":"Evento","date":"Data","time":"Horário","region":"Região","source":"Fonte","observation":"Observações"})
        calendar_frame["Data"]=pd.to_datetime(calendar_frame["Data"],errors="coerce").dt.strftime("%d/%m/%Y")
        columns=[column for column in ("Data","Categoria","Evento","Horário","Região","Observações","Fonte") if column in calendar_frame]
        display=calendar_frame[columns]
        def _highlight_super_wednesday(row):
            special="SUPER QUARTA" in str(row.get("Observações") or "")
            return ["background-color: #fff1b8; color: #6b3f00; font-weight: 700" if special else "" for _ in row]
        st.dataframe(display.style.apply(_highlight_super_wednesday,axis=1),use_container_width=True,hide_index=True)
    else:st.info("Os calendários oficiais não responderam nesta atualização.")

    warnings=data.get("warnings") or []
    with st.expander("ℹ️ Metodologia, fontes e indisponibilidades",expanded=False):
        st.write("As variações de mercado usam fechamentos de aproximadamente 1, 5, 21 e 252 pregões. CDI é acumulado por capitalização das taxas diárias. Inflação brasileira é acumulada em 12 divulgações mensais; o CPI compara o índice com o mesmo mês do ano anterior.")
        st.write("Fontes principais: Banco Central do Brasil, ANBIMA, IBGE/FGV via SGS, BLS, FRED, B3, NYSE e cotações Yahoo Finance.")
        if warnings:
            st.warning("Algumas fontes não responderam. Os demais dados foram preservados.")
            for warning in warnings:st.caption(f"• {warning}")


@st.fragment(run_every=20)
def _market_dashboard_fragment():
    payload,error=api_get("/market-dashboard")
    if error:
        st.error(f"Não foi possível consultar o retrato de mercado: {error}")
        return
    _render_market_dashboard_data(payload or {})


def render_market_dashboard():
    st.title("🌐 Painel de Mercado")
    st.caption("Brasil e exterior em um único retrato: juros, bolsas, moedas, inflação, criptoativos, commodities e agenda econômica.")
    _market_dashboard_fragment()


def render_market():
    st.title("📊 Mercado e Análise Individual")
    st.caption("Escolha primeiro onde procurar e depois aplique a análise. Assim, cada filtro trabalha somente com os ativos do universo selecionado.")
    market=st.radio(
        "Tipo de ativo",list(MARKET_ASSET_TYPES),horizontal=True,key="market_asset_class",
        on_change=_change_market_asset_class,
    )
    asset_type=MARKET_ASSET_TYPES[market]
    all_market_label={"stock":"Todas as ações","fii":"Todos os FIIs","other_b3":"Todos os Demais Ativos B3"}[asset_type]
    if asset_type=="other_b3":
        catalog=[]; catalog_errors=[]
        for subtype in ("etf","bdr","future"):
            rows,subtype_error=api_get("/assets",{"asset_type":subtype,"limit":1200,"offset":0})
            catalog.extend(rows or [])
            if subtype_error:catalog_errors.append(f"{subtype}: {subtype_error}")
        catalog_err=" | ".join(catalog_errors) or None
        catalog.sort(key=lambda item:str(item.get("ticker") or ""))
    else:
        catalog,catalog_err=api_get("/assets",{"asset_type":asset_type,"limit":1200,"offset":0}); catalog=catalog or []
    catalog_map={str(item.get("ticker") or "").upper():item for item in catalog}

    custom_payload={"items":[],"limit":int(PERMISSIONS.get("custom_filter_limit") or 0),"used":0}
    if custom_payload["limit"]>0 and asset_type in {"stock","fii"}:
        loaded,custom_err=api_get("/screen/custom-filters",{"asset_type":asset_type})
        if not custom_err and loaded:custom_payload=loaded
    custom_items=custom_payload.get("items") or []

    sync_message=st.session_state.pop("market_sync_message",None)
    if sync_message:
        st.success(sync_message)
    with st.expander("🗄️ Dados usados pelos filtros",expanded=not bool(catalog)):
        st.write(f"Ativos cadastrados neste mercado: **{len(catalog)}**.")
        if catalog_err:
            st.error(f"Não foi possível consultar o catálogo: {catalog_err}")
        elif not catalog:
            st.warning("O banco online ainda não possui o catálogo deste mercado. Sem esses dados, nenhum filtro pode retornar ações.")
        else:
            if asset_type=="other_b3":
                st.caption("A atualização renova ETFs, BDRs e os futuros/derivativos disponibilizados pela fonte técnica. Filtros empresariais não são aplicados a esta categoria.")
            else:
                st.caption("Use a atualização quando o banco for novo ou quando quiser renovar fundamentos, nomes, setores e indicadores técnicos.")
        if can("can_sync_market") and st.button(f"🔄 Carregar / atualizar dados de {market}",type="primary" if not catalog else "secondary",key=f"sync_market_{asset_type}"):
            with st.spinner(f"Buscando e organizando os dados de {market}. Isso pode levar alguns minutos..."):
                sync_result,sync_err=api_post("/data/sync-market",{"asset_type":asset_type},timeout=360)
            if sync_err:
                st.error(f"A atualização não foi concluída: {sync_err}")
            else:
                steps=(sync_result or {}).get("steps") or {}
                failed=[name for name,value in steps.items() if value.get("status")!="ok"]
                count=(sync_result or {}).get("catalog_count",0)
                if failed:
                    st.warning(f"Catálogo carregado com {count} ativos, mas uma etapa precisa ser repetida: {', '.join(failed)}.")
                    st.json(steps)
                else:
                    st.session_state.market_sync_message=f"Dados atualizados: {count} ativo(s) disponíveis para os filtros."
                    st.rerun()
        elif not can("can_sync_market"):
            st.caption("Atualização do banco disponível somente para contas autorizadas pelo administrador.")

    scope_key=f"market_universe_mode_{asset_type}"
    st.session_state.setdefault(scope_key,"all")
    scope_labels={
        "all":all_market_label,
        "portfolio":"Minha carteira",
        "besst":"Método BESST",
        "specific":"Ativos específicos",
    }
    scope_options=["all"]
    if can("can_view_portfolio"):scope_options.append("portfolio")
    if asset_type=="stock":scope_options.append("besst")
    scope_options.append("specific")
    if st.session_state[scope_key] not in scope_options:st.session_state[scope_key]="all"

    with st.expander("🎯 Universo e subfiltros — clique para ajustar",expanded=False):
        st.subheader("Universo de ativos")
        st.caption("Primeiro escolha o grupo principal. Ao trocá-lo, os subfiltros e a análise anterior são limpos para que 100% do novo grupo fique disponível.")
        universe_mode=st.radio(
            "Onde deseja procurar?",scope_options,horizontal=True,
            format_func=lambda value:scope_labels[value],key=scope_key,
            on_change=_change_market_base_universe,args=(asset_type,),
        )

        selected_scope_tickers=None
        besst_group="all"
        scope_detail=""
        if universe_mode=="portfolio":
            portfolios,portfolio_err=api_get("/portfolios")
            portfolios=portfolios or []
            if portfolio_err:
                st.error(f"Não foi possível consultar sua carteira: {portfolio_err}")
                selected_scope_tickers=[]
            elif not portfolios:
                st.info("Você ainda não possui uma carteira. Cadastre ativos em Minha carteira ou volte a todas as ações.")
                selected_scope_tickers=[]
            else:
                portfolio_labels={"all":"Todas as minhas carteiras"}
                portfolio_labels.update({str(item["id"]):item["name"] for item in portfolios})
                portfolio_choice=st.selectbox(
                    "Carteira usada como universo",list(portfolio_labels),
                    format_func=lambda value:portfolio_labels[value],key=f"market_portfolio_scope_{asset_type}",
                    on_change=_change_market_base_universe,args=(asset_type,),
                )
                selected_portfolios=portfolios if portfolio_choice=="all" else [item for item in portfolios if str(item["id"])==portfolio_choice]
                selected_scope_tickers=[]
                portfolio_failures=[]
                for item in selected_portfolios:
                    snapshot,snapshot_err=api_get(f"/portfolios/{item['id']}")
                    if snapshot_err:
                        portfolio_failures.append(item["name"])
                        continue
                    selected_scope_tickers.extend(position.get("ticker") for position in (snapshot or {}).get("positions") or [] if position.get("ticker"))
                if portfolio_failures:st.warning(f"Não foi possível ler: {', '.join(portfolio_failures)}.")
                scope_detail=portfolio_labels[portfolio_choice]
        elif universe_mode=="besst":
            besst_group=st.selectbox(
                "Grupo BESST",list(BESST_LABELS),format_func=lambda value:BESST_LABELS[value],
                key=f"market_besst_group_{asset_type}",on_change=_change_market_base_universe,args=(asset_type,),
            )
            scope_detail=BESST_LABELS[besst_group]
        elif universe_mode=="specific":
            ticker_labels={item["ticker"]:f"{item['ticker']} — {item.get('name') or 'nome ainda não cadastrado'}" for item in catalog}
            selected_scope_tickers=st.multiselect(
                "Escolha um ou mais ativos",list(ticker_labels),format_func=lambda value:ticker_labels[value],
                key=f"market_specific_tickers_{asset_type}",on_change=_change_market_base_universe,args=(asset_type,),
            )
            scope_detail="Seleção manual"

        base_tickers=universe_tickers(
            catalog,universe_mode,selected_tickers=selected_scope_tickers,
            besst_group=besst_group,
        )
        base_set=set(base_tickers)
        base_catalog=[item for item in catalog if str(item.get("ticker") or "").upper() in base_set]

        st.markdown("##### Subfiltros do universo escolhido")
        st.caption("Porte, IBOV e Setor refinam o grupo acima e podem ser usados juntos. Eles nunca acrescentam ativos de fora do universo principal.")
        subfilter_labels=[]
        sf1,sf2,sf3=st.columns(3)

        size_enabled=False
        selected_sizes=[]
        if asset_type=="stock":
            size_enabled=sf1.checkbox(
                "Filtrar por Tamanho da Empresa",key=f"market_subfilter_size_enabled_{asset_type}",
                on_change=_reset_market_refinements,args=(asset_type,"O subfiltro Tamanho da Empresa foi alterado."),
            )
            if size_enabled:
                selected_sizes=sf1.multiselect(
                    "Portes aceitos",list(COMPANY_SIZE_LABELS),default=[],
                    format_func=lambda value:COMPANY_SIZE_LABELS[value],key=f"market_subfilter_size_values_{asset_type}",
                    on_change=_reset_market_refinements,args=(asset_type,"Os portes aceitos foram alterados."),
                )
                sf1.caption("Large Cap ≥ R$ 20 bi; Mid Cap de R$ 2 bi a R$ 20 bi; Small Cap abaixo de R$ 2 bi.")
                if selected_sizes:subfilter_labels.append("Porte: "+", ".join(COMPANY_SIZE_LABELS[value] for value in selected_sizes))
            else:
                sf1.caption("Desativado: todos os portes.")
        else:
            sf1.caption("Tamanho da Empresa é um subfiltro exclusivo de ações.")

        ibov_enabled=False
        ibov_choice="inside"
        ibov_members=set()
        if asset_type=="stock":
            ibov_enabled=sf2.checkbox(
                "Filtrar por IBOV",key=f"market_subfilter_ibov_enabled_{asset_type}",
                on_change=_reset_market_refinements,args=(asset_type,"O subfiltro IBOV foi alterado."),
            )
            if ibov_enabled:
                ibov_choice_labels={"inside":"Está no IBOV","outside":"Não está no IBOV"}
                ibov_choice=sf2.radio(
                    "Participação",list(ibov_choice_labels),horizontal=False,
                    format_func=lambda value:ibov_choice_labels[value],key=f"market_subfilter_ibov_value_{asset_type}",
                    on_change=_reset_market_refinements,args=(asset_type,"A participação no IBOV foi alterada."),
                )
                ibov_data,ibov_err=api_get("/market/index-members/IBOV")
                if ibov_err:
                    sf2.error(f"IBOV indisponível: {ibov_err}")
                else:
                    ibov_members={str(item.get("ticker") or "").upper() for item in (ibov_data or {}).get("members") or []}
                    reference=(ibov_data or {}).get("as_of") or "carteira vigente"
                    sf2.caption(f"Fonte B3 • {reference}")
                subfilter_labels.append(ibov_choice_labels[ibov_choice])
            else:
                sf2.caption("Desativado: dentro e fora do IBOV.")
        else:
            sf2.caption("IBOV é um subfiltro exclusivo de ações.")

        class_enabled=sf3.checkbox(
            "Filtrar por Setor / Categoria",key=f"market_subfilter_class_enabled_{asset_type}",
            on_change=_reset_market_refinements,args=(asset_type,"O subfiltro Setor / Categoria foi alterado."),
        )
        selected_classes=[]
        classification_field="sector_label"
        dimension_labels={"sector_label":"Setor","segment_label":"Segmento","classification":"Categoria consolidada"}
        if class_enabled:
            available_dimensions=[field for field in dimension_labels if any(str(item.get(field) or "").strip() for item in base_catalog)]
            if available_dimensions:
                classification_field=sf3.selectbox(
                    "Agrupar por",available_dimensions,format_func=lambda value:dimension_labels[value],
                    key=f"market_subfilter_class_dimension_{asset_type}",
                    on_change=_reset_market_refinements,args=(asset_type,"O agrupamento do subfiltro foi alterado."),
                )
                classifications=sorted({str(item.get(classification_field) or "").strip() for item in base_catalog if str(item.get(classification_field) or "").strip()},key=str.casefold)
                selected_classes=sf3.multiselect(
                    dimension_labels[classification_field],classifications,default=[],
                    key=f"market_subfilter_class_values_{asset_type}_{classification_field}",
                    on_change=_reset_market_refinements,args=(asset_type,"Os setores ou categorias aceitos foram alterados."),
                )
                if selected_classes:subfilter_labels.append(f"{dimension_labels[classification_field]}: "+", ".join(selected_classes))
            else:
                sf3.info("O banco ainda não possui classificação para este grupo.")
        else:
            sf3.caption("Desativado: todos os setores e categorias.")

        allowed_tickers=apply_universe_subfilters(
            base_catalog,base_tickers,
            company_sizes=selected_sizes if size_enabled else None,
            ibov_members=ibov_members if ibov_enabled else None,
            ibov_inside=ibov_choice=="inside",
            classification_field=classification_field if class_enabled else None,
            classification_values=selected_classes if class_enabled else None,
        )

        allowed_set=set(allowed_tickers)
        scoped_catalog=[item for item in catalog if str(item.get("ticker") or "").upper() in allowed_set]
        scope_label=scope_labels[universe_mode]+(f" • {scope_detail}" if scope_detail else "")
        if subfilter_labels:scope_label += " • "+" • ".join(subfilter_labels)
        subfilters_active=size_enabled or ibov_enabled or class_enabled
        left,right=st.columns([4,1])
        left.success(f"Universo atual: **{scope_label}** • **{len(allowed_tickers)} ativo(s)**")
        right.button(
            "↩ Limpar universo e subfiltros",key=f"restore_all_{asset_type}",use_container_width=True,
            disabled=universe_mode=="all" and not subfilters_active,on_click=_restore_full_market,args=(asset_type,),
        )

    _compact_summary(
        "UNIVERSO ATUAL",
        [market,scope_label,f"{len(allowed_tickers)} ativo(s)"],
        ["Filtros do universo recolhidos acima"],
    )

    notice=st.session_state.pop(f"market_scope_notice_{asset_type}",None)
    if notice:
        st.info(f"{notice} Agora você pode aplicar novamente Padrão, FDI - CNPI, ALB, um filtro personalizado ou indicadores ajustados somente dentro dos {len(allowed_tickers)} ativo(s) deste universo.")

    if asset_type=="other_b3":
        preset_labels={
            "preset:all":"Sem filtros — mostrar 100% do universo",
            "preset:default":"Padrão técnico — priorizar os 50 mais líquidos",
        }
    else:
        preset_labels={
            "preset:all":"Sem filtros — mostrar 100% do universo",
            "preset:default":"Padrão","preset:cnpi":"FDI - CNPI","preset:alb":"ALB",
        }
    strategy_options=list(preset_labels)+[f"custom:{item['id']}" for item in custom_items]
    custom_by_id={str(item["id"]):item for item in custom_items}
    def strategy_name(value):
        if value in preset_labels:return preset_labels[value]
        item=custom_by_id.get(value.split(":",1)[1])
        return f"Personalizado — {item['name']}" if item else "Personalizado indisponível"
    strategy_key=f"market_strategy_ref_{asset_type}"
    st.session_state.setdefault(strategy_key,"preset:default")
    if st.session_state[strategy_key] not in strategy_options:st.session_state[strategy_key]="preset:default"

    strategy_ref=st.session_state[strategy_key]
    adjusted_result=None
    active_form_instance=None
    with st.expander("🧭 Análises, filtros e indicadores — clique para abrir",expanded=False):
        st.subheader("Análises de ativos")
        st.caption("Escolha um método. Clicar no botão restaura imediatamente os valores padrão daquela análise; depois você pode ajustar os indicadores abaixo sem alterar a definição oficial.")
        analysis_buttons=[(key,label) for key,label in preset_labels.items() if key!="preset:all"]
        analysis_buttons.extend((f"custom:{item['id']}",f"👤 {item['name']}") for item in custom_items)
        button_columns=st.columns(min(3,max(1,len(analysis_buttons))))
        for index,(analysis_ref,analysis_label) in enumerate(analysis_buttons):
            button_columns[index%len(button_columns)].button(
                analysis_label,key=f"analysis_button_{asset_type}_{analysis_ref}",use_container_width=True,
                type="primary" if strategy_ref==analysis_ref else "secondary",
                on_click=_select_market_analysis,args=(asset_type,analysis_ref),
            )
        st.button(
            "Limpar análise e mostrar 100% do universo",key=f"analysis_button_all_{asset_type}",
            use_container_width=True,type="primary" if strategy_ref=="preset:all" else "secondary",
            on_click=_select_market_analysis,args=(asset_type,"preset:all"),
        )

        strategy_ref=st.session_state[strategy_key]
        strategy_label=strategy_name(strategy_ref)
        c1,c2=st.columns([3,1])
        c1.success(f"Análise ativa: **{strategy_label}**")
        limit=c2.slider("Máximo exibido",10,200,50,10,key=f"market_result_limit_{asset_type}")

        ticker_labels={"":"Todos os ativos aprovados"}
        ticker_labels.update({item["ticker"]:f"{item['ticker']} — {item.get('name') or 'nome ainda não cadastrado'}" for item in scoped_catalog})
        selected_table_ticker=st.selectbox(
            "Localizar um ativo dentro deste universo",list(ticker_labels),
            format_func=lambda value:ticker_labels[value],key=f"market_table_ticker_{asset_type}",
        )

        if can("can_use_advanced_filters"):
            initial_analysis_filters=_analysis_filter_defaults(asset_type,strategy_ref,custom_by_id)
            revision=int(st.session_state.get(f"market_analysis_revision_{asset_type}",0))
            active_form_instance=f"{strategy_ref.replace(':','_')}_{revision}"
            adjusted_result=render_advanced_screener(
                asset_type,allowed_tickers=allowed_tickers,universe_label=scope_label,
                initial_filters=initial_analysis_filters,form_instance=active_form_instance,compact=True,
            )
        else:
            st.caption("Ajustes combinados de indicadores fundamentalistas e técnicos dependem de autorização do administrador. As análises oficiais acima continuam disponíveis.")

    _compact_summary(
        "VISUALIZAÇÃO",
        [strategy_label,f"Até {limit} resultado(s)"],
        [f"Ativo localizado: {selected_table_ticker}" if selected_table_ticker else "Todos os ativos aprovados"],
    )

    if strategy_ref=="preset:all" or asset_type=="other_b3":
        endpoint=f"/screen/db/universe/{asset_type}"
    elif strategy_ref.startswith("custom:"):
        endpoint=f"/screen/db/custom/{strategy_ref.split(':',1)[1]}"
    else:
        strategy=strategy_ref.split(":",1)[1]
        endpoint=f"/screen/db/stocks/{strategy}" if asset_type=="stock" else f"/screen/db/fiis/{strategy}"
    raw_rows,err=api_get(endpoint,{"limit":1200}) if allowed_tickers else ([],None)
    if err:
        st.error(f"Não foi possível carregar o filtro: {err}"); raw_rows=[]
    if asset_type=="other_b3" and strategy_ref=="preset:default":
        raw_rows=sorted(raw_rows or [],key=lambda row:float(row.get("daily_liquidity") or 0),reverse=True)
    if adjusted_result and adjusted_result.get("_analysis_context")==active_form_instance:
        raw_rows=adjusted_result.get("rows") or []
        strategy_label=f"{strategy_label} • ajustes ativos"
    if asset_type=="stock":
        raw_rows=sorted(raw_rows or [],key=_graham_sort_key,reverse=True)
    refined_rows=filter_rows_by_tickers(raw_rows or [],allowed_tickers)
    visible_rows=refined_rows[:limit]
    visible_rows=[{**catalog_map.get(str(row.get("ticker") or "").upper(),{}),**row} for row in visible_rows]
    df=pd.DataFrame(visible_rows)

    if selected_table_ticker:
        detail_one,e_detail=api_get(f"/assets/{selected_table_ticker}")
        intel_one,e_intel=api_get(f"/assets/{selected_table_ticker}/intelligence")
        if e_detail or detail_one is None:
            st.error(f"Não foi possível carregar {selected_table_ticker}: {e_detail or 'ativo não encontrado'}")
            df=pd.DataFrame()
        else:
            asset_one=detail_one.get("asset") or {}
            fund_one=detail_one.get("fundamentals") or {}
            intel_one=intel_one or {}
            df=pd.DataFrame([{
                "ticker":asset_one.get("ticker"),
                "name":asset_one.get("name"),
                "asset_type_label":{"stock":"Ação","fii":"FII","etf":"ETF","bdr":"BDR","future":"Futuro / derivativo"}.get(asset_one.get("asset_type"),"Outro"),
                "sector":asset_one.get("sector"),
                "sector_label":asset_one.get("sector_label"),
                "industry":asset_one.get("industry"),
                "segment":asset_one.get("segment"),
                "segment_label":asset_one.get("segment_label"),
                "classification":asset_one.get("classification"),
                "company_size_label":asset_one.get("company_size_label"),
                "price":fund_one.get("price") if fund_one.get("price") is not None else (detail_one.get("technical") or {}).get("close"),
                "pe":fund_one.get("pe"),
                "pbv":fund_one.get("pbv"),
                "dy":fund_one.get("dividend_yield_pct"),
                "roe":fund_one.get("roe_pct"),
                "graham_number":intel_one.get("graham_number"),
                "graham_upside_pct":intel_one.get("graham_upside_pct"),
                "ffo_yield":fund_one.get("ffo_yield_pct"),
                "cap_rate":fund_one.get("cap_rate_pct"),
                "vacancy":fund_one.get("vacancy_pct"),
                "daily_liquidity":fund_one.get("daily_liquidity") if fund_one.get("daily_liquidity") is not None else (detail_one.get("technical") or {}).get("daily_liquidity"),
                "signal_tv":(detail_one.get("technical") or {}).get("signal_tv"),
                "rsi14_screen":(detail_one.get("technical") or {}).get("rsi14"),
                "sma20":(detail_one.get("technical") or {}).get("sma20"),
                "sma50":(detail_one.get("technical") or {}).get("sma50"),
                "sma200":(detail_one.get("technical") or {}).get("sma200"),
                "quality_score":intel_one.get("quality_score"),
                "value_score":intel_one.get("value_score"),
                "growth_score":intel_one.get("growth_score"),
                "technical_score":intel_one.get("technical_score"),
                "risk_score":intel_one.get("risk_score"),
                "liquidity_score":intel_one.get("liquidity_score"),
                "alb_score":intel_one.get("alb_score"),
                "data_quality_score":(intel_one.get("data_quality") or {}).get("score"),
            }])
            st.caption("Ativo localizado: a tabela mostra somente este ticker do universo atual, independentemente de ele passar pelo refinamento escolhido.")

    c1,c2,c3,c4=st.columns(4)
    c1.metric("Universo selecionado",len(allowed_tickers))
    c2.metric("Após o refinamento",len(refined_rows))
    c3.metric("Exibidos",len(df))
    if not df.empty:
        c4.metric("Data Quality médio",br_num(pd.to_numeric(df.get("data_quality_score"),errors="coerce").mean(),1,"%"))
    else:c4.metric("Data Quality médio","N/D")

    st.subheader(f"{scope_label} • {strategy_label}")
    if df.empty:
        if asset_type=="stock" and PERMISSIONS.get("is_owner"):
            _remember_market_backtest_selection([],f"{scope_label} • {strategy_label}")
        if not catalog:
            st.warning("Não há ativos deste mercado cadastrados no banco. Abra ‘Dados usados pelos filtros’ acima e carregue o mercado.")
        elif not allowed_tickers:
            st.info(f"O universo selecionado está vazio. Escolha ativos, cadastre uma posição na carteira ou use ‘{all_market_label}’ para recomeçar.")
        else:
            st.info(f"Nenhum dos {len(allowed_tickers)} ativo(s) passou por {strategy_label}. Escolha ‘Sem filtros’ para recuperar 100% deste universo ou ajuste o refinamento.")
    else:
        rename={"ticker":"Ticker","name":"Nome","asset_type_label":"Tipo","company_size_label":"Porte","sector_label":"Setor","classification":"Categoria","segment_label":"Segmento","price":"Preço","pe":"P/L","pbv":"P/VP","dy":"DY %","roe":"ROE %","graham_number":"Preço Justo Graham","graham_upside_pct":"Potencial Graham %","ffo_yield":"FFO Yield %","cap_rate":"Cap Rate %","vacancy":"Vacância %","daily_liquidity":"Liquidez","signal_tv":"Sinal técnico","rsi14_screen":"RSI 14","sma20":"SMA 20","sma50":"SMA 50","sma200":"SMA 200","quality_score":"Quality","value_score":"Value","growth_score":"Growth","technical_score":"Technical","risk_score":"Risk","liquidity_score":"Liquidity","alb_score":"ALB","data_quality_score":"Data Quality"}
        view=df.rename(columns=rename)
        preferred=[c for c in ["Ticker","Nome","Tipo","Porte","Categoria","Setor","Segmento","Preço","Preço Justo Graham","Potencial Graham %","Liquidez","Sinal técnico","RSI 14","SMA 20","SMA 50","SMA 200","P/L","P/VP","DY %","ROE %","FFO Yield %","Cap Rate %","Vacância %","Quality","Value","Growth","Technical","Risk","Liquidity","ALB","Data Quality"] if c in view.columns]
        st.dataframe(view[preferred],hide_index=True,use_container_width=True,height=460)

        if asset_type=="stock" and PERMISSIONS.get("is_owner"):
            market_tickers=_remember_market_backtest_selection(
                [str(value).upper() for value in df["ticker"].dropna().tolist()],
                f"{scope_label} • {strategy_label}",
            )
            if market_tickers:
                transfer_label=f"🧪 Gerar backtests oficiais destes {min(len(market_tickers),100)} ativo(s)"
                st.button(
                    transfer_label,key="market_to_official_backtests",type="primary",use_container_width=True,
                    on_click=_send_market_selection_to_official_batch,
                    args=(market_tickers,f"{scope_label} • {strategy_label}"),
                )
                st.caption("A seleção enviada será exatamente a que aparece na tabela acima, na mesma ordem.")
                if len(market_tickers)>100:st.caption("O lote administrativo aceita no máximo 100 ativos; serão levados os 100 primeiros desta tabela.")

    if can("can_view_backtests") and not df.empty and "ticker" in df:
        st.markdown("#### Três backtests oficiais mais efetivos por ativo")
        st.caption("O ranking combina retorno, risco, drawdown, profit factor, quantidade de operações e os 30% finais do período. Resultados com pouca amostra recebem penalidade.")
        displayed_tickers=[str(value).upper() for value in df["ticker"].dropna().tolist()][:200]
        leaderboard,leaderboard_error=api_get("/backtests/leaderboard",{
            "tickers":",".join(displayed_tickers),"per_asset":3,
        })
        if leaderboard_error:
            st.warning(f"Não foi possível consultar os backtests oficiais: {leaderboard_error}")
        else:
            leaders=(leaderboard or {}).get("items") or {}
            signal_labels={"buy":"🟢 Comprar","sell":"🔴 Vender","neutral":"⚪ Neutro"}
            leaderboard_rows=[]
            for current_ticker in displayed_tickers:
                row={"Ativo":current_ticker}
                ticker_leaders=leaders.get(current_ticker) or []
                for position,item in enumerate(ticker_leaders,start=1):
                    row[f"{position}º backtest"]=f"{item.get('strategy_name')} • {br_num(item.get('ranking_score'),1)}"
                    row[f"Sinal {position}"]=signal_labels.get(item.get("current_signal"),"⚪ Neutro")
                newest_analysis=max((_datetime_sort_value(item.get("created_at")) for item in ticker_leaders),default=-1)
                newest_item=max(ticker_leaders,key=lambda item:_datetime_sort_value(item.get("created_at")),default={})
                row["Analisado em"]=br_datetime(newest_item.get("created_at"))
                row["Sinal atualizado em"]=br_datetime(newest_item.get("signal_as_of"))
                row["_analysis_order"]=newest_analysis
                leaderboard_rows.append(row)
            leaderboard_frame=pd.DataFrame(leaderboard_rows).sort_values("_analysis_order",ascending=False,kind="stable")
            st.dataframe(leaderboard_frame.drop(columns=["_analysis_order"]),hide_index=True,use_container_width=True,height=420)
            if not any(leaders.values()):
                st.info("O catálogo oficial ainda não foi processado. O primeiro lote será criado pela atualização semanal ou por uma execução manual do proprietário.")
            refreshable=[ticker for ticker in displayed_tickers if leaders.get(ticker)]
            if can("can_refresh_backtest_signals") and refreshable:
                u1,u2=st.columns([3,1])
                refresh_ticker=u1.selectbox("Ativo para atualizar os três sinais",refreshable,key=f"market_signal_refresh_{asset_type}")
                if u2.button("Atualizar sinais",key=f"market_signal_refresh_button_{asset_type}",use_container_width=True):
                    with st.spinner(f"Atualizando os sinais de {refresh_ticker}..."):
                        refreshed,refresh_error=api_post(f"/backtests/signals/{refresh_ticker}/refresh",{},timeout=900)
                    if refresh_error:st.error(f"Atualização não concluída: {refresh_error}")
                    else:
                        st.success("Sinais atualizados. Configurações idênticas já calculadas hoje foram reutilizadas.")
                        st.rerun()

    if int(PERMISSIONS.get("custom_filter_limit") or 0)>0 and asset_type in {"stock","fii"}:
        render_custom_filter_manager(asset_type,custom_payload)
    elif asset_type=="other_b3":
        st.caption("Filtros personalizados fundamentalistas ficam ocultos em Demais Ativos B3; os indicadores técnicos compatíveis permanecem no bloco Análises acima.")

    st.markdown("---"); st.header("🔎 Análise individual")
    if "analysis_payload_v14" not in st.session_state:st.session_state.analysis_payload_v14=None
    if scoped_catalog:
        options=[a["ticker"] for a in scoped_catalog]; labels={a["ticker"]:f"{a['ticker']} — {a.get('name') or 'nome ainda não cadastrado'}" for a in scoped_catalog}
        default_ticker=selected_table_ticker if selected_table_ticker in options else ("BBAS3" if "BBAS3" in options else options[0])
        default_index=options.index(default_ticker)
        ticker=st.selectbox("Buscar / selecionar ticker",options,index=default_index,format_func=lambda t:labels.get(t,t),key=f"v14_ticker_{asset_type}")
    elif not catalog:ticker=st.text_input("Ticker",value="BOVA11" if asset_type=="other_b3" else "BBAS3").strip().upper()
    else:
        ticker=""
        st.info("Não há ativo disponível no universo atual para análise individual.")
    if st.button("Analisar ativo",type="primary",disabled=not bool(ticker)):
        with st.spinner(f"Calculando análise para {ticker}..."):
            detail,e1=api_get(f"/assets/{ticker}"); prices,e3=api_get(f"/assets/{ticker}/prices",{"limit":260})
            if asset_type=="other_b3":
                intel={}; hist=[]; vals=[]; e2=e4=e5=None
            else:
                intel,e2=api_get(f"/assets/{ticker}/intelligence"); hist,e4=api_get(f"/assets/{ticker}/scores/history",{"limit":120}); vals,e5=api_get(f"/assets/{ticker}/valuations",{"limit":120})
        st.session_state.analysis_payload_v14={"ticker":ticker,"detail":detail,"intel":intel,"prices":prices or [],"hist":hist or [],"vals":vals or [],"errors":{"Ativo":e1,"Inteligência":e2,"Preços":e3,"Scores":e4,"Valuation":e5}}

    p=st.session_state.analysis_payload_v14
    if p:
        errors={k:v for k,v in p["errors"].items() if v}
        if p["detail"] is None:st.error(f"Não foi possível carregar {p['ticker']}.")
        else:
            detail=p["detail"]; intel=p["intel"] or {}; asset=detail.get("asset") or {}; fund=detail.get("fundamentals") or {}; tech=detail.get("technical") or {}
            st.subheader(f"{asset.get('ticker')} — {asset.get('name') or 'Nome não disponível'}")
            if asset.get("asset_type") in {"etf","bdr","future"}:
                type_label={"etf":"ETF","bdr":"BDR","future":"Futuro / derivativo"}.get(asset.get("asset_type"),"Outro ativo B3")
                st.info(f"Análise técnica de **{type_label}**. Indicadores fundamentalistas de empresas e FIIs foram ocultados por não serem comparáveis.")
                m1,m2,m3,m4=st.columns(4)
                m1.metric("Preço",br_money(tech.get("close")))
                m2.metric("RSI 14",br_num(tech.get("rsi14"),1))
                m3.metric("Sinal técnico",str(tech.get("signal_tv") or "N/D").replace("_"," ").title())
                m4.metric("Liquidez diária",br_money(tech.get("daily_liquidity")))
                identity,indicators=st.columns(2)
                with identity:
                    st.markdown("#### Identidade")
                    st.dataframe(pd.DataFrame([
                        {"Campo":"Tipo","Valor":type_label},{"Campo":"Categoria","Valor":asset.get("classification")},
                        {"Campo":"Setor","Valor":asset.get("sector_label") or asset.get("sector")},
                        {"Campo":"Segmento","Valor":asset.get("segment_label") or asset.get("segment")},
                    ]),hide_index=True,use_container_width=True)
                with indicators:
                    st.markdown("#### Indicadores técnicos")
                    fields=["sma20","sma50","sma200","rsi14","bb_lower","bb_upper","macd","atr14","volatility_annual_pct","max_drawdown_1y_pct","return_1m_pct","return_3m_pct","return_12m_pct"]
                    st.dataframe(pd.DataFrame([{"Indicador":field.upper(),"Valor":tech.get(field) if tech.get(field) is not None else "N/D"} for field in fields]),hide_index=True,use_container_width=True)
                if p["prices"]:
                    ph=pd.DataFrame(p["prices"]); ph["timestamp"]=pd.to_datetime(ph["timestamp"]); ph=ph.set_index("timestamp").sort_index(); st.line_chart(ph[["close"]])
                else:
                    st.info("O snapshot atual está disponível, mas o histórico local ainda não foi carregado para este ativo.")
                    if can("can_sync_market") and asset.get("asset_type") in {"etf","bdr"} and st.button("Carregar histórico deste ativo",key=f"load_other_history_{asset.get('ticker')}"):
                        _,history_error=api_post(f"/assets/{asset.get('ticker')}/prices/ingest",{},timeout=300)
                        if history_error:st.error(f"Histórico não carregado: {history_error}")
                        else:
                            st.success("Histórico carregado. Clique novamente em Analisar ativo para atualizar o gráfico.")
                return
            profile=intel.get("profile") or {}
            st.info(f"Modelo aplicado: **{profile.get('label','N/D')}**. {profile.get('notes','')}")
            if errors:
                with st.expander("Chamadas parcialmente indisponíveis"):st.json(errors)
            m1,m2,m3,m4=st.columns(4); m1.metric("Preço",br_money(fund.get("price"))); m2.metric("ALB Score",br_num(intel.get("alb_score"),1)); m3.metric("Cobertura ALB",br_num(intel.get("coverage_pct"),1,"%")); m4.metric("Data Quality",br_num((intel.get("data_quality") or {}).get("score"),1,"%"))
            cols=st.columns(6)
            vals_scores=[("Quality",intel.get("quality_score"),intel.get("quality_coverage_pct")),("Value",intel.get("value_score"),intel.get("value_coverage_pct")),("Growth",intel.get("growth_score"),intel.get("growth_coverage_pct")),("Technical",intel.get("technical_score"),intel.get("technical_coverage_pct")),("Risk",intel.get("risk_score"),intel.get("risk_coverage_pct")),("Liquidity",intel.get("liquidity_score"),intel.get("liquidity_coverage_pct"))]
            for col,(name,value,cov) in zip(cols,vals_scores):
                with col:render_score_card(name,value,cov)
            if intel.get("technical_score") is None:
                st.warning(f"Technical/Risk podem ficar N/D até existir histórico de preços interno. Para este ticker, rode: `python scripts/ingest_prices.py {asset.get('ticker')}` e depois `python scripts/calculate_scores.py`.")

            tabs=st.tabs(["Resumo","Por que esta nota?","Fundamentos","Técnico","Scores","Histórico","Valuation"])
            with tabs[0]:
                a,b=st.columns(2)
                with a:
                    st.markdown("#### Identidade")
                    st.dataframe(pd.DataFrame([{"Campo":"Setor","Valor":asset.get("sector")},{"Campo":"Indústria","Valor":asset.get("industry")},{"Campo":"Segmento","Valor":asset.get("segment")},{"Campo":"Perfil do score","Valor":profile.get("label")}]),hide_index=True,use_container_width=True)
                with b:
                    st.markdown("#### Pesos do ALB")
                    weights=profile.get("weights") or {}
                    if weights:st.dataframe(pd.DataFrame([{"Componente":k.title(),"Peso %":round(v*100,1)} for k,v in weights.items()]),hide_index=True,use_container_width=True)
            with tabs[1]:
                ex=intel.get("explanation") or {}
                cpos,catt=st.columns(2)
                with cpos:
                    st.markdown("#### Pontos positivos")
                    pos=ex.get("positives") or []
                    if pos:
                        for x in pos:st.write(f"✓ **{x['item']}** — {x['score']:.0f}/100")
                    else:st.caption("Nenhum componente com nota alta e dados suficientes.")
                with catt:
                    st.markdown("#### Pontos de atenção")
                    att=ex.get("attention") or []
                    if att:
                        for x in att:st.write(f"⚠ **{x['item']}** — {x['score']:.0f}/100")
                    else:st.caption("Nenhum componente crítico identificado.")
                missing=ex.get("missing") or []
                if missing:
                    with st.expander("Dados que faltaram no cálculo"):st.write(missing)
            with tabs[2]:
                labels={"pe":"P/L","pbv":"P/VP","dividend_yield_pct":"Dividend Yield %","ev_ebitda":"EV/EBITDA","ebit_margin_pct":"Margem EBIT %","net_margin_pct":"Margem Líquida %","current_ratio":"Liquidez Corrente","roe_pct":"ROE %","roic_pct":"ROIC %","gross_debt_to_equity":"Dívida Bruta/PL","net_debt_to_ebitda":"Dívida Líquida/EBITDA","revenue_cagr_5y_pct":"CAGR Receita 5a %","earnings_cagr_5y_pct":"CAGR Lucro 5a %","ffo_yield_pct":"FFO Yield %","cap_rate_pct":"Cap Rate %","vacancy_pct":"Vacância %","financial_vacancy_pct":"Vacância financeira %","ltv_pct":"LTV %","wale_years":"WALE (anos)","daily_liquidity":"Liquidez diária"}
                st.dataframe(pd.DataFrame([{"Indicador":label,"Valor":fund.get(k) if fund.get(k) is not None else "N/D"} for k,label in labels.items()]),hide_index=True,use_container_width=True)
            with tabs[3]:
                fields=["sma20","sma50","sma200","rsi14","bb_lower","bb_upper","macd","atr14","volatility_annual_pct","max_drawdown_1y_pct","return_1m_pct","return_3m_pct","return_12m_pct"]
                if not tech:st.info("Ainda não há snapshot técnico para este ativo.")
                else:st.dataframe(pd.DataFrame([{"Indicador":k,"Valor":tech.get(k) if tech.get(k) is not None else "N/D"} for k in fields]),hide_index=True,use_container_width=True)
            with tabs[4]:
                components=intel.get("components") or {}
                rows=[]
                for key in ["quality","value","growth","technical","risk","liquidity"]:
                    comp=components.get(key)
                    if comp:rows.append({"Componente":key.title(),"Score":comp.get("score"),"Cobertura %":comp.get("coverage")})
                st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
                st.caption(f"Modelo: {intel.get('model_version','N/D')}. O score é ferramenta de triagem e não recomendação de investimento.")
            with tabs[5]:
                if p["prices"]:
                    ph=pd.DataFrame(p["prices"]); ph["timestamp"]=pd.to_datetime(ph["timestamp"]); ph=ph.set_index("timestamp").sort_index(); st.line_chart(ph[["close"]])
                else:st.info("Histórico de preços ainda não carregado para este ativo.")
                if p["hist"]:
                    sh=pd.DataFrame(p["hist"]); sh["as_of"]=pd.to_datetime(sh["as_of"]); cols2=[c for c in ["quality_score","value_score","growth_score","technical_score","risk_score","liquidity_score","alb_score"] if c in sh]
                    if cols2:st.line_chart(sh.set_index("as_of").sort_index()[cols2])
            with tabs[6]:
                st.markdown("#### Valuation atual")
                st.caption("Cada linha representa um método diferente. Versões históricas do mesmo método ficam separadas abaixo.")
                current_rows=[]
                method_labels={"graham_number":"Graham Number","dividend_yield_target":"Preço Teto Bazin/Barsi (6%)","gordon_ddm_ceiling":"Preço Teto Gordon DDM"}
                if p["vals"]:
                    vdf=pd.DataFrame(p["vals"])
                    if not vdf.empty:
                        vdf["as_of_dt"]=pd.to_datetime(vdf["as_of"],errors="coerce",utc=True)
                        vdf=vdf.sort_values(["method","as_of_dt"],ascending=[True,False])
                        latest=vdf.drop_duplicates(subset=["method"],keep="first")
                        for _,r in latest.iterrows():
                            inputs=r.get("inputs") if isinstance(r.get("inputs"),dict) else {}
                            premise=""
                            if r.get("method")=="dividend_yield_target":
                                premise=f"DPA R$ {inputs.get('dividend_per_share', inputs.get('implied_dividend_per_share','N/D'))} • yield mínimo {inputs.get('target_yield_pct',6)}%"
                            elif r.get("method")=="gordon_ddm_ceiling":
                                premise=f"k {inputs.get('required_return_pct','N/D')}% • g {inputs.get('growth_pct','N/D')}% • margem {inputs.get('margin_of_safety_pct','N/D')}%"
                            elif r.get("method")=="graham_number":
                                premise="LPA e VPA implícitos a partir de P/L e P/VP"
                            current_rows.append({
                                "Método":method_labels.get(r.get("method"),r.get("method")),
                                "Versão":r.get("method_version"),
                                "Data de referência":r.get("as_of"),
                                "Valor justo / teto":r.get("value"),
                                "Diferença vs preço %":r.get("upside_pct"),
                                "Premissas":premise,
                                "Status":r.get("status"),
                            })
                if current_rows:
                    st.dataframe(pd.DataFrame(current_rows),hide_index=True,use_container_width=True)
                else:
                    st.info("Ainda não há valuations persistidos para este ativo.")

                with st.expander("Histórico e versões anteriores"):
                    if p["vals"]:
                        hist_df=pd.DataFrame(p["vals"]).copy()
                        if "method" in hist_df:
                            hist_df["method"]=hist_df["method"].map(lambda x:method_labels.get(x,x))
                        st.dataframe(hist_df,hide_index=True,use_container_width=True)
                    else:
                        st.caption("Sem histórico de valuation.")



def render_portfolio():
    st.title("💼 Carteira — posição, alvos e composição")
    st.caption("Controle a posição atual, ativos-alvo e ativos em análise. Percentuais atuais são calculados pelo valor de mercado; percentuais-alvo são definidos por você.")
    if not can("can_write_portfolio"):
        st.info("Modo somente leitura: esta conta pode consultar a carteira, mas não pode salvar, remover ou atualizar dados.")

    portfolios,err=api_get("/portfolios")
    if err:
        st.error(f"Não foi possível carregar as carteiras: {err}"); return
    portfolios=portfolios or []
    if not portfolios:
        st.info("Ainda não existe uma carteira cadastrada.")
        if st.button("Criar Carteira Principal",type="primary",disabled=not can("can_write_portfolio")):
            created,e=api_post("/portfolios",{"name":"Carteira Principal","cash_balance":0,"target_cash_pct":0})
            if e:st.error(e)
            else:st.success("Carteira criada."); st.rerun()
        return

    labels={p["id"]:p["name"] for p in portfolios}
    pid=st.selectbox("Carteira",list(labels),format_func=lambda x:labels[x])
    snap,err=api_get(f"/portfolios/{pid}")
    if err or not snap:
        st.error(f"Não foi possível carregar a carteira: {err}"); return
    portfolio=snap["portfolio"]; summary=snap["summary"]; positions=snap.get("positions") or []

    with st.expander("⚙️ Configurações da carteira"):
        c1,c2,c3=st.columns(3)
        name=c1.text_input("Nome",value=portfolio.get("name") or "Carteira Principal",key="pf_name")
        cash=c2.number_input("Saldo em caixa (R$)",min_value=0.0,value=float(portfolio.get("cash_balance") or 0),step=100.0,key="pf_cash")
        target_cash=c3.number_input("Alvo de caixa (%)",min_value=0.0,max_value=100.0,value=float(portfolio.get("target_cash_pct") or 0),step=0.5,key="pf_target_cash")
        notes=st.text_area("Observações",value=portfolio.get("notes") or "",key="pf_notes")
        if st.button("Salvar configurações da carteira",disabled=not can("can_write_portfolio")):
            _,e=api_patch(f"/portfolios/{pid}",{"name":name,"cash_balance":cash,"target_cash_pct":target_cash,"notes":notes})
            if e:st.error(e)
            else:st.success("Configurações salvas."); st.rerun()

    m1,m2,m3,m4,m5=st.columns(5)
    m1.metric("Patrimônio atual",br_money(summary.get("market_value")))
    m2.metric("Valor investido",br_money(summary.get("invested_market_value")))
    m3.metric("Custo das posições",br_money(summary.get("cost_basis")))
    m4.metric("Resultado não realizado",br_money(summary.get("unrealized_pnl")),_pct(summary.get("unrealized_pnl_pct")))
    m5.metric("Soma dos alvos",_pct(summary.get("target_total_pct")))
    _compact_summary(
        "CARTEIRA ATUAL",
        [labels[pid],f"{len(positions)} ativo(s)",br_money(summary.get("market_value"))],
        ["Configurações recolhidas acima"],
    )
    if not summary.get("target_is_balanced"):
        st.warning(f"Os percentuais-alvo somam {_pct(summary.get('target_total_pct'))}. Para uma alocação completa, o ideal é totalizar 100% incluindo o caixa.")

    existing_map={p["ticker"]:p for p in positions}
    portfolio_catalog,catalog_error=api_get("/assets",{"limit":500,"offset":0})
    portfolio_catalog=portfolio_catalog or []
    catalog_map={a["ticker"]:a for a in portfolio_catalog}
    type_options=["Ação","FII","ETF","BDR","Renda Fixa","Cripto","Outro"]
    type_map={"Ação":"stock","FII":"fii","ETF":"etf","BDR":"bdr","Futuro / derivativo":"future","Renda Fixa":"fixed_income","Cripto":"crypto","Outro":"other"}
    type_rev={v:k for k,v in type_map.items()}
    stage_options=["Posição atual","Alvo","Em análise"]
    stage_map={"Posição atual":"position","Alvo":"target","Em análise":"analysis"}
    stage_rev={v:k for k,v in stage_map.items()}

    left,right=st.columns([3,1])
    with left.expander("➕ Movimentações e edição — clique para abrir",expanded=False):
        purchase_tab,edit_tab=st.tabs(["➕ Adicionar compra","✏️ Editar posição"])
        with purchase_tab:
            st.caption("Uma nova compra soma ações à posição existente e recalcula automaticamente o preço médio ponderado.")
            known_options=[""]+sorted(catalog_map)
            known_ticker=st.selectbox(
                "Ativo comprado",known_options,
                format_func=lambda value:"Digitar outro ticker" if value=="" else f"{value} — {catalog_map[value].get('name') or 'nome não cadastrado'}",
                key="pf_purchase_catalog_ticker",
            )
            purchase_ticker=known_ticker or st.text_input("Ticker",placeholder="Ex.: BBAS3, HGLG11, BOVA11",key="pf_purchase_manual_ticker").strip().upper()
            purchase_metadata=catalog_map.get(purchase_ticker) or {}
            purchase_existing=existing_map.get(purchase_ticker) or {}
            if purchase_existing:
                st.info(f"Você já possui {purchase_existing.get('quantity',0):.0f} ação(ões) de {purchase_ticker}. Esta compra será somada à posição.")
            detected_type=purchase_metadata.get("asset_type") or purchase_existing.get("asset_type") or "stock"
            ptype=st.selectbox("Tipo",type_options,index=type_options.index(type_rev.get(detected_type,"Ação")),key="pf_purchase_type")
            qty_key=f"pf_purchase_qty_{pid}_{purchase_ticker or 'new'}"
            reset_key=f"{qty_key}_reset_pending"
            purchase_qty=_quantity_control(
                "Quantidade desta compra",qty_key,f"purchase_adjust_{pid}_{purchase_ticker or 'new'}",
                initial_value=100,reset_key=reset_key,disabled=not can("can_write_portfolio"),
            )
            purchase_price_text=st.text_input("Preço unitário desta compra (R$)",value="",placeholder="Ex.: 27,45",key=f"pf_purchase_price_{pid}_{purchase_ticker}")
            automatic=purchase_metadata.get("classification") or purchase_existing.get("classification") or "Não localizado no cadastro"
            st.text_input("Setor / segmento / categoria (automático)",value=automatic,disabled=True,key=f"pf_purchase_class_{pid}_{purchase_ticker}")
            purchase_notes=st.text_input("Observação (opcional)",value="",key=f"pf_purchase_notes_{pid}_{purchase_ticker}")
            if st.button("Cadastrar esta compra",type="primary",key=f"pf_save_purchase_{pid}_{purchase_ticker}",disabled=not can("can_write_portfolio")):
                try:
                    purchase_price=parse_brl_price_input(purchase_price_text)
                    if not purchase_ticker: raise ValueError("Informe o ticker.")
                    if int(purchase_qty)<=0: raise ValueError("Informe uma quantidade maior que zero.")
                    if purchase_price is None: raise ValueError("Informe o preço unitário da compra.")
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    new_quantity,new_average=_merge_purchase_position(
                        purchase_existing.get("quantity"),purchase_existing.get("average_price"),
                        purchase_qty,purchase_price,
                    )
                    payload={
                        "asset_type":type_map[ptype],"stage":"position","quantity":new_quantity,
                        "average_price":round(new_average,6),
                        "target_weight_pct":float(purchase_existing.get("target_weight_pct") or 0),
                        "classification_override":purchase_existing.get("classification_override"),
                        "notes":purchase_notes or purchase_existing.get("notes"),
                    }
                    result,e=api_put(f"/portfolios/{pid}/positions/{purchase_ticker}",payload)
                    if e:st.error(e)
                    else:
                        st.success(f"Compra adicionada. Nova posição: {new_quantity:.0f} ação(ões), preço médio {br_money(new_average)}.")
                        st.session_state[reset_key]=True; st.rerun()

        with edit_tab:
            if not positions:
                st.info("Ainda não há posição para editar.")
            else:
                edit_ticker=st.selectbox("Posição",sorted(existing_map),format_func=lambda x:f"{x} — {existing_map[x].get('name') or ''}",key="pf_edit_existing_v170")
                existing=existing_map[edit_ticker]
                edit_qty_key=f"pf_edit_qty_{pid}_{edit_ticker}"
                edit_qty=_quantity_control(
                    "Quantidade total da posição",edit_qty_key,f"edit_adjust_{pid}_{edit_ticker}",
                    initial_value=int(float(existing.get("quantity") or 0)),disabled=not can("can_write_portfolio"),
                )
                e1,e2=st.columns(2)
                default_stage=stage_rev.get(existing.get("stage"),"Posição atual")
                edit_stage=e1.selectbox("Situação",stage_options,index=stage_options.index(default_stage),key=f"pf_edit_stage_{pid}_{edit_ticker}")
                edit_target=e2.number_input("Percentual alvo (%)",min_value=0.0,max_value=100.0,value=float(existing.get("target_weight_pct") or 0),step=0.5,key=f"pf_edit_target_{pid}_{edit_ticker}")
                current_avg=format_brl_price_input(existing.get("average_price"))
                edit_avg_text=st.text_input("Substituir preço médio (opcional)",value="",placeholder=f"Atual: {current_avg}" if current_avg else "Ex.: 27,45",key=f"pf_edit_avg_{pid}_{edit_ticker}")
                st.text_input("Setor / segmento / categoria (automático)",value=existing.get("classification") or "Não localizado",disabled=True,key=f"pf_edit_class_auto_{pid}_{edit_ticker}")
                edit_override=st.text_input("Ajuste manual da classificação (opcional)",value=existing.get("classification_override") or "",key=f"pf_edit_override_{pid}_{edit_ticker}")
                edit_notes=st.text_input("Observação / tese curta",value=existing.get("notes") or "",key=f"pf_edit_notes_{pid}_{edit_ticker}")
                save_col,delete_col=st.columns(2)
                if save_col.button("Salvar alterações",type="primary",key=f"pf_save_edit_{pid}_{edit_ticker}",use_container_width=True,disabled=not can("can_write_portfolio")):
                    try: typed_avg=parse_brl_price_input(edit_avg_text)
                    except ValueError as exc: st.error(str(exc))
                    else:
                        payload={"asset_type":existing.get("asset_type") or "stock","stage":stage_map[edit_stage],"quantity":int(edit_qty),"average_price":typed_avg if typed_avg is not None else existing.get("average_price"),"target_weight_pct":edit_target,"classification_override":edit_override or None,"notes":edit_notes or None}
                        _,e=api_put(f"/portfolios/{pid}/positions/{edit_ticker}",payload)
                        if e:st.error(e)
                        else:st.success(f"{edit_ticker} atualizado."); st.rerun()
                if delete_col.button("Excluir da carteira",key=f"pf_delete_edit_{pid}_{edit_ticker}",use_container_width=True,disabled=not can("can_write_portfolio")):
                    _,e=api_delete(f"/portfolios/{pid}/positions/{edit_ticker}")
                    if e:st.error(e)
                    else:st.success(f"{edit_ticker} removido."); st.rerun()
    with right:
        st.subheader("Cotações")
        st.caption("Atualiza pelo Yahoo e grava o histórico no banco. Útil também para ETFs.")
        if st.button("🔄 Atualizar preços da carteira",use_container_width=True,disabled=not can("can_write_portfolio")):
            with st.spinner("Atualizando cotações..."):
                r,e=api_post(f"/portfolios/{pid}/refresh-prices",{},timeout=240)
            if e:st.error(e)
            else:
                ok=sum(1 for x in r.get("results",[]) if x.get("status")=="ok")
                st.success(f"Cotações atualizadas: {ok} ativo(s).")
                st.rerun()

    portfolio_tab_labels=["Posição atual","Alvos","Em análise","Composição geral","Setores / segmentos","Rebalanceamento"]
    news_tab_index=None
    alerts_tab_index=None
    if can("can_view_news_insights"):
        news_tab_index=len(portfolio_tab_labels); portfolio_tab_labels.append("📰 Notícias")
    if can("can_use_price_alerts"):
        alerts_tab_index=len(portfolio_tab_labels); portfolio_tab_labels.append("🔔 Alertas")
    tabs=st.tabs(portfolio_tab_labels)
    pdf=pd.DataFrame(positions)
    display_cols={
        "ticker":"Ticker","name":"Nome","asset_class_label":"Classe","classification":"Setor/segmento","quantity":"Quantidade",
        "average_price":"Preço médio","current_price":"Preço atual","current_price_as_of":"Data do preço","cost_value":"Custo","market_value":"Valor atual","pnl_value":"Resultado R$",
        "pnl_pct":"Resultado %","current_weight_pct":"% carteira atual","target_weight_pct":"% alvo informado","effective_target_weight_pct":"% alvo efetivo","weight_gap_pct":"Gap p.p.",
        "within_class_current_pct":"% dentro da classe","within_class_target_pct":"% alvo dentro da classe","notes":"Observação",
    }
    def show_positions(stage):
        if pdf.empty:
            st.info("Nenhum ativo cadastrado."); return
        d=pdf[pdf["stage"]==stage].copy()
        if d.empty:
            st.info("Nenhum ativo nesta categoria."); return
        d=d.rename(columns=display_cols)
        cols=[v for v in display_cols.values() if v in d.columns]
        st.dataframe(d[cols],hide_index=True,use_container_width=True,height=420)
    with tabs[0]:
        st.markdown("#### Posições que compõem o patrimônio atual")
        show_positions("position")
    with tabs[1]:
        st.markdown("#### Ativos-alvo")
        st.caption("Podem ter quantidade zero e ainda assim participar do percentual-alvo e do rebalanceamento.")
        show_positions("target")
    with tabs[2]:
        st.markdown("#### Ativos em análise")
        st.caption("Lista de estudo. Não interfere na composição atual nem no alvo estratégico até você mudar a situação para ‘Alvo’ ou ‘Posição atual’.")
        show_positions("analysis")
    with tabs[3]:
        class_df=pd.DataFrame(snap.get("class_allocation") or [])
        if class_df.empty:st.info("Adicione posições para visualizar a composição.")
        else:
            class_view=class_df.rename(columns={"asset_class_label":"Classe","current_value":"Valor atual","current_weight_pct":"% atual","target_weight_pct":"% alvo","gap_pct":"Gap p.p."})
            st.dataframe(class_view[["Classe","Valor atual","% atual","% alvo","Gap p.p."]],hide_index=True,use_container_width=True)
            chart=class_view.set_index("Classe")[["% atual","% alvo"]]
            st.bar_chart(chart)
    with tabs[4]:
        sector_df=pd.DataFrame(snap.get("sector_allocation") or [])
        if sector_df.empty:st.info("Ainda não há composição setorial calculável.")
        else:
            classes=sector_df["asset_class_label"].dropna().unique().tolist()
            chosen=st.selectbox("Classe para detalhar",classes,key="pf_sector_class")
            sd=sector_df[sector_df["asset_class_label"]==chosen].copy().rename(columns={"classification":"Setor/segmento","current_value":"Valor atual","within_class_current_pct":"% atual dentro da classe","global_current_pct":"% da carteira total","target_global_pct":"% alvo da carteira","within_class_target_pct":"% alvo dentro da classe"})
            st.dataframe(sd[["Setor/segmento","Valor atual","% atual dentro da classe","% da carteira total","% alvo da carteira","% alvo dentro da classe"]],hide_index=True,use_container_width=True)
            st.bar_chart(sd.set_index("Setor/segmento")[["% atual dentro da classe","% alvo dentro da classe"]])
    with tabs[5]:
        if pdf.empty:st.info("Defina percentuais-alvo para gerar o rebalanceamento.")
        else:
            rb=pdf.copy()
            cols=["ticker","asset_class_label","stage_label","current_price","market_value","current_weight_pct","effective_target_weight_pct","target_value","rebalance_value","rebalance_quantity"]
            rb=rb[cols].rename(columns={"ticker":"Ticker","asset_class_label":"Classe","stage_label":"Situação","current_price":"Preço atual","market_value":"Valor atual","current_weight_pct":"% atual","effective_target_weight_pct":"% alvo efetivo","target_value":"Valor alvo","rebalance_value":"Comprar (+) / reduzir (-) R$","rebalance_quantity":"Qtd. estimada"})
            st.dataframe(rb,hide_index=True,use_container_width=True)
            st.caption("A quantidade de rebalanceamento é uma estimativa baseada no preço atual e não considera lote padrão, impostos ou custos de execução.")
    if news_tab_index is not None:
        with tabs[news_tab_index]:
            _render_market_news(selected_portfolio_id=pid,selected_portfolio_detail=snap)
    if alerts_tab_index is not None:
        with tabs[alerts_tab_index]:
            _render_price_alerts()


def _backtest_configuration_rows(result):
    """Human-readable, auditable description of the configuration actually returned by the API."""
    strategy=result.get("strategy") or {}
    params=result.get("parameters") or {}
    filters=result.get("filters") or {}
    saved_financial={}
    # Saved runs store strategy and filters together in the parameters JSON.
    if isinstance(params.get("strategy"),dict):
        saved_financial=params.get("financial") or {}
        filters=params.get("filters") or filters
        params=params["strategy"]
    rows=[]
    sid=strategy.get("id")
    if sid=="bollinger_rsi_trend" or all(x in params for x in ("period","stddev","entry_rsi","trend_period")):
        trigger_labels={"close":"Fechamento ≤ banda inferior","low_touch":"Mínima toca a banda inferior","close_reentry":"Reentrada acima da banda após fechar abaixo"}
        structural_labels={
            "price_above":"Preço > SMA","sma_rising":"SMA ascendente",
            "price_above_and_sma_rising":"Preço > SMA E SMA ascendente",
            "price_above_or_sma_rising":"Preço > SMA OU SMA ascendente","none":"Sem filtro estrutural",
        }
        mode=params.get("trend_filter_mode","price_above")
        structural=f"{structural_labels.get(mode,mode)} {int(params.get('trend_period',200))}"
        if mode in {"sma_rising","price_above_and_sma_rising","price_above_or_sma_rising"}:
            structural+=f" (inclinação: {int(params.get('trend_slope_lookback',20))} pregões)"
        rows.extend([
            {"Etapa":"Estratégia-base","Regra":"Banda de Bollinger","Configuração":f"{int(params.get('period',20))} períodos / {float(params.get('stddev',2)):.2f} desvios"},
            {"Etapa":"Entrada","Regra":"Gatilho de preço","Configuração":trigger_labels.get(params.get("band_trigger","close"),params.get("band_trigger"))},
            {"Etapa":"Entrada","Regra":"RSI","Configuração":f"RSI {int(params.get('rsi_period',14))} ≤ {float(params.get('entry_rsi',35)):.2f}"},
            {"Etapa":"Entrada estrutural","Regra":"Tendência longa","Configuração":structural},
            {"Etapa":"Saída da estratégia","Regra":"Regra original","Configuração":f"Banda central OU RSI ≥ {float(params.get('exit_rsi',55)):.2f} OU falha do filtro estrutural"},
        ])
    else:
        rows.append({"Etapa":"Estratégia-base","Regra":strategy.get("name","Estratégia"),"Configuração":strategy.get("rules","Regra definida no catálogo")})
        labels={"fast_period":"Período rápido","slow_period":"Período lento","fast_type":"Média rápida","slow_type":"Média lenta"}
        for key,value in params.items():
            rows.append({"Etapa":"Parâmetro","Regra":labels.get(key,key),"Configuração":value})

    timeframe_labels={"daily_trend":"Diária","weekly_trend":"Semanal","monthly_trend":"Mensal"}
    mode_labels={"price_above":"Preço acima da SMA","sma_rising":"SMA ascendente","price_above_or_sma_rising":"Preço acima OU SMA ascendente","price_above_and_sma_rising":"Preço acima E SMA ascendente"}
    active_trends=[]
    for key,label in timeframe_labels.items():
        rule=filters.get(key) or {}
        if rule.get("enabled"):
            text=f"{mode_labels.get(rule.get('mode','price_above'),rule.get('mode'))} {int(rule.get('period',21))}"
            if rule.get("mode") in {"sma_rising","price_above_or_sma_rising","price_above_and_sma_rising"}:
                text+=f"; inclinação {int(rule.get('slope_lookback',5))} períodos"
            rows.append({"Etapa":"Tendência adicional","Regra":label,"Configuração":text})
            active_trends.append(label)
    if active_trends:
        logic={"all":"TODOS (AND)","any":"QUALQUER (OR)","majority":"MAIORIA"}.get(filters.get("trend_combination","all"),filters.get("trend_combination"))
        rows.append({"Etapa":"Combinação","Regra":"Timeframes ativos","Configuração":f"{logic}: {', '.join(active_trends)}"})
    else:
        rows.append({"Etapa":"Tendência adicional","Regra":"Timeframes","Configuração":"Nenhum filtro adicional ativo"})

    technical_specs=[("adx_min","ADX 14","≥"),("volume_ratio_min","Volume / média 20","≥"),("rsi_min","RSI 14","≥"),("rsi_max","RSI 14","≤"),("atr_pct_min","ATR 14 %","≥"),("atr_pct_max","ATR 14 %","≤")]
    active_technical=[]
    for key,label,operator in technical_specs:
        if filters.get(key) is not None:
            active_technical.append(f"{label} {operator} {filters[key]}")
    rows.append({"Etapa":"Confirmação técnica","Regra":"Filtros ativos","Configuração":"; ".join(active_technical) if active_technical else "Nenhum filtro adicional ativo"})

    field_labels={"pe":"P/L","pbv":"P/VP","dividend_yield_pct":"DY %","roe_pct":"ROE %","roic_pct":"ROIC %","net_debt_to_ebitda":"Dívida líquida/EBITDA","ffo_yield_pct":"FFO Yield %","vacancy_pct":"Vacância %","ltv_pct":"LTV %"}
    for phase,key in (("Entrada fundamentalista","fundamental_entry"),("Saída fundamentalista","fundamental_exit")):
        rules=filters.get(key) or {}
        for field,limits in rules.items():
            parts=[]
            if limits.get("min") is not None:parts.append(f"≥ {limits['min']}")
            if limits.get("max") is not None:parts.append(f"≤ {limits['max']}")
            rows.append({"Etapa":phase,"Regra":field_labels.get(field,field),"Configuração":" e ".join(parts)})
    if not (filters.get("fundamental_entry") or filters.get("fundamental_exit")):
        rows.append({"Etapa":"Fundamentos","Regra":"Histórico point-in-time","Configuração":"Nenhum filtro ativo"})
    rows.append({"Etapa":"Saída por filtros","Regra":"Falha dos filtros de entrada","Configuração":"ATIVA" if filters.get("exit_on_filter_failure") else "DESATIVADA — filtros adicionais atuam somente na entrada"})
    assumptions={**saved_financial, **(result.get("assumptions") or {})}
    cash_enabled=assumptions.get("cash_yield_enabled",assumptions.get("apply_cash_yield",False))
    cash_rate=assumptions.get("cash_yield_rate_pct_annual",assumptions.get("cash_yield_rate_pct",0))
    rows.append({
        "Etapa":"Caixa","Regra":"Remuneração quando fora do mercado",
        "Configuração":f"ATIVA — {float(cash_rate):.2f}% a.a. constante" if cash_enabled else "DESATIVADA",
    })
    if assumptions.get("fee_pct_per_turnover") is not None or assumptions.get("fee_pct") is not None:
        fee=assumptions.get("fee_pct_per_turnover",assumptions.get("fee_pct",0))
        slippage=assumptions.get("slippage_pct_per_turnover",assumptions.get("slippage_pct",0))
        rows.append({"Etapa":"Custos","Regra":"Por movimentação","Configuração":f"Taxa {float(fee):.3f}% + slippage {float(slippage):.3f}%"})
    rows.append({"Etapa":"Execução","Regra":"Sem antecipação","Configuração":"Sinal no fechamento; posição no pregão seguinte"})
    return rows


def _render_backtest_configuration(result):
    rows=_backtest_configuration_rows(result)
    df=pd.DataFrame(rows)
    st.markdown("#### Mapa do teste executado")
    active_trend_rows=[x for x in rows if x["Etapa"]=="Tendência adicional" and "Nenhum" not in str(x["Configuração"])]
    active_trends=len(active_trend_rows)
    active_confirmations=sum(1 for x in rows if x["Etapa"] in {"Confirmação técnica","Entrada fundamentalista"} and "Nenhum" not in str(x["Configuração"]))
    base_rows=[x for x in rows if x["Etapa"] in {"Entrada","Entrada estrutural"}]
    base_summary=" • ".join(str(x["Configuração"]) for x in base_rows[:2]) or "Sinal técnico original"
    trend_summary=", ".join(str(x["Regra"]) for x in active_trend_rows) if active_trends else "Sem filtro adicional"
    flow=st.columns(4)
    flow[0].info(f"🎯 **Estratégia-base**\n\n{base_summary}")
    flow[1].info(f"📈 **Tendência**\n\n{trend_summary}")
    flow[2].info(f"🧩 **Confirmações**\n\n{active_confirmations} regra(s) ativa(s)" if active_confirmations else "🧩 **Confirmações**\n\nSem filtro adicional")
    flow[3].info("⏭️ **Execução**\n\nPosição no pregão seguinte")
    st.dataframe(df,hide_index=True,use_container_width=True,column_config={"Etapa":st.column_config.TextColumn(width="medium"),"Regra":st.column_config.TextColumn(width="medium"),"Configuração":st.column_config.TextColumn(width="large")})


def _render_filter_audit(result):
    fdiag=result.get("filter_diagnostics") or {}
    if not fdiag.get("active"):
        return
    diag=result.get("signal_diagnostics") or {}
    st.caption(f"Entradas da estratégia antes dos filtros: {diag.get('base_entry_signals',0)} • após filtros: {diag.get('filtered_entry_signals',0)}")
    trend_audit=[]
    for label in ("Tendência diária","Tendência semanal","Tendência mensal"):
        item=(fdiag.get("conditions") or {}).get(label)
        if item:
            trend_audit.append({"Filtro":label,"Sinais candidatos":item.get("candidate_signals",0),"Bloqueados isoladamente":item.get("signals_blocked",0),"Barras válidas":item.get("bars_valid",0)})
    combination=fdiag.get("trend_combination")
    if combination:
        labels={"all":"TODOS (AND)","any":"QUALQUER (OR)","majority":"MAIORIA"}
        trend_audit.append({"Filtro":f"Combinação: {labels.get(combination.get('logic'),combination.get('logic'))}","Sinais candidatos":combination.get("candidate_signals",0),"Bloqueados isoladamente":combination.get("signals_blocked",0),"Barras válidas":"—"})
    if trend_audit:
        st.markdown("##### Auditoria dos filtros de tendência")
        st.dataframe(pd.DataFrame(trend_audit),hide_index=True,use_container_width=True)


def _render_backtest_result(result):
    metrics=result.get("metrics") or {}
    if result.get("cached"):
        st.info("Resultado recuperado do histórico de hoje. O motor não repetiu um backtest idêntico.")
    alias=result.get("ticker_alias")
    if alias:
        st.info(f"Código atualizado automaticamente: {alias.get('requested')} → {alias.get('ticker')}. {alias.get('reason')}.")
    st.subheader(f"{result.get('ticker')} • {result.get('strategy',{}).get('name','Estratégia')}")
    st.caption(f"Período efetivo: {str(result.get('actual_start',''))[:10]} a {str(result.get('actual_end',''))[:10]} • sinais sem antecipação (posição no pregão seguinte).")
    signal=result.get("current_signal") or {}
    signal_labels={"buy":"🟢 Comprar","sell":"🔴 Vender","neutral":"⚪ Neutro"}
    s1,s2,s3=st.columns(3)
    s1.metric("Sinal no último pregão",signal_labels.get(signal.get("status"),"⚪ Neutro"))
    s2.metric("Nota de robustez",br_num(result.get("ranking_score"),1," / 100"))
    sample_labels={"adequate":"Amostra adequada","limited":"Amostra limitada","insufficient":"Amostra insuficiente"}
    s3.metric("Confiabilidade",sample_labels.get(result.get("sample_status"),"Não classificada"))
    if signal.get("as_of"):st.caption(f"Sinal calculado com dados concluídos até {str(signal.get('as_of'))[:10]}. {signal.get('reason','')}")
    r1=st.columns(6)
    r1[0].metric("Retorno",_pct(metrics.get("total_return_pct")))
    r1[1].metric("CAGR",_pct(metrics.get("cagr_pct")))
    r1[2].metric("Buy & Hold",_pct(metrics.get("benchmark_total_return_pct")))
    r1[3].metric("Max drawdown",_pct(metrics.get("max_drawdown_pct")))
    r1[4].metric("Sharpe",br_num(metrics.get("sharpe_ratio"),2))
    r1[5].metric("Exposição",_pct(metrics.get("exposure_pct")))
    r2=st.columns(6)
    r2[0].metric("Trades encerrados",metrics.get("closed_trades",metrics.get("trades",0)))
    r2[1].metric("Acerto (encerrados)",_pct(metrics.get("win_rate_pct")))
    r2[2].metric("PF (encerrados)",br_num(metrics.get("profit_factor"),2))
    r2[3].metric("Sortino",br_num(metrics.get("sortino_ratio"),2))
    r2[4].metric("Volatilidade",_pct(metrics.get("annual_volatility_pct")))
    r2[5].metric("Excesso vs B&H",_pct(metrics.get("excess_total_return_pct")))

    if metrics.get("open_trades",0):
        st.warning(
            f"Há {int(metrics.get('open_trades',0))} posição(ões) aberta(s) no fim do período. "
            "O retorno total e o drawdown incluem a marcação a mercado; Trades, taxa de acerto e PF acima consideram somente operações encerradas."
        )
        o1,o2,o3=st.columns(3)
        o1.metric("Posições abertas",int(metrics.get("open_trades",0)))
        o2.metric("Resultado aberto",_pct(metrics.get("open_position_return_pct")))
        o3.metric("PF incluindo posição aberta",br_num(metrics.get("profit_factor_mark_to_market"),2))

    _render_backtest_configuration(result)
    _render_filter_audit(result)

    curve=pd.DataFrame(result.get("equity_curve") or [])
    if not curve.empty:
        curve["timestamp"]=pd.to_datetime(curve["timestamp"]); curve=curve.set_index("timestamp").sort_index()
        st.markdown("#### Curva de capital")
        st.line_chart(curve[["equity","benchmark"]].rename(columns={"equity":"Estratégia","benchmark":"Buy & Hold"}))
        a,b=st.columns(2)
        with a:
            st.markdown("#### Preço e indicadores da estratégia")
            excluded={"price","position","equity","benchmark","drawdown_pct"}
            ind=[c for c in curve.columns if c not in excluded]
            chart_cols=["price"]+[c for c in ind if not c.upper().startswith("RSI") and "MACD" not in c][:4]
            st.line_chart(curve[chart_cols])
        with b:
            st.markdown("#### Drawdown")
            st.line_chart(curve[["drawdown_pct"]])
    trades=pd.DataFrame(result.get("trades") or [])
    st.markdown("#### Operações")
    if trades.empty:
        diag=result.get("signal_diagnostics") or {}
        bars=diag.get("price_bars_loaded",metrics.get("bars"))
        st.info(f"Os dados foram carregados ({bars} barras no período), mas a estratégia não concluiu nenhuma operação. Retorno, volatilidade e drawdown da estratégia ficam em 0% porque ela permaneceu fora do mercado — isso não significa ausência de cotações.")
        if diag.get("base_entry_signals",0)==0:
            st.error("A estratégia-base gerou 0 sinais de entrada. Portanto, os filtros adicionais não chegaram a avaliar nenhum candidato; o bloqueio ocorreu nas regras originais da estratégia.")
        elif diag.get("filtered_entry_signals",0)==0:
            st.error(f"A estratégia-base gerou {diag.get('base_entry_signals')} sinal(is), mas os filtros adicionais bloquearam todos eles.")
        if result.get("strategy",{}).get("id")=="bollinger_rsi_trend" and diag.get("bollinger"):
            b=diag["bollinger"]
            st.markdown("##### Diagnóstico do gatilho Bollinger")
            dcols=st.columns(5)
            dcols[0].metric("Barras válidas",b.get("valid_bars",0))
            dcols[1].metric("Gatilho da banda",b.get("band_trigger_bars",0))
            dcols[2].metric("RSI dentro da entrada",b.get("rsi_entry_bars",0))
            dcols[3].metric("Filtro estrutural",b.get("trend_filter_bars",0))
            dcols[4].metric("Tudo ao mesmo tempo",b.get("all_entry_conditions_bars",0))
            d2=st.columns(4)
            d2[0].metric("Banda + RSI",b.get("band_and_rsi_bars",0))
            d2[1].metric("Banda + tendência",b.get("band_and_trend_bars",0))
            d2[2].metric("RSI + tendência",b.get("rsi_and_trend_bars",0))
            d2[3].metric("Banda+RSI bloqueados pela tendência",b.get("band_rsi_blocked_by_trend_bars",0))
            if b.get("band_and_rsi_bars",0)>0 and b.get("all_entry_conditions_bars",0)==0:
                st.warning("Houve eventos que atenderam Banda + RSI, mas nenhum passou pelo filtro estrutural selecionado. Isso indica que o bloqueio está na regra de tendência, não na carga de dados.")
            elif b.get("band_trigger_bars",0)>0 and b.get("band_and_rsi_bars",0)==0:
                st.warning("A banda foi acionada, mas o RSI não chegou ao limite de entrada simultaneamente. Teste a sensibilidade do RSI sem alterar as demais regras.")
            elif b.get("band_trigger_bars",0)==0:
                st.warning("Nenhuma barra acionou o gatilho de banda escolhido neste período. Compare fechamento, mínima tocando a banda ou reentrada após fechamento abaixo da banda.")
            dates=b.get("blocked_candidate_dates") or []
            if dates:
                st.caption("Primeiras datas em que Banda + RSI ocorreram, mas o filtro estrutural bloqueou a compra: "+", ".join(dates))
            st.caption("O diagnóstico separa as condições para mostrar qual regra está eliminando as entradas. Isso permite ajustar uma premissa por vez, evitando overfitting por tentativa e erro.")
    else:
        st.dataframe(trades,hide_index=True,use_container_width=True,height=350)
    with st.expander("Regras, filtros, parâmetros e premissas do backtest"):
        st.write(result.get("strategy",{}).get("rules"))
        st.json({"parameters":result.get("parameters"),"filters":result.get("filters"),"filter_diagnostics":result.get("filter_diagnostics"),"signal_diagnostics":result.get("signal_diagnostics"),"assumptions":result.get("assumptions")})
        st.warning("Resultado histórico não é previsão. Impostos não estão incluídos; custos e slippage são aproximações configuráveis.")


def _backtest_filters_ui(asset_type):
    """Build optional entry/exit filters. All are OFF by default so the base strategy remains reproducible."""
    cfg={
        "daily_trend":{"enabled":False,"direction":"up","period":21,"mode":"price_above","slope_lookback":5},
        "weekly_trend":{"enabled":False,"direction":"up","period":21,"mode":"price_above","slope_lookback":4},
        "monthly_trend":{"enabled":False,"direction":"up","period":21,"mode":"price_above","slope_lookback":3},
        "trend_combination":"all",
        "exit_on_filter_failure":False,
        "fundamental_entry":{},"fundamental_exit":{},"fundamental_exit_logic":"any",
        "fundamental_min_coverage_pct":70.0,"fundamental_max_age_days":45,
    }
    st.markdown("### 🧩 Filtros da Estratégia")
    st.caption("Configure aqui as condições adicionais. Todos os filtros começam desligados e, por padrão, atuam somente na entrada.")
    if st.button("🧹 Desativar todos os filtros adicionais",key="bt_clear_all_filters",use_container_width=True):
        for key in (
            "bt_daily_trend_enabled","bt_weekly_trend_enabled","bt_monthly_trend_enabled","bt_exit_filter_fail",
            "bt_use_adx","bt_use_vol","bt_use_rsi","bt_use_atr",
            "bt_fb_pbv","bt_fb_pe","bt_fb_dy","bt_fb_roe","bt_fb_roic","bt_fb_debt",
            "bt_fs_pbv","bt_fs_pe","bt_fs_roe","bt_fs_debt",
            "bt_fifb_pbv","bt_fifb_dy","bt_fifb_ffo","bt_fifb_vac","bt_fifb_ltv",
            "bt_fifs_pbv","bt_fifs_vac","bt_fifs_ltv",
        ):
            st.session_state[key]=False
        st.rerun()
    with st.container(border=True):
        st.markdown("#### Tendência")
        st.caption("Cada timeframe pode testar o preço, a inclinação da SMA ou ambos. A inclinação compara a SMA atual com a de N períodos concluídos atrás.")
        cols=st.columns(3)
        mode_labels={"price_above":"Preço acima da SMA","sma_rising":"SMA ascendente","price_above_or_sma_rising":"Preço acima OU SMA ascendente","price_above_and_sma_rising":"Preço acima E SMA ascendente"}
        default_lookbacks={"daily_trend":5,"weekly_trend":4,"monthly_trend":3}
        for i,(key,label) in enumerate([("daily_trend","Diária"),("weekly_trend","Semanal"),("monthly_trend","Mensal")]):
            with cols[i]:
                enabled=st.checkbox(f"Ativar tendência {label.lower()}",key=f"bt_{key}_enabled")
                period=st.selectbox(f"Período {label.lower()}",[21,50],key=f"bt_{key}_period")
                mode=st.selectbox(f"Modo {label.lower()}",list(mode_labels),format_func=lambda x:mode_labels[x],key=f"bt_{key}_mode")
                lookback=st.number_input(f"Inclinação ({label.lower()}: períodos)",min_value=1,max_value=100,value=default_lookbacks[key],step=1,key=f"bt_{key}_slope")
                cfg[key]={"enabled":enabled,"direction":"up","period":period,"mode":mode,"slope_lookback":int(lookback)}
        cfg["trend_combination"]=st.radio(
            "Como combinar os timeframes ativos",
            ["all","any","majority"],horizontal=True,key="bt_trend_combination",
            format_func=lambda x:{"all":"TODOS (AND)","any":"QUALQUER (OR)","majority":"MAIORIA"}[x],
            help="MAIORIA exige 2 de 3 quando três estão ativos; com dois ativos, exige ambos.",
        )
        cfg["exit_on_filter_failure"]=st.checkbox(
            "Sair da posição quando qualquer filtro técnico de entrada deixar de ser atendido",
            value=False,key="bt_exit_filter_fail",
            help="Desligado: os filtros só controlam a entrada. Ligado: passam a funcionar também como stop/regra de saída.",
        )

        st.divider()
        st.markdown("#### Confirmação Técnica")
        c1,c2,c3,c4=st.columns(4)
        use_adx=c1.checkbox("Força por ADX",key="bt_use_adx")
        adx_min=c1.number_input("ADX 14 mínimo",min_value=0.0,max_value=100.0,value=25.0,step=1.0,disabled=not use_adx)
        use_vol=c2.checkbox("Confirmar por volume",key="bt_use_vol")
        vol_ratio=c2.number_input("Volume / média 20 mínimo",min_value=0.1,max_value=10.0,value=1.0,step=0.1,disabled=not use_vol)
        use_rsi=c3.checkbox("Faixa de RSI",key="bt_use_rsi")
        rsi_min=c3.number_input("RSI 14 mínimo",min_value=0.0,max_value=100.0,value=0.0,step=1.0,disabled=not use_rsi)
        rsi_max=c3.number_input("RSI 14 máximo",min_value=0.0,max_value=100.0,value=70.0,step=1.0,disabled=not use_rsi)
        use_atr=c4.checkbox("Regime de volatilidade (ATR%)",key="bt_use_atr")
        atr_min=c4.number_input("ATR 14 mínimo (% preço)",min_value=0.0,max_value=100.0,value=0.0,step=0.25,disabled=not use_atr)
        atr_max=c4.number_input("ATR 14 máximo (% preço)",min_value=0.0,max_value=100.0,value=8.0,step=0.25,disabled=not use_atr)
        cfg.update({
            "adx_min":float(adx_min) if use_adx else None,
            "volume_ratio_min":float(vol_ratio) if use_vol else None,
            "rsi_min":float(rsi_min) if use_rsi else None,"rsi_max":float(rsi_max) if use_rsi else None,
            "atr_pct_min":float(atr_min) if use_atr else None,"atr_pct_max":float(atr_max) if use_atr else None,
        })
        st.caption("ADX mede força, não direção; a direção vem dos filtros de tendência. Volume compara o pregão com sua média de 20 dias. ATR% limita regimes muito calmos ou muito voláteis.")

        st.divider()
        st.markdown("#### Fundamentos")
        if asset_type not in {"stock","fii"}:
            st.info("Filtros fundamentalistas ocultos para ETF, BDR e outros ativos sem demonstrações empresariais/FII comparáveis. Tendência, ADX, volume, RSI e ATR continuam disponíveis acima.")
            return cfg
        st.warning("Estes filtros só são executados se o banco possuir histórico fundamentalista suficiente ao longo do período. O motor recusa usar o P/VP ou outros números de hoje no passado para evitar look-ahead bias.")
        buy, sell = st.tabs(["Condição para COMPRA","Condição para VENDA"])
        entry={}; exit_={}
        if asset_type=="stock":
            with buy:
                x1,x2,x3,x4,x5,x6=st.columns(6)
                if x1.checkbox("P/VP máx.",key="bt_fb_pbv"):entry["pbv"]={"max":x1.number_input("máx",value=1.50,step=0.05,key="bt_fb_pbv_v")}
                if x2.checkbox("P/L máx.",key="bt_fb_pe"):entry["pe"]={"max":x2.number_input("máx",value=15.0,step=0.5,key="bt_fb_pe_v")}
                if x3.checkbox("DY mín.",key="bt_fb_dy"):entry["dividend_yield_pct"]={"min":x3.number_input("mín %",value=4.0,step=0.5,key="bt_fb_dy_v")}
                if x4.checkbox("ROE mín.",key="bt_fb_roe"):entry["roe_pct"]={"min":x4.number_input("mín %",value=10.0,step=1.0,key="bt_fb_roe_v")}
                if x5.checkbox("ROIC mín.",key="bt_fb_roic"):entry["roic_pct"]={"min":x5.number_input("mín %",value=8.0,step=1.0,key="bt_fb_roic_v")}
                if x6.checkbox("Dív.Liq/EBITDA máx.",key="bt_fb_debt"):entry["net_debt_to_ebitda"]={"max":x6.number_input("máx",value=3.0,step=0.25,key="bt_fb_debt_v")}
            with sell:
                x1,x2,x3,x4=st.columns(4)
                if x1.checkbox("P/VP mín. para vender",key="bt_fs_pbv"):exit_["pbv"]={"min":x1.number_input("P/VP >=",value=2.0,step=0.05,key="bt_fs_pbv_v")}
                if x2.checkbox("P/L mín. para vender",key="bt_fs_pe"):exit_["pe"]={"min":x2.number_input("P/L >=",value=20.0,step=0.5,key="bt_fs_pe_v")}
                if x3.checkbox("ROE baixo para vender",key="bt_fs_roe"):exit_["roe_pct"]={"max":x3.number_input("ROE <= %",value=8.0,step=1.0,key="bt_fs_roe_v")}
                if x4.checkbox("Dívida alta para vender",key="bt_fs_debt"):exit_["net_debt_to_ebitda"]={"min":x4.number_input("Dív.Liq/EBITDA >=",value=4.0,step=0.25,key="bt_fs_debt_v")}
        else:
            with buy:
                x1,x2,x3,x4,x5=st.columns(5)
                if x1.checkbox("P/VP máx.",key="bt_fifb_pbv"):entry["pbv"]={"max":x1.number_input("máx",value=1.0,step=0.05,key="bt_fifb_pbv_v")}
                if x2.checkbox("DY mín.",key="bt_fifb_dy"):entry["dividend_yield_pct"]={"min":x2.number_input("mín %",value=8.0,step=0.5,key="bt_fifb_dy_v")}
                if x3.checkbox("FFO Yield mín.",key="bt_fifb_ffo"):entry["ffo_yield_pct"]={"min":x3.number_input("mín %",value=6.0,step=0.5,key="bt_fifb_ffo_v")}
                if x4.checkbox("Vacância máx.",key="bt_fifb_vac"):entry["vacancy_pct"]={"max":x4.number_input("máx %",value=10.0,step=1.0,key="bt_fifb_vac_v")}
                if x5.checkbox("LTV máx.",key="bt_fifb_ltv"):entry["ltv_pct"]={"max":x5.number_input("máx %",value=40.0,step=1.0,key="bt_fifb_ltv_v")}
            with sell:
                x1,x2,x3=st.columns(3)
                if x1.checkbox("P/VP mín. para vender",key="bt_fifs_pbv"):exit_["pbv"]={"min":x1.number_input("P/VP >=",value=1.20,step=0.05,key="bt_fifs_pbv_v")}
                if x2.checkbox("Vacância alta para vender",key="bt_fifs_vac"):exit_["vacancy_pct"]={"min":x2.number_input("Vacância >= %",value=15.0,step=1.0,key="bt_fifs_vac_v")}
                if x3.checkbox("LTV alto para vender",key="bt_fifs_ltv"):exit_["ltv_pct"]={"min":x3.number_input("LTV >= %",value=50.0,step=1.0,key="bt_fifs_ltv_v")}
        cfg["fundamental_entry"]=entry; cfg["fundamental_exit"]=exit_
        if exit_:
            cfg["fundamental_exit_logic"]=st.radio("Se houver mais de uma regra de venda",["any","all"],horizontal=True,format_func=lambda x:"Vender se QUALQUER regra ocorrer" if x=="any" else "Vender somente se TODAS ocorrerem",key="bt_fund_exit_logic")
        with st.popover("Qualidade mínima do histórico fundamentalista"):
            cfg["fundamental_min_coverage_pct"]=st.slider("Cobertura mínima (%)",1,100,70,key="bt_fund_cov")
            cfg["fundamental_max_age_days"]=st.slider("Idade máxima de um snapshot (dias)",1,365,45,key="bt_fund_age")
    return cfg


def _render_basket_result(result):
    metrics=result.get("metrics") or {}
    st.subheader(f"Cesta • {result.get('strategy',{}).get('name','Estratégia')}")
    st.caption(f"{metrics.get('asset_count',0)} ativo(s) válido(s) • pesos iguais • {str(result.get('actual_start',''))[:10]} a {str(result.get('actual_end',''))[:10]}")
    a=st.columns(6)
    a[0].metric("Retorno da cesta",_pct(metrics.get("total_return_pct")))
    a[1].metric("CAGR",_pct(metrics.get("cagr_pct")))
    a[2].metric("Buy & Hold cesta",_pct(metrics.get("benchmark_total_return_pct")))
    a[3].metric("Max drawdown",_pct(metrics.get("max_drawdown_pct")))
    a[4].metric("Sharpe",br_num(metrics.get("sharpe_ratio"),2))
    a[5].metric("Exposição média",_pct(metrics.get("average_exposure_pct")))
    b=st.columns(6)
    b[0].metric("Trades encerrados",metrics.get("closed_trades",0))
    b[1].metric("Posições abertas",metrics.get("open_trades",0))
    b[2].metric("PF marcado a mercado",br_num(metrics.get("profit_factor_mark_to_market"),2))
    b[3].metric("Acerto marcado",_pct(metrics.get("win_rate_mark_to_market_pct")))
    b[4].metric("Ativos positivos",f"{metrics.get('positive_assets',0)}/{metrics.get('asset_count',0)}")
    b[5].metric("Top 2 nos lucros",_pct(metrics.get("top_2_profit_concentration_pct")))

    aliases=[x.get("ticker_alias") for x in (result.get("assets") or []) if x.get("ticker_alias")]
    for alias in aliases:
        st.info(f"Código atualizado automaticamente: {alias.get('requested')} → {alias.get('ticker')}. {alias.get('reason')}.")
    failures=result.get("failures") or []
    if failures:
        st.warning(f"{len(failures)} item(ns) foram excluídos da cesta. Consulte os motivos abaixo; os pesos foram redistribuídos entre os ativos válidos.")
        st.dataframe(pd.DataFrame(failures).rename(columns={"requested_ticker":"Solicitado","resolved_ticker":"Resolvido","error":"Motivo"}),hide_index=True,use_container_width=True)

    curve=pd.DataFrame(result.get("portfolio_curve") or [])
    if not curve.empty:
        curve["timestamp"]=pd.to_datetime(curve["timestamp"]); curve=curve.set_index("timestamp").sort_index()
        st.markdown("#### Curva consolidada da carteira")
        st.line_chart(curve[["equity","benchmark"]].rename(columns={"equity":"Estratégia","benchmark":"Buy & Hold"}))
        st.markdown("#### Drawdown consolidado")
        st.line_chart(curve[["drawdown_pct"]].rename(columns={"drawdown_pct":"Drawdown %"}))

    assets=pd.DataFrame(result.get("assets") or [])
    if not assets.empty:
        view=assets.rename(columns={
            "requested_ticker":"Solicitado","ticker":"Ticker","weight_pct":"Peso %","initial_capital":"Capital inicial",
            "final_equity":"Capital final","return_pct":"Retorno %","contribution_pct_points":"Contribuição p.p.",
            "max_drawdown_pct":"Max DD %","exposure_pct":"Exposição %","closed_trades":"Trades encerrados",
            "open_trades":"Posições abertas","profit_factor_closed":"PF encerrados","profit_factor_mark_to_market":"PF marcado",
        })
        st.markdown("#### Contribuição por ativo")
        st.bar_chart(view.set_index("Ticker")[["Contribuição p.p."]])
        cols=[c for c in ["Solicitado","Ticker","Peso %","Retorno %","Contribuição p.p.","Max DD %","Exposição %","Trades encerrados","Posições abertas","PF encerrados","PF marcado"] if c in view]
        st.dataframe(view[cols].sort_values("Contribuição p.p.",ascending=False),hide_index=True,use_container_width=True)
        if metrics.get("top_2_profit_concentration_pct") is not None:
            st.caption(f"Os dois maiores contribuidores representam {_pct(metrics.get('top_2_profit_concentration_pct'))} dos lucros positivos da cesta. Concentração elevada indica dependência de poucos vencedores.")
    _render_backtest_configuration(result)


def render_backtests():
    if not can("can_run_backtests"):
        st.info("Modo consulta: esta conta pode visualizar resultados autorizados, mas não pode executar nem salvar novos backtests.")
    st.title("🧪 Backtests — Estratégias Técnicas")
    st.caption("Teste regras objetivas em diferentes horizontes, compare com buy-and-hold e examine risco, custos e operações.")
    catalog,err=api_get("/backtests/strategies")
    if err or not catalog:
        st.error(f"Não foi possível carregar as estratégias: {err}"); return
    strategies=catalog.get("strategies") or []
    by_id={x["id"]:x for x in strategies}
    periods=catalog.get("periods") or {"6m":"6 meses","1y":"1 ano","2y":"2 anos","3y":"3 anos","5y":"5 anos","10y":"10 anos","15y":"15 anos","20y":"20 anos"}

    a,b,c=st.columns([2,1,1])
    ticker=a.text_input("Ativo para o backtest",value="BBAS3",key="bt_ticker").strip().upper()
    type_label=b.selectbox("Tipo do ativo",["Ação","FII","ETF","BDR","Outro"],key="bt_type")
    type_map={"Ação":"stock","FII":"fii","ETF":"etf","BDR":"bdr","Outro":"other"}
    period_options=list(periods.keys())+["custom"]
    period=c.selectbox("Período",period_options,index=(period_options.index("5y") if "5y" in period_options else 0),format_func=lambda x:periods.get(x,"Personalizado"),key="bt_period")
    start=end=None
    if period=="custom":
        d1,d2=st.columns(2); start=d1.date_input("Data inicial",value=date.today()-timedelta(days=365)); end=d2.date_input("Data final",value=date.today())

    with st.expander("Custos e premissas financeiras"):
        x1,x2,x3,x4=st.columns(4)
        capital=x1.number_input("Capital inicial (R$)",min_value=100.0,value=10000.0,step=1000.0)
        fee=x2.number_input("Custos por movimentação (%)",min_value=0.0,max_value=5.0,value=0.03,step=0.01,format="%.3f")
        slip=x3.number_input("Slippage por movimentação (%)",min_value=0.0,max_value=5.0,value=0.05,step=0.01,format="%.3f")
        rf=x4.number_input("Taxa livre de risco anual (%)",min_value=-20.0,max_value=100.0,value=0.0,step=0.5)
        y1,y2=st.columns(2)
        apply_cash_yield=y1.checkbox("Remunerar o capital em caixa",value=False,key="bt_apply_cash_yield",help="Aplica uma taxa anual constante somente nos pregões em que a estratégia está fora do ativo.")
        cash_yield_rate=y2.number_input("Rendimento anual do caixa (%)",min_value=-99.0,max_value=100.0,value=10.0,step=0.5,disabled=not apply_cash_yield,key="bt_cash_yield_rate")
        st.caption("Custos e slippage são descontados quando a posição muda. A taxa livre de risco afeta Sharpe/Sortino. A remuneração do caixa, quando ativada, entra efetivamente no retorno e usa uma taxa anual constante.")

    with st.expander("🧩 Filtros da estratégia — clique para configurar",expanded=False):
        filters=_backtest_filters_ui(type_map[type_label])

    _compact_summary(
        "BACKTEST PREPARADO",
        [ticker,type_label,periods.get(period,"Período personalizado")]+_backtest_filter_summary(filters),
        ["Filtros e regras recolhidos acima"],
    )

    st.markdown("#### Cinco melhores backtests oficiais")
    signal_labels={"buy":"🟢 Comprar","sell":"🔴 Vender","neutral":"⚪ Neutro"}
    top_rows,top_error=api_get("/backtests/top",{"limit":5})
    if top_error:
        st.warning(f"O ranking oficial ainda não pôde ser carregado: {top_error}")
    elif not top_rows:
        st.info("O ranking aparecerá após a primeira atualização semanal ou manual do catálogo oficial.")
    else:
        top_table=[]
        for position,item in enumerate(top_rows,start=1):
            metrics=item.get("metrics") or {}
            top_table.append({
                "Posição":position,"Ativo":item.get("ticker"),"Setor":item.get("sector"),
                "Estratégia":item.get("strategy_name"),"Nota":item.get("ranking_score"),
                "Sinal":signal_labels.get(item.get("current_signal"),"⚪ Neutro"),
                "CAGR %":metrics.get("cagr_pct"),"Sharpe":metrics.get("sharpe_ratio"),
                "Max DD %":metrics.get("max_drawdown_pct"),"Trades":metrics.get("closed_trades",metrics.get("trades")),
                "Amostra":item.get("sample_status"),"Atualização":item.get("signal_as_of"),
            })
        st.dataframe(pd.DataFrame(top_table),hide_index=True,use_container_width=True)

    backtest_tab_labels=["Executar estratégia","Testar cesta","Comparar estratégias","Histórico salvo"]
    if can("can_view_backtest_studies"):backtest_tab_labels.append("🏆 Estudo dos Backtests")
    backtest_tabs=st.tabs(backtest_tab_labels)
    run_tab,basket_tab,compare_tab,history_tab=backtest_tabs[:4]
    study_tab=backtest_tabs[4] if can("can_view_backtest_studies") else None
    with run_tab:
        sid=st.selectbox("Estratégia",list(by_id),format_func=lambda x:by_id[x]["name"],key="bt_strategy")
        definition=by_id[sid]
        with st.expander("📖 Entenda a estratégia e suas regras",expanded=False):
            st.info(f"**{definition['family']}** — {definition['description']}\n\n**Regra:** {definition['rules']}")
        _compact_summary("ESTRATÉGIA",[definition["name"],definition["family"]],["Parâmetros ajustáveis abaixo"])
        params={}
        if sid=="custom_ma_cross":
            st.markdown("##### Parâmetros personalizados")
            p1,p2,p3,p4=st.columns(4)
            params["fast_period"]=p1.number_input("Período rápido",min_value=2,max_value=200,value=9,step=1)
            params["slow_period"]=p2.number_input("Período lento",min_value=3,max_value=400,value=40,step=1)
            params["fast_type"]=p3.selectbox("Tipo rápida",["ema","sma"],format_func=lambda x:x.upper())
            params["slow_type"]=p4.selectbox("Tipo lenta",["sma","ema"],format_func=lambda x:x.upper())
        elif sid=="bollinger_rsi_trend":
            st.markdown("##### Parâmetros da estratégia Bollinger")
            if st.button("🎯 Aplicar controle validado: SMA200 ascendente + mínima toca a banda",key="bt_boll_control_preset",use_container_width=True):
                st.session_state.update({
                    "bt_boll_period":20,"bt_boll_stddev":2.0,"bt_boll_rsi_period":14,"bt_boll_entry_rsi":35.0,
                    "bt_boll_exit_rsi":55.0,"bt_boll_trend_period":200,"bt_boll_trend_mode":"sma_rising",
                    "bt_boll_slope":20,"bt_boll_trigger":"low_touch",
                })
                st.rerun()
            p1,p2,p3,p4=st.columns(4)
            params["period"]=p1.number_input("Período Bollinger",min_value=10,max_value=100,value=20,step=1,key="bt_boll_period")
            params["stddev"]=p2.number_input("Desvios",min_value=1.0,max_value=4.0,value=2.0,step=0.1,key="bt_boll_stddev")
            params["rsi_period"]=p3.number_input("Período RSI",min_value=2,max_value=50,value=14,step=1,key="bt_boll_rsi_period")
            params["entry_rsi"]=p4.number_input("RSI entrada ≤",min_value=10.0,max_value=60.0,value=35.0,step=1.0,key="bt_boll_entry_rsi")
            q1,q2,q3,q4=st.columns(4)
            params["exit_rsi"]=q1.number_input("RSI saída ≥",min_value=40.0,max_value=90.0,value=55.0,step=1.0,key="bt_boll_exit_rsi")
            params["trend_period"]=q2.number_input("SMA tendência",min_value=20,max_value=400,value=200,step=10,key="bt_boll_trend_period")
            mode_labels={
                "price_above":"Preço > SMA",
                "sma_rising":"SMA ascendente",
                "price_above_and_sma_rising":"Preço > SMA E SMA ascendente",
                "price_above_or_sma_rising":"Preço > SMA OU SMA ascendente",
                "none":"Sem filtro estrutural",
            }
            params["trend_filter_mode"]=q3.selectbox("Filtro estrutural",list(mode_labels),format_func=lambda x:mode_labels[x],key="bt_boll_trend_mode")
            params["trend_slope_lookback"]=q4.number_input("Inclinação da SMA (pregões)",min_value=1,max_value=100,value=20,step=1,disabled=params["trend_filter_mode"] not in {"sma_rising","price_above_and_sma_rising","price_above_or_sma_rising"},key="bt_boll_slope")
            z1,z2=st.columns(2)
            trig_labels={"close":"Fechamento ≤ banda","low_touch":"Mínima toca a banda","close_reentry":"Reentrada: fechou abaixo e voltou acima da banda"}
            params["band_trigger"]=z1.selectbox("Gatilho da banda",list(trig_labels),format_func=lambda x:trig_labels[x],key="bt_boll_trigger")
            z2.info("Sugestão de teste controlado: mantenha Bollinger/RSI iguais e altere somente o filtro estrutural. Assim você identifica se a SMA200 está bloqueando o setup sem misturar várias mudanças ao mesmo tempo.")
            if params["trend_filter_mode"]=="price_above":
                st.warning(f"Configuração atual: Preço > SMA{int(params['trend_period'])}. Este modo é diferente de ‘SMA ascendente’ e pode bloquear pullbacks abaixo da média.")
            else:
                st.success(f"Filtro estrutural selecionado: {mode_labels[params['trend_filter_mode']]}. Esta escolha aparecerá novamente no mapa do resultado.")
            st.caption("O modo ‘SMA ascendente’ aceita um pullback temporariamente abaixo da SMA, desde que a tendência longa continue inclinada para cima. A execução permanece no pregão seguinte ao sinal.")
            st.info(
                f"**Configuração pronta para executar:** Bollinger {int(params['period'])}/{float(params['stddev']):.2f} • "
                f"RSI {int(params['rsi_period'])} ≤ {float(params['entry_rsi']):.2f} / saída ≥ {float(params['exit_rsi']):.2f} • "
                f"{mode_labels[params['trend_filter_mode']]} {int(params['trend_period'])} • "
                f"{trig_labels[params['band_trigger']]}"
            )
        if st.button("▶ Executar backtest",type="primary",key="bt_run",disabled=not can("can_run_backtests")):
            payload={"ticker":ticker,"asset_type":type_map[type_label],"strategy_id":sid,"period":period,"initial_capital":capital,"fee_pct":fee,"slippage_pct":slip,"risk_free_rate_pct":rf,"apply_cash_yield":apply_cash_yield,"cash_yield_rate_pct":cash_yield_rate,"params":params,"filters":filters,"persist":True}
            if period=="custom":payload.update({"start":datetime.combine(start,datetime.min.time(),tzinfo=timezone.utc).isoformat(),"end":datetime.combine(end,datetime.max.time(),tzinfo=timezone.utc).isoformat()})
            with st.spinner("Carregando histórico, calculando sinais e simulando operações..."):
                result,e=api_post("/backtests/run",payload,timeout=300)
            if e:st.error(f"Backtest não concluído: {e}")
            else:st.session_state.bt_last_result=result
        if st.session_state.get("bt_last_result"):
            _render_backtest_result(st.session_state.bt_last_result)

    with basket_tab:
        st.markdown("#### Backtest de cesta com pesos iguais")
        st.caption("Cada ativo recebe o mesmo peso entre os códigos com histórico válido. Retorno e drawdown são calculados pela curva consolidada diária.")
        basket_text=st.text_area("Ativos da cesta (separados por vírgula, espaço ou linha)",value="BBAS3, PETR4, USIM5, VIVA3, POMO4, TAEE11, VIVT4, BBSE3, KLBN11, EMBR3",height=90,key="bt_basket_tickers")
        basket_tickers=[x.strip().upper() for x in basket_text.replace("\n",",").replace(";",",").replace(" ",",").split(",") if x.strip()]
        z1,z2=st.columns([2,1])
        basket_sid=z1.selectbox("Estratégia da cesta",list(by_id),index=(list(by_id).index("bollinger_rsi_trend") if "bollinger_rsi_trend" in by_id else 0),format_func=lambda x:by_id[x]["name"],key="bt_basket_strategy")
        basket_capital=z2.number_input("Capital total da cesta (R$)",min_value=1000.0,value=100000.0,step=10000.0,key="bt_basket_capital")
        basket_params={}
        if basket_sid=="bollinger_rsi_trend":
            st.markdown("##### Parâmetros Bollinger da cesta")
            p1,p2,p3,p4=st.columns(4)
            basket_params["period"]=p1.number_input("Período Bollinger",10,100,20,1,key="basket_boll_period")
            basket_params["stddev"]=p2.number_input("Desvios",1.0,4.0,2.0,0.1,key="basket_boll_stddev")
            basket_params["rsi_period"]=p3.number_input("Período RSI",2,50,14,1,key="basket_boll_rsi_period")
            basket_params["entry_rsi"]=p4.number_input("RSI entrada ≤",10.0,60.0,35.0,1.0,key="basket_boll_entry")
            q1,q2,q3,q4=st.columns(4)
            basket_params["exit_rsi"]=q1.number_input("RSI saída ≥",40.0,90.0,55.0,1.0,key="basket_boll_exit")
            basket_params["trend_period"]=q2.number_input("SMA tendência",20,400,200,10,key="basket_boll_trend")
            bmodes={"sma_rising":"SMA ascendente","price_above":"Preço > SMA","price_above_or_sma_rising":"Preço > SMA OU ascendente","price_above_and_sma_rising":"Preço > SMA E ascendente","none":"Sem filtro estrutural"}
            basket_params["trend_filter_mode"]=q3.selectbox("Filtro estrutural",list(bmodes),format_func=lambda x:bmodes[x],key="basket_boll_mode")
            basket_params["trend_slope_lookback"]=q4.number_input("Inclinação (pregões)",1,100,20,1,key="basket_boll_slope")
            triggers={"low_touch":"Mínima toca a banda","close":"Fechamento ≤ banda","close_reentry":"Reentrada acima da banda"}
            basket_params["band_trigger"]=st.selectbox("Gatilho da banda",list(triggers),format_func=lambda x:triggers[x],key="basket_boll_trigger")
        elif basket_sid=="custom_ma_cross":
            p1,p2,p3,p4=st.columns(4)
            basket_params["fast_period"]=p1.number_input("Período rápido",2,200,9,1,key="basket_fast")
            basket_params["slow_period"]=p2.number_input("Período lento",3,400,40,1,key="basket_slow")
            basket_params["fast_type"]=p3.selectbox("Tipo rápida",["ema","sma"],key="basket_fast_type")
            basket_params["slow_type"]=p4.selectbox("Tipo lenta",["sma","ema"],key="basket_slow_type")
        if st.button("🧪 Executar backtest da cesta",type="primary",key="bt_basket_run",disabled=(len(set(basket_tickers))<2 or not can("can_run_backtests")),use_container_width=True):
            payload={"tickers":basket_tickers,"asset_type":type_map[type_label],"strategy_id":basket_sid,"period":period,"initial_capital":basket_capital,"fee_pct":fee,"slippage_pct":slip,"risk_free_rate_pct":rf,"apply_cash_yield":apply_cash_yield,"cash_yield_rate_pct":cash_yield_rate,"params":basket_params,"filters":filters}
            if period=="custom":payload.update({"start":datetime.combine(start,datetime.min.time(),tzinfo=timezone.utc).isoformat(),"end":datetime.combine(end,datetime.max.time(),tzinfo=timezone.utc).isoformat()})
            with st.spinner("Carregando os ativos e consolidando as curvas diárias da cesta..."):
                basket_result,e=api_post("/backtests/basket",payload,timeout=900)
            if e:st.error(f"Backtest da cesta não concluído: {e}")
            else:st.session_state.bt_basket_result=basket_result
        if st.session_state.get("bt_basket_result"):
            _render_basket_result(st.session_state.bt_basket_result)

    with compare_tab:
        default_ids=[x for x in ["ema9_sma50","ema9_sma40","sma3_ema9_sma21","sma50_sma200","macd_12_26_9","donchian_20_10","momentum_12m"] if x in by_id]
        selected=st.multiselect("Estratégias para comparar",list(by_id),default=default_ids,format_func=lambda x:by_id[x]["name"])
        if st.button("Comparar no mesmo ativo e período",key="bt_compare",disabled=(not bool(selected) or not can("can_run_backtests"))):
            payload={"ticker":ticker,"asset_type":type_map[type_label],"strategy_ids":selected,"period":period,"initial_capital":capital,"fee_pct":fee,"slippage_pct":slip,"risk_free_rate_pct":rf,"apply_cash_yield":apply_cash_yield,"cash_yield_rate_pct":cash_yield_rate,"filters":filters}
            if period=="custom":payload.update({"start":datetime.combine(start,datetime.min.time(),tzinfo=timezone.utc).isoformat(),"end":datetime.combine(end,datetime.max.time(),tzinfo=timezone.utc).isoformat()})
            with st.spinner("Comparando estratégias sobre a mesma série histórica..."):
                rows,e=api_post("/backtests/compare",payload,timeout=300)
            if e:
                st.session_state.bt_compare=[]
                st.error(f"Comparação não concluída: {e}")
            elif not isinstance(rows,list):
                st.session_state.bt_compare=[]
                st.error("A API devolveu uma resposta inesperada na comparação. Nenhuma tabela foi construída para evitar o erro do pandas.")
            else:st.session_state.bt_compare=rows
        comp=st.session_state.get("bt_compare") or []
        if isinstance(comp,list) and comp:
            cdf=pd.DataFrame.from_records(comp).rename(columns={"strategy_name":"Estratégia","total_return_pct":"Retorno %","cagr_pct":"CAGR %","sharpe_ratio":"Sharpe","sortino_ratio":"Sortino","max_drawdown_pct":"Max DD %","trades":"Trades encerrados","open_trades":"Posições abertas","win_rate_pct":"Acerto encerrados %","profit_factor":"PF encerrados","profit_factor_mark_to_market":"PF marcado a mercado","exposure_pct":"Exposição %","benchmark_total_return_pct":"Buy & Hold %","excess_total_return_pct":"Excesso %"})
            cols=[c for c in ["Estratégia","Retorno %","CAGR %","Buy & Hold %","Excesso %","Sharpe","Sortino","Max DD %","Trades encerrados","Posições abertas","Acerto encerrados %","PF encerrados","PF marcado a mercado","Exposição %"] if c in cdf]
            st.dataframe(cdf[cols].sort_values("CAGR %",ascending=False,na_position="last"),hide_index=True,use_container_width=True)
            st.caption("A comparação não escolhe automaticamente a ‘melhor’ estratégia: retorno, drawdown, estabilidade, número de operações e robustez precisam ser avaliados em conjunto.")

    with history_tab:
        st.markdown("#### 100 backtests mais recentes")
        st.caption("A conta vê seu histórico particular e o catálogo oficial. Somente o proprietário pode consultar históricos particulares de outras contas.")
        h1,h2,h3=st.columns(3)
        history_ticker=h1.text_input("Filtrar por ação",value="",placeholder="Ex.: BBAS3",key="bt_history_ticker").strip().upper()
        history_sector=h2.text_input("Filtrar por setor",value="",placeholder="Ex.: Energia",key="bt_history_sector").strip()
        scope_labels={"":"Pessoal + oficial","personal":"Somente pessoais","official":"Somente oficiais"}
        history_scope=h3.selectbox("Origem",list(scope_labels),format_func=lambda value:scope_labels[value],key="bt_history_scope")
        query={"limit":100}
        if history_ticker:query["ticker"]=history_ticker
        if history_sector:query["sector"]=history_sector
        if history_scope:query["scope"]=history_scope
        filtered_top_query={"limit":5}
        if history_ticker:filtered_top_query["ticker"]=history_ticker
        if history_sector:filtered_top_query["sector"]=history_sector
        filtered_top,filtered_top_error=api_get("/backtests/top",filtered_top_query)
        if not filtered_top_error and filtered_top:
            st.markdown("##### Cinco melhores oficiais dentro destes filtros")
            filtered_rows=[]
            for position,item in enumerate(filtered_top,start=1):
                metrics=item.get("metrics") or {}
                filtered_rows.append({
                    "Posição":position,"Ativo":item.get("ticker"),"Setor":item.get("sector"),
                    "Estratégia":item.get("strategy_name"),"Nota":item.get("ranking_score"),
                    "Sinal":signal_labels.get(item.get("current_signal"),"⚪ Neutro"),
                    "CAGR %":metrics.get("cagr_pct"),"Sharpe":metrics.get("sharpe_ratio"),
                    "Max DD %":metrics.get("max_drawdown_pct"),"Trades":metrics.get("closed_trades",metrics.get("trades")),
                })
            st.dataframe(pd.DataFrame(filtered_rows),hide_index=True,use_container_width=True)
        runs,e=api_get("/backtests/runs",query)
        if e:st.error(e)
        elif not runs:st.info("Nenhum backtest salvo atende aos filtros escolhidos.")
        else:
            runs=sorted(runs,key=lambda item:_datetime_sort_value(item.get("created_at")),reverse=True)
            st.caption("Ordem da tabela: análise mais recente primeiro.")
            rows=[]
            for r in runs:
                m=r.get("metrics") or {}
                signal_labels={"buy":"Comprar","sell":"Vender","neutral":"Neutro"}
                rows.append({
                    "ID":r["id"],"Data e horário":br_datetime(r.get("created_at")),"Origem":"Oficial" if r.get("scope")=="official" else "Pessoal",
                    "Ativo":r.get("ticker"),"Setor":r.get("sector"),"Estratégia":r.get("strategy_name"),
                    "Sinal":signal_labels.get(r.get("current_signal"),"Neutro"),"Nota":r.get("ranking_score"),
                    "Amostra":r.get("sample_status"),"Início":r.get("actual_start"),"Fim":r.get("actual_end"),
                    "Retorno %":m.get("total_return_pct"),"CAGR %":m.get("cagr_pct"),"Sharpe":m.get("sharpe_ratio"),
                    "Max DD %":m.get("max_drawdown_pct"),"Trades encerrados":m.get("closed_trades",m.get("trades")),
                    "Posições abertas":m.get("open_trades",0),"Versão":r.get("engine_version"),
                })
            hdf=pd.DataFrame(rows); st.dataframe(hdf,hide_index=True,use_container_width=True,height=360)
            rid=st.selectbox("Abrir execução salva",[r["id"] for r in runs],format_func=lambda x:next((f"{r['ticker']} • {r['strategy_name']} • {br_datetime(r.get('created_at'))}" for r in runs if r["id"]==x),x))
            if st.button("Abrir resultado salvo"):
                detail,e=api_get(f"/backtests/runs/{rid}")
                if e:st.error(e)
                else:
                    if not detail.get("strategy"):
                        detail["strategy"]={"name":detail.get("strategy_name"),"rules":"Execução histórica salva; consulte os parâmetros abaixo."}
                    detail.setdefault("assumptions",{"fee_pct":detail.get("fee_pct"),"slippage_pct":detail.get("slippage_pct"),"risk_free_rate_pct":detail.get("risk_free_rate_pct")})
                    _render_backtest_result(detail)

    if study_tab is not None:
        with study_tab:
            _render_backtest_study()


_BACKTEST_CONFIG_LABELS={
    "fast_period":"Período da média rápida","slow_period":"Período da média lenta",
    "fast_type":"Tipo da média rápida","slow_type":"Tipo da média lenta",
    "mid_period":"Período da média intermediária","period":"Período",
    "stddev":"Desvios da Bollinger","rsi_period":"Período do RSI",
    "entry_rsi":"RSI máximo para entrada","exit_rsi":"RSI mínimo para saída",
    "trend_period":"Período da SMA estrutural","trend_filter_mode":"Filtro estrutural",
    "trend_slope_lookback":"Inclinação da SMA (pregões)","band_trigger":"Gatilho da banda",
    "entry_period":"Período de entrada","exit_period":"Período de saída",
    "lookback":"Período de observação","fast":"Período rápido","slow":"Período lento",
    "signal":"Período do sinal","daily_trend":"Tendência diária",
    "weekly_trend":"Tendência semanal","monthly_trend":"Tendência mensal",
    "enabled":"Ativo","direction":"Direção","mode":"Modo","slope_lookback":"Inclinação (períodos)",
    "trend_combination":"Combinação dos timeframes","adx_min":"ADX mínimo",
    "volume_ratio_min":"Volume / média 20 mínimo","rsi_min":"RSI mínimo","rsi_max":"RSI máximo",
    "atr_pct_min":"ATR mínimo (% do preço)","atr_pct_max":"ATR máximo (% do preço)",
    "exit_on_filter_failure":"Sair quando filtro falhar","fundamental_entry":"Fundamentos na entrada",
    "fundamental_exit":"Fundamentos na saída","fundamental_exit_logic":"Lógica da saída fundamental",
    "fundamental_min_coverage_pct":"Cobertura fundamental mínima (%)",
    "fundamental_max_age_days":"Idade máxima do fundamento (dias)",
    "apply_cash_yield":"Remunerar caixa livre","cash_yield_rate_pct":"Taxa do caixa (%)",
    "initial_capital":"Capital inicial","fee_pct":"Taxa operacional (%)",
    "slippage_pct":"Slippage (%)","risk_free_rate_pct":"Taxa livre de risco (%)",
}
_BACKTEST_CONFIG_VALUES={
    "ema":"EMA (exponencial)","sma":"SMA (simples)","price_above":"Preço acima da SMA",
    "sma_rising":"SMA ascendente","price_above_or_sma_rising":"Preço acima OU SMA ascendente",
    "price_above_and_sma_rising":"Preço acima E SMA ascendente","none":"Nenhum",
    "close":"Fechamento ≤ banda","low_touch":"Mínima toca a banda",
    "close_reentry":"Reentrada após fechar abaixo da banda","all":"TODOS (AND)",
    "any":"QUALQUER (OR)","majority":"MAIORIA","up":"Alta","down":"Baixa",
}


def _backtest_config_value(value):
    if isinstance(value,bool):return "Sim" if value else "Não"
    if value is None:return "Não aplicado"
    if isinstance(value,float):return br_num(value,2)
    return _BACKTEST_CONFIG_VALUES.get(str(value),value)


def _flatten_backtest_config(mapping,prefix=""):
    rows=[]
    for key,value in (mapping or {}).items():
        label=_BACKTEST_CONFIG_LABELS.get(key,str(key).replace("_"," ").capitalize())
        full_label=f"{prefix} • {label}" if prefix else label
        if isinstance(value,dict):
            if value:rows.extend(_flatten_backtest_config(value,full_label))
        else:rows.append({"Configuração":full_label,"Valor":_backtest_config_value(value)})
    return rows


def _backtest_parameter_summary(parameters):
    values=parameters or {}
    if {"fast_period","slow_period"}.issubset(values):
        fast=str(values.get("fast_type") or "").upper() or "Média"
        slow=str(values.get("slow_type") or "").upper() or "Média"
        return f"{fast} {values['fast_period']} × {slow} {values['slow_period']}"
    parts=[]
    for key,value in list(values.items())[:4]:
        parts.append(f"{_BACKTEST_CONFIG_LABELS.get(key,key)}: {_backtest_config_value(value)}")
    return " • ".join(parts) or "Parâmetros padrão"


def _render_study_configuration_details(strategy):
    strategy_id=strategy.get("strategy_id")
    details,error=api_get(f"/backtests/study/{strategy_id}/configurations")
    if error:
        st.error(f"Não foi possível abrir as configurações: {error}"); return
    details=details or {}; configurations=details.get("items") or []
    st.markdown(f"### Configurações usadas — {details.get('strategy_name') or strategy.get('strategy_name')}")
    st.caption(details.get("strategy_rules") or "Cada linha abaixo representa uma combinação efetivamente executada no catálogo oficial.")
    c1,c2,c3=st.columns(3)
    c1.metric("Combinações diferentes",details.get("configuration_count",0))
    c2.metric("Resultados consolidados",details.get("run_count",0))
    c3.metric("Melhor nota média",br_num((configurations[0].get("mean_ranking_score") if configurations else None),2))
    if not configurations:
        st.info("Ainda não existem configurações oficiais salvas para esta estratégia."); return
    summary_rows=[]
    for item in configurations:
        metrics=item.get("mean_metrics") or {}
        summary_rows.append({
            "#":item.get("configuration_number"),"Parâmetros":_backtest_parameter_summary(item.get("strategy_parameters")),
            "Ativos":item.get("assets_tested"),"Nota média":item.get("mean_ranking_score"),
            "CAGR médio %":metrics.get("mean_cagr_pct"),"Sharpe médio":metrics.get("mean_sharpe_ratio"),
            "Drawdown médio %":metrics.get("mean_max_drawdown_pct"),"PF médio":metrics.get("mean_profit_factor"),
            "Acerto médio %":metrics.get("mean_win_rate_pct"),"Última análise":br_datetime(item.get("latest_analysis_at")),
        })
    st.dataframe(pd.DataFrame(summary_rows),hide_index=True,use_container_width=True,height=min(430,80+35*len(summary_rows)))
    configuration_ids=[item.get("configuration_id") for item in configurations]
    by_id={item.get("configuration_id"):item for item in configurations}
    selected_id=st.selectbox(
        "Abrir uma combinação",configuration_ids,
        format_func=lambda value: (
            f"#{by_id[value].get('configuration_number')} • "
            f"{_backtest_parameter_summary(by_id[value].get('strategy_parameters'))} • "
            f"{by_id[value].get('assets_tested')} ativo(s)"
        ),key=f"study_configuration_{strategy_id}",
    )
    selected=by_id[selected_id]; metrics=selected.get("mean_metrics") or {}
    st.markdown(f"#### Combinação #{selected.get('configuration_number')} — detalhes completos")
    left,right=st.columns(2)
    with left:
        st.markdown("**Parâmetros da estratégia**")
        parameter_rows=_flatten_backtest_config(selected.get("strategy_parameters"))
        st.dataframe(pd.DataFrame(parameter_rows),hide_index=True,use_container_width=True)
    with right:
        st.markdown("**Custos e premissas financeiras**")
        financial={**(selected.get("financial") or {}),**(selected.get("assumptions") or {})}
        st.dataframe(pd.DataFrame(_flatten_backtest_config(financial)),hide_index=True,use_container_width=True)
    st.markdown("**Filtros adicionais aplicados**")
    filter_rows=_flatten_backtest_config(selected.get("filters"))
    if filter_rows:st.dataframe(pd.DataFrame(filter_rows),hide_index=True,use_container_width=True)
    else:st.info("Nenhum filtro adicional foi aplicado nesta combinação.")
    r1,r2,r3,r4=st.columns(4)
    r1.metric("Retorno médio",br_num(metrics.get("mean_total_return_pct"),2,"%"))
    r2.metric("CAGR médio",br_num(metrics.get("mean_cagr_pct"),2,"%"))
    r3.metric("Sharpe médio",br_num(metrics.get("mean_sharpe_ratio"),2))
    r4.metric("Trades médios",br_num(metrics.get("mean_closed_trades"),1))
    st.caption(
        f"Ativos consolidados ({selected.get('assets_tested',0)}): "+", ".join(selected.get("tickers") or [])
    )
    with st.expander("Ver estrutura técnica completa desta combinação",expanded=False):
        st.json({
            "parametros_da_estrategia":selected.get("strategy_parameters") or {},
            "filtros":selected.get("filters") or {},"financeiro":selected.get("financial") or {},
            "premissas":selected.get("assumptions") or {},"status_das_amostras":selected.get("sample_status_counts") or {},
            "sinais_atuais":selected.get("signal_counts") or {},
        })


def _render_backtest_study():
    st.subheader("🏆 Estratégias mais consistentes do catálogo oficial")
    st.caption("O estudo compara a melhor configuração de cada estratégia em cada ativo e premia principalmente a recorrência entre os três primeiros.")
    result,error=api_get("/backtests/study",{"limit":5})
    if error:
        st.error(f"Não foi possível calcular o estudo: {error}"); return
    result=result or {}
    ranking=result.get("ranking") or []
    m1,m2,m3=st.columns(3)
    m1.metric("Ativos comparáveis",result.get("eligible_assets",0))
    m2.metric("Pares estratégia/ativo",result.get("eligible_strategy_asset_pairs",0))
    m3.metric("Amostra mínima por estratégia",result.get("minimum_assets_per_strategy",0))
    if not ranking:
        st.info("Ainda não há resultados oficiais suficientes. O estudo começa quando pelo menos três estratégias válidas puderem ser comparadas nos mesmos ativos.")
    else:
        rows=[]
        for item in ranking:
            rows.append({
                "Posição":item.get("position"),"Estratégia":item.get("strategy_name"),
                "Nota do estudo":item.get("study_score"),"Top 3":item.get("top3_count"),
                "Recorrência Top 3 %":item.get("top3_frequency_pct"),"1º lugares":item.get("first_places"),
                "2º lugares":item.get("second_places"),"3º lugares":item.get("third_places"),
                "Ativos testados":item.get("assets_tested"),"Cobertura %":item.get("coverage_pct"),
                "Qualidade robusta média":item.get("mean_robust_score"),"Acerto médio %":item.get("mean_win_rate_pct"),
            })
        st.caption("Clique em uma estratégia da tabela para abrir todas as combinações e variáveis usadas.")
        ranking_event=st.dataframe(
            pd.DataFrame(rows),hide_index=True,use_container_width=True,height=280,
            key="backtest_study_ranking",on_select="rerun",selection_mode="single-row",
        )
        leader=ranking[0]
        st.success(
            f"Líder atual: **{leader.get('strategy_name')}** — apareceu {leader.get('top3_count')} vez(es) "
            f"entre os três primeiros, em {leader.get('assets_tested')} ativo(s) testado(s)."
        )
        selected_rows=[]
        try:selected_rows=list(ranking_event.selection.rows or [])
        except (AttributeError,TypeError):
            if isinstance(ranking_event,dict):selected_rows=list((ranking_event.get("selection") or {}).get("rows") or [])
        if selected_rows and 0<=selected_rows[0]<len(ranking):
            _render_study_configuration_details(ranking[selected_rows[0]])
    methodology=result.get("methodology") or {}
    with st.expander("Como a pontuação foi calculada",expanded=False):
        weights=methodology.get("weights_pct") or {}
        st.write(
            f"A nota dá **{weights.get('top3_recurrence',55)}%** à recorrência no Top 3, "
            f"**{weights.get('placement_quality',25)}%** à posição obtida, "
            f"**{weights.get('robust_backtest_quality',15)}%** à qualidade robusta do backtest e "
            f"**{weights.get('catalog_coverage',5)}%** à cobertura do catálogo."
        )
        st.write("Pontos por posição: 1º = 10, 2º = 7, 3º = 5, 4º = 2 e 5º = 1.")
        for rule in methodology.get("rules") or []:st.write(f"• {rule}")
        st.caption("A taxa de acerto é exibida para consulta, mas não decide o ranking sozinha: uma taxa alta pode esconder poucas perdas muito grandes.")


def _render_news_items(items,empty_message,key_prefix):
    if not items:
        st.info(empty_message); return
    for index,item in enumerate(items):
        with st.container(border=True):
            st.write(f"**{item.get('title') or 'Notícia sem título'}**")
            details=[item.get("institution"),item.get("source"),br_datetime(item.get("published_at"))]
            st.caption(" • ".join(str(value) for value in details if value and value!="N/D"))
            tickers=item.get("mentioned_tickers") or []
            if tickers:st.caption("Ativos identificados no título: "+", ".join(tickers))
            if item.get("url"):
                context=str(key_prefix).replace("_"," ").strip().upper()
                st.link_button(f"Abrir na fonte · {context}",item["url"])


def _news_cache_feedback(cache,subject):
    status=(cache or {}).get("status")
    if status in {"queued","running"}:
        st.info(f"Atualizando {subject} em segundo plano. Você pode continuar usando todas as outras funções.")
    elif status=="failed":
        st.warning(f"A atualização de {subject} não foi concluída. O conteúdo anterior foi mantido; use o botão abaixo para tentar novamente.")
    elif status=="not_requested":
        st.info(f"A primeira atualização de {subject} será preparada automaticamente hoje.")
    finished=(cache or {}).get("finished_at")
    if finished:st.caption(f"Última atualização concluída: {br_datetime(finished)}")


@st.fragment(run_every="10s")
def _render_cached_portfolio_news(portfolio_id):
    cache,error=api_get(f"/insights/news/cache/portfolios/{portfolio_id}")
    if error:
        st.error(f"Não foi possível consultar as notícias salvas: {error}"); return
    _news_cache_feedback(cache,"as notícias da carteira")
    if st.button("Atualizar novamente hoje",use_container_width=True,key=f"refresh_portfolio_news_{portfolio_id}"):
        queued,queue_error=api_post(f"/insights/news/cache/portfolios/{portfolio_id}/refresh",timeout=15)
        if queue_error:st.error(f"A atualização não pôde ser iniciada: {queue_error}")
        elif queued.get("scheduled"):st.success("Atualização iniciada em segundo plano.")
        else:st.info("Já existe uma atualização em andamento.")
        st.rerun(scope="fragment")
    news=(cache or {}).get("data") or {}
    if news.get("truncated"):st.warning("A carteira possui mais de 50 ações; foram consideradas as 50 primeiras em ordem alfabética.")
    for asset_news in news.get("assets") or []:
        current_ticker=asset_news.get("ticker") or "Ativo"
        title=f"{current_ticker} — {asset_news.get('company_name') or 'Nome não disponível'}"
        with st.expander(title,expanded=False):
            if asset_news.get("fallback_used") and asset_news.get("items"):
                st.info("Uma busca alternativa foi usada para completar as notícias deste ativo.")
            if asset_news.get("warning") and not asset_news.get("items"):
                st.warning("As fontes externas não responderam para este ativo na última tentativa.")
            _render_news_items(
                asset_news.get("items") or [],
                f"Nenhuma notícia recente diretamente relacionada a {current_ticker} foi localizada nas fontes consultadas.",
                current_ticker,
            )


@st.fragment(run_every="10s")
def _render_cached_recommendation_news():
    category_labels={"all":"Bancos brasileiros e mundiais","brazil":"Somente bancos brasileiros","global":"Somente bancos mundiais"}
    category=st.selectbox("Instituições",list(category_labels),format_func=lambda value:category_labels[value],key="recommendation_news_category")
    cache,error=api_get("/insights/news/cache/recommendations",{"category":category})
    if error:
        st.error(f"Não foi possível consultar as recomendações salvas: {error}"); return
    _news_cache_feedback(cache,"as recomendações dos bancos")
    if st.button("Atualizar recomendações novamente hoje",use_container_width=True,key=f"refresh_recommendations_{category}"):
        queued,queue_error=api_post(f"/insights/news/cache/recommendations/refresh?category={category}",timeout=15)
        if queue_error:st.error(f"A atualização não pôde ser iniciada: {queue_error}")
        elif queued.get("scheduled"):st.success("Atualização iniciada em segundo plano.")
        else:st.info("Já existe uma atualização em andamento.")
        st.rerun(scope="fragment")
    recommendations=(cache or {}).get("data") or {}
    if recommendations.get("fallback_used") and recommendations.get("items"):
        st.info("A busca alternativa foi ativada para complementar as publicações encontradas.")
    if recommendations.get("warnings") and not recommendations.get("items"):
        st.warning("As fontes externas estavam indisponíveis na última tentativa.")
    _render_news_items(
        recommendations.get("items") or [],
        "Nenhuma publicação recente foi encontrada para este grupo de instituições.",
        f"bank_news_{category}",
    )


def _render_market_news(selected_portfolio_id=None,selected_portfolio_detail=None):
    st.subheader("📰 Notícias da carteira")
    st.caption("As notícias são atualizadas automaticamente no primeiro acesso do dia e permanecem salvas para uma navegação imediata.")
    portfolio_id=selected_portfolio_id
    detail=selected_portfolio_detail
    if portfolio_id is None:
        portfolios,error=api_get("/portfolios")
        if error:
            st.error(f"Não foi possível consultar sua carteira: {error}"); return
        portfolios=portfolios or []
        if portfolios:
            portfolio_by_id={item["id"]:item for item in portfolios}
            portfolio_id=st.selectbox(
                "Carteira",list(portfolio_by_id),
                format_func=lambda value:portfolio_by_id[value].get("name") or value,
                key="news_portfolio_id",
            )
    if portfolio_id is None:
        st.info("Cadastre uma carteira e ao menos uma ação para habilitar as notícias dos seus ativos.")
    else:
        detail_error=None
        if detail is None:detail,detail_error=api_get(f"/portfolios/{portfolio_id}")
        if detail_error:
            st.error(f"Não foi possível abrir a carteira: {detail_error}")
        else:
            positions=[item for item in (detail or {}).get("positions") or [] if item.get("asset_type")=="stock" and float(item.get("quantity") or 0)>0]
            if not positions:st.info("Esta carteira ainda não possui ações com quantidade maior que zero.")
            else:
                st.metric("Ações na carteira",len(positions))
                _render_cached_portfolio_news(portfolio_id)

    st.markdown("---")
    st.subheader("🏦 Recomendações publicadas por grandes bancos")
    st.caption("Também atualizadas em segundo plano uma vez ao dia. Os links jornalísticos não representam recomendação do aplicativo.")
    _render_cached_recommendation_news()
    st.caption("Fontes de descoberta: GDELT DOC 2.0 e Google News RSS. Títulos, datas e links pertencem às publicações indicadas. Sempre leia a matéria completa e verifique a data antes de tomar qualquer decisão.")


def _render_price_alerts():
    st.subheader("🔔 Alertas de ativos")
    st.caption("O servidor monitora os ativos mesmo quando esta página está fechada. Cada ativo usa uma vaga e pode reunir até quatro condições.")
    dashboard,error=api_get("/alerts")
    catalog,catalog_error=api_get("/alerts/catalog")
    if error or catalog_error:
        st.error(f"Não foi possível carregar os alertas: {error or catalog_error}"); return
    dashboard=dashboard or {}; catalog=catalog or {}
    active_count=int(dashboard.get("active_count") or 0); limit=int(dashboard.get("limit") or 0)
    m1,m2,m3=st.columns(3)
    m1.metric("Alertas ativos",active_count); m2.metric("Limite autorizado",limit); m3.metric("Vagas disponíveis",max(0,limit-active_count))
    st.info(f"B3: {catalog.get('b3_schedule')} Outros mercados: {catalog.get('market_schedule')}")
    st.caption(catalog.get("quote_notice") or "Cotações indicativas podem apresentar atraso.")
    if not dashboard.get("delivery_configured"):
        st.error("O envio de e-mail ainda não foi configurado pelo administrador no servidor. O cadastro será liberado quando o SMTP estiver ativo.")

    with st.expander("✉️ E-mails que receberão os alertas",expanded=False):
        st.text_input("E-mail principal do cadastro",value=dashboard.get("primary_email") or CURRENT_USER_EMAIL,disabled=True,key="alert_primary_email")
        secondary=st.text_input("Segundo e-mail (opcional)",value=dashboard.get("secondary_email") or "",placeholder="nome@exemplo.com",key="alert_secondary_email")
        email_save,email_test=st.columns(2)
        if email_save.button("Salvar e-mails",use_container_width=True,key="alert_save_emails"):
            _,save_error=api_put("/alerts/preferences",{"secondary_email":secondary or None})
            if save_error:st.error(f"Não foi possível salvar: {save_error}")
            else:st.success("E-mails atualizados."); st.rerun()
        if email_test.button("Enviar e-mail de teste",use_container_width=True,key="alert_test_email",disabled=not dashboard.get("delivery_configured")):
            with st.spinner("Enviando teste..."):
                _,test_error=api_post("/alerts/test-email",{},timeout=45)
            if test_error:st.error(f"Falha no teste: {test_error}")
            else:st.success("E-mail de teste enviado.")

    with st.expander("➕ Cadastrar ou atualizar alerta",expanded=not bool(dashboard.get("alerts"))):
        scope_label=st.radio("Tipo de ativo",["Ativo da B3","Ativo do Painel de Mercado"],horizontal=True,key="alert_scope")
        market_scope="b3" if scope_label=="Ativo da B3" else "market"
        options=catalog.get(market_scope) or []; by_key={str(item.get("key")):item for item in options}
        selected_symbol=None
        if not by_key:
            st.warning("Não há ativos elegíveis carregados nesta categoria.")
        else:
            selected_symbol=st.selectbox("Ativo",list(by_key),format_func=lambda key:f"{key} — {by_key[key].get('label') or key}",key=f"alert_symbol_{market_scope}")
        existing_by_symbol={str(item.get("symbol")):item for item in (dashboard.get("alerts") or [])}
        existing=existing_by_symbol.get(selected_symbol) or {}
        if existing:st.caption(f"Este ativo já possui um alerta ({existing.get('status')}). Ao salvar, as condições serão substituídas e reativadas.")
        permissions=dashboard.get("permissions") or {}; c1,c2=st.columns(2); values={}
        if permissions.get("price_above"):
            values["price_above"]=c1.number_input("Preço subindo: atingir ou ultrapassar",min_value=0.0,value=float(existing.get("price_above")) if existing.get("price_above") is not None else None,step=0.01,format="%.4f",placeholder="Em branco = não usar",key=f"alert_above_{selected_symbol}")
        if permissions.get("price_below"):
            values["price_below"]=c1.number_input("Preço caindo: atingir ou ficar abaixo",min_value=0.0,value=float(existing.get("price_below")) if existing.get("price_below") is not None else None,step=0.01,format="%.4f",placeholder="Em branco = não usar",key=f"alert_below_{selected_symbol}")
        if permissions.get("change_positive_pct"):
            values["change_positive_pct"]=c2.number_input("Variação positiva desde o fechamento (%)",min_value=0.0,value=float(existing.get("change_positive_pct")) if existing.get("change_positive_pct") is not None else None,step=0.1,format="%.2f",placeholder="Ex.: 3,00",key=f"alert_pos_{selected_symbol}")
        if permissions.get("change_negative_pct"):
            values["change_negative_pct"]=c2.number_input("Variação negativa desde o fechamento (%)",min_value=0.0,value=float(existing.get("change_negative_pct")) if existing.get("change_negative_pct") is not None else None,step=0.1,format="%.2f",placeholder="Informe o módulo: 3,00",key=f"alert_neg_{selected_symbol}")
        if not any(permissions.values()):st.warning("O administrador ainda não liberou nenhum tipo de condição para sua conta.")
        if st.button("Ativar este alerta",type="primary",use_container_width=True,key="alert_save",disabled=not selected_symbol or not dashboard.get("delivery_configured") or not any(permissions.values())):
            _,save_error=api_post("/alerts",{"market_scope":market_scope,"symbol":selected_symbol,**values})
            if save_error:st.error(f"Não foi possível ativar: {save_error}")
            else:st.success(f"Alerta de {selected_symbol} ativado."); st.rerun()

    st.markdown("#### Alertas cadastrados")
    alerts=dashboard.get("alerts") or []
    if not alerts:
        st.info("Nenhum alerta cadastrado.")
    else:
        alert_rows=[]
        for item in alerts:
            conditions=[]
            if item.get("price_above") is not None:conditions.append(f"Preço ≥ {item['price_above']}")
            if item.get("price_below") is not None:conditions.append(f"Preço ≤ {item['price_below']}")
            if item.get("change_positive_pct") is not None:conditions.append(f"Variação ≥ +{item['change_positive_pct']}%")
            if item.get("change_negative_pct") is not None:conditions.append(f"Variação ≤ -{item['change_negative_pct']}%")
            alert_rows.append({"Ativo":item.get("symbol"),"Nome":item.get("display_name"),"Situação":{"active":"Ativo","triggered":"Disparado","disabled":"Desativado"}.get(item.get("status"),item.get("status")),"Condições":" • ".join(conditions),"Último preço":item.get("last_price"),"Última variação %":item.get("last_change_pct"),"Última verificação":br_datetime(item.get("last_checked_at"))})
        st.dataframe(pd.DataFrame(alert_rows),hide_index=True,use_container_width=True)
        selected_alert=st.selectbox("Gerenciar alerta",alerts,format_func=lambda item:f"{item.get('symbol')} — {item.get('display_name')} ({item.get('status')})",key="alert_manage_selected")
        desired="disabled" if selected_alert.get("status")=="active" else "active"; label="Desativar alerta" if desired=="disabled" else "Reativar alerta"
        if st.button(label,key="alert_toggle",use_container_width=True):
            _,toggle_error=api_patch(f"/alerts/{selected_alert['id']}/status",{"status":desired})
            if toggle_error:st.error(f"Não foi possível alterar: {toggle_error}")
            else:st.success("Situação atualizada."); st.rerun()

    st.markdown("#### Histórico de alertas enviados")
    history=dashboard.get("history") or []
    if not history:
        st.info("Nenhum alerta foi disparado até agora.")
    else:
        labels={"price_above":"Preço subindo","price_below":"Preço caindo","change_positive_pct":"Variação positiva","change_negative_pct":"Variação negativa"}; history_rows=[]
        for item in history:
            observed=item.get("observed") or {}
            history_rows.append({"Ativo":item.get("symbol"),"Condição":" • ".join(labels.get(rule,rule) for rule in item.get("triggered_rules") or []),"Preço":observed.get("price"),"Variação %":observed.get("change_pct"),"Cotação":br_datetime(observed.get("quote_at")),"E-mails":"; ".join(item.get("recipients") or []),"Envio":{"sent":"Enviado","pending":"Aguardando/repetindo","failed":"Falhou"}.get(item.get("delivery_status"),item.get("delivery_status")),"Enviado em":br_datetime(item.get("sent_at"))})
        st.dataframe(pd.DataFrame(history_rows),hide_index=True,use_container_width=True)


@st.fragment(run_every="15s")
def _render_official_batch_history(
    github_token: str,
    github_repository: str,
    github_workflow: str,
    github_ref: str,
):
    st.markdown("#### Histórico dos lotes oficiais")
    st.caption("O andamento é atualizado automaticamente a cada 15 segundos enquanto esta página estiver aberta.")
    notice=st.session_state.pop("official_batch_action_notice",None)
    if notice:
        notice_kind,notice_message=notice
        getattr(st,notice_kind,st.info)(notice_message)
    if st.button("↻ Atualizar agora",key="refresh_official_batch_progress",use_container_width=True):
        st.rerun(scope="fragment")

    jobs,jobs_error=api_get("/backtests/batch/jobs",{"limit":20})
    github_runs=[]
    github_runs_error=None
    if github_token:
        try:
            github_runs=list_workflow_runs(
                token=github_token,repository=github_repository,workflow=github_workflow,
                branch=github_ref,limit=20,
            )
        except GitHubActionsError as exc:
            github_runs_error=str(exc)
    if github_runs_error:
        st.warning(f"Não foi possível consultar o andamento no GitHub: {github_runs_error}")
    elif github_runs:
        status_labels={"queued":"Na fila","in_progress":"Executando","completed":"Finalizado"}
        conclusion_labels={
            "success":"Concluído","failure":"Falhou","cancelled":"Cancelado",
            "timed_out":"Tempo esgotado","action_required":"Exige intervenção",
            "skipped":"Ignorado","neutral":"Neutro","stale":"Interrompido",
        }
        run_rows=[]
        for run in github_runs[:10]:
            situation=(conclusion_labels.get(run.get("conclusion")) if run.get("conclusion") else status_labels.get(run.get("status"))) or (run.get("status") or "Desconhecido")
            run_rows.append({
                "Execução":f"#{run.get('run_number')}","Pedido":run.get("display_title"),
                "Situação":situation,"Solicitado em":br_datetime(run.get("created_at")),
                "Atualizado em":br_datetime(run.get("updated_at")),"Detalhes":run.get("html_url"),
            })
        st.caption("Andamento informado diretamente pelo GitHub")
        st.dataframe(
            pd.DataFrame(run_rows),hide_index=True,use_container_width=True,
            column_config={"Detalhes":st.column_config.LinkColumn("Detalhes",display_text="Abrir")},
        )

    if jobs_error:
        st.warning(f"Não foi possível consultar as execuções em lote: {jobs_error}")
        return
    if not jobs:
        st.info("Nenhuma execução oficial foi registrada ainda.")
        return

    def matched_run(item):
        return next((
            run for run in github_runs
            if str(item.get("id")) in str(run.get("display_title") or "")
        ),None)

    terminal_failures={"failure","timed_out","action_required","stale"}
    for item in jobs:
        matched=matched_run(item)
        if not matched or item.get("status") not in {"queued","running"}:
            continue
        if matched.get("conclusion")=="cancelled":
            updated,_=api_patch(f"/backtests/batch/jobs/{item['id']}/cancelled",{
                "reason":"A execução correspondente foi cancelada no GitHub.",
                "details":{"run_url":matched.get("html_url"),"run_number":matched.get("run_number")},
            })
            if updated:item.update(updated)
        elif matched.get("conclusion") in terminal_failures:
            updated,_=api_patch(f"/backtests/batch/jobs/{item['id']}/failed",{
                "code":"github_workflow_failed",
                "message":f"O processamento no GitHub terminou como {matched.get('conclusion')}.",
                "details":{"run_url":matched.get("html_url"),"run_number":matched.get("run_number")},
            })
            if updated:item.update(updated)
        elif matched.get("conclusion")=="success":
            processed=int(item.get("processed_assets") or 0)
            total=int(item.get("total_assets") or len(item.get("tickers") or []))
            if processed < total:
                updated,_=api_patch(f"/backtests/batch/jobs/{item['id']}/failed",{
                    "code":"secure_delivery_missing",
                    "message":"O GitHub terminou, mas nem todos os resultados chegaram ao banco privado da Oracle.",
                    "details":{"run_url":matched.get("html_url"),"processed_assets":processed,"total_assets":total},
                })
                if updated:item.update(updated)

    batch_status_labels={
        "queued":"Na fila","running":"Executando","completed":"Concluído",
        "completed_with_errors":"Concluído com falhas","failed":"Falhou","cancelled":"Cancelado",
    }
    source_labels={
        "site":"Painel administrativo","manual":"GitHub manual","scheduled":"Agendado",
        "retry":"Repetição de falhas",
    }
    job_rows=[{
        "Pedido":str(item.get("id"))[:8],"Criado em":br_datetime(item.get("created_at")),
        "Origem":source_labels.get(item.get("source"),item.get("source")),
        "Situação":batch_status_labels.get(item.get("status"),item.get("status")),
        "Ativos":len(item.get("tickers") or []),"Processados":item.get("processed_assets",0),
        "Progresso":f"{float(item.get('progress_pct') or 0):.1f}%",
        "Último ativo":item.get("last_ticker"),"Combinações/ativo":item.get("max_combinations"),
        "Concluídos":item.get("completed_runs"),"Falhas":item.get("failed_runs"),
        "Última atualização":br_datetime(item.get("last_update_at")),
        "Início":br_datetime(item.get("started_at")),"Fim":br_datetime(item.get("finished_at")),
    } for item in jobs]
    st.dataframe(pd.DataFrame(job_rows),hide_index=True,use_container_width=True)

    active_jobs=[item for item in jobs if item.get("status") in {"queued","running"}]
    for item in active_jobs:
        processed=int(item.get("processed_assets") or 0)
        total=max(1,int(item.get("total_assets") or len(item.get("tickers") or []) or 1))
        progress=max(0.0,min(1.0,float(item.get("progress_pct") or 0)/100.0))
        short_id=str(item.get("id"))[:8]
        with st.container(border=True):
            st.markdown(f"**Pedido {short_id} • {processed} de {total} ativo(s)**")
            st.progress(
                progress,
                text=(
                    f"{float(item.get('progress_pct') or 0):.1f}% recebido pela Oracle"
                    + (f" • último: {item.get('last_ticker')}" if item.get("last_ticker") else "")
                ),
            )
            p1,p2,p3=st.columns(3)
            p1.metric("Resultados concluídos",int(item.get("completed_runs") or 0))
            p2.metric("Falhas isoladas",int(item.get("failed_runs") or 0))
            p3.metric("Ativos pendentes",len(item.get("pending_tickers") or []))
            confirm=st.checkbox(
                "Confirmo que desejo interromper este lote",
                key=f"confirm_cancel_batch_{item['id']}",
            )
            if st.button(
                "■ Cancelar este lote",key=f"cancel_batch_{item['id']}",
                disabled=not confirm,use_container_width=True,
            ):
                refresh_after_action=False
                matched=matched_run(item)
                github_cancelled=True
                github_details={}
                if matched and matched.get("status") in {"queued","in_progress"}:
                    try:
                        cancellation=cancel_workflow_run(
                            token=github_token,run_id=matched.get("id"),repository=github_repository,
                        )
                    except GitHubActionsError as exc:
                        github_cancelled=False
                        st.error(f"O GitHub não confirmou o cancelamento: {exc}")
                    else:
                        github_details={"run_url":matched.get("html_url"),"run_number":matched.get("run_number")}
                        if cancellation.get("already_finished"):
                            github_cancelled=False
                            st.warning("A execução terminou antes do cancelamento. Aguarde a atualização do resultado.")
                elif matched and matched.get("status")=="completed":
                    github_cancelled=False
                    st.warning("A execução já terminou no GitHub. Aguarde a atualização do resultado.")
                if github_cancelled:
                    cancelled,cancel_error=api_patch(f"/backtests/batch/jobs/{item['id']}/cancelled",{
                        "reason":"Cancelamento confirmado pelo administrador no painel.",
                        "details":github_details,
                    })
                    if cancel_error:
                        st.error(f"O pedido de cancelamento não foi concluído: {cancel_error}")
                    elif cancelled:
                        st.session_state["official_batch_action_notice"]=(
                            "success",f"Pedido {short_id} cancelado. Resultados já recebidos foram preservados.",
                        )
                        refresh_after_action=True
                if refresh_after_action:
                    st.rerun(scope="fragment")

    retryable=[
        item for item in jobs
        if item.get("status") in {"failed","cancelled","completed_with_errors"}
        and item.get("retry_tickers")
    ]
    if retryable:
        with st.expander("Repetir somente ativos com falha ou pendentes",expanded=False):
            st.caption("Cada repetição cria um novo pedido e não recalcula os ativos que já terminaram corretamente.")
            for item in retryable:
                retry_tickers=list(item.get("retry_tickers") or [])
                short_id=str(item.get("id"))[:8]
                failed_count=len(item.get("failed_tickers") or [])
                pending_count=len(item.get("pending_tickers") or [])
                r1,r2=st.columns([3,2])
                r1.write(
                    f"**Pedido {short_id}** • {len(retry_tickers)} ativo(s) para repetir "
                    f"({failed_count} com falha; {pending_count} pendente(s))"
                )
                if r2.button(
                    f"Repetir {len(retry_tickers)} ativo(s)",
                    key=f"retry_batch_{item['id']}",use_container_width=True,disabled=not bool(github_token),
                ):
                    refresh_after_action=False
                    retry_job,retry_error=api_post(f"/backtests/batch/jobs/{item['id']}/retry")
                    if retry_error:
                        st.error(f"A repetição não pôde ser registrada: {retry_error}")
                    elif not retry_job.get("dispatch_required",True):
                        st.warning(f"O pedido {retry_job['id'][:8]} já está na fila ou em execução.")
                    else:
                        try:
                            dispatched=dispatch_official_backtests(
                                token=github_token,tickers=retry_job.get("tickers") or retry_tickers,
                                repository=github_repository,workflow=github_workflow,ref=github_ref,
                                max_combinations=retry_job.get("max_combinations") or 200,
                                job_id=retry_job["id"],
                            )
                        except (GitHubActionsError,ValueError) as exc:
                            api_patch(f"/backtests/batch/jobs/{retry_job['id']}/failed",{
                                "code":"github_retry_dispatch_failed","message":str(exc),
                            })
                            st.error(f"A repetição foi registrada, mas o GitHub não a aceitou: {exc}")
                        else:
                            st.session_state["official_batch_action_notice"]=(
                                "success",
                                f"Novo pedido {retry_job['id'][:8]} enviado para {len(dispatched['tickers'])} ativo(s).",
                            )
                            refresh_after_action=True
                    if refresh_after_action:
                        st.rerun(scope="fragment")

    jobs_with_errors=[item for item in jobs if item.get("errors")]
    if jobs_with_errors:
        with st.expander("Ver diagnóstico dos lotes com falhas",expanded=False):
            for item in jobs_with_errors[:5]:
                st.markdown(f"**Pedido {str(item.get('id'))[:8]}**")
                for error in (item.get("errors") or [])[-5:]:
                    message=error.get("message") or error.get("error") or "Falha sem descrição"
                    ticker=error.get("ticker")
                    st.write(f"- {ticker + ': ' if ticker else ''}{message}")


def _render_official_backtest_admin():
    st.subheader("🧪 Backtests manuais e catálogo oficial")
    st.write("Esta área é exclusiva do proprietário e concentra as execuções administrativas.")
    individual,batch=st.tabs(["Backtest individual","Lote oficial completo"])
    with individual:
        st.write("Use a tela normal de Backtests para executar uma estratégia, comparar estratégias ou testar uma cesta. O resultado fica salvo no seu histórico.")
        st.button("Ir para Backtests individuais",type="primary",key="admin_go_backtests",on_click=_navigate_to,args=("backtests",))
    with batch:
        st.write("O lote oficial testa as configurações do catálogo em até 100 ativos. Escolha os códigos e envie o processamento diretamente por esta tela.")
        st.caption("O GitHub faz apenas os cálculos. Os resultados retornam em pacotes autenticados para a Oracle; o PostgreSQL permanece privado e não é exposto à internet.")
        st.info("Execução automática: todos os sábados, às 00h01 de Brasília, usando as 50 ações do filtro Padrão.")
        github_token=_private_setting("GITHUB_ACTIONS_TOKEN")
        callback_token=_private_setting("BACKTEST_CALLBACK_TOKEN")
        callback_ready=len(str(callback_token or "").strip())>=32
        github_repository=_private_setting("GITHUB_ACTIONS_REPOSITORY","andrelbr22/invest")
        github_workflow=_private_setting("GITHUB_BACKTEST_WORKFLOW","backtests-semanais.yml")
        github_ref=_private_setting("GITHUB_ACTIONS_REF","main")
        if not github_token:
            st.warning("A conexão segura com o GitHub ainda não foi configurada. Adicione GITHUB_ACTIONS_TOKEN aos Secrets do aplicativo.")
        if not callback_ready:
            st.error(
                "A credencial que traz os resultados de volta ao site ainda não está configurada. "
                "Adicione BACKTEST_CALLBACK_TOKEN aos Secrets do servidor e, com o mesmo valor, "
                "aos Repository secrets do GitHub. Novos lotes ficarão bloqueados até isso ser concluído."
            )
        default_rows,default_error=api_get("/screen/db/stocks/default",{"limit":50,"offset":0})
        stock_rows,stock_error=api_get("/assets",{"asset_type":"stock","limit":1200,"offset":0})
        if default_error or stock_error:
            st.error(f"Não foi possível montar a lista de ativos: {default_error or stock_error}")
        else:
            stock_rows=stock_rows or []
            default_tickers=[row.get("ticker") for row in (default_rows or []) if row.get("ticker")]
            catalog={row.get("ticker"):row for row in stock_rows if row.get("ticker")}
            available=sorted(catalog)
            defaults=[ticker for ticker in default_tickers if ticker in catalog][:50]
            selection_key="official_batch_selected_tickers"
            market_selection=st.session_state.get("market_backtest_selection_stock") or {}
            market_tickers=[ticker for ticker in (market_selection.get("tickers") or []) if ticker in catalog][:100]
            market_signature=str(market_selection.get("signature") or "")
            if market_signature and st.session_state.get("official_batch_market_signature_applied")!=market_signature:
                st.session_state[selection_key]=market_tickers
                st.session_state["official_batch_selection_source"]={
                    "label":market_selection.get("label") or "Mercado e análise","count":len(market_tickers),
                }
                st.session_state["official_batch_market_signature_applied"]=market_signature
            if selection_key not in st.session_state:
                st.session_state[selection_key]=market_tickers or defaults
                st.session_state["official_batch_selection_source"]={
                    "label":market_selection.get("label") if market_tickers else "Filtro Padrão",
                    "count":len(market_tickers or defaults),
                }
            current_selection=[ticker for ticker in st.session_state.get(selection_key,defaults) if ticker in catalog][:100]
            st.session_state[selection_key]=current_selection
            source=st.session_state.get("official_batch_selection_source") or {}
            source_label=source.get("label") or "Seleção manual"
            st.success(f"Seleção carregada: **{source_label}** • **{len(current_selection)} ativo(s)**")
            b1,b2=st.columns(2)
            if market_tickers:
                b1.button(
                    f"Usar os {len(market_tickers)} da tela Mercado e análise",
                    key="official_use_market_selection",use_container_width=True,
                    on_click=_set_official_batch_selection,
                    args=(market_tickers,market_selection.get("label") or "Mercado e análise"),
                )
            else:
                b1.button("Abra Mercado e análise para trazer a lista filtrada",disabled=True,use_container_width=True)
            b2.button(
                f"Restaurar filtro Padrão ({len(defaults)})",key="official_use_default_selection",
                use_container_width=True,on_click=_set_official_batch_selection,args=(defaults,"Filtro Padrão"),
            )
            st.caption("O limite por pedido é de 100 ativos. Você ainda pode retirar ou acrescentar códigos manualmente abaixo.")
            with st.form("official_batch_dispatch_form"):
                selected=st.multiselect(
                    "Ativos que serão processados",
                    available,
                    key=selection_key,
                    max_selections=100,
                    format_func=lambda ticker:f"{ticker} — {catalog[ticker].get('name') or 'Sem nome'}",
                    help="Recebe a tabela filtrada de Mercado e análise. Você pode retirar ou acrescentar códigos antes de enviar.",
                )
                submitted=st.form_submit_button(
                    "▶ Gerar backtests dos ativos selecionados",
                    type="primary",use_container_width=True,disabled=not bool(github_token) or not callback_ready or not bool(selected),
                )
            if submitted:
                job,job_error=api_post("/backtests/batch/jobs",{
                    "tickers":selected,"max_combinations":200,
                })
                if job_error:
                    st.error(f"O pedido não pôde ser registrado no banco: {job_error}")
                elif not job.get("dispatch_required",True):
                    st.warning(
                        f"O pedido {job['id'][:8]} já estava na fila ou em execução. "
                        "Nenhum processamento duplicado foi enviado ao GitHub."
                    )
                else:
                    try:
                        dispatched=dispatch_official_backtests(
                            token=github_token,tickers=selected,repository=github_repository,
                            workflow=github_workflow,ref=github_ref,max_combinations=200,
                            job_id=job["id"],
                        )
                    except (GitHubActionsError,ValueError) as exc:
                        api_patch(f"/backtests/batch/jobs/{job['id']}/failed",{
                            "code":"github_dispatch_failed","message":str(exc),
                        })
                        st.error(f"O pedido {job['id'][:8]} foi registrado, mas o GitHub não o aceitou: {exc}")
                    else:
                        st.success(
                            f"Pedido {job['id'][:8]} registrado e enviado. "
                            f"Acompanhe abaixo os backtests de {len(dispatched['tickers'])} ativo(s)."
                        )
                        st.link_button("Acompanhar processamento no GitHub",dispatched["actions_url"],use_container_width=True)
        st.caption("As credenciais ficam guardadas apenas nos Secrets e nunca são mostradas aos usuários ou gravadas nos resultados.")

    _render_official_batch_history(
        github_token,
        github_repository,
        github_workflow,
        github_ref,
    )


def _render_users_admin():
    st.subheader("🔐 Usuários e permissões")
    st.caption("Somente a conta proprietária pode alterar estas liberações. Novas contas entram como visitantes: Mercado básico em modo somente leitura.")
    users,err=api_get("/access/users")
    if err:
        st.error(f"Não foi possível carregar os usuários: {err}"); return
    users=users or []
    if not users:
        st.info("Nenhum outro usuário entrou no aplicativo ainda."); return

    table=[]
    for user in users:
        table.append({
            "E-mail":user.get("email"),"Nome":user.get("display_name"),"Situação":user.get("status"),"Perfil":user.get("role"),
            "Mercado":user.get("can_view_market"),"Filtros avançados":user.get("can_use_advanced_filters"),
            "Filtros pessoais":user.get("custom_filter_limit",0),
            "Ver carteira":user.get("can_view_portfolio"),"Alterar carteira":user.get("can_write_portfolio"),
            "Ver backtests":user.get("can_view_backtests"),"Executar backtests":user.get("can_run_backtests"),
            "Atualizar sinais":user.get("can_refresh_backtest_signals"),
            "Estudo dos backtests":user.get("can_view_backtest_studies"),
            "Notícias na carteira":user.get("can_view_news_insights"),
            "Alertas":user.get("can_use_price_alerts"),
            "Limite de alertas":user.get("alert_asset_limit",0),
            "Atualizar banco":user.get("can_sync_market"),"Último acesso":user.get("last_seen_at"),
        })
    st.dataframe(pd.DataFrame(table),hide_index=True,use_container_width=True)

    editable=[u for u in users if not u.get("is_owner")]
    if not editable:
        st.info("Quando outra conta Google entrar, ela aparecerá aqui para você autorizar."); return
    by_email={u["email"]:u for u in editable}
    selected=st.selectbox("Usuário para configurar",sorted(by_email),format_func=lambda email:f"{by_email[email].get('display_name') or 'Sem nome'} — {email}")
    current=by_email[selected]
    status_options=["pending","approved","blocked"]
    status_labels={"pending":"Pendente","approved":"Aprovado","blocked":"Bloqueado"}
    role_options=["visitor","member","admin"]
    role_labels={"visitor":"Visitante","member":"Membro","admin":"Administrador sem gestão de usuários"}
    with st.form(f"access_policy_{selected}"):
        a,b=st.columns(2)
        status=a.selectbox("Situação da conta",status_options,index=status_options.index(current.get("status","pending")),format_func=lambda value:status_labels[value])
        role=b.selectbox("Nome do perfil",role_options,index=role_options.index(current.get("role","visitor")),format_func=lambda value:role_labels[value])
        st.markdown("#### Permissões individuais")
        c1,c2=st.columns(2)
        view_market=c1.checkbox("Ver Mercado e filtros básicos",value=bool(current.get("can_view_market")))
        advanced=c1.checkbox("Usar filtros avançados",value=bool(current.get("can_use_advanced_filters")))
        view_portfolio=c1.checkbox("Ver Carteira",value=bool(current.get("can_view_portfolio")))
        write_portfolio=c1.checkbox("Alterar e salvar Carteira",value=bool(current.get("can_write_portfolio")))
        view_backtests=c2.checkbox("Ver Backtests e históricos",value=bool(current.get("can_view_backtests")))
        run_backtests=c2.checkbox("Executar novos Backtests",value=bool(current.get("can_run_backtests")))
        refresh_signals=c2.checkbox("Atualizar os sinais dos backtests oficiais",value=bool(current.get("can_refresh_backtest_signals")))
        backtest_studies=c2.checkbox("Ver estudo e ranking dos backtests",value=bool(current.get("can_view_backtest_studies")))
        news_insights=c2.checkbox("Ver notícias da carteira e recomendações de bancos",value=bool(current.get("can_view_news_insights")))
        sync_market=c2.checkbox("Atualizar dados do Mercado no banco",value=bool(current.get("can_sync_market")))
        custom_filter_limit=c2.selectbox(
            "Quantidade de filtros personalizados",[0,1,2,3],
            index=max(0,min(3,int(current.get("custom_filter_limit") or 0))),
            help="Zero bloqueia o uso. De 1 a 3 define quantas configurações próprias esta conta pode manter salvas.",
        )
        st.markdown("#### Alertas por e-mail")
        st.caption("Cada ativo ocupa uma vaga e pode reunir as condições autorizadas abaixo.")
        alert_enabled=st.checkbox(
            "Permitir alertas de ativos",
            value=bool(current.get("can_use_price_alerts")),
        )
        alert_limits=[0,1,3,5,10]
        current_alert_limit=int(current.get("alert_asset_limit") or 0)
        if current_alert_limit not in alert_limits:current_alert_limit=0
        alert_limit=st.selectbox(
            "Máximo de ativos monitorados",
            alert_limits,index=alert_limits.index(current_alert_limit),
            disabled=not alert_enabled,
            help="Um ativo é um alerta, mesmo quando possui duas, três ou quatro condições.",
        )
        al1,al2=st.columns(2)
        alert_price_above=al1.checkbox(
            "Preço subindo até o valor definido",value=bool(current.get("can_alert_price_above")),disabled=not alert_enabled,
        )
        alert_price_below=al1.checkbox(
            "Preço caindo até o valor definido",value=bool(current.get("can_alert_price_below")),disabled=not alert_enabled,
        )
        alert_change_positive=al2.checkbox(
            "Variação percentual positiva",value=bool(current.get("can_alert_change_positive")),disabled=not alert_enabled,
        )
        alert_change_negative=al2.checkbox(
            "Variação percentual negativa",value=bool(current.get("can_alert_change_negative")),disabled=not alert_enabled,
        )
        st.caption("Nenhum usuário recebe permissão para administrar contas. Essa função permanece exclusiva do proprietário.")
        save=st.form_submit_button("Salvar permissões",type="primary")
    if save:
        payload={
            "status":status,"role":role,"can_view_market":view_market,"can_use_advanced_filters":advanced,
            "can_view_portfolio":view_portfolio,"can_write_portfolio":write_portfolio,
            "can_view_backtests":view_backtests,"can_run_backtests":run_backtests,
            "can_refresh_backtest_signals":refresh_signals,"can_view_backtest_studies":backtest_studies,
            "can_view_news_insights":news_insights,"can_sync_market":sync_market,
            "custom_filter_limit":custom_filter_limit,
            "can_use_price_alerts":alert_enabled and alert_limit>0,
            "alert_asset_limit":alert_limit if alert_enabled else 0,
            "can_alert_price_above":alert_enabled and alert_price_above,
            "can_alert_price_below":alert_enabled and alert_price_below,
            "can_alert_change_positive":alert_enabled and alert_change_positive,
            "can_alert_change_negative":alert_enabled and alert_change_negative,
        }
        _,save_err=api_put(f"/access/users/{selected}",payload)
        if save_err:st.error(f"Não foi possível salvar: {save_err}")
        else:st.success("Permissões atualizadas."); st.rerun()


def render_access_admin():
    st.title("⚙️ Administração")
    st.caption("Central exclusiva do proprietário. Novas funções administrativas poderão ser acrescentadas aqui nas próximas versões.")
    backtests_tab,users_tab=st.tabs(["🧪 Backtests oficiais","🔐 Usuários e permissões"])
    with backtests_tab:_render_official_backtest_admin()
    with users_tab:_render_users_admin()


health,err=api_get("/health")
if err:
    st.error("Não consegui falar com o Investment Engine. Ligue a API primeiro.")
    st.code("python -m uvicorn investment_engine.api.app:app --host 127.0.0.1 --port 8000")
    st.stop()
registered=None; registration_err=None
if st.session_state.get("access_registered_email") != CURRENT_USER_EMAIL:
    registered,registration_err=api_post("/access/register",{"display_name":CURRENT_USER_NAME})
    if not registration_err:st.session_state.access_registered_email=CURRENT_USER_EMAIL
access,access_err=api_get("/access/me")
if registration_err or access_err:
    st.error(f"Não foi possível validar as permissões desta conta: {registration_err or access_err}")
    st.stop()
PERMISSIONS=access or registered or {}
if can("can_view_market"):
    daily_market_key=f"daily_market_dashboard_requested_{date.today().isoformat()}"
    if not st.session_state.get(daily_market_key):
        _market_result,_market_error=api_post("/market-dashboard/ensure",timeout=15)
        st.session_state[daily_market_key]=True
        if _market_error:st.session_state["daily_market_dashboard_error"]=_market_error
if can("can_view_news_insights"):
    daily_news_key=f"daily_news_refresh_requested_{date.today().isoformat()}"
    if not st.session_state.get(daily_news_key):
        # This request only places work in the API background queue. It does not
        # wait for external news sources and therefore cannot freeze the page.
        _daily_news,_daily_news_error=api_post("/insights/news/refresh-daily",timeout=15)
        st.session_state[daily_news_key]=True
        if _daily_news_error:
            st.session_state["daily_news_refresh_error"]=_daily_news_error
module_labels={
    "dashboard":"🌐 Painel de Mercado",
    "market":"📊 Mercado e análise",
    "portfolio":"💼 Minha carteira",
    "backtests":"🧪 Backtests",
    "access":"⚙️ Administração",
}
modules=[]
if can("can_view_market"):modules.extend(["dashboard","market"])
if can("can_view_portfolio"):modules.append("portfolio")
if can("can_view_backtests"):modules.append("backtests")
if PERMISSIONS.get("is_owner"):modules.append("access")
if not modules:
    st.title("Acesso aguardando autorização")
    st.info("Sua conta Google foi identificada, mas ainda não possui menus liberados. Solicite ao proprietário a autorização necessária.")
    st.stop()
_render_sidebar_identity(health)
if st.session_state.get("main_navigation") not in modules:st.session_state["main_navigation"]=modules[0]
module=st.sidebar.radio("Escolha uma área",modules,index=0,format_func=lambda value:module_labels[value],label_visibility="collapsed",key="main_navigation")
st.sidebar.markdown('<div class="ie-sidebar-footer">Ambiente privado e protegido</div>',unsafe_allow_html=True)
previous_module=st.session_state.get("_previous_main_navigation")
if module=="market" and previous_module!="market":
    _initialize_market_panel()
st.session_state["_previous_main_navigation"]=module
if module=="dashboard":render_market_dashboard()
elif module=="market":render_market()
elif module=="portfolio":render_portfolio()
elif module=="backtests":render_backtests()
else:render_access_admin()
st.markdown("---")
st.caption("Formação do Investidor • Investment Engine V1.14.2. Ferramenta educacional de análise e simulação; não constitui recomendação de investimento.")
