import math
import os
from datetime import date, datetime, timedelta, timezone
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Formação do Investidor", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

def _env_flag(name,default=False):
    return os.getenv(name,"true" if default else "false").strip().lower() in {"1","true","yes","on"}

def _protect_private_beta():
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
    allowed={item.strip().lower() for item in os.getenv("APP_ALLOWED_EMAILS","").split(",") if item.strip()}
    if allowed and email not in allowed:
        st.error("Esta conta não está autorizada para o beta privado.")
        if st.button("Sair"):
            st.logout()
        st.stop()
    st.sidebar.caption(f"Acesso privado: {email or 'usuário autenticado'}")
    if st.sidebar.button("Sair da conta",key="app_logout"):
        st.logout()

_protect_private_beta()

DEFAULT_API=os.getenv("INVESTMENT_API_URL","http://127.0.0.1:8000").rstrip("/")
if _env_flag("SHOW_API_SELECTOR",True):
    API=st.sidebar.text_input("Investment Engine API",DEFAULT_API).rstrip("/")
else:
    API=DEFAULT_API

def _request(method,path,params=None,json=None,timeout=120):
    try:
        r=requests.request(method,f"{API}{path}",params=params,json=json,timeout=timeout)
        r.raise_for_status(); return r.json(),None
    except requests.RequestException as exc:
        detail=getattr(exc.response,"text",None) if getattr(exc,"response",None) is not None else None
        return None,(detail or str(exc))

def api_get(path,params=None):return _request("GET",path,params=params)
def api_post(path,json=None,timeout=180):return _request("POST",path,json=json,timeout=timeout)
def api_put(path,json=None,timeout=120):return _request("PUT",path,json=json,timeout=timeout)
def api_patch(path,json=None,timeout=120):return _request("PATCH",path,json=json,timeout=timeout)
def api_delete(path,timeout=120):return _request("DELETE",path,timeout=timeout)

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

def _pct(v):
    return "N/D" if v is None else br_num(v,1,"%")


def _active_range(enabled, min_value=None, max_value=None):
    if not enabled:
        return None
    out={}
    if min_value is not None:out["min"]=float(min_value)
    if max_value is not None:out["max"]=float(max_value)
    return out


