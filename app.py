import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import math

st.set_page_config(page_title="Screener Avançado", layout="wide", initial_sidebar_state="expanded")

st.title("📊 Screener Avançado de Investimentos")
st.markdown("Cruzamento Fundamentalista, Rastreador de Tendências e Indicadores de Valuation.")

# Dicionário super otimizado para tradução instantânea dos setores do TradingView
SETORES_TRADUCAO = {
    "Finance": "Finanças",
    "Electronic Technology": "Tecnologia Eletrônica",
    "Energy Minerals": "Minerais Energéticos",
    "Commercial Services": "Serviços Comerciais",
    "Process Industries": "Indústrias de Transformação",
    "Utilities": "Utilidade Pública",
    "Consumer Non-Durables": "Bens de Consumo Não-Duráveis",
    "Consumer Durables": "Bens de Consumo Duráveis",
    "Health Technology": "Tecnologia em Saúde",
    "Health Services": "Serviços de Saúde",
    "Transportation": "Transportes",
    "Retail Trade": "Varejo",
    "Producer Manufacturing": "Manufatura de Produção",
    "Non-Energy Minerals": "Minerais Não-Energéticos",
    "Technology Services": "Serviços de Tecnologia",
    "Communications": "Comunicações",
    "Industrial Services": "Serviços Industriais",
    "Consumer Services": "Serviços ao Consumidor",
    "Distribution Services": "Serviços de Distribuição",
    "Miscellaneous": "Diversos",
    "Government": "Governo",
    "Real Estate": "Imobiliário",
    "Outros": "Outros"
}

# ==========================================
# 1. CONFIGURAÇÃO DE ESTADO E SETUP CNPI FLEXÍVEL
# ==========================================
def aplicar_setup_cnpi_acoes():
    st.session_state.f_busca = ''
    st.session_state.f_tv = []
    st.session_state.f_tend_d = []; st.session_state.f_tend_s = []; st.session_state.f_tend_m = []
    st.session_state.f_tamanho = []; st.session_state.f_setor = []; st.session_state.f_apenas_ibov = False
    st.session_state.f_barsi = False; st.session_state.f_graham = False
    st.session_state.f_roe = 8.0           
    st.session_state.f_mebit = 5.0         
    st.session_state.f_mliq = 0.0 
    st.session_state.f_cagr = 0.0           
    st.session_state.f_evebitda = 0.0 
    st.session_state.f_dy = 0.0
    st.session_state.f_pvp_max = 5.0        
    st.session_state.f_pl_min = 0.1         
    st.session_state.f_pl_max = 20.0        
    st.session_state.f_liq = 1.0            
    st.session_state.f_divida = 0.0 # Novo Indicador
    st.session_state.val_liq_acoes = 1000000.0

def limpar_filtros_acoes():
    st.session_state.f_busca = ''
    st.session_state.f_tv = []
    st.session_state.f_tend_d = []; st.session_state.f_tend_s = []; st.session_state.f_tend_m = []
    st.session_state.f_tamanho = []; st.session_state.f_setor = []; st.session_state.f_apenas_ibov = False
    st.session_state.f_barsi = False; st.session_state.f_graham = False
    st.session_state.f_roe = 0.0; st.session_state.f_mliq = 0.0; st.session_state.f_mebit = 0.0
    st.session_state.f_cagr = 0.0; st.session_state.f_evebitda = 0.0; st.session_state.f_dy = 0.0
    st.session_state.f_pvp_max = 100.0
    st.session_state.f_pl_min = -100.0; st.session_state.f_pl_max = 1000.0
    st.session_state.f_liq = 0.0
    st.session_state.f_divida = 0.0
    st.session_state.val_liq_acoes = 1000000.0

def aplicar_setup_cnpi_fiis():
    st.session_state.f_busca = ''
    st.session_state.f_tv = []
    st.session_state.f_tend_d = []; st.session_state.f_tend_s = []; st.session_state.f_tend_m = []
    st.session_state.f_fii_segmento = []
    st.session_state.f_fii_barsi = False
    st.session_state.f_fii_pvp_max = 1.10   
    st.session_state.f_fii_dy_min = 8.0     
    st.session_state.f_fii_ffo_min = 7.0     
    st.session_state.f_fii_cap_rate = 0.0 # Novo Indicador
    st.session_state.f_fii_vacancia_max = 15.0 
    st.session_state.val_liq_fiis = 500000.0

def limpar_filtros_fiis():
    st.session_state.f_busca = ''
    st.session_state.f_tv = []
    st.session_state.f_tend_d = []; st.session_state.f_tend_s = []; st.session_state.f_tend_m = []
    st.session_state.f_fii_segmento = []
    st.session_state.f_fii_barsi = False
    st.session_state.f_fii_pvp_max = 10.0
    st.session_state.f_fii_dy_min = 0.0
    st.session_state.f_fii_ffo_min = 0.0
    st.session_state.f_fii_cap_rate = 0.0
    st.session_state.f_fii_vacancia_max = 100.0
    st.session_state.val_liq_fiis = 500000.0

