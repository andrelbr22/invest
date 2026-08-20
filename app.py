import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import math

st.set_page_config(page_title="Screener Avançado", layout="wide", initial_sidebar_state="expanded")

st.title("📊 Screener Avançado de Investimentos")
st.markdown("Cruzamento Fundamentalista e Rastreador de Tendências (Ações e FIIs).")

# ==========================================
# CONFIGURAÇÃO DE ESTADO (FILTROS DOS ~30% MELHORES)
# ==========================================
def iniciar_estado_filtros():
    valores_padrao = {
        'tipo_ativo': 'Ações',
        'f_busca': '', 'f_tv': [],
        'f_tend_d': [], 'f_tend_s': [], 'f_tend_m': [],
        
        # AÇÕES: Setup Inicial de Qualidade (~30% da bolsa)
        'f_tamanho': [], 'f_apenas_ibov': False, 'f_barsi': False, 'f_graham': False,
        'f_roe': 10.0,           # Apenas empresas rentáveis
        'f_mebit': 5.0,          # Operacional saudável
        'f_mliq': 0.0, 'f_cagr': 0.0, 'f_evebitda': 0.0, 'f_dy': 0.0,
        'f_pvp_min': 0.2,        # Corta distorções contábeis
        'f_pvp_max': 2.5,        # Corta empresas muito caras
        'f_pl_min': 2.0,         # Corta empresas dando prejuízo
        'f_pl_max': 15.0,        # Preço justo
        'f_liq': 1.0,            # Liquidez corrente segura
        
        # FIIs: Setup Inicial de Qualidade (~30% dos fundos)
        'f_fii_segmento': [],
        'f_fii_pvp_min': 0.50,   # Corta fundos problemáticos/em liquidação
        'f_fii_pvp_max': 1.05,   # Apenas fundos com desconto ou preço justo
        'f_fii_dy_min': 8.0,     # Provento atrativo
        'f_fii_vacancia_max': 10.0, # Imóveis ocupados
        'f_fii_liq_min': 500000.0,  # Liquidez financeira segura
        'f_fii_barsi': False
    }
    for chave, valor in valores_padrao.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor

def limpar_filtros_acoes():
    st.session_state.f_busca = ''; st.session_state.f_tv = []
    st.session_state.f_tend_d = []; st.session_state.f_tend_s = []; st.session_state.f_tend_m = []
    st.session_state.f_tamanho = []; st.session_state.f_apenas_ibov = False
    st.session_state.f_barsi = False; st.session_state.f_graham = False
    st.session_state.f_roe = 0.0; st.session_state.f_mliq = 0.0; st.session_state.f_mebit = 0.0
    st.session_state.f_cagr = 0.0; st.session_state.f_evebitda = 0.0; st.session_state.f_dy = 0.0
    st.session_state.f_pvp_min = 0.0; st.session_state.f_pvp_max = 100.0
    st.session_state.f_pl_min = -100.0; st.session_state.f_pl_max = 1000.0
    st.session_state.f_liq = 0.0

def limpar_filtros_fiis():
    st.session_state.f_busca = ''; st.session_state.f_tv = []
    st.session_state.f_tend_d = []; st.session_state.f_tend_s = []; st.session_state.f_tend_m = []
    st.session_state.f_fii_segmento = []; st.session_state.f_fii_barsi = False
    st.session_state.f_fii_pvp_min = 0.0; st.session_state.f_fii_pvp_max = 10.0
    st.session_state.f_fii_dy_min = 0.0; st.session_state.f_fii_vacancia_max = 100.0
    st.session_state.f_fii_liq_min = 0.0

iniciar_estado_filtros()

# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================
def classificar_sinal(score):
    if pd.isna(score): return "Sem Dados"
    return "Compra" if score > 0.1 else "Venda" if score < -0.1 else "Manter"

def calc_tendencia(cotacao, sma):
    if pd.isna(sma) or sma == 0 or pd.isna(cotacao) or cotacao == 0: return "Sem Dados"
    return "🟢 Alta" if cotacao > sma else "🔴 Baixa"

def limpar_numero(texto):
    val_str = texto.text.strip().replace('%', '').replace('.', '').replace(',', '.')
    if not val_str or val_str in ['-', 'nan', 'N/D']: return 0.0
    try: return float(val_str)
    except ValueError: return 0.0

@st.cache_data(ttl=3600)
def obter_carteira_ibov():
    try:
        tbs = pd.read_html('https://pt.wikipedia.org/wiki/Ibovespa', match='Código')
        return tbs[0]['Código'].str.strip().tolist()
    except: return ['ABEV3', 'B3SA3', 'BBAS3', 'BBDC4', 'ITUB4', 'PETR4', 'VALE3', 'WEGE3']

