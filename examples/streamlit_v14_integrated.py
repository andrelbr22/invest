import math
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Investment Engine V1.4.1", layout="wide", initial_sidebar_state="expanded")
DEFAULT_API="http://127.0.0.1:8000"
API=st.sidebar.text_input("Investment Engine API",DEFAULT_API)

def api_get(path,params=None):
    try:
        r=requests.get(f"{API}{path}",params=params,timeout=60); r.raise_for_status(); return r.json(),None
    except requests.RequestException as exc:return None,str(exc)

def br_money(v):
    if v is None or (isinstance(v,float) and math.isnan(v)):return "N/D"
    return f"R$ {float(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")

def br_num(v,digits=1,suffix=""):
    if v is None or (isinstance(v,float) and math.isnan(v)):return "N/D"
    return f"{float(v):.{digits}f}".replace(".",",")+suffix

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

st.title("📊 Investment Engine — V1.4.1")
st.caption("Scores por perfil de ativo, componentes técnico/risco/liquidez e explicação do resultado. N/D nunca é convertido em zero.")
health,err=api_get("/health")
if err:
    st.error("Não consegui falar com o Investment Engine. Ligue a API primeiro.")
    st.code("python -m uvicorn investment_engine.api.app:app --host 127.0.0.1 --port 8000")
    st.stop()
st.sidebar.success(f"Motor online • versão {health.get('version','?')}")
market=st.sidebar.radio("Mercado",["Ações","FIIs"])
strategy_label=st.sidebar.selectbox("Estratégia",["Padrão","CNPI","ALB"])
strategy={"Padrão":"default","CNPI":"cnpi","ALB":"alb"}[strategy_label]
limit=st.sidebar.slider("Máximo de resultados",10,200,50,10)
asset_type="stock" if market=="Ações" else "fii"
catalog,catalog_err=api_get("/assets",{"asset_type":asset_type,"limit":500,"offset":0}); catalog=catalog or []
endpoint=f"/screen/db/stocks/{strategy}" if market=="Ações" else f"/screen/db/fiis/{strategy}"
rows,err=api_get(endpoint,{"limit":limit})
if err:
    st.error(f"Não foi possível carregar o screener: {err}"); st.stop()
df=pd.DataFrame(rows or [])

# V1.4.1: o filtro por ticker é independente da estratégia.
# Ao selecionar um ativo específico, ele é buscado diretamente na API e
# aparece sozinho na tabela, mesmo que não passe pelo setup atual.
ticker_options=[""]+[a["ticker"] for a in catalog]
ticker_labels={"":"Todos os ativos do screener"}
ticker_labels.update({a["ticker"]:f"{a['ticker']} — {a.get('name') or 'nome ainda não cadastrado'}" for a in catalog})
selected_table_ticker=st.sidebar.selectbox(
    "Filtrar ticker na tabela",
    ticker_options,
    format_func=lambda t:ticker_labels.get(t,t),
    key="v141_table_ticker",
)

if selected_table_ticker:
    detail_one,e_detail=api_get(f"/assets/{selected_table_ticker}")
    intel_one,e_intel=api_get(f"/assets/{selected_table_ticker}/intelligence")
    if e_detail or detail_one is None:
        st.sidebar.error(f"Não foi possível carregar {selected_table_ticker}: {e_detail or 'ativo não encontrado'}")
        df=pd.DataFrame()
    else:
        asset_one=detail_one.get("asset") or {}
        fund_one=detail_one.get("fundamentals") or {}
        intel_one=intel_one or {}
        df=pd.DataFrame([{
            "ticker":asset_one.get("ticker"),
            "name":asset_one.get("name"),
            "segment":asset_one.get("segment"),
            "price":fund_one.get("price"),
            "pe":fund_one.get("pe"),
            "pbv":fund_one.get("pbv"),
            "dy":fund_one.get("dividend_yield_pct"),
            "roe":fund_one.get("roe_pct"),
            "ffo_yield":fund_one.get("ffo_yield_pct"),
            "cap_rate":fund_one.get("cap_rate_pct"),
            "vacancy":fund_one.get("vacancy_pct"),
            "daily_liquidity":fund_one.get("daily_liquidity"),
            "quality_score":intel_one.get("quality_score"),
            "value_score":intel_one.get("value_score"),
            "growth_score":intel_one.get("growth_score"),
            "technical_score":intel_one.get("technical_score"),
            "risk_score":intel_one.get("risk_score"),
            "liquidity_score":intel_one.get("liquidity_score"),
            "alb_score":intel_one.get("alb_score"),
            "data_quality_score":(intel_one.get("data_quality") or {}).get("score"),
        }])
        st.sidebar.caption("Ticker selecionado: a tabela ignora temporariamente os filtros da estratégia e mostra este ativo individualmente.")

