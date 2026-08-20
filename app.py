import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import math

st.set_page_config(page_title="Screener Avançado de Investimentos", layout="wide", initial_sidebar_state="expanded")

st.title("📊 Screener Avançado de Investimentos")
st.markdown("Cruzamento fundamentalista e técnico para Ações e Fundos Imobiliários (FIIs).")

# ==========================================
# CONFIGURAÇÃO DE ESTADO (VALORES PADRÃO)
# ==========================================
def iniciar_estado_filtros():
    valores_padrao = {
        # Comuns
        'tipo_ativo': 'Ações',
        'f_busca': '',
        'f_tv': [],
        # Ações
        'f_tamanho': [],
        'f_apenas_ibov': False,
        'f_barsi': False,
        'f_graham': False,
        'f_roe': 10.0,       
        'f_mliq': 5.0,       
        'f_mebit': 5.0,      
        'f_cagr': 0.0,
        'f_pvp': 2.0,        
        'f_pl': 15.0,        
        'f_evebitda': 10.0,  
        'f_dy': 6.0,         
        'f_liq': 1.0,
        # FIIs
        'f_fii_segmento': [],
        'f_fii_pvp_max': 1.10,
        'f_fii_dy_min': 8.0,
        'f_fii_vacancia_max': 15.0,
        'f_fii_liq_min': 1000000.0,
        'f_fii_barsi': False
    }
    for chave, valor in valores_padrao.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor

def limpar_filtros_acoes():
    st.session_state.f_busca = ''
    st.session_state.f_tv = []
    st.session_state.f_tamanho = []
    st.session_state.f_apenas_ibov = False
    st.session_state.f_barsi = False
    st.session_state.f_graham = False
    st.session_state.f_roe = 0.0
    st.session_state.f_mliq = 0.0
    st.session_state.f_mebit = 0.0
    st.session_state.f_cagr = 0.0
    st.session_state.f_pvp = 0.0
    st.session_state.f_pl = 0.0
    st.session_state.f_evebitda = 0.0
    st.session_state.f_dy = 0.0
    st.session_state.f_liq = 0.0

def limpar_filtros_fiis():
    st.session_state.f_busca = ''
    st.session_state.f_tv = []
    st.session_state.f_fii_segmento = []
    st.session_state.f_fii_pvp_max = 0.0
    st.session_state.f_fii_dy_min = 0.0
    st.session_state.f_fii_vacancia_max = 100.0
    st.session_state.f_fii_liq_min = 0.0
    st.session_state.f_fii_barsi = False

iniciar_estado_filtros()

# ==========================================
# FUNÇÕES AUXILIARES COMUNS
# ==========================================
def classificar_tendencia(score):
    if pd.isna(score): return "Sem Dados"
    if score > 0.1: return "Compra"
    elif score < -0.1: return "Venda"
    else: return "Manter"

def limpar_numero(texto):
    val_str = texto.text.strip().replace('%', '').replace('.', '').replace(',', '.')
    if not val_str or val_str == '-' or val_str == 'nan' or val_str == 'N/D': return 0.0
    try: return float(val_str)
    except ValueError: return 0.0

# ==========================================
# EXTRAÇÃO DE DADOS - AÇÕES
# ==========================================
def classificar_tamanho(mcap):
    if pd.isna(mcap) or mcap == 0: return "Desconhecido"
    if mcap >= 15e9: return "Blue Chip"
    elif mcap <= 3e9: return "Small Cap"
    else: return "Mid Cap"

@st.cache_data(ttl=3600)
def obter_carteira_ibov():
    try:
        tabelas = pd.read_html('https://pt.wikipedia.org/wiki/Ibovespa', match='Código')
        return tabelas[0]['Código'].str.strip().tolist()
    except:
        return ['ABEV3', 'B3SA3', 'BBAS3', 'BBDC4', 'ITUB4', 'PETR4', 'VALE3', 'WEGE3']

