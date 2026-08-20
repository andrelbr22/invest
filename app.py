import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import math

st.set_page_config(page_title="Screener Avançado de Ações", layout="wide", initial_sidebar_state="expanded")

st.title("📊 Screener Avançado de Ações")
st.markdown("Cruzamento fundamentalista e técnico avançado com Metodologias de Valuation.")

# ==========================================
# CONFIGURAÇÃO DE ESTADO (VALORES PADRÃO)
# ==========================================
def iniciar_estado_filtros():
    valores_padrao = {
        'f_busca': '',
        'f_tv': [],
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
        'f_liq': 1.0         
    }
    for chave, valor in valores_padrao.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor

def limpar_filtros():
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

iniciar_estado_filtros()

# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================
def classificar_tendencia(score):
    if pd.isna(score): return "Sem Dados"
    if score > 0.1: return "Compra"
    elif score < -0.1: return "Venda"
    else: return "Manter"

def classificar_tamanho(mcap):
    if pd.isna(mcap) or mcap == 0: return "Desconhecido"
    if mcap >= 15e9: return "Blue Chip"
    elif mcap <= 3e9: return "Small Cap"
    else: return "Mid Cap"

@st.cache_data(ttl=3600)
def obter_carteira_ibov():
    """Busca a lista atualizada do IBOV direto da Wikipedia ou usa fallback de segurança"""
    try:
        # Lê todas as tabelas da página e pega a que contém a coluna 'Código'
        tabelas = pd.read_html('https://pt.wikipedia.org/wiki/Ibovespa', match='Código')
        return tabelas[0]['Código'].str.strip().tolist()
    except Exception:
        # Fallback de segurança (Principais ações da B3) caso o site falhe
        return ['ABEV3', 'ALOS3', 'AZUL4', 'B3SA3', 'BBAS3', 'BBDC3', 'BBDC4', 'BBSE3', 'BEEF3', 'BPAC11', 'BRAP4', 'BRFS3', 'BRKM5', 'CCRO3', 'CMIG4', 'COGN3', 'CPFE3', 'CPLE6', 'CRFB3', 'CSAN3', 'CSNA3', 'CVCB3', 'CYRE3', 'DIRR3', 'ELET3', 'ELET6', 'EMBR3', 'ENEV3', 'EGIE3', 'EQTL3', 'EZTC3', 'FLRY3', 'GGBR4', 'GOAU4', 'GOLL4', 'HAPV3', 'HYPE3', 'IGTI11', 'ITSA4', 'ITUB4', 'JBSS3', 'KLBN11', 'LREN3', 'LWSA3', 'MGLU3', 'MRFG3', 'MRVE3', 'MULT3', 'NTCO3', 'PCAR3', 'PETR3', 'PETR4', 'PETZ3', 'PRIO3', 'RADL3', 'RAIZ4', 'RDOR3', 'RENT3', 'RRRP3', 'SANB11', 'SBSP3', 'SLCE3', 'SMTO3', 'SOMA3', 'SUZB3', 'TAEE11', 'TIMS3', 'TOTS3', 'UGPA3', 'USIM5', 'VALE3', 'VIVT3', 'WEGE3', 'YDUQ3']

# ==========================================
# EXTRAÇÃO E PROCESSAMENTO PRINCIPAL
# ==========================================
@st.cache_data(ttl=3600)
def carregar_dados():
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 1. Fundamentus
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
                        val_str = texto.text.strip().replace('%', '').replace('.', '').replace(',', '.')
                        if not val_str or val_str == '-' or val_str == 'nan': return 0.0
                        try: return float(val_str)
                        except ValueError: return 0.0
                    
                    dados_fund.append({
                        "Ticker": col[0].text.strip(),
                        "Cotação": limpar(col[1]),
                        "P/L": limpar(col[2]),
                        "P/VP": limpar(col[3]),
                        "Div. Yield (%)": limpar(col[5]),
                        "EV/EBITDA": limpar(col[11]),
                        "Margem EBIT (%)": limpar(col[12]),
                        "Margem Líquida (%)": limpar(col[13]),
                        "Liq. Corrente": limpar(col[14]),
                        "ROE (%)": limpar(col[16]),
                        "Dívida Bruta/Patrimônio": limpar(col[19]),
                        "CAGR Receita 5a (%)": limpar(col[20])
                    })
        df = pd.DataFrame(dados_fund)
    except Exception:
        return pd.DataFrame()

    if df.empty: return df

    # 2. TradingView (Incluindo Market Cap)
    try:
        payload_tv = {
            "filter": [{"left": "type", "operation": "equal", "right": "stock"}],
            "options": {"lang": "pt"},
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name", "Recommend.All", "market_cap_basic"] # Pedindo o Market Cap
        }
        resp_tv = requests.post("https://scanner.tradingview.com/brazil/scan", json=payload_tv, timeout=15)
        res_json = resp_tv.json()
        
        tv_dict = {}
        for item in res_json.get('data', []):
            ticker = item['d'][0].split(":")[-1]
            tv_dict[ticker] = {
                'Score TV': item['d'][1],
                'Market Cap': item['d'][2]
            }
            
        df_tv = pd.DataFrame.from_dict(tv_dict, orient='index').reset_index().rename(columns={'index': 'Ticker'})
        df = pd.merge(df, df_tv, on='Ticker', how='left')
    except Exception:
        df['Score TV'] = None
        df['Market Cap'] = 0

    # 3. Cruzamento e Engenharia
    lista_ibov = obter_carteira_ibov()
    
    df['Recomendação Técnica'] = df['Score TV'].apply(classificar_tendencia)
    df['Categoria'] = df['Market Cap'].apply(classificar_tamanho)
    df['IBOV'] = df['Ticker'].apply(lambda x: "Sim" if x in lista_ibov else "Não")

    df['VPA'] = df.apply(lambda r: r['Cotação'] / r['P/VP'] if r['P/VP'] > 0 else 0, axis=1)
    df['LPA'] = df.apply(lambda r: r['Cotação'] / r['P/L'] if r['P/L'] > 0 else 0, axis=1)
    
    df['Preço Justo (Graham)'] = df.apply(lambda r: math.sqrt(22.5 * r['VPA'] * r['LPA']) if r['VPA'] > 0 and r['LPA'] > 0 else 0, axis=1)
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    
    return df