# Colunas de Médias Móveis do TradingView
TV_COLS = ["name", "Recommend.All", "market_cap_basic", "SMA20", "SMA50", "SMA200", "SMA20|1W", "SMA50|1W", "SMA20|1M", "SMA50|1M"]

# ==========================================
# EXTRAÇÃO DE DADOS 
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
        
        tv_dict = {}
        for item in resp.get('data', []):
            d = item['d']
            tv_dict[d[0].split(":")[-1]] = {
                'Score TV': d[1], 'Market Cap': d[2], 'SMA20': d[3], 'SMA50': d[4], 'SMA200': d[5],
                'SMA20|1W': d[6], 'SMA50|1W': d[7], 'SMA20|1M': d[8], 'SMA50|1M': d[9]
            }
        df = pd.merge(df, pd.DataFrame.from_dict(tv_dict, orient='index').reset_index().rename(columns={'index': 'Ticker'}), on='Ticker', how='left')
    except:
        for col in TV_COLS[1:]: df[col] = None

    lista_ibov = obter_carteira_ibov()
    df['Sinal Técnico'] = df['Score TV'].apply(classificar_sinal)
    df['Categoria'] = df['Market Cap'].apply(lambda m: "Blue Chip" if m >= 15e9 else ("Small Cap" if m > 0 and m <= 3e9 else "Mid Cap" if m > 0 else "Desconhecido"))
    df['IBOV'] = df['Ticker'].apply(lambda x: "Sim" if x in lista_ibov else "Não")

    df['VPA'] = df.apply(lambda r: r['Cotação'] / r['P/VP'] if r['P/VP'] > 0 else 0, axis=1)
    df['LPA'] = df.apply(lambda r: r['Cotação'] / r['P/L'] if r['P/L'] > 0 else 0, axis=1)
    df['Preço Justo (Graham)'] = df.apply(lambda r: math.sqrt(22.5 * r['VPA'] * r['LPA']) if r['VPA'] > 0 and r['LPA'] > 0 else 0, axis=1)
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    
    return df

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

    try:
        payload = {"filter": [{"left": "type", "operation": "equal", "right": "fund"}], "options": {"lang": "pt"}, "symbols": {"query": {"types": []}, "tickers": []}, "columns": TV_COLS}
        resp = requests.post("https://scanner.tradingview.com/brazil/scan", json=payload, timeout=15).json()
        
        tv_dict = {}
        for item in resp.get('data', []):
            d = item['d']
            tv_dict[d[0].split(":")[-1]] = {
                'Score TV': d[1], 'SMA20': d[3], 'SMA50': d[4], 'SMA200': d[5],
                'SMA20|1W': d[6], 'SMA50|1W': d[7], 'SMA20|1M': d[8], 'SMA50|1M': d[9]
            }
        df = pd.merge(df, pd.DataFrame.from_dict(tv_dict, orient='index').reset_index().rename(columns={'index': 'Ticker'}), on='Ticker', how='left')
    except:
        for col in TV_COLS[1:]: df[col] = None

    df['Sinal Técnico'] = df['Score TV'].apply(classificar_sinal)
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    
    return df

# ==========================================
# RENDERIZAÇÃO DA BARRA LATERAL
# ==========================================
st.sidebar.title("Configurações")
tipo_ativo = st.sidebar.radio("1. Selecione o mercado:", ("Ações", "Fundos Imobiliários (FIIs)"), key="tipo_ativo")
st.sidebar.markdown("---")