@st.cache_data(ttl=3600)
def carregar_dados_acoes():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resposta = requests.get('https://www.fundamentus.com.br/resultado.php', headers=headers, timeout=15)
        soup = BeautifulSoup(resposta.text, 'html.parser')
        tabela = soup.find('table', id='resultado')
        
        dados = []
        if tabela:
            for linha in tabela.find_all('tr')[1:]:
                col = linha.find_all('td')
                if len(col) >= 21:
                    dados.append({
                        "Ticker": col[0].text.strip(),
                        "Cotação": limpar_numero(col[1]),
                        "P/L": limpar_numero(col[2]),
                        "P/VP": limpar_numero(col[3]),
                        "Div. Yield (%)": limpar_numero(col[5]),
                        "EV/EBITDA": limpar_numero(col[11]),
                        "Margem EBIT (%)": limpar_numero(col[12]),
                        "Margem Líquida (%)": limpar_numero(col[13]),
                        "Liq. Corrente": limpar_numero(col[14]),
                        "ROE (%)": limpar_numero(col[16]),
                        "Dívida Bruta/Patrimônio": limpar_numero(col[19]),
                        "CAGR Receita 5a (%)": limpar_numero(col[20])
                    })
        df = pd.DataFrame(dados)
    except Exception:
        return pd.DataFrame()

    if df.empty: return df

    try:
        payload_tv = {
            "filter": [{"left": "type", "operation": "equal", "right": "stock"}],
            "options": {"lang": "pt"},
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name", "Recommend.All", "market_cap_basic"]
        }
        resp_tv = requests.post("https://scanner.tradingview.com/brazil/scan", json=payload_tv, timeout=15)
        res_json = resp_tv.json()
        
        tv_dict = {item['d'][0].split(":")[-1]: {'Score TV': item['d'][1], 'Market Cap': item['d'][2]} for item in res_json.get('data', [])}
        df_tv = pd.DataFrame.from_dict(tv_dict, orient='index').reset_index().rename(columns={'index': 'Ticker'})
        df = pd.merge(df, df_tv, on='Ticker', how='left')
    except Exception:
        df['Score TV'] = None
        df['Market Cap'] = 0

    lista_ibov = obter_carteira_ibov()
    df['Recomendação Técnica'] = df['Score TV'].apply(classificar_tendencia)
    df['Categoria'] = df['Market Cap'].apply(classificar_tamanho)
    df['IBOV'] = df['Ticker'].apply(lambda x: "Sim" if x in lista_ibov else "Não")

    df['VPA'] = df.apply(lambda r: r['Cotação'] / r['P/VP'] if r['P/VP'] > 0 else 0, axis=1)
    df['LPA'] = df.apply(lambda r: r['Cotação'] / r['P/L'] if r['P/L'] > 0 else 0, axis=1)
    df['Preço Justo (Graham)'] = df.apply(lambda r: math.sqrt(22.5 * r['VPA'] * r['LPA']) if r['VPA'] > 0 and r['LPA'] > 0 else 0, axis=1)
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    
    return df

