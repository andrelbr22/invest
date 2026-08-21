import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import math

st.set_page_config(page_title="Screener Avançado", layout="wide", initial_sidebar_state="expanded")

st.title("📊 Screener Avançado de Investimentos")

# Inicialização global robusta (Força os valores corretos)
if 'tipo_ativo' not in st.session_state:
    st.session_state.tipo_ativo = 'Ações'
    st.session_state.f_liq_global = 1000000.0       # Ações: R$ 1 Milhão
    st.session_state.f_liq_global_fii = 500000.0    # FIIs: R$ 500 Mil
    st.session_state.iniciado = True

# Funções de Setup/Limpeza omitidas para brevidade, mas mantidas no seu arquivo...
# (O código abaixo já contempla a correção na função de FIIs)

# ==========================================
# 4. EXTRAÇÃO DE DADOS (FIIs - CORRIGIDA)
# ==========================================
@st.cache_data(ttl=3600)
def carregar_dados_fiis():
    try:
        resposta = requests.get('https://www.fundamentus.com.br/fii_resultado.php', headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(resposta.text, 'html.parser')
        tabela = soup.find('table', id='tabelaResultado') or soup.find('table')
        dados = []
        if tabela:
            for l in tabela.find_all('tr')[1:]:
                c = l.find_all('td')
                if len(c) >= 13:
                    dados.append({
                        "Ticker": c[0].text.strip(), "Segmento": c[1].text.strip(), "Cotação": limpar_numero(c[2]),
                        "FFO Yield (%)": limpar_numero(c[3]), "Div. Yield (%)": limpar_numero(c[4]), "P/VP": limpar_numero(c[5]),
                        "Liquidez Diária (R$)": limpar_numero(c[7]), "Cap Rate (%)": limpar_numero(c[11]), "Vacância Média (%)": limpar_numero(c[12])
                    })
        df = pd.DataFrame(dados)
    except: return pd.DataFrame()
    if df.empty: return df

    # Tenta pegar dados técnicos do TradingView (sem sobrescrever liquidez)
    try:
        payload = {"filter": [{"left": "type", "operation": "equal", "right": "fund"}], "options": {"lang": "pt"}, "symbols": {"query": {"types": []}, "tickers": []}, "columns": ["name", "Recommend.All", "SMA20", "SMA50", "SMA200", "SMA20|1W", "SMA50|1W", "SMA20|1M", "SMA50|1M"]}
        resp = requests.post("https://scanner.tradingview.com/brazil/scan", json=payload, timeout=15).json()
        tv_dict = {item['d'][0].split(":")[-1]: {
            'Score TV': item['d'][1], 'SMA20': item['d'][2], 'SMA50': item['d'][3], 'SMA200': item['d'][4],
            'SMA20|1W': item['d'][5], 'SMA50|1W': item['d'][6], 'SMA20|1M': item['d'][7], 'SMA50|1M': item['d'][8]
        } for item in resp.get('data', [])}
        
        # Merge mantendo apenas colunas técnicas do TV
        df_tv = pd.DataFrame.from_dict(tv_dict, orient='index').reset_index().rename(columns={'index': 'Ticker'})
        df = pd.merge(df, df_tv, on='Ticker', how='left')
    except:
        pass

    # !!! CORREÇÃO AQUI !!! 
    # Forçamos a coluna "Liq. Diária" a ser exatamente a "Liquidez Diária (R$)" do Fundamentus
    df['Liq. Diária'] = df['Liquidez Diária (R$)']

    df['Sinal Técnico'] = df['Score TV'].apply(classificar_sinal)
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    df['Margem Barsi (%)'] = df.apply(lambda r: ((r['Preço Teto (Barsi)'] - r['Cotação']) / r['Cotação']) * 100 if r['Cotação'] > 0 and r['Preço Teto (Barsi)'] > 0 else 0, axis=1)
    df['DY Mensal Est. (%)'] = df.apply(lambda r: (math.pow(1 + (r['Div. Yield (%)'] / 100), 1/12) - 1) * 100 if r['Div. Yield (%)'] > 0 else 0, axis=1)
    
    return df

# ... Restante do código (ajuste a função no bloco correspondente na sua barra lateral)