if tipo_ativo == "Ações":
    with st.spinner("Carregando base de Ações..."): df_dados = carregar_dados_acoes()
    if not df_dados.empty:
        st.sidebar.header("🔍 Filtros de Ações")
        st.sidebar.button("🗑️ Limpar Todos os Filtros", on_click=limpar_filtros_acoes, type="primary", use_container_width=True)
        
        busca = st.sidebar.text_input("Buscar Ticker (ex: BBAS3)", key='f_busca').upper()
        
        # Filtros de Tendência Gráfica (Médias Móveis)
        with st.sidebar.expander("📈 Rastreador de Tendências", expanded=True):
            opcoes_tv = st.multiselect("Sinal Geral", ["Compra", "Venda", "Manter"], key='f_tv')
            
            p_diario = st.selectbox("Média Móvel Diária", [20, 50, 200], index=1)
            t_diario = st.multiselect("Tendência Diária", ["🟢 Alta", "🔴 Baixa"], key='f_tend_d')
            
            p_semanal = st.selectbox("Média Móvel Semanal", [20, 50], index=0)
            t_semanal = st.multiselect("Tendência Semanal", ["🟢 Alta", "🔴 Baixa"], key='f_tend_s')
            
            p_mensal = st.selectbox("Média Móvel Mensal", [20, 50], index=0)
            t_mensal = st.multiselect("Tendência Mensal", ["🟢 Alta", "🔴 Baixa"], key='f_tend_m')

        st.sidebar.subheader("📊 Classificação e Valuation")
        apenas_ibov = st.sidebar.checkbox("Apenas ações do IBOV", key='f_apenas_ibov')
        opcoes_tamanho = st.sidebar.multiselect("Tamanho", ["Blue Chip", "Mid Cap", "Small Cap"], key='f_tamanho')
        filtro_barsi = st.sidebar.checkbox("Abaixo do Preço Teto (Barsi)", key='f_barsi')
        filtro_graham = st.sidebar.checkbox("Abaixo do Preço Justo (Graham)", key='f_graham')
        
        with st.sidebar.expander("💼 Preço & Múltiplos"):
            min_pvp = st.number_input("P/VP Mínimo", step=0.1, key='f_pvp_min')
            max_pvp = st.number_input("P/VP Máximo", step=0.1, key='f_pvp_max')
            min_pl = st.number_input("P/L Mínimo", step=1.0, key='f_pl_min')
            max_pl = st.number_input("P/L Máximo", step=1.0, key='f_pl_max')
            min_dy = st.number_input("Dividend Yield Mín. (%)", step=0.5, key='f_dy')
            max_evebitda = st.number_input("EV/EBITDA Máx. (0=desativa)", step=1.0, key='f_evebitda')

        with st.sidebar.expander("💼 Rentabilidade & Saúde"):
            min_roe = st.number_input("ROE Mínimo (%)", step=1.0, key='f_roe')
            min_mebit = st.number_input("Margem EBIT Mín. (%)", step=1.0, key='f_mebit')
            min_mliq = st.number_input("Margem Líquida Mín. (%)", step=1.0, key='f_mliq')
            min_liq = st.number_input("Liquidez Corrente Mínima", step=0.1, key='f_liq')
            min_cagr = st.number_input("CAGR Receita Mínimo (%)", step=1.0, key='f_cagr')

        # Calculando as tendências em tempo real com base no período selecionado
        df_dados['Tend. Diária'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_diario}', 0)), axis=1)
        df_dados['Tend. Semanal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_semanal}|1W', 0)), axis=1)
        df_dados['Tend. Mensal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_mensal}|1M', 0)), axis=1)

        # Aplicando filtros
        df_f = df_dados.copy()
        if busca: df_f = df_f[df_f['Ticker'].str.contains(busca)]
        if apenas_ibov: df_f = df_f[df_f['IBOV'] == "Sim"]
        if opcoes_tamanho: df_f = df_f[df_f['Categoria'].isin(opcoes_tamanho)]
        if opcoes_tv: df_f = df_f[df_f['Sinal Técnico'].isin(opcoes_tv)]
        
        # Filtros de Tendência
        if t_diario: df_f = df_f[df_f['Tend. Diária'].isin(t_diario)]
        if t_semanal: df_f = df_f[df_f['Tend. Semanal'].isin(t_semanal)]
        if t_mensal: df_f = df_f[df_f['Tend. Mensal'].isin(t_mensal)]

        if filtro_barsi: df_f = df_f[df_f['Cotação'] < df_f['Preço Teto (Barsi)']]
        if filtro_graham: df_f = df_f[df_f['Cotação'] < df_f['Preço Justo (Graham)']]
        
        if max_pvp > 0: df_f = df_f[(df_f['P/VP'] >= min_pvp) & (df_f['P/VP'] <= max_pvp)]
        if max_pl > 0: df_f = df_f[(df_f['P/L'] >= min_pl) & (df_f['P/L'] <= max_pl)]
        if min_dy > 0: df_f = df_f[df_f['Div. Yield (%)'] >= min_dy]
        if max_evebitda > 0: df_f = df_f[df_f['EV/EBITDA'] <= max_evebitda]
        if min_roe > 0: df_f = df_f[df_f['ROE (%)'] >= min_roe]
        if min_mebit > 0: df_f = df_f[df_f['Margem EBIT (%)'] >= min_mebit]
        if min_mliq > 0: df_f = df_f[df_f['Margem Líquida (%)'] >= min_mliq]
        if min_liq > 0: df_f = df_f[df_f['Liq. Corrente'] >= min_liq]
        if min_cagr > 0: df_f = df_f[df_f['CAGR Receita 5a (%)'] >= min_cagr]

        st.subheader(f"🏢 Ações Encontradas: {len(df_f)}")
        colunas = ['Ticker', 'IBOV', 'Tend. Mensal', 'Tend. Semanal', 'Tend. Diária', 'Sinal Técnico', 'Cotação', 'Preço Justo (Graham)', 'Preço Teto (Barsi)', 'Div. Yield (%)', 'P/L', 'P/VP', 'ROE (%)', 'Margem EBIT (%)']
        st.dataframe(df_f[colunas].style.format({"Cotação": "R$ {:.2f}", "Preço Justo (Graham)": "R$ {:.2f}", "Preço Teto (Barsi)": "R$ {:.2f}", "Div. Yield (%)": "{:.1f}%", "ROE (%)": "{:.1f}%", "Margem EBIT (%)": "{:.1f}%", "P/L": "{:.2f}", "P/VP": "{:.2f}"}), use_container_width=True, height=600)