# ==========================================
# EXTRAÇÃO DE DADOS - FIIs
# ==========================================
@st.cache_data(ttl=3600)
def carregar_dados_fiis():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # Site específico para Fundos Imobiliários
        resposta = requests.get('https://www.fundamentus.com.br/fii_resultado.php', headers=headers, timeout=15)
        soup = BeautifulSoup(resposta.text, 'html.parser')
        tabela = soup.find('table', id='tabelaResultado')
        if not tabela: tabela = soup.find('table') # Fallback
        
        dados = []
        if tabela:
            for linha in tabela.find_all('tr')[1:]:
                col = linha.find_all('td')
                if len(col) >= 13:
                    dados.append({
                        "Ticker": col[0].text.strip(),
                        "Segmento": col[1].text.strip(),
                        "Cotação": limpar_numero(col[2]),
                        "FFO Yield (%)": limpar_numero(col[3]),
                        "Div. Yield (%)": limpar_numero(col[4]),
                        "P/VP": limpar_numero(col[5]),
                        "Valor de Mercado": limpar_numero(col[6]),
                        "Liquidez Diária (R$)": limpar_numero(col[7]),
                        "Qtd Imóveis": limpar_numero(col[8]),
                        "Cap Rate (%)": limpar_numero(col[11]),
                        "Vacância Média (%)": limpar_numero(col[12])
                    })
        df = pd.DataFrame(dados)
    except Exception:
        return pd.DataFrame()

    if df.empty: return df

    # Tenta puxar o sinal técnico do TradingView para FIIs
    try:
        payload_tv = {
            "filter": [{"left": "type", "operation": "equal", "right": "fund"}], # Fundos
            "options": {"lang": "pt"},
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name", "Recommend.All"]
        }
        resp_tv = requests.post("https://scanner.tradingview.com/brazil/scan", json=payload_tv, timeout=15)
        res_json = resp_tv.json()
        
        tv_dict = {item['d'][0].split(":")[-1]: item['d'][1] for item in res_json.get('data', [])}
        df_tv = pd.DataFrame(list(tv_dict.items()), columns=['Ticker', 'Score TV'])
        df = pd.merge(df, df_tv, on='Ticker', how='left')
    except Exception:
        df['Score TV'] = None

    df['Recomendação Técnica'] = df['Score TV'].apply(classificar_tendencia)
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    
    return df

# ==========================================
# RENDERIZAÇÃO DA BARRA LATERAL (SELETOR PRINCIPAL)
# ==========================================
st.sidebar.title("Configurações")

# O usuário escolhe o motor de busca aqui
tipo_selecionado = st.sidebar.radio(
    "1. Selecione o tipo de ativo:",
    ("Ações", "Fundos Imobiliários (FIIs)"),
    key="tipo_ativo"
)

st.sidebar.markdown("---")

