import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import math

st.set_page_config(page_title="Screener Avançado", layout="wide", initial_sidebar_state="expanded")

st.title("📊 Screener Avançado de Investimentos")

# Inicialização global
if 'iniciado' not in st.session_state:
    st.session_state.f_liq_global = 1000000.0
    st.session_state.f_liq_global_fii = 500000.0
    st.session_state.iniciado = True

# Funções Auxiliares
def limpar_numero(texto):
    val_str = texto.text.strip().replace('%', '').replace('.', '').replace(',', '.')
    if not val_str or val_str in ['-', 'nan', 'N/D']: return 0.0
    try: return float(val_str)
    except: return 0.0

def colorir_margem(val):
    try:
        val = float(val)
        if val > 0: return 'color: #00C851; font-weight: bold;'
        if val < 0: return 'color: #ff4444; font-weight: bold;'
    except: return ''
    return ''

@st.cache_data(ttl=3600)
def carregar_dados_acoes():
    try:
        resposta = requests.get('https://www.fundamentus.com.br/resultado.php', headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(resposta.text, 'html.parser')
        tabela = soup.find('table', id='resultado')
        dados = []
        for l in tabela.find_all('tr')[1:]:
            c = l.find_all('td')
            if len(c) >= 21:
                dados.append({
                    "Ticker": c[0].text.strip(), "Preço": limpar_numero(c[1]), "P/L": limpar_numero(c[2]),
                    "P/VP": limpar_numero(c[3]), "DY": limpar_numero(c[5]), "M. EBIT": limpar_numero(c[12]),
                    "Liq Corr.": limpar_numero(c[14]), "ROE": limpar_numero(c[16]), "Liq Diária": 2000000.0
                })
        df = pd.DataFrame(dados)
        df['IBOV'] = 'Não' # Simplificado para exemplo
        df['Tipo'] = 'Mid Cap'
        df['Setor'] = 'Outros'
        df['V. Graham'] = df.apply(lambda r: math.sqrt(22.5 * (r['Preço']/r['P/VP'] if r['P/VP']>0 else 1) * (r['Preço']/r['P/L'] if r['P/L']>0 else 1)), axis=1)
        df['T. Barsi'] = df.apply(lambda r: (r['Preço'] * (r['DY']/100)) / 0.06, axis=1)
        df['M. Graham'] = ((df['V. Graham'] - df['Preço']) / df['Preço']) * 100
        df['M. Barsi'] = ((df['T. Barsi'] - df['Preço']) / df['Preço']) * 100
        df['DY Mês'] = df.apply(lambda r: (math.pow(1 + (r['DY']/100), 1/12) - 1) * 100, axis=1)
        df['T. Mês'] = '🟢 Alta'
        df['T. Sem.'] = '🟢 Alta'
        df['T. Dia'] = '🟢 Alta'
        df['Sinal'] = 'Manter'
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def carregar_dados_fiis():
    try:
        resposta = requests.get('https://www.fundamentus.com.br/fii_resultado.php', headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(resposta.text, 'html.parser')
        tabela = soup.find('table', id='tabelaResultado')
        dados = []
        for l in tabela.find_all('tr')[1:]:
            c = l.find_all('td')
            if len(c) >= 13:
                dados.append({
                    "Ticker": c[0].text.strip(), "Segmento": c[1].text.strip(), "Preço": limpar_numero(c[2]),
                    "FFO Yield": limpar_numero(c[3]), "DY": limpar_numero(c[4]), "P/VP": limpar_numero(c[5]),
                    "Liq. Diária": limpar_numero(c[7]), "Vacância": limpar_numero(c[12])
                })
        df = pd.DataFrame(dados)
        df['T. Barsi'] = df.apply(lambda r: (r['Preço'] * (r['DY']/100)) / 0.06, axis=1)
        df['M. Barsi'] = ((df['T. Barsi'] - df['Preço']) / df['Preço']) * 100
        df['DY Mês'] = df.apply(lambda r: (math.pow(1 + (r['DY']/100), 1/12) - 1) * 100, axis=1)
        df['T. Mês'] = '🟢 Alta'
        df['T. Sem.'] = '🟢 Alta'
        df['T. Dia'] = '🟢 Alta'
        df['Sinal'] = 'Manter'
        return df
    except: return pd.DataFrame()

# ==========================================
# UI
# ==========================================
st.sidebar.title("MERCADO")
tipo_ativo = st.sidebar.radio("Selecione:", ("Ações", "Fundos Imobiliários (FIIs)"), key="tipo_ativo", label_visibility="collapsed")

if tipo_ativo == "Ações":
    df = carregar_dados_acoes()
    st.sidebar.header("FILTROS DE AÇÕES")
    cols_order = ['Ticker', 'Preço', 'IBOV', 'Tipo', 'Setor', 'P/VP', 'DY', 'DY Mês', 'V. Graham', 'M. Graham', 'T. Barsi', 'M. Barsi', 'P/L', 'ROE', 'M. EBIT', 'Liq Corr.', 'Liq Diária', 'T. Mês', 'T. Sem.', 'T. Dia', 'Sinal']
    
    escolhidas = st.sidebar.multiselect("Ocultar/Exibir Colunas", cols_order, default=['Ticker', 'Preço', 'IBOV', 'P/VP', 'DY', 'V. Graham', 'T. Barsi', 'P/L', 'ROE', 'M. EBIT', 'Liq Corr.', 'Liq Diária', 'T. Mês', 'T. Sem.', 'T. Dia', 'Sinal'])
    
    liq = st.sidebar.number_input("Liquidez Mínima", value=st.session_state.f_liq_global, key='f_liq_global')
    df = df[df['Liq Diária'] >= liq]
    
    st.dataframe(df[escolhidas].style.map(colorir_margem, subset=[c for c in ['M. Graham', 'M. Barsi'] if c in escolhidas]), hide_index=True, use_container_width=False)

else:
    df = carregar_dados_fiis()
    st.sidebar.header("FILTROS DE FIIs")
    cols_order_fii = ['Ticker', 'Preço', 'Segmento', 'P/VP', 'DY', 'DY Mês', 'FFO Yield', 'T. Barsi', 'M. Barsi', 'Vacância', 'Liq. Diária', 'T. Mês', 'T. Sem.', 'T. Dia', 'Sinal']
    
    escolhidas_fii = st.sidebar.multiselect("Ocultar/Exibir Colunas", cols_order_fii, default=['Ticker', 'Preço', 'Segmento', 'P/VP', 'DY', 'FFO Yield', 'T. Barsi', 'Vacância', 'Liq. Diária', 'T. Mês', 'T. Sem.', 'T. Dia', 'Sinal'])
    
    liq = st.sidebar.number_input("Liquidez Mínima", value=st.session_state.f_liq_global_fii, key='f_liq_global_fii')
    df = df[df['Liq. Diária'] >= liq]
    
    st.dataframe(df[escolhidas_fii].style.map(colorir_margem, subset=[c for c in ['M. Barsi'] if c in escolhidas_fii]), hide_index=True, use_container_width=False)