# Shadow State (Variáveis de Sombra)
if 'val_liq_acoes' not in st.session_state:
    st.session_state.val_liq_acoes = 1000000.0
if 'val_liq_fiis' not in st.session_state:
    st.session_state.val_liq_fiis = 500000.0

if 'iniciado' not in st.session_state:
    aplicar_setup_cnpi_acoes()
    aplicar_setup_cnpi_fiis()
    st.session_state.tipo_ativo = 'Ações'
    st.session_state.iniciado = True

# ==========================================
# 2. FUNÇÕES AUXILIARES DE CORES E DADOS
# ==========================================
def classificar_sinal(score):
    if pd.isna(score): return "Sem Dados"
    return "Compra" if score > 0.1 else "Venda" if score < -0.1 else "Manter"

def calc_tendencia(cotacao, sma):
    try:
        if pd.isna(float(sma)) or float(sma) == 0 or pd.isna(float(cotacao)) or float(cotacao) == 0: 
            return "Sem Dados"
        return "🟢 Alta" if float(cotacao) > float(sma) else "🔴 Baixa"
    except:
        return "Sem Dados"

def limpar_numero(texto):
    val_str = texto.text.strip().replace('%', '').replace('.', '').replace(',', '.')
    if not val_str or val_str in ['-', 'nan', 'N/D']: return 0.0
    try: return float(val_str)
    except ValueError: return 0.0

def colorir_margem(val):
    if pd.isna(val): return ''
    if val > 0: return 'color: #00C851; font-weight: bold;'
    if val < 0: return 'color: #ff4444; font-weight: bold;'
    return ''

def colorir_sinal(val):
    if val == 'Compra': return 'color: #00C851; font-weight: bold;'
    if val == 'Venda': return 'color: #ff4444; font-weight: bold;'
    if val == 'Manter': return 'color: #FFBB33;'
    return ''

def colorir_tendencia(val):
    if '🟢' in str(val): return 'color: #00C851;'
    if '🔴' in str(val): return 'color: #ff4444;'
    return ''

@st.cache_data(ttl=3600)
def obter_carteira_ibov():
    try:
        tbs = pd.read_html('https://pt.wikipedia.org/wiki/Ibovespa', match='Código')
        return tbs[0]['Código'].str.strip().tolist()
    except: 
        return ['ABEV3', 'B3SA3', 'BBAS3', 'BBDC4', 'ITUB4', 'PETR4', 'VALE3', 'WEGE3']

TV_COLS = ["name", "Recommend.All", "market_cap_basic", "Value.Traded", "sector", "SMA20", "SMA50", "SMA200", "SMA20|1W", "SMA50|1W", "SMA20|1M", "SMA50|1M"]