# ==========================================
# LÓGICA E RENDERIZAÇÃO - AÇÕES
# ==========================================
if st.session_state.tipo_ativo == "Ações":
    with st.spinner("Atualizando base de Ações..."):
        df_acoes = carregar_dados_acoes()

    if df_acoes.empty:
        st.warning("Falha ao carregar Ações.")
    else:
        st.sidebar.header("🔍 Filtros de Ações")
        st.sidebar.button("🗑️ Limpar Filtros de Ações", on_click=limpar_filtros_acoes, type="primary", use_container_width=True)
        
        busca = st.sidebar.text_input("Buscar Ticker (ex: BBAS3)", key='f_busca').upper()
        
        st.sidebar.subheader("📊 Classificação e Índice")
        apenas_ibov = st.sidebar.checkbox("Apenas ações do IBOV", key='f_apenas_ibov')
        opcoes_tamanho = st.sidebar.multiselect("Tamanho", ["Blue Chip", "Mid Cap", "Small Cap"], key='f_tamanho')
        
        st.sidebar.subheader("📈 Análise Técnica")
        opcoes_tv = st.sidebar.multiselect("Sinal do TradingView", ["Compra", "Venda", "Manter"], key='f_tv')

        st.sidebar.subheader("🎯 Metodologias de Valuation")
        filtro_barsi = st.sidebar.checkbox("Abaixo do Preço Teto (Barsi)", key='f_barsi')
        filtro_graham = st.sidebar.checkbox("Abaixo do Preço Justo (Graham)", key='f_graham')
        
        st.sidebar.subheader("💼 Filtros Fundamentalistas")
        with st.sidebar.expander("Rentabilidade & Margens"):
            min_roe = st.number_input("ROE Mínimo (%)", step=1.0, key='f_roe')
            min_mebit = st.number_input("Margem EBIT Mín. (%)", step=1.0, key='f_mebit')
            min_mliq = st.number_input("Margem Líquida Mín. (%)", step=1.0, key='f_mliq')
            min_cagr = st.number_input("CAGR Receita Mínimo (%)", step=1.0, key='f_cagr')

        with st.sidebar.expander("Preço & Múltiplos"):
            max_pvp = st.number_input("P/VP Máximo (0 = sem limite)", step=0.5, key='f_pvp')
            max_pl = st.number_input("P/L Máximo (0 = sem limite)", step=1.0, key='f_pl')
            max_evebitda = st.number_input("EV/EBITDA Máximo (0 = sem limite)", step=1.0, key='f_evebitda')
            min_dy = st.number_input("Dividend Yield Mín. (%)", step=0.5, key='f_dy')

        with st.sidebar.expander("Saúde Financeira"):
            min_liq = st.number_input("Liquidez Corrente Mínima", step=0.1, key='f_liq')

        # Aplicando filtros
        df_filtrado = df_acoes.copy()
        if busca: df_filtrado = df_filtrado[df_filtrado['Ticker'].str.contains(busca)]
        if apenas_ibov: df_filtrado = df_filtrado[df_filtrado['IBOV'] == "Sim"]
        if opcoes_tamanho: df_filtrado = df_filtrado[df_filtrado['Categoria'].isin(opcoes_tamanho)]
        if opcoes_tv: df_filtrado = df_filtrado[df_filtrado['Recomendação Técnica'].isin(opcoes_tv)]
        if filtro_barsi: df_filtrado = df_filtrado[df_filtrado['Cotação'] < df_filtrado['Preço Teto (Barsi)']]
        if filtro_graham: df_filtrado = df_filtrado[df_filtrado['Cotação'] < df_filtrado['Preço Justo (Graham)']]
        
        if min_roe > 0: df_filtrado = df_filtrado[df_filtrado['ROE (%)'] >= min_roe]
        if min_mebit > 0: df_filtrado = df_filtrado[df_filtrado['Margem EBIT (%)'] >= min_mebit]
        if min_mliq > 0: df_filtrado = df_filtrado[df_filtrado['Margem Líquida (%)'] >= min_mliq]
        if min_cagr > 0: df_filtrado = df_filtrado[df_filtrado['CAGR Receita 5a (%)'] >= min_cagr]
        if max_pvp > 0: df_filtrado = df_filtrado[df_filtrado['P/VP'] <= max_pvp]
        if max_pl > 0: df_filtrado = df_filtrado[df_filtrado['P/L'] <= max_pl]
        if max_evebitda > 0: df_filtrado = df_filtrado[df_filtrado['EV/EBITDA'] <= max_evebitda]
        if min_dy > 0: df_filtrado = df_filtrado[df_filtrado['Div. Yield (%)'] >= min_dy]
        if min_liq > 0: df_filtrado = df_filtrado[df_filtrado['Liq. Corrente'] >= min_liq]

        st.subheader(f"🏢 Ações Encontradas: {len(df_filtrado)}")
        colunas_exibir = [
            'Ticker', 'IBOV', 'Categoria', 'Recomendação Técnica', 'Cotação', 'Preço Justo (Graham)', 'Preço Teto (Barsi)', 
            'Div. Yield (%)', 'P/L', 'P/VP', 'EV/EBITDA', 'ROE (%)', 'Margem EBIT (%)', 'Margem Líquida (%)', 
            'Liq. Corrente', 'Dívida Bruta/Patrimônio', 'CAGR Receita 5a (%)'
        ]
        st.dataframe(
            df_filtrado[colunas_exibir].style.format({
                "Cotação": "R$ {:.2f}", "Preço Justo (Graham)": "R$ {:.2f}", "Preço Teto (Barsi)": "R$ {:.2f}",
                "Div. Yield (%)": "{:.1f}%", "ROE (%)": "{:.1f}%", "Margem EBIT (%)": "{:.1f}%", "Margem Líquida (%)": "{:.1f}%",
                "CAGR Receita 5a (%)": "{:.1f}%", "P/L": "{:.2f}", "P/VP": "{:.2f}", "EV/EBITDA": "{:.2f}",
                "Liq. Corrente": "{:.2f}", "Dívida Bruta/Patrimônio": "{:.2f}"
            }), use_container_width=True, height=600
        )

