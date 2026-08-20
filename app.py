import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import math

# Configuração da página para ficar com visual profissional
st.set_page_config(page_title="Screener Avançado de Ações", layout="wide")

st.title("📊 Screener Avançado de Ações")
st.markdown("Cruzamento fundamentalista (Fundamentus) com tendências técnicas (TradingView) e Metodologias de Valuation.")

@st.cache_data(ttl=3600) # Guarda em cache por 1 hora para o app voar de rápido
def carregar_dados():
    # 1. Extração Fundamentus
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        resposta = requests.get('https://www.fundamentus.com.br/resultado.php', headers=headers, timeout=15)
        soup = BeautifulSoup(resposta.text, 'html.parser')
        tabela = soup.find('table', id='resultado')
        
        dados_fund = []
        if tabela:
            for linha in tabela.find_all('tr')[1:]:
                col = linha.find_all('td')
                if len(col) >= 21:
                    def limpar(texto):
                        return float(texto.text.replace('%', '').replace('.', '').replace(',', '.') or 0)
                    
                    ticker = col[0].text.strip()
                    cotacao = limpar(col[1])
                    p_l = limpar(col[2])
                    p_vp = limpar(col[3])
                    div_yield = limpar(col[5])
                    ev_ebit = limpar(col[10])
                    div_bruta_patrim = limpar(col[19])
                    cresc_rec_5a = limpar(col[20])
                    
                    dados_fund.append({
                        "Ticker": ticker,
                        "Cotação": cotacao,
                        "P/L": p_l,
                        "P/VP": p_vp,
                        "Div. Yield (%)": div_yield,
                        "EV/EBIT": ev_ebit,
                        "Dív./Patrimônio": div_bruta_patrim,
                        "Cresc. Rec. 5a (%)": cresc_rec_5a
                    })
        df = pd.DataFrame(dados_fund)
    except Exception as e:
        st.error(f"Erro ao carregar Fundamentus: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    # 2. Extração TradingView (Indicação de Compra e Volume)
    try:
        payload_tv = {
            "filter": [{"left": "type", "operation": "equal", "right": "stock"}],
            "options": {"lang": "pt"},
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name", "Recommend.All", "volume"]
        }
        resp_tv = requests.post("https://scanner.tradingview.com/brazil/scan", json=payload_tv, timeout=15)
        res_json = resp_tv.json()
        
        tv_dict = {}
        for item in res_json.get('data', []):
            ticker_completo = item['d'][0]
            ticker_limpo = ticker_completo.split(":")[-1]
            score = item['d'][1]
            tv_dict[ticker_limpo] = {
                "Indicação de Compra (TV)": score > 0.1,
                "Volume": item['d'][2]
            }
        
        df_tv = pd.DataFrame.from_dict(tv_dict, orient='index').reset_index().rename(columns={'index': 'Ticker'})
        df = pd.merge(df, df_tv, on='Ticker', how='left')
    except Exception as e:
        df["Indicação de Compra (TV)"] = False

    # 3. Engenharia de Valuation e Indicadores
    # VPA = Cotação / P_VP | LPA = Cotação / P_L
    df['VPA'] = df.apply(lambda r: r['Cotação'] / r['P/VP'] if r['P/VP'] > 0 else 0, axis=1)
    df['LPA'] = df.apply(lambda r: r['Cotação'] / r['P/L'] if r['P/L'] > 0 else 0, axis=1)
    
    # Preço Justo Graham = sqrt(22.5 * VPA * LPA)
    df['Preço Justo (Graham)'] = df.apply(lambda r: math.sqrt(22.5 * r['VPA'] * r['LPA']) if r['VPA'] > 0 and r['LPA'] > 0 else 0, axis=1)
    
    # Preço Teto Barsi = (Cotação * Div_Yield) / 6%
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    
    # Earnings Yield = (1 / EV_EBIT) * 100
    df['Earnings Yield (%)'] = df.apply(lambda r: (1 / r['EV/EBIT']) * 100 if r['EV/EBIT'] > 0 else 0, axis=1)
    
    # Margem de Segurança Graham (%)
    df['Margem Seg. Graham (%)'] = df.apply(lambda r: ((r['Preço Justo (Graham)'] - r['Cotação']) / r['Preço Justo (Graham)']) * 100 if r['Preço Justo (Graham)'] > 0 else 0, axis=1)
    
    return df

with st.spinner("Atualizando dados da bolsa... Por favor, aguarde."):
    df_acoes = carregar_dados()

if df_acoes.empty:
    st.warning("Não foi possível carregar os dados no momento.")
else:
    # Barra lateral de Filtros
    st.sidebar.header("🔍 Filtros Avançados")
    
    busca = st.sidebar.text_input("Buscar Ticker (ex: PETR4)").upper()
    max_pvp = st.sidebar.slider("P/VP Máximo", 0.0, 10.0, 3.0, 0.1)
    min_dy = st.sidebar.slider("Dividend Yield Mínimo (%)", 0.0, 20.0, 0.0, 0.5)
    apenas_compra = st.sidebar.checkbox("Apenas com Indicação de Compra (TV)")
    
    # Aplicando os filtros
    df_filtrado = df_acoes.copy()
    if busca:
        df_filtrado = df_filtrado[df_filtrado['Ticker'].str.contains(busca)]
    df_filtrado = df_filtrado[df_filtrado['P/VP'] <= max_pvp]
    df_filtrado = df_filtrado[df_filtrado['Div. Yield (%)'] >= min_dy]
    
    if apenas_compra:
        df_filtrado = df_filtrado[df_filtrado['Indicação de Compra (TV)'] == True]

    st.subheader(f"Resultados Encontrados: {len(df_filtrado)} ações")
    
    # Exibindo a tabela formatada
    colunas_exibir = ['Ticker', 'Cotação', 'P/VP', 'Div. Yield (%)', 'Preço Justo (Graham)', 'Preço Teto (Barsi)', 'Margem Seg. Graham (%)', 'Earnings Yield (%)', 'Indicação de Compra (TV)']
    st.dataframe(df_filtrado[colunas_exibir], use_container_width=True)