# ==========================================
# 3. EXTRAÇÃO DE DADOS (AÇÕES)
# ==========================================
@st.cache_data(ttl=3600)
def carregar_dados_acoes():
    try:
        resposta = requests.get('https://www.fundamentus.com.br/resultado.php', headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(resposta.text, 'html.parser')
        tabela = soup.find('table', id='resultado')
        dados = []
        if tabela:
            for l in tabela.find_all('tr')[1:]:
                c = l.find_all('td')
                if len(c) >= 21:
                    dados.append({
                        "Ticker": c[0].text.strip(), "Cotação": limpar_numero(c[1]), "P/L": limpar_numero(c[2]),
                        "P/VP": limpar_numero(c[3]), "Div. Yield (%)": limpar_numero(c[5]), "EV/EBITDA": limpar_numero(c[11]),
                        "Margem EBIT (%)": limpar_numero(c[12]), "Margem Líquida (%)": limpar_numero(c[13]),
                        "Liq. Corrente": limpar_numero(c[14]), "ROE (%)": limpar_numero(c[16]),
                        "Dívida Bruta/Patrimônio": limpar_numero(c[19]), "CAGR Receita 5a (%)": limpar_numero(c[20])
                    })
        df = pd.DataFrame(dados)
    except: return pd.DataFrame()
    if df.empty: return df

    try:
        payload = {"filter": [{"left": "type", "operation": "equal", "right": "stock"}], "options": {"lang": "pt"}, "symbols": {"query": {"types": []}, "tickers": []}, "columns": TV_COLS}
        resp = requests.post("https://scanner.tradingview.com/brazil/scan", json=payload, timeout=15).json()
        tv_dict = {item['d'][0].split(":")[-1]: {
            'Score TV': item['d'][1], 'Market Cap': item['d'][2], 'Liq. Diária TV': item['d'][3] if item['d'][3] is not None else 0.0,
            'Setor': item['d'][4] if item['d'][4] else "Outros", 'SMA20': item['d'][5], 'SMA50': item['d'][6], 'SMA200': item['d'][7],
            'SMA20|1W': item['d'][8], 'SMA50|1W': item['d'][9], 'SMA20|1M': item['d'][10], 'SMA50|1M': item['d'][11]
        } for item in resp.get('data', [])}
        df = pd.merge(df, pd.DataFrame.from_dict(tv_dict, orient='index').reset_index().rename(columns={'index': 'Ticker'}), on='Ticker', how='left')
    except:
        df['Liq. Diária TV'] = 0.0; df['Setor'] = 'Outros'; 
        for col in TV_COLS[5:]: df[col] = None

    # Aplica a tradução rápida dos Setores
    df['Setor'] = df['Setor'].map(SETORES_TRADUCAO).fillna(df['Setor'])
    
    df['Liq. Diária'] = df['Liq. Diária TV']

    lista_ibov = obter_carteira_ibov()
    df['Sinal Técnico'] = df['Score TV'].apply(classificar_sinal)
    df['Categoria'] = df['Market Cap'].apply(lambda m: "Blue Chip" if m >= 15e9 else ("Small Cap" if m > 0 and m <= 3e9 else "Mid Cap" if m > 0 else "Desconhecido"))
    df['IBOV'] = df['Ticker'].apply(lambda x: "Sim" if x in lista_ibov else "Não")

    df['VPA'] = df.apply(lambda r: r['Cotação'] / r['P/VP'] if r['P/VP'] > 0 else 0, axis=1)
    df['LPA'] = df.apply(lambda r: r['Cotação'] / r['P/L'] if r['P/L'] > 0 else 0, axis=1)
    
    df['Preço Justo (Graham)'] = df.apply(lambda r: math.sqrt(22.5 * r['VPA'] * r['LPA']) if r['VPA'] > 0 and r['LPA'] > 0 else 0, axis=1)
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    df['Margem Graham (%)'] = df.apply(lambda r: ((r['Preço Justo (Graham)'] - r['Cotação']) / r['Cotação']) * 100 if r['Cotação'] > 0 and r['Preço Justo (Graham)'] > 0 else 0, axis=1)
    df['Margem Barsi (%)'] = df.apply(lambda r: ((r['Preço Teto (Barsi)'] - r['Cotação']) / r['Cotação']) * 100 if r['Cotação'] > 0 and r['Preço Teto (Barsi)'] > 0 else 0, axis=1)
    df['DY Mensal Est. (%)'] = df.apply(lambda r: (math.pow(1 + (r['Div. Yield (%)'] / 100), 1/12) - 1) * 100 if r['Div. Yield (%)'] > 0 else 0, axis=1)
    
    return df

# ==========================================
# 4. EXTRAÇÃO DE DADOS (FIIs)
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
                        "Liq. Diária Fundamentus": limpar_numero(c[7]), "Cap Rate (%)": limpar_numero(c[11]), "Vacância Média (%)": limpar_numero(c[12])
                    })
        df = pd.DataFrame(dados)
    except: return pd.DataFrame()
    if df.empty: return df

    try:
        payload = {"filter": [{"left": "type", "operation": "equal", "right": "fund"}], "options": {"lang": "pt"}, "symbols": {"query": {"types": []}, "tickers": []}, "columns": TV_COLS}
        resp = requests.post("https://scanner.tradingview.com/brazil/scan", json=payload, timeout=15).json()
        tv_dict = {item['d'][0].split(":")[-1]: {
            'Score TV': item['d'][1], 'Liq. Diária TV': item['d'][3] if item['d'][3] is not None else 0.0,
            'Setor': item['d'][4], 'SMA20': item['d'][5], 'SMA50': item['d'][6], 'SMA200': item['d'][7],
            'SMA20|1W': item['d'][8], 'SMA50|1W': item['d'][9], 'SMA20|1M': item['d'][10], 'SMA50|1M': item['d'][11]
        } for item in resp.get('data', [])}
        df = pd.merge(df, pd.DataFrame.from_dict(tv_dict, orient='index').reset_index().rename(columns={'index': 'Ticker'}), on='Ticker', how='left')
    except:
        df['Liq. Diária TV'] = 0.0
        for col in TV_COLS[4:]: df[col] = None

    # Prioridade Categórica para o Fundamentus
    df['Liq. Diária'] = df.apply(lambda r: r['Liq. Diária Fundamentus'] if pd.notna(r['Liq. Diária Fundamentus']) and r['Liq. Diária Fundamentus'] > 0 else r.get('Liq. Diária TV', 0.0), axis=1)

    df['Sinal Técnico'] = df['Score TV'].apply(classificar_sinal)
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    df['Margem Barsi (%)'] = df.apply(lambda r: ((r['Preço Teto (Barsi)'] - r['Cotação']) / r['Cotação']) * 100 if r['Cotação'] > 0 and r['Preço Teto (Barsi)'] > 0 else 0, axis=1)
    df['DY Mensal Est. (%)'] = df.apply(lambda r: (math.pow(1 + (r['Div. Yield (%)'] / 100), 1/12) - 1) * 100 if r['Div. Yield (%)'] > 0 else 0, axis=1)
    
    return df