# ==========================================
# LÓGICA E RENDERIZAÇÃO - FUNDOS IMOBILIÁRIOS (FIIs)
# ==========================================
else:
    with st.spinner("Atualizando base de FIIs..."):
        df_fiis = carregar_dados_fiis()

    if df_fiis.empty:
        st.warning("Falha ao carregar FIIs.")
    else:
        st.sidebar.header("🏢 Filtros de FIIs")
        st.sidebar.button("🗑️ Limpar Filtros de FIIs", on_click=limpar_filtros_fiis, type="primary", use_container_width=True)
        
        busca = st.sidebar.text_input("Buscar FII (ex: MXRF11)", key='f_busca').upper()
        
        # Filtro de Segmento (Lista dinâmica baseada nos dados)
        segmentos_disp = sorted(df_fiis['Segmento'].unique().tolist())
        opcoes_seg = st.sidebar.multiselect("Filtrar por Segmento", segmentos_disp, key='f_fii_segmento')
        
        st.sidebar.subheader("📈 Análise Técnica")
        opcoes_tv = st.sidebar.multiselect("Sinal do TradingView", ["Compra", "Venda", "Manter"], key='f_tv')

        st.sidebar.subheader("🎯 Metodologias")
        filtro_barsi = st.sidebar.checkbox("Abaixo do Preço Teto (Barsi)", key='f_fii_barsi')

        st.sidebar.subheader("💼 Filtros Fundamentalistas")
        min_dy = st.sidebar.number_input("Dividend Yield Mín. (%)", step=0.5, key='f_fii_dy_min')
        max_pvp = st.sidebar.number_input("P/VP Máximo (0 = sem limite)", step=0.05, key='f_fii_pvp_max')
        max_vac = st.sidebar.number_input("Vacância Média Máxima (%) (0 = sem limite)", step=1.0, key='f_fii_vacancia_max')
        min_liq = st.sidebar.number_input("Liquidez Diária Mín. (R$)", step=100000.0, format="%f", key='f_fii_liq_min')

        # Aplicando filtros
        df_filtrado = df_fiis.copy()
        if busca: df_filtrado = df_filtrado[df_filtrado['Ticker'].str.contains(busca)]
        if opcoes_seg: df_filtrado = df_filtrado[df_filtrado['Segmento'].isin(opcoes_seg)]
        if opcoes_tv: df_filtrado = df_filtrado[df_filtrado['Recomendação Técnica'].isin(opcoes_tv)]
        if filtro_barsi: df_filtrado = df_filtrado[df_filtrado['Cotação'] < df_filtrado['Preço Teto (Barsi)']]
        
        if min_dy > 0: df_filtrado = df_filtrado[df_filtrado['Div. Yield (%)'] >= min_dy]
        if max_pvp > 0: df_filtrado = df_filtrado[df_filtrado['P/VP'] <= max_pvp]
        if max_vac > 0: df_filtrado = df_filtrado[df_filtrado['Vacância Média (%)'] <= max_vac]
        if min_liq > 0: df_filtrado = df_filtrado[df_filtrado['Liquidez Diária (R$)'] >= min_liq]

        st.subheader(f"🏢 FIIs Encontrados: {len(df_filtrado)}")
        colunas_exibir = [
            'Ticker', 'Segmento', 'Recomendação Técnica', 'Cotação', 'Preço Teto (Barsi)', 
            'Div. Yield (%)', 'P/VP', 'Vacância Média (%)', 'Liquidez Diária (R$)', 
            'FFO Yield (%)', 'Qtd Imóveis', 'Cap Rate (%)'
        ]
        
        st.dataframe(
            df_filtrado[colunas_exibir].style.format({
                "Cotação": "R$ {:.2f}", "Preço Teto (Barsi)": "R$ {:.2f}",
                "Div. Yield (%)": "{:.1f}%", "P/VP": "{:.2f}", "Vacância Média (%)": "{:.1f}%", 
                "FFO Yield (%)": "{:.1f}%", "Cap Rate (%)": "{:.1f}%",
                "Liquidez Diária (R$)": "R$ {:,.2f}" # Formatação com separador de milhar
            }), use_container_width=True, height=600
        )
