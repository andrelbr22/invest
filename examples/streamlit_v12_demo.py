import streamlit as st
import pandas as pd
import requests
API=st.sidebar.text_input("Investment Engine API","http://localhost:8000")
st.title("Investment Engine V1.2 — teste visual")
strategy=st.selectbox("Estratégia",["padrao","cnpi","alb"])
if st.button("Carregar ações do novo motor"):
    r=requests.get(f"{API}/screen/db/stocks/{strategy}",timeout=20); r.raise_for_status(); data=r.json()
    st.metric("Ações encontradas",len(data)); st.dataframe(pd.DataFrame(data),use_container_width=True)
ticker=st.text_input("Ticker para análise","BBAS3").upper()
if st.button("Analisar ativo"):
    r=requests.get(f"{API}/assets/{ticker}/intelligence",timeout=20)
    if r.ok: st.json(r.json())
    else: st.error(r.text)