# ==========================================
# 5. RENDERIZAÇÃO DA BARRA LATERAL (MERCADO)
# ==========================================
st.sidebar.title("MERCADO")
tipo_ativo = st.sidebar.radio("Selecione o mercado:", ("Ações", "Fundos Imobiliários (FIIs)"), key="tipo_ativo", label_visibility="collapsed")
st.sidebar.markdown("---")

# ==========================================
# 6. LÓGICA E TELAS - AÇÕES
# ==========================================
if tipo_ativo == "Ações":
    with st.spinner("Carregando base de Ações..."): 
        df_dados = carregar_dados_acoes()
        
    if not df_dados.empty:
        st.sidebar.header("FILTROS DE AÇÕES")
        
        col1, col2 = st.sidebar.columns(2)
        with col1:
            st.button("🧹 Limpar Tudo", on_click=limpar_filtros_acoes, use_container_width=True)
        with col2:
            st.button("🎯 Análise Padrão", on_click=aplicar_setup_cnpi_acoes, type="primary", use_container_width=True)
            
        busca = st.sidebar.text_input("Buscar Ticker (ex: BBAS3)", key='f_busca').upper()
        
        # Adicionado o novo indicador Dívida Bruta/PL
        colunas_disponiveis = {
            'Ticker': 'Ticker', 'Cotação': 'Preço', 'IBOV': 'IBOV', 'Categoria': 'Tipo', 
            'Setor': 'Setor', 'P/VP': 'P/VP', 'Div. Yield (%)': 'DY', 'DY Mensal Est. (%)': 'DY Mês', 
            'Preço Justo (Graham)': 'V. Graham', 'Margem Graham (%)': 'M. Graham', 'Preço Teto (Barsi)': 'T. Barsi', 
            'Margem Barsi (%)': 'M. Barsi', 'P/L': 'P/L', 'ROE (%)': 'ROE', 'Margem EBIT (%)': 'M. EBIT', 
            'Dívida Bruta/Patrimônio': 'Dív. Bruta/PL', 'Liq. Corrente': 'Liq Corr.', 'Liq. Diária': 'Liq Diária', 
            'Tend. Mensal': 'T. Mês', 'Tend. Semanal': 'T. Sem.', 'Tend. Diária': 'T. Dia', 'Sinal Técnico': 'Sinal'
        }
        
        colunas_padrao_visiveis = [
            'Ticker', 'Preço', 'IBOV', 'P/VP', 'DY', 'V. Graham', 'T. Barsi', 
            'P/L', 'ROE', 'M. EBIT', 'Dív. Bruta/PL', 'Liq Corr.', 'Liq Diária', 'T. Mês', 'T. Sem.', 'T. Dia', 'Sinal'
        ]
        
        colunas_escolhidas = st.sidebar.multiselect(
            "Ocultar/Exibir Colunas", 
            options=list(colunas_disponiveis.values()), 
            default=colunas_padrao_visiveis
        )
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("RASTREADOR DE TENDÊNCIAS")
        with st.sidebar.expander("Configurar Médias Móveis"):
            p_diario = st.selectbox("Período da Média Diária", [20, 50, 200], index=0)
            t_diario = st.multiselect("Tendência Diária", ["🟢 Alta", "🔴 Baixa"], key='f_tend_d')
            p_semanal = st.selectbox("Período da Média Semanal", [20, 50], index=0)
            t_semanal = st.multiselect("Tendência Semanal", ["🟢 Alta", "🔴 Baixa"], key='f_tend_s')
            p_mensal = st.selectbox("Período da Média Mensal", [20, 50], index=0)
            t_mensal = st.multiselect("Tendência Mensal", ["🟢 Alta", "🔴 Baixa"], key='f_tend_m')

        st.sidebar.subheader("CLASSIFICAÇÃO E VALUATION")
        apenas_ibov = st.sidebar.checkbox("Filtrar IBOV (Sim / Não)", key='f_apenas_ibov')
        opcoes_tamanho = st.sidebar.multiselect("Filtrar Tamanho", ["Blue Chip", "Mid Cap", "Small Cap"], key='f_tamanho')
        
        setores_disp = sorted(df_dados['Setor'].dropna().unique().tolist())
        opcoes_setor = st.sidebar.multiselect("Filtrar Setor", setores_disp, key='f_setor')
        opcoes_tv = st.sidebar.multiselect("Filtrar Sinal", ["Compra", "Venda", "Manter", "Sem Dados"], key='f_tv')
        
        filtro_barsi = st.sidebar.checkbox("Cotação Abaixo do Preço Teto (Barsi)", key='f_barsi')
        filtro_graham = st.sidebar.checkbox("Cotação Abaixo do Preço Justo (Graham)", key='f_graham')
        
        with st.sidebar.expander("Preços e Múltiplos"):
            max_pvp = st.number_input("P/VP Máximo (0=desativa)", step=0.1, key='f_pvp_max')
            min_pl = st.number_input("P/L Mínimo", step=1.0, key='f_pl_min')
            max_pl = st.number_input("P/L Máximo (0=desativa)", step=1.0, key='f_pl_max')
            min_dy = st.number_input("Dividend Yield Mín. (%)", step=0.5, key='f_dy')
            max_evebitda = st.number_input("EV/EBITDA Máx. (0=desativa)", step=1.0, key='f_evebitda')

        with st.sidebar.expander("Rentabilidade e Saúde"):
            min_roe = st.number_input("ROE Mínimo (%)", step=1.0, key='f_roe')
            min_mebit = st.number_input("Margem EBIT Mín. (%)", step=1.0, key='f_mebit')
            min_mliq = st.number_input("Margem Líquida Mín. (%)", step=1.0, key='f_mliq')
            max_divida = st.number_input("Dívida Bruta/PL Máx. (0=desativa)", step=0.5, key='f_divida')
            min_liq = st.number_input("Liquidez Corrente Mínima", step=0.1, key='f_liq')
            min_cagr = st.number_input("CAGR Receita Mínimo (%)", step=1.0, key='f_cagr')

        st.sidebar.subheader("LIQUIDEZ MÍNIMA")
        filtro_liq_permanente = st.sidebar.number_input(
            "Volume Diário Mín. (R$)", 
            min_value=0.0, step=500000.0, format="%.0f", 
            value=st.session_state.val_liq_acoes,
            help="Filtro de segurança permanente. Padrão R$ 1.000.000."
        )
        st.session_state.val_liq_acoes = filtro_liq_permanente

        df_dados['Tend. Diária'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_diario}', 0)), axis=1)
        df_dados['Tend. Semanal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_semanal}|1W', 0)), axis=1)
        df_dados['Tend. Mensal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_mensal}|1M', 0)), axis=1)

        df_f = df_dados.copy()
        
        if filtro_liq_permanente > 0: df_f = df_f[df_f['Liq. Diária'] >= filtro_liq_permanente]
        if busca: df_f = df_f[df_f['Ticker'].astype(str).str.contains(busca)]
        if apenas_ibov: df_f = df_f[df_f['IBOV'] == "Sim"]
        if opcoes_tamanho: df_f = df_f[df_f['Categoria'].isin(opcoes_tamanho)]
        if opcoes_setor: df_f = df_f[df_f['Setor'].isin(opcoes_setor)]
        if opcoes_tv: df_f = df_f[df_f['Sinal Técnico'].isin(opcoes_tv)]
        if t_diario: df_f = df_f[df_f['Tend. Diária'].isin(t_diario)]
        if t_semanal: df_f = df_f[df_f['Tend. Semanal'].isin(t_semanal)]
        if t_mensal: df_f = df_f[df_f['Tend. Mensal'].isin(t_mensal)]
        if filtro_barsi: df_f = df_f[df_f['Cotação'] < df_f['Preço Teto (Barsi)']]
        if filtro_graham: df_f = df_f[df_f['Cotação'] < df_f['Preço Justo (Graham)']]
        if max_pvp > 0: df_f = df_f[df_f['P/VP'] <= max_pvp]
        if max_pl > 0: df_f = df_f[(df_f['P/L'] >= min_pl) & (df_f['P/L'] <= max_pl)]
        if min_dy > 0: df_f = df_f[df_f['Div. Yield (%)'] >= min_dy]
        if max_evebitda > 0: df_f = df_f[df_f['EV/EBITDA'] <= max_evebitda]
        if min_roe > 0: df_f = df_f[df_f['ROE (%)'] >= min_roe]
        if min_mebit > 0: df_f = df_f[df_f['Margem EBIT (%)'] >= min_mebit]
        if min_mliq > 0: df_f = df_f[df_f['Margem Líquida (%)'] >= min_mliq]
        if max_divida > 0: df_f = df_f[df_f['Dívida Bruta/Patrimônio'] <= max_divida]
        if min_liq > 0: df_f = df_f[df_f['Liq. Corrente'] >= min_liq]
        if min_cagr > 0: df_f = df_f[df_f['CAGR Receita 5a (%)'] >= min_cagr]

        df_f = df_f.sort_values(by='Margem Graham (%)', ascending=False)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏢 Ações Encontradas", len(df_f))
        if not df_f.empty:
            c2.metric("Média P/VP", f"{df_f['P/VP'].mean():.2f}")
            c3.metric("Média DY Anual", f"{df_f['Div. Yield (%)'].mean():.2f}%")
            c4.metric("Mediana Liq. Diária", f"R$ {df_f['Liq. Diária'].median()/1e6:.1f} Milhões")
        st.markdown("---")

        chaves_reais_ordenadas = [k for k, v in colunas_disponiveis.items() if v in colunas_escolhidas]

        if chaves_reais_ordenadas:
            df_view = df_f[chaves_reais_ordenadas].rename(columns=colunas_disponiveis)
            
            styled_df = df_view.style.format({
                "Preço": "R$ {:.2f}", "V. Graham": "R$ {:.2f}", "M. Graham": "{:+.1f}%",
                "T. Barsi": "R$ {:.2f}", "M. Barsi": "{:+.1f}%", "DY": "{:.1f}%", 
                "DY Mês": "{:.2f}%", "ROE": "{:.1f}%", "M. EBIT": "{:.1f}%", 
                "P/L": "{:.2f}", "P/VP": "{:.2f}", "Dív. Bruta/PL": "{:.2f}", 
                "Liq Corr.": "{:.2f}", "Liq Diária": "R$ {:,.0f}"
            })
            
            cols_margem = [c for c in ['M. Graham', 'M. Barsi'] if c in df_view.columns]
            if cols_margem: styled_df = styled_df.map(colorir_margem, subset=cols_margem)
            
            cols_sinal = [c for c in ['Sinal'] if c in df_view.columns]
            if cols_sinal: styled_df = styled_df.map(colorir_sinal, subset=cols_sinal)
            
            cols_tendencia = [c for c in ['T. Mês', 'T. Sem.', 'T. Dia'] if c in df_view.columns]
            if cols_tendencia: styled_df = styled_df.map(colorir_tendencia, subset=cols_tendencia)

            st.dataframe(styled_df, 
                hide_index=True, 
                use_container_width=False, 
                height=600,
                column_config={
                    "DY": st.column_config.NumberColumn("DY", help="Dividendos (12m) / Preço. Quanto maior, melhor."),
                    "DY Mês": st.column_config.NumberColumn("DY Mês", help="Taxa equivalente mensal (Juros Compostos)."),
                    "M. Graham": st.column_config.NumberColumn("M. Graham", help="Distância % entre o Preço Justo e a Cotação. Positivo = Desconto."),
                    "M. Barsi": st.column_config.NumberColumn("M. Barsi", help="Distância % entre o Preço Teto e a Cotação. Positivo = Desconto."),
                    "P/L": st.column_config.NumberColumn("P/L", help="Preço / Lucro. Quanto menor (acima de zero), mais barata."),
                    "P/VP": st.column_config.NumberColumn("P/VP", help="Preço / Valor Patrimonial. Menor que 1 indica desconto patrimonial."),
                    "ROE": st.column_config.NumberColumn("ROE", help="Retorno sobre o Patrimônio Líquido. Capacidade de gerar lucro com capital próprio."),
                    "M. EBIT": st.column_config.NumberColumn("M. EBIT", help="Margem Operacional. Eficiência do negócio principal."),
                    "V. Graham": st.column_config.NumberColumn("V. Graham", help="Preço Justo calculado por Benjamin Graham."),
                    "T. Barsi": st.column_config.NumberColumn("T. Barsi", help="Preço Teto calculado pela metodologia de Décio Barsi."),
                    "Tipo": st.column_config.TextColumn("Tipo", help="Tamanho da empresa por valor de mercado na bolsa."),
                    "Setor": st.column_config.TextColumn("Setor", help="Setor de atuação da empresa segundo o TradingView."),
                    "Dív. Bruta/PL": st.column_config.NumberColumn("Dív. Bruta/PL", help="Dívida Bruta sobre o Patrimônio Líquido. Mede o nível de endividamento da empresa."),
                    "Liq Corr.": st.column_config.NumberColumn("Liq Corr.", help="Liquidez Corrente: Caixa para pagar dívidas de curto prazo (>1.0 é bom).")
                })
        else:
            st.warning("Selecione ao menos uma coluna para exibir na tabela.")