with st.spinner("Atualizando base de dados em tempo real (Fundamentus + TradingView + IBOV)..."):
    df_acoes = carregar_dados()

if df_acoes.empty:
    st.warning("Não foi possível carregar os dados no momento.")
else:
    # ==========================================
    # INTERFACE DE FILTROS (BARRA LATERAL)
    # ==========================================
    st.sidebar.header("🔍 Filtros de Busca")
    st.sidebar.button("🗑️ Limpar Todos os Filtros", on_click=limpar_filtros, type="primary", use_container_width=True)
    st.sidebar.markdown("---")
    
    busca = st.sidebar.text_input("Buscar Ticker (ex: BBAS3)", key='f_busca').upper()
    
    st.sidebar.subheader("📊 Classificação e Índice")
    apenas_ibov = st.sidebar.checkbox("Apenas ações do IBOV", key='f_apenas_ibov')
    opcoes_tamanho = st.sidebar.multiselect(
        "Tamanho da Empresa",
        options=["Blue Chip", "Mid Cap", "Small Cap", "Desconhecido"],
        key='f_tamanho'
    )
    
    st.sidebar.subheader("📈 Análise Técnica")
    opcoes_tv = st.sidebar.multiselect(
        "Sinal do TradingView",
        options=["Compra", "Venda", "Manter", "Sem Dados"],
        key='f_tv'
    )

    st.sidebar.subheader("🎯 Metodologias de Valuation")
    filtro_barsi = st.sidebar.checkbox("Cotação Abaixo do Preço Teto (Barsi)", key='f_barsi')
    filtro_graham = st.sidebar.checkbox("Cotação Abaixo do Preço Justo (Graham)", key='f_graham')
    
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

    # ==========================================
    # APLICAÇÃO DOS FILTROS NO DATAFRAME
    # ==========================================
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

    # ==========================================
    # RENDERIZAÇÃO DA TABELA
    # ==========================================
    st.subheader(f"Ativos Encontrados: {len(df_filtrado)}")
    
    colunas_exibir = [
        'Ticker', 'IBOV', 'Categoria', 'Recomendação Técnica', 'Cotação', 'Preço Justo (Graham)', 'Preço Teto (Barsi)', 
        'Div. Yield (%)', 'P/L', 'P/VP', 'EV/EBITDA', 'ROE (%)', 'Margem EBIT (%)', 'Margem Líquida (%)', 
        'Liq. Corrente', 'Dívida Bruta/Patrimônio', 'CAGR Receita 5a (%)'
    ]
    
    st.dataframe(
        df_filtrado[colunas_exibir].style.format({
            "Cotação": "R$ {:.2f}",
            "Preço Justo (Graham)": "R$ {:.2f}",
            "Preço Teto (Barsi)": "R$ {:.2f}",
            "Div. Yield (%)": "{:.1f}%",
            "ROE (%)": "{:.1f}%",
            "Margem EBIT (%)": "{:.1f}%",
            "Margem Líquida (%)": "{:.1f}%",
            "CAGR Receita 5a (%)": "{:.1f}%",
            "P/L": "{:.2f}",
            "P/VP": "{:.2f}",
            "EV/EBITDA": "{:.2f}",
            "Liq. Corrente": "{:.2f}",
            "Dívida Bruta/Patrimônio": "{:.2f}"
        }),
        use_container_width=True,
        height=600
    )
