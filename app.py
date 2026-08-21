import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import math

st.set_page_config(page_title="Screener Avançado", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 0. INICIALIZAÇÃO ROBUSTA DO ESTADO
# ==========================================
def init_session_state():
    defaults = {
        'f_liq_global': 1000000.0,
        'f_liq_global_fii': 500000.0,
        'f_busca': '', 'f_tv': [], 'f_tend_d': [], 'f_tend_s': [], 'f_tend_m': [],
        'f_tamanho': [], 'f_setor': [], 'f_apenas_ibov': False, 'f_barsi': False, 'f_graham': False,
        'f_roe': 8.0, 'f_mebit': 5.0, 'f_mliq': 0.0, 'f_cagr': 0.0, 'f_evebitda': 0.0, 'f_dy': 0.0,
        'f_pvp_max': 5.0, 'f_pl_min': 0.1, 'f_pl_max': 20.0, 'f_liq': 1.0,
        'f_fii_segmento': [], 'f_fii_barsi': False, 'f_fii_pvp_max': 1.10, 'f_fii_dy_min': 8.0,
        'f_fii_ffo_min': 7.0, 'f_fii_vacancia_max': 15.0
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

st.title("📊 Screener Avançado de Investimentos")

# Funções Auxiliares
def limpar_numero(texto):
    try:
        val_str = texto.text.strip().replace('%', '').replace('.', '').replace(',', '.')
        return float(val_str) if val_str and val_str not in ['-', 'nan', 'N/D'] else 0.0
    except: return 0.0

def colorir_margem(val):
    try:
        # Tenta extrair o número de strings formatadas como "R$ 10,00" ou "+15%"
        clean_val = str(val).replace('R$', '').replace('%', '').replace('+', '').strip()
        num = float(clean_val)
        if num > 0: return 'color: #00C851; font-weight: bold;'
        if num < 0: return 'color: #ff4444; font-weight: bold;'
    except: pass
    return ''

# ==========================================
# 3. CARGA DE DADOS
# ==========================================
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
        df['IBOV'] = 'Não'
        df['Tipo'] = 'Mid Cap'
        df['Setor'] = 'Outros'
        df['V. Graham'] = df.apply(lambda r: math.sqrt(22.5 * (r['Preço']/r['P/VP'] if r['P/VP']>0 else 1) * (r['Preço']/r['P/L'] if r['P/L']>0 else 1)), axis=1)
        df['T. Barsi'] = df.apply(lambda r: (r['Preço'] * (r['DY']/100)) / 0.06, axis=1)
        df['M. Graham'] = ((df['V. Graham'] - df['Preço']) / df['Preço']) * 100
        df['M. Barsi'] = ((df['T. Barsi'] - df['Preço']) / df['Preço']) * 100
        df['DY Mês'] = df.apply(lambda r: (math.pow(1 + (r['DY']/100), 1/12) - 1) * 100, axis=1)
        df['T. Mês'] = '🟢 Alta'; df['T. Sem.'] = '🟢 Alta'; df['T. Dia'] = '🟢 Alta'; df['Sinal'] = 'Manter'
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
        df['T. Mês'] = '🟢 Alta'; df['T. Sem.'] = '🟢 Alta'; df['T. Dia'] = '🟢 Alta'; df['Sinal'] = 'Manter'
        return df
    except: return pd.DataFrame()

# ==========================================
# 4. UI
# ==========================================
st.sidebar.title("MERCADO")
tipo_ativo = st.sidebar.radio("Selecione:", ("Ações", "Fundos Imobiliários (FIIs)"), key="tipo_ativo", label_visibility="collapsed")

if tipo_ativo == "Ações":
    df = carregar_dados_acoes()
    st.sidebar.header("FILTROS DE AÇÕES")
    if st.sidebar.button("🧹 Limpar Tudo"): 
        # Lógica de reset que não altera liquidez
        st.session_state.f_liq_global = 1000000.0
        st.rerun()
    
    colunas_disponiveis = {
        'Ticker': 'Ticker', 'Preço': 'Preço', 'IBOV': 'IBOV', 'Tipo': 'Tipo', 'Setor': 'Setor', 
        'P/VP': 'P/VP', 'DY': 'DY', 'DY Mês': 'DY Mês', 'V. Graham': 'V. Graham', 
        'M. Graham': 'M. Graham', 'T. Barsi': 'T. Barsi', 'M. Barsi': 'M. Barsi', 
        'P/L': 'P/L', 'ROE': 'ROE', 'M. EBIT': 'M. EBIT', 'Liq Corr.': 'Liq Corr.', 'Liq Diária': 'Liq Diária',
        'T. Mês': 'T. Mês', 'T. Sem.': 'T. Sem.', 'T. Dia': 'T. Dia', 'Sinal': 'Sinal'
    }
    
    # Ordem solicitada
    ordem_padrao = ['Ticker', 'Preço', 'IBOV', 'Tipo', 'Setor', 'P/VP', 'DY', 'DY Mês', 'V. Graham', 'M. Graham', 'T. Barsi', 'M. Barsi', 'P/L', 'ROE', 'M. EBIT', 'Liq Corr.', 'Liq Diária', 'T. Mês', 'T. Sem.', 'T. Dia', 'Sinal']
    escolhidas = st.sidebar.multiselect("Ocultar/Exibir Colunas", ordem_padrao, default=['Ticker', 'Preço', 'IBOV', 'P/VP', 'DY', 'V. Graham', 'T. Barsi', 'P/L', 'ROE', 'M. EBIT', 'Liq Corr.', 'Liq Diária', 'T. Mês', 'T. Sem.', 'T. Dia', 'Sinal'])
    
    liq = st.sidebar.number_input("Liquidez Mínima (R$)", value=st.session_state.f_liq_global, step=500000.0, key='f_liq_global')
    
    df_f = df[df['Liq Diária'] >= liq]
    st.dataframe(df_f[escolhidas].style.map(colorir_margem, subset=[c for c in ['M. Graham', 'M. Barsi'] if c in escolhidas]), hide_index=True, use_container_width=False)

else:
    df = carregar_dados_fiis()
    st.sidebar.header("FILTROS DE FIIs")
    if st.sidebar.button("🧹 Limpar Tudo"):
        st.session_state.f_liq_global_fii = 500000.0
        st.rerun()

    colunas_disponiveis_fii = {
        'Ticker': 'Ticker', 'Preço': 'Preço', 'Segmento': 'Segmento', 'P/VP': 'P/VP', 'DY': 'DY', 
        'DY Mês': 'DY Mês', 'FFO Yield': 'FFO Yield', 'T. Barsi': 'T. Barsi', 
        'M. Barsi': 'M. Barsi', 'Vacância': 'Vacância', 'Liq. Diária': 'Liq. Diária', 
        'T. Mês': 'T. Mês', 'T. Sem.': 'T. Sem.', 'T. Dia': 'T. Dia', 'Sinal': 'Sinal'
    }
    ordem_padrao_fii = ['Ticker', 'Preço', 'Segmento', 'P/VP', 'DY', 'DY Mês', 'FFO Yield', 'T. Barsi', 'M. Barsi', 'Vacância', 'Liq. Diária', 'T. Mês', 'T. Sem.', 'T. Dia', 'Sinal']
    
    escolhidas_fii = st.sidebar.multiselect("Ocultar/Exibir Colunas", ordem_padrao_fii, default=ordem_padrao_fii)
    
    liq_fii = st.sidebar.number_input("Liquidez Mínima (R$)", value=st.session_state.f_liq_global_fii, step=100000.0, key='f_liq_global_fii')
    
    df_f = df[df['Liq. Diária'] >= liq_fii]
    st.dataframe(df_f[escolhidas_fii].style.map(colorir_margem, subset=[c for c in ['M. Barsi'] if c in escolhidas_fii]), hide_index=True, use_container_width=False)