# ==========================================
# 7. LÓGICA E TELAS - FIIs
# ==========================================
else:
    with st.spinner("Carregando base de FIIs..."): 
        df_dados = carregar_dados_fiis()
        
    if not df_dados.empty:
        st.sidebar.header("FILTROS DE FIIs")
        
        col1, col2 = st.sidebar.columns(2)
        with col1:
            st.button("🧹 Limpar Tudo", on_click=limpar_filtros_fiis, use_container_width=True)
        with col2:
            st.button("🎯 Análise Padrão", on_click=aplicar_setup_cnpi_fiis, type="primary", use_container_width=True)
        
        busca = st.sidebar.text_input("Buscar FII pelo código (ex: MXRF11)", key='f_busca').upper()
        opcoes_seg = st.sidebar.multiselect("Filtrar por Segmento", sorted(df_dados['Segmento'].unique().tolist()), key='f_fii_segmento')
        
        st.sidebar.subheader("RASTREADOR DE TENDENCIAS")
        with st.sidebar.expander("Configurar Médias Móveis"):
            opcoes_tv = st.multiselect("Filtrar Sinal (TradingView)", ["Compra", "Venda", "Manter", "Sem Dados"], key='f_tv')
            p_diario = st.selectbox("Período da Média Diária", [20, 50, 200], index=0)
            t_diario = st.multiselect("Tendência Diária", ["🟢 Alta", "🔴 Baixa"], key='f_tend_d')
            p_semanal = st.selectbox("Período da Média Semanal", [20, 50], index=0)
            t_semanal = st.multiselect("Tendência Semanal", ["🟢 Alta", "🔴 Baixa"], key='f_tend_s')
            p_mensal = st.selectbox("Período da Média Mensal", [20, 50], index=0)
            t_mensal = st.multiselect("Tendência Mensal", ["🟢 Alta", "🔴 Baixa"], key='f_tend_m')

        # Adicionado o novo indicador Cap Rate
        colunas_disponiveis_fii = {
            'Ticker': 'Ticker', 'Cotação': 'Preço', 'Segmento': 'Segmento', 'P/VP': 'P/VP', 
            'Div. Yield (%)': 'DY', 'DY Mensal Est. (%)': 'DY Mês', 'FFO Yield (%)': 'FFO Yield', 
            'Cap Rate (%)': 'Cap Rate', 'Preço Teto (Barsi)': 'T. Barsi', 'Margem Barsi (%)': 'M. Barsi', 
            'Vacância Média (%)': 'Vacância', 'Liq. Diária': 'Liq. Diária', 'Tend. Mensal': 'T. Mês', 
            'Tend. Semanal': 'T. Sem.', 'Tend. Diária': 'T. Dia', 'Sinal Técnico': 'Sinal'
        }
        
        colunas_padrao_fii_visiveis = [
            'Ticker', 'Preço', 'Segmento', 'P/VP', 'DY', 'FFO Yield', 'Cap Rate', 'T. Barsi', 
            'Vacância', 'Liq. Diária', 'T. Mês', 'T. Sem.', 'T. Dia', 'Sinal'
        ]
        
        colunas_escolhidas_fii = st.sidebar.multiselect(
            "Ocultar/Exibir Colunas", 
            options=list(colunas_disponiveis_fii.values()), 
            default=colunas_padrao_fii_visiveis
        )

        st.sidebar.subheader("METODOLOGIAS E INDICADORES")
        filtro_barsi = st.sidebar.checkbox("Cotação Abaixo do Preço Teto (Barsi)", key='f_fii_barsi')
        max_pvp = st.sidebar.number_input("P/VP Máximo (0=desativa)", step=0.05, key='f_fii_pvp_max')
        min_dy = st.sidebar.number_input("Dividend Yield Mínimo (%)", step=0.5, key='f_fii_dy_min')
        min_ffo = st.sidebar.number_input("FFO Yield Mínimo (%)", step=0.5, key='f_fii_ffo_min')
        min_cap = st.sidebar.number_input("Cap Rate Mínimo (%)", step=0.5, key='f_fii_cap_rate')
        max_vac = st.sidebar.number_input("Vacância Máxima (%)", step=1.0, key='f_fii_vacancia_max')

        st.sidebar.subheader("LIQUIDEZ MÍNIMA")
        filtro_liq_permanente = st.sidebar.number_input(
            "Volume Diário Mín. (R$)", 
            min_value=0.0, step=100000.0, format="%.0f", 
            value=st.session_state.val_liq_fiis,
            help="Filtro de segurança permanente. Padrão FIIs: R$ 500.000."
        )
        st.session_state.val_liq_fiis = filtro_liq_permanente 

        df_dados['Tend. Diária'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_diario}', 0)), axis=1)
        df_dados['Tend. Semanal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_semanal}|1W', 0)), axis=1)
        df_dados['Tend. Mensal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_mensal}|1M', 0)), axis=1)

        df_f = df_dados.copy()
        
        if filtro_liq_permanente > 0: df_f = df_f[df_f['Liq. Diária'] >= filtro_liq_permanente]
        if busca: df_f = df_f[df_f['Ticker'].astype(str).str.contains(busca)]
        if opcoes_seg: df_f = df_f[df_f['Segmento'].isin(opcoes_seg)]
        if opcoes_tv: df_f = df_f[df_f['Sinal Técnico'].isin(opcoes_tv)]
        if t_diario: df_f = df_f[df_f['Tend. Diária'].isin(t_diario)]
        if t_semanal: df_f = df_f[df_f['Tend. Semanal'].isin(t_semanal)]
        if t_mensal: df_f = df_f[df_f['Tend. Mensal'].isin(t_mensal)]
        if filtro_barsi: df_f = df_f[df_f['Cotação'] < df_f['Preço Teto (Barsi)']]
        if max_pvp > 0: df_f = df_f[df_f['P/VP'] <= max_pvp]
        if min_dy > 0: df_f = df_f[df_f['Div. Yield (%)'] >= min_dy]
        if min_ffo > 0: df_f = df_f[df_f['FFO Yield (%)'] >= min_ffo]
        if min_cap > 0: df_f = df_f[df_f['Cap Rate (%)'] >= min_cap]
        if max_vac > 0: df_f = df_f[df_f['Vacância Média (%)'] <= max_vac]

        df_f = df_f.sort_values(by='Margem Barsi (%)', ascending=False)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏢 FIIs Encontrados", len(df_f))
        if not df_f.empty:
            c2.metric("Média P/VP", f"{df_f['P/VP'].mean():.2f}")
            c3.metric("Média DY Anual", f"{df_f['Div. Yield (%)'].mean():.2f}%")
            c4.metric("Mediana Vacância", f"{df_f['Vacância Média (%)'].median():.1f}%")
        st.markdown("---")
        
        chaves_reais_fii_ordenadas = [k for k, v in colunas_disponiveis_fii.items() if v in colunas_escolhidas_fii]

        if chaves_reais_fii_ordenadas:
            df_view_fii = df_f[chaves_reais_fii_ordenadas].rename(columns=colunas_disponiveis_fii)
            
            styled_df_fii = df_view_fii.style.format({
                "Preço": "R$ {:.2f}", "T. Barsi": "R$ {:.2f}", "M. Barsi": "{:+.1f}%",
                "DY": "{:.1f}%", "DY Mês": "{:.2f}%", "FFO Yield": "{:.1f}%", "Cap Rate": "{:.1f}%", 
                "P/VP": "{:.2f}", "Vacância": "{:.1f}%", "Liq. Diária": "R$ {:,.0f}"
            })
            
            cols_margem_fii = [c for c in ['M. Barsi'] if c in df_view_fii.columns]
            if cols_margem_fii: styled_df_fii = styled_df_fii.map(colorir_margem, subset=cols_margem_fii)
            
            cols_sinal_fii = [c for c in ['Sinal'] if c in df_view_fii.columns]
            if cols_sinal_fii: styled_df_fii = styled_df_fii.map(colorir_sinal, subset=cols_sinal_fii)
            
            cols_tend_fii = [c for c in ['T. Mês', 'T. Sem.', 'T. Dia'] if c in df_view_fii.columns]
            if cols_tend_fii: styled_df_fii = styled_df_fii.map(colorir_tendencia, subset=cols_tend_fii)

            st.dataframe(styled_df_fii, 
                hide_index=True,
                use_container_width=False, 
                height=600,
                column_config={
                    "DY": st.column_config.NumberColumn("DY", help="Dividendos (12m) / Preço. Quanto maior, melhor."),
                    "DY Mês": st.column_config.NumberColumn("DY Mês", help="Taxa equivalente mensal (Juros Compostos)."),
                    "M. Barsi": st.column_config.NumberColumn("M. Barsi", help="Distância % entre o Preço Teto calculado e a Cotação atual do FII. Positivo indica que está abaixo do teto."),
                    "P/VP": st.column_config.NumberColumn("P/VP", help="Preço / Valor Patrimonial. Abaixo de 1.0 = Fundo com desconto."),
                    "Vacância": st.column_config.NumberColumn("Vacância", help="Percentual do portfólio físico desocupado. Quanto menor, melhor."),
                    "FFO Yield": st.column_config.NumberColumn("FFO Yield", help="Caixa gerado pelas operações do fundo sobre o preço. Mostra o potencial de distribuição."),
                    "Cap Rate": st.column_config.NumberColumn("Cap Rate", help="Retorno médio anual que os imóveis físicos do fundo estão gerando com aluguéis.")
                })
        else:
            st.warning("Selecione ao menos uma coluna para exibir na tabela.")