c1,c2,c3,c4=st.columns(4); c1.metric("Ativos encontrados",len(df))
if not df.empty:
    c2.metric("ALB médio",br_num(pd.to_numeric(df.get("alb_score"),errors="coerce").mean(),1))
    c3.metric("Technical médio",br_num(pd.to_numeric(df.get("technical_score"),errors="coerce").mean(),1))
    c4.metric("Data Quality médio",br_num(pd.to_numeric(df.get("data_quality_score"),errors="coerce").mean(),1,"%"))

st.subheader(f"{market} • Estratégia {strategy_label}")
if df.empty:st.info("Nenhum ativo corresponde aos filtros atuais.")
else:
    rename={"ticker":"Ticker","name":"Nome","segment":"Segmento","price":"Preço","pe":"P/L","pbv":"P/VP","dy":"DY %","roe":"ROE %","ffo_yield":"FFO Yield %","cap_rate":"Cap Rate %","vacancy":"Vacância %","daily_liquidity":"Liquidez","quality_score":"Quality","value_score":"Value","growth_score":"Growth","technical_score":"Technical","risk_score":"Risk","liquidity_score":"Liquidity","alb_score":"ALB","data_quality_score":"Data Quality"}
    view=df.rename(columns=rename)
    preferred=[c for c in ["Ticker","Nome","Segmento","Preço","P/L","P/VP","DY %","ROE %","FFO Yield %","Cap Rate %","Vacância %","Quality","Value","Growth","Technical","Risk","Liquidity","ALB","Data Quality"] if c in view.columns]
    st.dataframe(view[preferred],hide_index=True,use_container_width=True,height=460)

st.markdown("---"); st.header("🔎 Análise individual")
if "analysis_payload_v14" not in st.session_state:st.session_state.analysis_payload_v14=None
if catalog:
    options=[a["ticker"] for a in catalog]; labels={a["ticker"]:f"{a['ticker']} — {a.get('name') or 'nome ainda não cadastrado'}" for a in catalog}
    default_ticker=selected_table_ticker if selected_table_ticker in options else ("BBAS3" if "BBAS3" in options else options[0])
    default_index=options.index(default_ticker)
    ticker=st.selectbox("Buscar / selecionar ticker",options,index=default_index,format_func=lambda t:labels.get(t,t),key="v14_ticker")
else:ticker=st.text_input("Ticker",value="BBAS3").strip().upper()
if st.button("Analisar ativo",type="primary"):
    with st.spinner(f"Calculando inteligência V1.4 para {ticker}..."):
        detail,e1=api_get(f"/assets/{ticker}"); intel,e2=api_get(f"/assets/{ticker}/intelligence"); prices,e3=api_get(f"/assets/{ticker}/prices",{"limit":260}); hist,e4=api_get(f"/assets/{ticker}/scores/history",{"limit":120}); vals,e5=api_get(f"/assets/{ticker}/valuations",{"limit":120})
    st.session_state.analysis_payload_v14={"ticker":ticker,"detail":detail,"intel":intel,"prices":prices or [],"hist":hist or [],"vals":vals or [],"errors":{"Ativo":e1,"Inteligência":e2,"Preços":e3,"Scores":e4,"Valuation":e5}}

p=st.session_state.analysis_payload_v14
if p:
    errors={k:v for k,v in p["errors"].items() if v}
    if p["detail"] is None:st.error(f"Não foi possível carregar {p['ticker']}.")
    else:
        detail=p["detail"]; intel=p["intel"] or {}; asset=detail.get("asset") or {}; fund=detail.get("fundamentals") or {}; tech=detail.get("technical") or {}
        st.subheader(f"{asset.get('ticker')} — {asset.get('name') or 'Nome não disponível'}")
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
            st.metric("Graham Number",br_money(intel.get("graham_number"))); st.metric("Diferença vs preço",br_num(intel.get("graham_upside_pct"),1,"%"))
            if p["vals"]:st.dataframe(pd.DataFrame(p["vals"]),hide_index=True,use_container_width=True)
            else:st.info("Ainda não há histórico de valuations persistidos.")

st.markdown("---"); st.caption("V1.4.1 é uma versão de desenvolvimento/triagem. Scores não constituem recomendação de investimento.")