else:
    with st.spinner("Carregando base de FIIs..."): df_dados = carregar_dados_fiis()
    if not df_dados.empty:
        st.sidebar.header("🏢 Filtros de FIIs")
        st.sidebar.button("🗑️ Limpar Filtros", on_click=limpar_filtros_fiis, type="primary", use_container_width=True)
        
        busca = st.sidebar.text_input("Buscar FII (ex: MXRF11)", key='f_busca').upper()
        opcoes_seg = st.sidebar.multiselect("Segmento", sorted(df_dados['Segmento'].unique().tolist()), key='f_fii_segmento')
        
        with st.sidebar.expander("📈 Rastreador de Tendências", expanded=True):
            opcoes_tv = st.multiselect("Sinal Geral", ["Compra", "Venda", "Manter"], key='f_tv')
            p_diario = st.selectbox("Média Móvel Diária", [20, 50, 200], index=1)
            t_diario = st.multiselect("Tendência Diária", ["🟢 Alta", "🔴 Baixa"], key='f_tend_d')
            p_semanal = st.selectbox("Média Móvel Semanal", [20, 50], index=0)
            t_semanal = st.multiselect("Tendência Semanal", ["🟢 Alta", "🔴 Baixa"], key='f_tend_s')

        st.sidebar.subheader("🎯 Metodologias e Indicadores")
        filtro_barsi = st.sidebar.checkbox("Abaixo do Preço Teto (Barsi)", key='f_fii_barsi')
        
        min_pvp = st.sidebar.number_input("P/VP Mínimo", step=0.05, key='f_fii_pvp_min')
        max_pvp = st.sidebar.number_input("P/VP Máximo (0=desativa)", step=0.05, key='f_fii_pvp_max')
        min_dy = st.sidebar.number_input("Dividend Yield Mín. (%)", step=0.5, key='f_fii_dy_min')
        max_vac = st.sidebar.number_input("Vacância Máxima (%)", step=1.0, key='f_fii_vacancia_max')
        min_liq = st.sidebar.number_input("Liquidez Mínima (R$)", step=100000.0, format="%f", key='f_fii_liq_min')

        df_dados['Tend. Diária'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_diario}', 0)), axis=1)
        df_dados['Tend. Semanal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_semanal}|1W', 0)), axis=1)
        df_dados['Tend. Mensal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA20|1M', 0)), axis=1) # Fixo em 20 pra FIIs (histórico curto)

        df_f = df_dados.copy()
        if busca: df_f = df_f[df_f['Ticker'].str.contains(busca)]
        if opcoes_seg: df_f = df_f[df_f['Segmento'].isin(opcoes_seg)]
        if opcoes_tv: df_f = df_f[df_f['Sinal Técnico'].isin(opcoes_tv)]
        if t_diario: df_f = df_f[df_f['Tend. Diária'].isin(t_diario)]
        if t_semanal: df_f = df_f[df_f['Tend. Semanal'].isin(t_semanal)]
        if filtro_barsi: df_f = df_f[df_f['Cotação'] < df_f['Preço Teto (Barsi)']]
        
        if max_pvp > 0: df_f = df_f[(df_f['P/VP'] >= min_pvp) & (df_f['P/VP'] <= max_pvp)]
        if min_dy > 0: df_f = df_f[df_f['Div. Yield (%)'] >= min_dy]
        if max_vac > 0: df_f = df_f[df_f['Vacância Média (%)'] <= max_vac]
        if min_liq > 0: df_f = df_f[df_f['Liquidez Diária (R$)'] >= min_liq]

        st.subheader(f"🏢 FIIs Encontrados: {len(df_f)}")
        colunas = ['Ticker', 'Segmento', 'Tend. Semanal', 'Tend. Diária', 'Sinal Técnico', 'Cotação', 'Preço Teto (Barsi)', 'Div. Yield (%)', 'P/VP', 'Vacância Média (%)', 'Liquidez Diária (R$)']
        st.dataframe(df_f[colunas].style.format({"Cotação": "R$ {:.2f}", "Preço Teto (Barsi)": "R$ {:.2f}", "Div. Yield (%)": "{:.1f}%", "P/VP": "{:.2f}", "Vacância Média (%)": "{:.1f}%", "Liquidez Diária (R$)": "R$ {:,.2f}"}), use_container_width=True, height=600)