def render_advanced_screener(asset_type):
    st.markdown("---")
    st.header("🧰 Screener configurável — Fundamentalista + Técnico")
    st.caption("Ative somente as regras que quiser. Filtros ativos são combinados por E (AND): o ativo precisa satisfazer todos eles. N/D nunca passa por um filtro ativo.")
    market_name="Ações" if asset_type=="stock" else "FIIs"
    if "advanced_screen_result" not in st.session_state:st.session_state.advanced_screen_result=None

    with st.form(f"advanced_screen_form_{asset_type}"):
        st.markdown(f"#### 1. Filtros fundamentalistas — {market_name}")
        fundamental={}
        if asset_type=="stock":
            c1,c2,c3,c4=st.columns(4)
            use_pe=c1.checkbox("Usar P/L"); pe_min=c1.number_input("P/L mínimo",value=0.0,step=0.5); pe_max=c1.number_input("P/L máximo",value=15.0,step=0.5)
            use_pbv=c2.checkbox("Usar P/VP"); pbv_max=c2.number_input("P/VP máximo",value=2.0,step=0.1)
            use_dy=c3.checkbox("Usar Dividend Yield"); dy_min=c3.number_input("DY mínimo (%)",value=4.0,step=0.5)
            use_liq=c4.checkbox("Usar liquidez diária"); liq_min=c4.number_input("Liquidez diária mínima (R$)",value=1000000.0,step=100000.0,format="%.0f")

            c1,c2,c3,c4=st.columns(4)
            use_roe=c1.checkbox("Usar ROE"); roe_min=c1.number_input("ROE mínimo (%)",value=10.0,step=1.0)
            use_roic=c2.checkbox("Usar ROIC"); roic_min=c2.number_input("ROIC mínimo (%)",value=8.0,step=1.0)
            use_ebit=c3.checkbox("Usar margem EBIT"); ebit_min=c3.number_input("Margem EBIT mínima (%)",value=8.0,step=1.0)
            use_net=c4.checkbox("Usar margem líquida"); net_min=c4.number_input("Margem líquida mínima (%)",value=5.0,step=1.0)

            c1,c2,c3,c4=st.columns(4)
            use_ev=c1.checkbox("Usar EV/EBITDA"); ev_max=c1.number_input("EV/EBITDA máximo",value=10.0,step=0.5)
            use_debt=c2.checkbox("Usar dívida bruta/PL"); debt_max=c2.number_input("Dívida bruta/PL máxima",value=1.5,step=0.1)
            use_ndebt=c3.checkbox("Usar dívida líquida/EBITDA"); ndebt_max=c3.number_input("Dív. líquida/EBITDA máxima",value=3.0,step=0.25)
            use_cr=c4.checkbox("Usar liquidez corrente"); cr_min=c4.number_input("Liquidez corrente mínima",value=1.0,step=0.1)

            c1,c2=st.columns(2)
            use_rev=c1.checkbox("Usar CAGR receita 5 anos"); rev_min=c1.number_input("CAGR receita mínimo (%)",value=5.0,step=1.0)
            use_earn=c2.checkbox("Usar CAGR lucro 5 anos"); earn_min=c2.number_input("CAGR lucro mínimo (%)",value=5.0,step=1.0)

            fundamental={
                "pe":_active_range(use_pe,pe_min,pe_max), "pbv":_active_range(use_pbv,None,pbv_max),
                "dividend_yield_pct":_active_range(use_dy,dy_min,None), "daily_liquidity":_active_range(use_liq,liq_min,None),
                "roe_pct":_active_range(use_roe,roe_min,None), "roic_pct":_active_range(use_roic,roic_min,None),
                "ebit_margin_pct":_active_range(use_ebit,ebit_min,None), "net_margin_pct":_active_range(use_net,net_min,None),
                "ev_ebitda":_active_range(use_ev,None,ev_max), "gross_debt_to_equity":_active_range(use_debt,None,debt_max),
                "net_debt_to_ebitda":_active_range(use_ndebt,None,ndebt_max), "current_ratio":_active_range(use_cr,cr_min,None),
                "revenue_cagr_5y_pct":_active_range(use_rev,rev_min,None), "earnings_cagr_5y_pct":_active_range(use_earn,earn_min,None),
            }
        else:
            c1,c2,c3,c4=st.columns(4)
            use_pbv=c1.checkbox("Usar P/VP"); pbv_min=c1.number_input("P/VP mínimo",value=0.5,step=0.05); pbv_max=c1.number_input("P/VP máximo",value=1.1,step=0.05)
            use_dy=c2.checkbox("Usar Dividend Yield"); dy_min=c2.number_input("DY mínimo (%)",value=7.0,step=0.5)
            use_ffo=c3.checkbox("Usar FFO Yield"); ffo_min=c3.number_input("FFO Yield mínimo (%)",value=5.0,step=0.5)
            use_cap=c4.checkbox("Usar Cap Rate"); cap_min=c4.number_input("Cap Rate mínimo (%)",value=5.0,step=0.5)
            c1,c2,c3,c4=st.columns(4)
            use_vac=c1.checkbox("Usar vacância física"); vac_max=c1.number_input("Vacância máxima (%)",value=10.0,step=1.0)
            use_fvac=c2.checkbox("Usar vacância financeira"); fvac_max=c2.number_input("Vacância financeira máxima (%)",value=10.0,step=1.0)
            use_ltv=c3.checkbox("Usar LTV"); ltv_max=c3.number_input("LTV máximo (%)",value=40.0,step=1.0)
            use_wale=c4.checkbox("Usar WALE"); wale_min=c4.number_input("WALE mínimo (anos)",value=2.0,step=0.5)
            use_liq=st.checkbox("Usar liquidez diária do FII"); liq_min=st.number_input("Liquidez diária mínima (R$)",value=500000.0,step=100000.0,format="%.0f")
            fundamental={
                "pbv":_active_range(use_pbv,pbv_min,pbv_max), "dividend_yield_pct":_active_range(use_dy,dy_min,None),
                "ffo_yield_pct":_active_range(use_ffo,ffo_min,None), "cap_rate_pct":_active_range(use_cap,cap_min,None),
                "vacancy_pct":_active_range(use_vac,None,vac_max), "financial_vacancy_pct":_active_range(use_fvac,None,fvac_max),
                "ltv_pct":_active_range(use_ltv,None,ltv_max), "wale_years":_active_range(use_wale,wale_min,None),
                "daily_liquidity":_active_range(use_liq,liq_min,None),
            }
        fundamental={k:v for k,v in fundamental.items() if v is not None}

        st.markdown("#### 2. Valuation e scores")
        v1,v2,v3=st.columns(3)
        below_graham=v1.checkbox("Preço abaixo do Graham",disabled=asset_type!="stock")
        below_barsi=v2.checkbox("Preço abaixo do Teto Bazin/Barsi (6%)")
        score_enabled=v3.checkbox("Filtrar também por scores")
        score_filters={}
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

        st.markdown("#### 3. Filtros técnicos combináveis")
        t1,t2,t3,t4=st.columns(4)
        trend_period=t1.selectbox("Período das médias",[21,20],help="21 é o padrão desta tela. Use 20 se quiser maior compatibilidade com snapshots TradingView já existentes.")
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

        with st.expander("Fórmulas de Pivot usadas pelo motor"):
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
        submitted=st.form_submit_button("🔎 Executar filtros combinados",type="primary")

    if submitted:
        tech={"daily_trend":daily,"weekly_trend":weekly,"monthly_trend":monthly,"pivot_zone":pivot_zone,"near_pivot_level":near_level,"pivot_tolerance_pct":tolerance}
        if use_rsi:tech["rsi14"]={"min":rsi_min,"max":rsi_max}
        payload={
            "asset_type":asset_type,"fundamental_filters":fundamental,"score_filters":score_filters,
            "valuation_flags":{"below_graham":bool(below_graham),"below_barsi_6pct":bool(below_barsi)},
            "technical_filters":tech,"trend_period":trend_period,"pivot_timeframe":pivot_tf,
            "include_technical_columns":True,"limit":limit,
        }
        with st.spinner("Aplicando fundamentos, scores, tendências e pivôs..."):
            result,e=api_post("/screen/advanced",payload,timeout=240)
        if e:st.error(f"Screener avançado não concluído: {e}")
        else:st.session_state.advanced_screen_result=result

    result=st.session_state.get("advanced_screen_result")
    if result:
        meta=result.get("meta") or {}; rows=result.get("rows") or []
        a,b,c,d=st.columns(4)
        a.metric("Universo",meta.get("universe_count",0)); b.metric("Após fundamentos/scores",meta.get("fundamental_candidates",0)); c.metric("Resultado final",meta.get("returned",0)); d.metric("Sem histórico técnico",meta.get("technical_history_missing",0))
        if meta.get("technical_filter_active") and meta.get("technical_history_missing",0)>0:
            cmd=f"python scripts/ingest_prices.py --all --type {asset_type} --range 3y"
            st.warning("Alguns ativos não possuem histórico local suficiente para filtros técnicos/pivôs. Para ampliar a cobertura, carregue o histórico do universo.")
            st.code(cmd)
        if not rows:
            st.info("Nenhum ativo satisfez simultaneamente todos os filtros ativados.")
        else:
            df=pd.DataFrame(rows)
            rename={
                "ticker":"Ticker","name":"Nome","sector":"Setor","segment":"Segmento","price":"Preço","pe":"P/L","pbv":"P/VP","dividend_yield_pct":"DY %","roe_pct":"ROE %","roic_pct":"ROIC %","ebit_margin_pct":"Margem EBIT %","net_margin_pct":"Margem Líquida %","ev_ebitda":"EV/EBITDA","gross_debt_to_equity":"Dív. Bruta/PL","net_debt_to_ebitda":"Dív. Líq./EBITDA","current_ratio":"Liq. Corrente","revenue_cagr_5y_pct":"CAGR Receita %","earnings_cagr_5y_pct":"CAGR Lucro %","ffo_yield_pct":"FFO Yield %","cap_rate_pct":"Cap Rate %","vacancy_pct":"Vacância %","ltv_pct":"LTV %","wale_years":"WALE","daily_liquidity":"Liquidez diária","alb_score":"ALB","quality_score":"Quality","value_score":"Value","growth_score":"Growth","technical_score":"Technical","risk_score":"Risk","liquidity_score":"Liquidity","data_quality_score":"Data Quality","trend_daily":"Tend. Dia","trend_weekly":"Tend. Sem.","trend_monthly":"Tend. Mês","sma_daily":"Média Dia","sma_weekly":"Média Sem.","sma_monthly":"Média Mês","rsi14_screen":"RSI 14","pp":"PP","s1":"S1","s2":"S2","s3":"S3","r1":"R1","r2":"R2","r3":"R3","pivot_zone":"Faixa Pivot","pivot_reference":"Referência Pivot",
            }
            view=df.rename(columns=rename)
            preferred=[c for c in ["Ticker","Nome","Setor","Segmento","Preço","P/L","P/VP","DY %","ROE %","ROIC %","FFO Yield %","Cap Rate %","Vacância %","ALB","Quality","Value","Technical","Risk","Liquidity","Tend. Dia","Tend. Sem.","Tend. Mês","Média Dia","Média Sem.","Média Mês","RSI 14","S3","S2","S1","PP","R1","R2","R3","Faixa Pivot","Referência Pivot"] if c in view.columns]
            st.dataframe(view[preferred],hide_index=True,use_container_width=True,height=520)
            st.caption("Tendência = preço atual acima/abaixo da média simples do período escolhido. Sem histórico suficiente, o filtro técnico ativo reprova o ativo em vez de assumir zero.")


