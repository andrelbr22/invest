import math
from datetime import datetime
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Screener Avançado V1.3", layout="wide", initial_sidebar_state="expanded")

DEFAULT_API = "http://127.0.0.1:8000"
API = st.sidebar.text_input("Investment Engine API", DEFAULT_API)


def api_get(path, params=None):
    try:
        r = requests.get(f"{API}{path}", params=params, timeout=60)
        r.raise_for_status()
        return r.json(), None
    except requests.RequestException as exc:
        return None, str(exc)


def br_money(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "N/D"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def br_num(v, digits=2, suffix=""):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "N/D"
    return f"{v:.{digits}f}".replace(".", ",") + suffix


st.title("📊 Screener Avançado de Investimentos — V1.3.5")
st.caption("Primeira versão visual integrada ao Investment Engine. A interface consulta a API; os dados e cálculos ficam no motor.")

health, health_err = api_get("/health")
if health_err:
    st.error("Não consegui falar com o Investment Engine. Verifique se a API está ligada com o comando uvicorn.")
    st.code("uvicorn investment_engine.api.app:app --reload")
    st.stop()

st.sidebar.success(f"Motor online • versão {health.get('version','?')}")
market = st.sidebar.radio("Mercado", ["Ações", "FIIs"])
strategy_label = st.sidebar.selectbox("Estratégia", ["Padrão", "CNPI", "ALB"])
strategy = {"Padrão": "default", "CNPI": "cnpi", "ALB": "alb"}[strategy_label]
limit = st.sidebar.slider("Máximo de resultados", 10, 200, 50, 10)

asset_type_api = "stock" if market == "Ações" else "fii"
asset_catalog, asset_catalog_err = api_get("/assets", {"asset_type": asset_type_api, "limit": 500, "offset": 0})
asset_catalog = asset_catalog or []

endpoint = f"/screen/db/stocks/{strategy}" if market == "Ações" else f"/screen/db/fiis/{strategy}"
rows, err = api_get(endpoint, {"limit": limit})
if err:
    st.error(f"Não foi possível carregar o screener: {err}")
    st.stop()

df = pd.DataFrame(rows or [])

search = st.sidebar.text_input("Filtrar ticker no screener", placeholder="Ex.: BBAS3").strip().upper()
if search and not df.empty and "ticker" in df:
    df = df[df["ticker"].astype(str).str.contains(search, case=False, regex=False)]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Ativos encontrados", len(df))
if not df.empty:
    c2.metric("ALB médio", br_num(pd.to_numeric(df.get("alb_score"), errors="coerce").mean(), 1))
    c3.metric("Value médio", br_num(pd.to_numeric(df.get("value_score"), errors="coerce").mean(), 1))
    c4.metric("Data Quality médio", br_num(pd.to_numeric(df.get("data_quality_score"), errors="coerce").mean(), 1, "%"))

st.subheader(f"{market} • Estratégia {strategy_label}")
if df.empty:
    st.info("Nenhum ativo encontrado. Se acabou de instalar, rode primeiro a ingestão e o cálculo de scores.")
else:
    rename = {
        "ticker": "Ticker", "name": "Nome", "segment": "Segmento", "price": "Preço",
        "pe": "P/L", "pbv": "P/VP", "dy": "DY %", "roe": "ROE %",
        "ffo_yield": "FFO Yield %", "cap_rate": "Cap Rate %", "vacancy": "Vacância %",
        "daily_liquidity": "Liquidez", "quality_score": "Quality", "value_score": "Value",
        "growth_score": "Growth", "alb_score": "ALB", "data_quality_score": "Data Quality",
    }
    view = df.rename(columns=rename)
    preferred = [c for c in ["Ticker","Nome","Segmento","Preço","P/L","P/VP","DY %","ROE %","FFO Yield %","Cap Rate %","Vacância %","Quality","Value","Growth","ALB","Data Quality"] if c in view.columns]
    st.dataframe(view[preferred], hide_index=True, use_container_width=True, height=460)

st.markdown("---")
st.header("🔎 Análise individual")
st.caption("Digite um ticker e clique em Analisar ativo. O resultado fica salvo na tela mesmo após novos reruns do Streamlit.")

if "analysis_payload" not in st.session_state:
    st.session_state.analysis_payload = None
if "analysis_ticker" not in st.session_state:
    st.session_state.analysis_ticker = None

col_a, col_b = st.columns([1, 2])
with col_a:
    default_ticker = df.iloc[0]["ticker"] if not df.empty else (asset_catalog[0]["ticker"] if asset_catalog else "BBAS3")
    if asset_catalog:
        options = [a["ticker"] for a in asset_catalog]
        labels = {a["ticker"]: f"{a['ticker']} — {a.get('name') or 'nome ainda não cadastrado'}" for a in asset_catalog}
        default_index = options.index(default_ticker) if default_ticker in options else 0
        ticker = st.selectbox(
            "Buscar / selecionar ticker",
            options,
            index=default_index,
            format_func=lambda t: labels.get(t, t),
            key="individual_ticker_select",
            help="Digite dentro da caixa para localizar rapidamente um ticker.",
        )
    else:
        ticker = st.text_input("Ticker", value=default_ticker, key="individual_ticker").strip().upper()
        if asset_catalog_err:
            st.caption("Catálogo de tickers indisponível; digite o código manualmente.")
    analyze = st.button("Analisar ativo", type="primary", use_container_width=True)

if analyze:
    if not ticker:
        st.warning("Informe um ticker, por exemplo BBAS3.")
    else:
        with st.spinner(f"Consultando {ticker} no Investment Engine..."):
            detail, e1 = api_get(f"/assets/{ticker}")
            intel, e2 = api_get(f"/assets/{ticker}/intelligence")
            prices, e3 = api_get(f"/assets/{ticker}/prices", {"limit": 260})
            scores_hist, e4 = api_get(f"/assets/{ticker}/scores/history", {"limit": 120})
            valuations, e5 = api_get(f"/assets/{ticker}/valuations", {"limit": 120})
        st.session_state.analysis_ticker = ticker
        st.session_state.analysis_payload = {
            "detail": detail, "intel": intel, "prices": prices, "scores_hist": scores_hist,
            "valuations": valuations,
            "errors": {"Ativo": e1, "Inteligência": e2, "Preços": e3, "Scores": e4, "Valuation": e5},
        }

payload = st.session_state.analysis_payload
if payload:
    errors = {k: v for k, v in payload["errors"].items() if v}
    if payload["detail"] is None:
        st.error(f"Não foi possível carregar o ativo {st.session_state.analysis_ticker}.")
        if errors:
            st.json(errors)
    else:
        detail = payload["detail"]
        intel = payload["intel"] or {}
        prices = payload["prices"] or []
        scores_hist = payload["scores_hist"] or []
        valuations = payload["valuations"] or []
        asset = detail.get("asset") or {}
        fund = detail.get("fundamentals") or {}
        tech = detail.get("technical") or {}

        with col_b:
            st.success(f"Análise de {asset.get('ticker', st.session_state.analysis_ticker)} carregada.")
            st.write(asset.get("name") or "Nome não disponível")
            if errors:
                st.warning("Algumas partes da análise não puderam ser carregadas. As demais continuam disponíveis.")
                with st.expander("Ver detalhes das chamadas com problema"):
                    st.json(errors)

        st.subheader(f"{asset.get('ticker', st.session_state.analysis_ticker)} — {asset.get('name') or 'Nome não disponível'}")
        st.caption("N/D significa que o dado não está disponível; não é tratado como zero.")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Preço", br_money(fund.get("price")))
        m2.metric("ALB preliminar", br_num(intel.get("alb_preliminary"), 1))
        m3.metric("Quality preliminar", br_num(intel.get("quality_score"), 1))
        m4.metric("Data Quality", br_num((intel.get("data_quality") or {}).get("score"), 1, "%"))
        if asset.get("sector") in {"Finance", "Financial", "Financeiro", "Commercial Services", "Banks"}:
            st.info(
                "Este ativo pertence ao setor financeiro. Os scores desta versão ainda usam uma régua genérica; "
                "por isso Quality/Growth não devem ser interpretados como avaliação definitiva do banco. "
                "A V1.4 terá modelos específicos por setor."
            )
        st.caption(
            f"Cobertura dos scores — Quality: {br_num(intel.get('quality_coverage_pct'),1,'%')} • "
            f"Value: {br_num(intel.get('value_coverage_pct'),1,'%')} • Growth: {br_num(intel.get('growth_coverage_pct'),1,'%')}"
        )

        tabs = st.tabs(["Visão geral", "Fundamentos", "Técnico", "Scores", "Histórico", "Valuation"])
        with tabs[0]:
            left, right = st.columns(2)
            with left:
                st.markdown("#### Identidade")
                st.write({"Setor": asset.get("sector"), "Indústria": asset.get("industry"), "Segmento": asset.get("segment"), "Tipo": asset.get("asset_type")})
            with right:
                st.markdown("#### Inteligência")
                st.write({
                    "Quality Score": intel.get("quality_score"),
                    "Value Score": intel.get("value_score"),
                    "Growth Score": intel.get("growth_score"),
                    "ALB preliminar": intel.get("alb_preliminary"),
                    "Cobertura %": intel.get("coverage_pct"),
                })
        with tabs[1]:
            labels = {
                "pe":"P/L", "pbv":"P/VP", "dividend_yield_pct":"Dividend Yield %", "ev_ebitda":"EV/EBITDA",
                "ebit_margin_pct":"Margem EBIT %", "net_margin_pct":"Margem Líquida %", "current_ratio":"Liquidez Corrente",
                "roe_pct":"ROE %", "roic_pct":"ROIC %", "gross_debt_to_equity":"Dívida Bruta/PL",
                "net_debt_to_ebitda":"Dívida Líquida/EBITDA", "revenue_cagr_5y_pct":"CAGR Receita 5a %",
                "earnings_cagr_5y_pct":"CAGR Lucro 5a %", "ffo_yield_pct":"FFO Yield %", "cap_rate_pct":"Cap Rate %",
                "vacancy_pct":"Vacância %", "ltv_pct":"LTV %", "wale_years":"WALE (anos)", "daily_liquidity":"Liquidez diária",
            }
            fd = [{"Indicador": label, "Valor": fund.get(key)} for key, label in labels.items() if key in fund]
            if fd:
                st.dataframe(pd.DataFrame(fd), hide_index=True, use_container_width=True)
            else:
                st.info("Nenhum fundamento disponível para este ativo.")
        with tabs[2]:
            if not tech:
                st.info("Ainda não há snapshot técnico para este ativo. Rode a ingestão de preços do ticker.")
            else:
                td = {k: tech.get(k) for k in ["sma20","sma50","sma200","rsi14","bb_lower","bb_upper","macd","atr14","volatility_annual_pct","max_drawdown_1y_pct","return_1m_pct","return_3m_pct","return_12m_pct"]}
                st.write(td)
        with tabs[3]:
            score_df = pd.DataFrame([
                {"Score":"Quality", "Valor": intel.get("quality_score")},
                {"Score":"Value", "Valor": intel.get("value_score")},
                {"Score":"Growth", "Valor": intel.get("growth_score")},
                {"Score":"ALB preliminar", "Valor": intel.get("alb_preliminary")},
            ])
            st.dataframe(score_df, hide_index=True, use_container_width=True)
            st.caption("Os pesos desta versão ainda são preliminares e serão calibrados antes de qualquer classificação definitiva.")
        with tabs[4]:
            if prices:
                p = pd.DataFrame(prices)
                p["timestamp"] = pd.to_datetime(p["timestamp"])
                p = p.set_index("timestamp").sort_index()
                if "close" in p:
                    st.line_chart(p[["close"]])
                with st.expander("Ver dados de preço"):
                    st.dataframe(p.tail(60), use_container_width=True)
            else:
                st.info("Histórico de preços ainda não carregado para este ativo.")
            if scores_hist:
                sh = pd.DataFrame(scores_hist)
                sh["as_of"] = pd.to_datetime(sh["as_of"])
                cols = [c for c in ["quality_score","value_score","growth_score","alb_score","data_quality_score"] if c in sh]
                if cols:
                    st.markdown("#### Evolução dos scores")
                    st.line_chart(sh.set_index("as_of").sort_index()[cols])
        with tabs[5]:
            st.metric("Graham Number", br_money(intel.get("graham_number")))
            st.metric("Diferença vs preço", br_num(intel.get("graham_upside_pct"), 1, "%"))
            if valuations:
                st.dataframe(pd.DataFrame(valuations), hide_index=True, use_container_width=True)
            else:
                st.info("Ainda não há histórico de valuations persistidos para este ativo.")

st.markdown("---")
st.caption("V1.3.4 é uma versão de integração/teste. Não constitui recomendação de investimento.")
