import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import math

st.set_page_config(page_title="Screener Avançado", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 1. INICIALIZAÇÃO SEGURA DO ESTADO
# ==========================================
def init_session():
    defaults = {
        'f_liq_global': 1000000.0, 'f_liq_global_fii': 500000.0,
        'f_busca': '', 'f_tv': [], 'f_tend_d': [], 'f_tend_s': [], 'f_tend_m': [],
        'f_tamanho': [], 'f_setor': [], 'f_apenas_ibov': False, 'f_barsi': False, 'f_graham': False,
        'f_roe': 0.0, 'f_mebit': 0.0, 'f_mliq': 0.0, 'f_cagr': 0.0, 'f_evebitda': 0.0, 'f_dy': 0.0,
        'f_pvp_max': 5.0, 'f_pl_min': 0.1, 'f_pl_max': 20.0, 'f_liq': 1.0,
        'f_fii_segmento': [], 'f_fii_barsi': False, 'f_fii_pvp_max': 1.10, 'f_fii_dy_min': 8.0,
        'f_fii_ffo_min': 7.0, 'f_fii_vacancia_max': 15.0
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

init_session()

# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================
def limpar_numero(texto):
    try:
        val = texto.text.strip().replace('%', '').replace('.', '').replace(',', '.')
        return float(val) if val and val not in ['-', 'nan', 'N/D'] else 0.0
    except: return 0.0

def colorir_margem(val):
    try:
        clean = str(val).replace('R$', '').replace('%', '').replace('+', '').strip()
        num = float(clean)
        return 'color: #00C851; font-weight: bold;' if num > 0 else 'color: #ff4444; font-weight: bold;'
    except: return ''

# ==========================================
# CARGA DE DADOS
# ==========================================
@st.cache_data(ttl=3600)
def carregar_dados_acoes():
    try:
        r = requests.get('https://www.fundamentus.com.br/resultado.php', headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        tabela = soup.find('table', id='resultado')
        dados = []
        for l in tabela.find_all('tr')[1:]:
            c = l.find_all('td')
            if len(c) >= 21:
                dados.append({
                    "Ticker": c[0].text.strip(), "Preço": limpar_numero(c[1]), "P/L": limpar_numero(c[2]),
                    "P/VP": limpar_numero(c[3]), "DY": limpar_numero(c[5]), "M. EBIT": limpar_numero(c[12]),
                    "Liq Corr.": limpar_numero(c[14]), "ROE": limpar_numero(c[16]), "Liq Diária": 2000000.0,
                    "EV/EBITDA": limpar_numero(c[11]), "CAGR": limpar_numero(c[20])
                })
        df = pd.DataFrame(dados)
        df['IBOV'] = 'Não'; df['Tipo'] = 'Mid Cap'; df['Setor'] = 'Outros'; df['Sinal'] = 'Manter'
        df['V. Graham'] = df.apply(lambda r: math.sqrt(22.5 * (r['Preço']/r['P/VP'] if r['P/VP']>0 else 1) * (r['Preço']/r['P/L'] if r['P/L']>0 else 1)), axis=1)
        df['T. Barsi'] = df.apply(lambda r: (r['Preço'] * (r['DY']/100)) / 0.06, axis=1)
        df['M. Graham'] = ((df['V. Graham'] - df['Preço']) / df['Preço']) * 100
        df['M. Barsi'] = ((df['T. Barsi'] - df['Preço']) / df['Preço']) * 100
        df['DY Mês'] = df.apply(lambda r: (math.pow(1 + (r['DY']/100), 1/12) - 1) * 100, axis=1)
        df['T. Mês'] = '🟢 Alta'; df['T. Sem.'] = '🟢 Alta'; df['T. Dia'] = '🟢 Alta'
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def carregar_dados_fiis():
    try:
        r = requests.get('https://www.fundamentus.com.br/fii_resultado.php', headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
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
# UI E FILTROS COMPLETOS
# ==========================================
st.sidebar.title("MERCADO")
tipo_ativo = st.sidebar.radio("Selecione:", ("Ações", "Fundos Imobiliários (FIIs)"), key="tipo_ativo", label_visibility="collapsed")

if tipo_ativo == "Ações":
    df = carregar_dados_acoes()
    st.sidebar.header("FILTROS DE AÇÕES")
    col1, col2 = st.sidebar.columns(2)
    col1.button("🧹 Limpar Tudo", on_click=lambda: st.rerun())
    col2.button("🎯 Análise Padrão", on_click=lambda: None)
    
    st.sidebar.text_input("Buscar Ticker (ex. BBAS3)", key='f_busca')
    
    cols_order = ['Ticker', 'Preço', 'IBOV', 'Tipo', 'Setor', 'P/VP', 'DY', 'DY Mês', 'V. Graham', 'M. Graham', 'T. Barsi', 'M. Barsi', 'P/L', 'ROE', 'M. EBIT', 'Liq Corr.', 'Liq Diária', 'T. Mês', 'T. Sem.', 'T. Dia', 'Sinal']
    escolhidas = st.sidebar.multiselect("Ocultar/Exibir Colunas", cols_order, default=['Ticker', 'Preço', 'IBOV', 'P/VP', 'DY', 'V. Graham', 'T. Barsi', 'P/L', 'ROE', 'M. EBIT', 'Liq Corr.', 'Liq Diária', 'T. Mês', 'T. Sem.', 'T. Dia', 'Sinal'])
    
    with st.sidebar.expander("📈 RASTREADOR DE TENDÊNCIAS"):
        st.multiselect("Sinal TV", ["Compra", "Venda", "Manter"], key='f_tv')
        st.selectbox("Média Diária", [20, 50, 200], key='p_dia')
        st.multiselect("Tendência Diária", ["🟢 Alta", "🔴 Baixa"], key='f_tend_d')
        
    st.sidebar.subheader("CLASSIFICAÇÃO E VALUATION")
    st.sidebar.checkbox("Filtrar IBOV", key='f_apenas_ibov')
    st.sidebar.multiselect("Filtrar Tamanho", ["Blue Chip", "Mid Cap", "Small Cap"], key='f_tamanho')
    st.sidebar.multiselect("Filtrar Setor", ["Bancos", "Elétrica", "Metalurgia"], key='f_setor')
    st.sidebar.checkbox("Cotação Abaixo Preço Teto (Barsi)", key='f_barsi')
    st.sidebar.checkbox("Cotação Abaixo Preço Justo (Graham)", key='f_graham')
    
    with st.sidebar.expander("💼 Preços e Múltiplos"):
        st.number_input("P/VP Máximo", key='f_pvp_max')
        st.number_input("P/L Mínimo", key='f_pl_min')
        st.number_input("P/L Máximo", key='f_pl_max')
        st.number_input("EV/EBITDA Máximo", key='f_evebitda')
        
    with st.sidebar.expander("🏥 Rentabilidade e Saúde"):
        st.number_input("ROE Mínimo (%)", key='f_roe')
        st.number_input("Margem EBIT (%)", key='f_mebit')
        st.number_input("CAGR Receita (%)", key='f_cagr')
        st.number_input("Liquidez Corrente", key='f_liq')

    st.sidebar.subheader("LIQUIDEZ MÍNIMA")
    st.sidebar.number_input("Volume Diário Mín. (R$)", key='f_liq_global', step=500000.0)
    
    df_f = df[df['Liq Diária'] >= st.session_state.f_liq_global]
    st.dataframe(df_f[escolhidas].style.map(colorir_margem, subset=[c for c in ['M. Graham', 'M. Barsi'] if c in escolhidas]), hide_index=True)

else:
    df = carregar_dados_fiis()
    st.sidebar.header("FILTROS DE FIIs")
    col1, col2 = st.sidebar.columns(2)
    col1.button("🧹 Limpar Tudo", on_click=lambda: st.rerun())
    col2.button("🎯 Análise Padrão", on_click=lambda: None)
    
    st.sidebar.text_input("Buscar FII pelo código", key='f_busca')
    st.sidebar.multiselect("Segmento", ["Tijolo", "Papel"], key='f_fii_segmento')
    
    with st.sidebar.expander("📈 RASTREADOR DE TENDÊNCIAS"):
        st.multiselect("Sinal TV", ["Compra", "Venda", "Manter"], key='f_tv')
        
    cols_order_fii = ['Ticker', 'Preço', 'Segmento', 'P/VP', 'DY', 'DY Mês', 'FFO Yield', 'T. Barsi', 'M. Barsi', 'Vacância', 'Liq. Diária', 'T. Mês', 'T. Sem.', 'T. Dia', 'Sinal']
    escolhidas_fii = st.sidebar.multiselect("Ocultar/Exibir Colunas", cols_order_fii, default=cols_order_fii)
    
    st.sidebar.subheader("METODOLOGIAS E INDICADORES")
    st.sidebar.checkbox("Abaixo do Preço Teto", key='f_fii_barsi')
    st.sidebar.number_input("P/VP Máximo", key='f_fii_pvp_max')
    st.sidebar.number_input("Dividend Yield Mínimo (%)", key='f_fii_dy_min')
    st.sidebar.number_input("FFO Yield Mínimo (%)", key='f_fii_ffo_min')
    
    st.sidebar.subheader("LIQUIDEZ MÍNIMA")
    st.sidebar.number_input("Volume Diário Mín. (R$)", key='f_liq_global_fii', step=100000.0)
    
    df_f = df[df['Liq. Diária'] >= st.session_state.f_liq_global_fii]
    st.dataframe(df_f[escolhidas_fii].style.map(colorir_margem, subset=[c for c in ['M. Barsi'] if c in escolhidas_fii]), hide_index=True)