def render_market():
    st.title("📊 Mercado e Análise Individual")
    st.caption("Screener, scores por perfil de ativo e valuation multi-método.")
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

    render_advanced_screener(asset_type)

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

    portfolios,err=api_get("/portfolios")
    if err:
        st.error(f"Não foi possível carregar as carteiras: {err}"); return
    portfolios=portfolios or []
    if not portfolios:
        st.info("Ainda não existe uma carteira cadastrada.")
        if st.button("Criar Carteira Principal",type="primary"):
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
        if st.button("Salvar configurações da carteira"):
            _,e=api_patch(f"/portfolios/{pid}",{"name":name,"cash_balance":cash,"target_cash_pct":target_cash,"notes":notes})
            if e:st.error(e)
            else:st.success("Configurações salvas."); st.rerun()

    m1,m2,m3,m4,m5=st.columns(5)
    m1.metric("Patrimônio atual",br_money(summary.get("market_value")))
    m2.metric("Valor investido",br_money(summary.get("invested_market_value")))
    m3.metric("Custo das posições",br_money(summary.get("cost_basis")))
    m4.metric("Resultado não realizado",br_money(summary.get("unrealized_pnl")),_pct(summary.get("unrealized_pnl_pct")))
    m5.metric("Soma dos alvos",_pct(summary.get("target_total_pct")))
    if not summary.get("target_is_balanced"):
        st.warning(f"Os percentuais-alvo somam {_pct(summary.get('target_total_pct'))}. Para uma alocação completa, o ideal é totalizar 100% incluindo o caixa.")

    left,right=st.columns([3,1])
    with left:
        st.subheader("Adicionar ou atualizar ativo")
        existing_map={p["ticker"]:p for p in positions}
        edit_ticker=st.selectbox("Editar posição existente (opcional)",[""]+sorted(existing_map),format_func=lambda x:"Novo ativo" if x=="" else f"Editar {x}",key="pf_edit_existing")
        existing=existing_map.get(edit_ticker) or {}
        type_options=["Ação","FII","ETF","BDR","Renda Fixa","Cripto","Outro"]
        type_map={"Ação":"stock","FII":"fii","ETF":"etf","BDR":"bdr","Renda Fixa":"fixed_income","Cripto":"crypto","Outro":"other"}
        type_rev={v:k for k,v in type_map.items()}
        stage_options=["Posição atual","Alvo","Em análise"]
        stage_map={"Posição atual":"position","Alvo":"target","Em análise":"analysis"}
        stage_rev={v:k for k,v in stage_map.items()}
        form_key=f"portfolio_position_form_{edit_ticker or 'new'}"
        with st.form(form_key):
            a,b,c=st.columns(3)
            ticker=a.text_input("Ticker",value=existing.get("ticker","") if existing else "",placeholder="Ex.: BBAS3, HGLG11, BOVA11",disabled=bool(existing)).strip().upper()
            default_type=type_rev.get(existing.get("asset_class") or existing.get("asset_type"),"Ação")
            type_label=b.selectbox("Tipo",type_options,index=type_options.index(default_type) if default_type in type_options else 0)
            default_stage=stage_rev.get(existing.get("stage"),"Posição atual")
            stage_label=c.selectbox("Situação",stage_options,index=stage_options.index(default_stage))
            d,e,f=st.columns(3)
            qty=d.number_input("Quantidade",min_value=0.0,value=float(existing.get("quantity") or 0.0),step=1.0,format="%.8f")
            avg=e.number_input("Preço médio de compra (R$)",min_value=0.0,value=float(existing.get("average_price") or 0.0),step=0.01)
            target=f.number_input("Percentual alvo da carteira (%)",min_value=0.0,max_value=100.0,value=float(existing.get("target_weight_pct") or 0.0),step=0.5)
            classification_override=st.text_input("Setor / segmento / categoria manual (opcional)",value=existing.get("classification_override") or "",placeholder="Útil para ETFs. Ex.: Índice Brasil, Tecnologia, Logística")
            pnotes=st.text_input("Observação / tese curta",value=existing.get("notes") or "",placeholder="Ex.: aumentar posição se valuation continuar atrativo")
            save=st.form_submit_button("Salvar ativo",type="primary")
        if save:
            if not ticker:st.error("Informe o ticker.")
            else:
                payload={"asset_type":type_map[type_label],"stage":stage_map[stage_label],"quantity":qty,"average_price":avg if avg>0 else None,"target_weight_pct":target,"classification_override":classification_override or None,"notes":pnotes or None}
                _,e=api_put(f"/portfolios/{pid}/positions/{ticker}",payload)
                if e:st.error(e)
                else:st.success(f"{ticker} salvo na carteira."); st.rerun()
    with right:
        st.subheader("Cotações")
        st.caption("Atualiza pelo Yahoo e grava o histórico no banco. Útil também para ETFs.")
        if st.button("🔄 Atualizar preços da carteira",use_container_width=True):
            with st.spinner("Atualizando cotações..."):
                r,e=api_post(f"/portfolios/{pid}/refresh-prices",{},timeout=240)
            if e:st.error(e)
            else:
                ok=sum(1 for x in r.get("results",[]) if x.get("status")=="ok")
                st.success(f"Cotações atualizadas: {ok} ativo(s).")
                st.rerun()
        if positions:
            delete_ticker=st.selectbox("Remover ativo",[""]+[p["ticker"] for p in positions],key="pf_delete")
            if st.button("Remover selecionado",disabled=not bool(delete_ticker),use_container_width=True):
                _,e=api_delete(f"/portfolios/{pid}/positions/{delete_ticker}")
                if e:st.error(e)
                else:st.success(f"{delete_ticker} removido."); st.rerun()

    tabs=st.tabs(["Posição atual","Alvos","Em análise","Composição geral","Setores / segmentos","Rebalanceamento"])
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
    alias=result.get("ticker_alias")
    if alias:
        st.info(f"Código atualizado automaticamente: {alias.get('requested')} → {alias.get('ticker')}. {alias.get('reason')}.")
    st.subheader(f"{result.get('ticker')} • {result.get('strategy',{}).get('name','Estratégia')}")
    st.caption(f"Período efetivo: {str(result.get('actual_start',''))[:10]} a {str(result.get('actual_end',''))[:10]} • sinais sem antecipação (posição no pregão seguinte).")
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
        with st.expander("Qualidade mínima do histórico fundamentalista",expanded=False):
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

    filters=_backtest_filters_ui(type_map[type_label])

    run_tab,basket_tab,compare_tab,history_tab=st.tabs(["Executar estratégia","Testar cesta","Comparar estratégias","Histórico salvo"])
    with run_tab:
        sid=st.selectbox("Estratégia",list(by_id),format_func=lambda x:by_id[x]["name"],key="bt_strategy")
        definition=by_id[sid]
        st.info(f"**{definition['family']}** — {definition['description']}\n\n**Regra:** {definition['rules']}")
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
        if st.button("▶ Executar backtest",type="primary",key="bt_run"):
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
        if st.button("🧪 Executar backtest da cesta",type="primary",key="bt_basket_run",disabled=len(set(basket_tickers))<2,use_container_width=True):
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
        if st.button("Comparar no mesmo ativo e período",key="bt_compare",disabled=not bool(selected)):
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
        runs,e=api_get("/backtests/runs",{"ticker":ticker,"limit":50})
        if e:st.error(e)
        elif not runs:st.info("Nenhum backtest salvo para este ticker.")
        else:
            rows=[]
            for r in runs:
                m=r.get("metrics") or {}
                rows.append({"ID":r["id"],"Data":r.get("created_at"),"Estratégia":r.get("strategy_name"),"Início":r.get("actual_start"),"Fim":r.get("actual_end"),"Retorno %":m.get("total_return_pct"),"CAGR %":m.get("cagr_pct"),"Sharpe":m.get("sharpe_ratio"),"Max DD %":m.get("max_drawdown_pct"),"Trades encerrados":m.get("closed_trades",m.get("trades")),"Posições abertas":m.get("open_trades",0)})
            hdf=pd.DataFrame(rows); st.dataframe(hdf,hide_index=True,use_container_width=True,height=360)
            rid=st.selectbox("Abrir execução salva",[r["id"] for r in runs],format_func=lambda x:next((f"{r['strategy_name']} • {str(r.get('created_at',''))[:19]}" for r in runs if r["id"]==x),x))
            if st.button("Abrir resultado salvo"):
                detail,e=api_get(f"/backtests/runs/{rid}")
                if e:st.error(e)
                else:
                    # Reuse the renderer shape.
                    detail["strategy"]={"name":detail.get("strategy_name"),"rules":"Execução histórica salva; consulte os parâmetros abaixo."}
                    detail["assumptions"]={"fee_pct":detail.get("fee_pct"),"slippage_pct":detail.get("slippage_pct"),"risk_free_rate_pct":detail.get("risk_free_rate_pct")}
                    _render_backtest_result(detail)


health,err=api_get("/health")
if err:
    st.error("Não consegui falar com o Investment Engine. Ligue a API primeiro.")
    st.code("python -m uvicorn investment_engine.api.app:app --host 127.0.0.1 --port 8000")
    st.stop()
st.sidebar.success(f"Motor online • versão {health.get('version','?')}")
module=st.sidebar.radio("Módulo",["Mercado & Análise","Carteira","Backtests"],index=0)
st.sidebar.markdown("---")
if module=="Mercado & Análise":render_market()
elif module=="Carteira":render_portfolio()
else:render_backtests()
st.markdown("---")
st.caption("Formação do Investidor • Investment Engine V1.6.0. Ferramenta educacional de análise e simulação; não constitui recomendação de investimento.")
