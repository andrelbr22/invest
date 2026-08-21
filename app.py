import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import math

st.set_page_config(page_title="Screener Avançado", layout="wide", initial_sidebar_state="expanded")

st.title("📊 Screener Avançado de Investimentos")
st.markdown("Cruzamento Fundamentalista, Rastreador de Tendências e Indicadores de Valuation.")

# ==========================================
# 1. CONFIGURAÇÃO DE ESTADO E SETUP CNPI FLEXÍVEL (~30%)
# ==========================================
def aplicar_setup_cnpi_acoes():
    st.session_state.f_busca = ''
    st.session_state.f_tv = []
    st.session_state.f_tend_d = []; st.session_state.f_tend_s = []; st.session_state.f_tend_m = []
    st.session_state.f_tamanho = []; st.session_state.f_apenas_ibov = False
    st.session_state.f_barsi = False; st.session_state.f_graham = False
    
    st.session_state.f_roe = 8.0           
    st.session_state.f_mebit = 5.0         
    st.session_state.f_mliq = 0.0 
    st.session_state.f_cagr = 0.0           
    st.session_state.f_evebitda = 0.0 
    st.session_state.f_dy = 0.0
    st.session_state.f_pvp_min = 0.2        
    st.session_state.f_pvp_max = 5.0        
    st.session_state.f_pl_min = 0.1         
    st.session_state.f_pl_max = 20.0        
    st.session_state.f_liq = 1.0            

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
    # Nota: f_liq_global (liquidez financeira) NÃO é resetada aqui de propósito.

def aplicar_setup_cnpi_fiis():
    st.session_state.f_busca = ''
    st.session_state.f_tv = []
    st.session_state.f_tend_d = []; st.session_state.f_tend_s = []; st.session_state.f_tend_m = []
    st.session_state.f_fii_segmento = []
    st.session_state.f_fii_barsi = False
    
    st.session_state.f_fii_pvp_min = 0.70   
    st.session_state.f_fii_pvp_max = 1.10   
    st.session_state.f_fii_dy_min = 8.0     
    st.session_state.f_fii_vacancia_max = 15.0 

def limpar_filtros_fiis():
    st.session_state.f_busca = ''
    st.session_state.f_tv = []
    st.session_state.f_tend_d = []; st.session_state.f_tend_s = []; st.session_state.f_tend_m = []
    st.session_state.f_fii_segmento = []
    st.session_state.f_fii_barsi = False
    st.session_state.f_fii_pvp_min = 0.0; st.session_state.f_fii_pvp_max = 10.0
    st.session_state.f_fii_dy_min = 0.0; st.session_state.f_fii_vacancia_max = 100.0
    # Nota: f_liq_global NÃO é resetada aqui.

# Inicialização global do estado e do filtro permanente de liquidez
if 'iniciado' not in st.session_state:
    aplicar_setup_cnpi_acoes()
    aplicar_setup_cnpi_fiis()
    st.session_state.tipo_ativo = 'Ações'
    st.session_state.f_liq_global = 1000000.0 # Filtro base permanente de R$ 1 Milhão
    st.session_state.iniciado = True

# ==========================================
# 2. FUNÇÕES AUXILIARES
# ==========================================
def classificar_sinal(score):
    if pd.isna(score): return "Sem Dados"
    return "Compra" if score > 0.1 else "Venda" if score < -0.1 else "Manter"

def calc_tendencia(cotacao, sma):
    try:
        cot_val = float(cotacao)
        sma_val = float(sma)
        if pd.isna(sma_val) or sma_val == 0 or pd.isna(cot_val) or cot_val == 0: 
            return "Sem Dados"
        return "🟢 Alta" if cot_val > sma_val else "🔴 Baixa"
    except:
        return "Sem Dados"

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
    except: 
        return ['ABEV3', 'B3SA3', 'BBAS3', 'BBDC4', 'ITUB4', 'PETR4', 'VALE3', 'WEGE3']

# Incluindo 'Value.Traded' para capturar o volume financeiro médio/recente
TV_COLS = ["name", "Recommend.All", "market_cap_basic", "Value.Traded", "SMA20", "SMA50", "SMA200", "SMA20|1W", "SMA50|1W", "SMA20|1M", "SMA50|1M"]

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
        
        tv_dict = {}
        for item in resp.get('data', []):
            d = item['d']
            tv_dict[d[0].split(":")[-1]] = {
                'Score TV': d[1], 'Market Cap': d[2], 'Liq. Diária': d[3] if d[3] is not None else 0.0,
                'SMA20': d[4], 'SMA50': d[5], 'SMA200': d[6],
                'SMA20|1W': d[7], 'SMA50|1W': d[8], 'SMA20|1M': d[9], 'SMA50|1M': d[10]
            }
        df_tv = pd.DataFrame.from_dict(tv_dict, orient='index').reset_index().rename(columns={'index': 'Ticker'})
        df = pd.merge(df, df_tv, on='Ticker', how='left')
    except:
        df['Liq. Diária'] = 0.0
        for col in TV_COLS[3:]: df[col] = None

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
                'Score TV': d[1], 'Liq. Diária': d[3] if d[3] is not None else 0.0,
                'SMA20': d[4], 'SMA50': d[5], 'SMA200': d[6],
                'SMA20|1W': d[7], 'SMA50|1W': d[8], 'SMA20|1M': d[9], 'SMA50|1M': d[10]
            }
        df_tv = pd.DataFrame.from_dict(tv_dict, orient='index').reset_index().rename(columns={'index': 'Ticker'})
        df = pd.merge(df, df_tv, on='Ticker', how='left')
    except:
        df['Liq. Diária'] = df.get('Liquidez Diária (R$)', 0.0)
        for col in TV_COLS[3:]: df[col] = None

    df['Sinal Técnico'] = df['Score TV'].apply(classificar_sinal)
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    df['Margem Barsi (%)'] = df.apply(lambda r: ((r['Preço Teto (Barsi)'] - r['Cotação']) / r['Cotação']) * 100 if r['Cotação'] > 0 and r['Preço Teto (Barsi)'] > 0 else 0, axis=1)
    df['DY Mensal Est. (%)'] = df.apply(lambda r: (math.pow(1 + (r['Div. Yield (%)'] / 100), 1/12) - 1) * 100 if r['Div. Yield (%)'] > 0 else 0, axis=1)
    
    return df

# ==========================================
# 5. RENDERIZAÇÃO DA BARRA LATERAL E CONTROLES
# ==========================================
st.sidebar.title("Configurações")
tipo_ativo = st.sidebar.radio("1. Selecione o mercado:", ("Ações", "Fundos Imobiliários (FIIs)"), key="tipo_ativo")
st.sidebar.markdown("---")

# Filtro Permanente de Liquidez Diária (Não afetado pelo botão "Limpar Tudo")
st.sidebar.subheader("💧 Liquidez Mínima")
filtro_liq_permanente = st.sidebar.number_input(
    "Volume Diário Mín. (R$)", 
    min_value=0.0, 
    step=500000.0, 
    format="%.0f",
    key='f_liq_global',
    help="Filtro permanente de segurança institucional. Não é resetado pelo botão 'Limpar Tudo'."
)
st.sidebar.markdown("---")

# ==========================================
# 6. LÓGICA E TELAS - AÇÕES
# ==========================================
if tipo_ativo == "Ações":
    with st.spinner("Carregando base de Ações..."): 
        df_dados = carregar_dados_acoes()
        
    if not df_dados.empty:
        st.sidebar.header("🔍 Filtros de Ações")
        
        col1, col2 = st.sidebar.columns(2)
        with col1:
            st.button("🧹 Limpar Tudo", on_click=limpar_filtros_acoes, use_container_width=True)
        with col2:
            st.button("🎯 Padrão CNPI", on_click=aplicar_setup_cnpi_acoes, type="primary", use_container_width=True)
            
        busca = st.sidebar.text_input("Buscar Ticker (ex: BBAS3)", key='f_busca').upper()
        
        with st.sidebar.expander("📈 Rastreador de Tendências", expanded=False):
            opcoes_tv = st.multiselect("Sinal Geral (TradingView)", ["Compra", "Venda", "Manter"], key='f_tv')
            p_diario = st.selectbox("Período da Média Diária", [20, 50, 200], index=0)
            t_diario = st.multiselect("Tendência Diária", ["🟢 Alta", "🔴 Baixa"], key='f_tend_d')
            p_semanal = st.selectbox("Período da Média Semanal", [20, 50], index=0)
            t_semanal = st.multiselect("Tendência Semanal", ["🟢 Alta", "🔴 Baixa"], key='f_tend_s')
            p_mensal = st.selectbox("Período da Média Mensal", [20, 50], index=0)
            t_mensal = st.multiselect("Tendência Mensal", ["🟢 Alta", "🔴 Baixa"], key='f_tend_m')

        st.sidebar.subheader("📊 Classificação e Valuation")
        apenas_ibov = st.sidebar.checkbox("Apenas ações do IBOV", key='f_apenas_ibov')
        opcoes_tamanho = st.sidebar.multiselect("Tamanho", ["Blue Chip", "Mid Cap", "Small Cap"], key='f_tamanho')
        filtro_barsi = st.sidebar.checkbox("Cotação Abaixo do Preço Teto (Barsi)", key='f_barsi')
        filtro_graham = st.sidebar.checkbox("Cotação Abaixo do Preço Justo (Graham)", key='f_graham')
        
        with st.sidebar.expander("💼 Preço & Múltiplos"):
            min_pvp = st.number_input("P/VP Mínimo", step=0.1, key='f_pvp_min')
            max_pvp = st.number_input("P/VP Máximo (0=desativa)", step=0.1, key='f_pvp_max')
            min_pl = st.number_input("P/L Mínimo", step=1.0, key='f_pl_min')
            max_pl = st.number_input("P/L Máximo (0=desativa)", step=1.0, key='f_pl_max')
            min_dy = st.number_input("Dividend Yield Mín. (%)", step=0.5, key='f_dy')
            max_evebitda = st.number_input("EV/EBITDA Máx. (0=desativa)", step=1.0, key='f_evebitda')

        with st.sidebar.expander("💼 Rentabilidade & Saúde"):
            min_roe = st.number_input("ROE Mínimo (%)", step=1.0, key='f_roe')
            min_mebit = st.number_input("Margem EBIT Mín. (%)", step=1.0, key='f_mebit')
            min_mliq = st.number_input("Margem Líquida Mín. (%)", step=1.0, key='f_mliq')
            min_liq = st.number_input("Liquidez Corrente Mínima", step=0.1, key='f_liq')
            min_cagr = st.number_input("CAGR Receita Mínimo (%)", step=1.0, key='f_cagr')

        df_dados['Tend. Diária'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_diario}', 0)), axis=1)
        df_dados['Tend. Semanal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_semanal}|1W', 0)), axis=1)
        df_dados['Tend. Mensal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_mensal}|1M', 0)), axis=1)

        df_f = df_dados.copy()
        
        # Aplicação do Filtro Permanente de Liquidez
        if filtro_liq_permanente > 0:
            df_f = df_f[df_f['Liq. Diária'] >= filtro_liq_permanente]
            
        if busca: df_f = df_f[df_f['Ticker'].str.contains(busca)]
        if apenas_ibov: df_f = df_f[df_f['IBOV'] == "Sim"]
        if opcoes_tamanho: df_f = df_f[df_f['Categoria'].isin(opcoes_tamanho)]
        if opcoes_tv: df_f = df_f[df_f['Sinal Técnico'].isin(opcoes_tv)]
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
        
        # Mapeamento com nomes curtos para colunas estreitas
        colunas_disponiveis = {
            'Ticker': 'Ticker', 'IBOV': 'IBOV', 'Tend. Mensal': 'T. Mês', 
            'Tend. Semanal': 'T. Sem', 'Tend. Diária': 'T. Dia', 'Sinal Técnico': 'Sinal', 
            'Cotação': 'Preço', 'Preço Justo (Graham)': 'V. Graham', 'Margem Graham (%)': 'M. Graham', 
            'Preço Teto (Barsi)': 'T. Barsi', 'Margem Barsi (%)': 'M. Barsi', 'Div. Yield (%)': 'DY', 
            'DY Mensal Est. (%)': 'DY Mês', 'P/L': 'P/L', 'P/VP': 'P/VP', 'ROE (%)': 'ROE', 
            'Margem EBIT (%)': 'M. EBIT', 'Liq. Corrente': 'Liq. Corr', 'Liq. Diária': 'Liq. Diária'
        }
        
        colunas_padrao = ['Ticker', 'Preço', 'V. Graham', 'M. Graham', 'T. Barsi', 'M. Barsi', 'DY', 'DY Mês', 'P/L', 'P/VP', 'ROE', 'Liq. Diária']
        
        colunas_escolhidas = st.sidebar.multiselect(
            "👁️ Ocultar/Exibir Colunas", 
            options=list(colunas_disponiveis.values()), 
            default=[colunas_disponiveis[c] for c in colunas_padrao if c in colunas_disponiveis]
        )
        
        # Mapeia de volta para os nomes reais internos do dataframe
        chaves_reais = [k for k, v in colunas_disponiveis.items() if v in colunas_escolhidas]

        if chaves_reais:
            st.dataframe(df_f[chaves_reais].rename(columns=colunas_disponiveis).style.format({
                "Preço": "R$ {:.2f}", "V. Graham": "R$ {:.2f}", "M. Graham": "{:+.1f}%",
                "T. Barsi": "R$ {:.2f}", "M. Barsi": "{:+.1f}%", "DY": "{:.1f}%", 
                "DY Mês": "{:.2f}%", "ROE": "{:.1f}%", "M. EBIT": "{:.1f}%", 
                "P/L": "{:.2f}", "P/VP": "{:.2f}", "Liq. Corr": "{:.2f}",
                "Liq. Diária": "R$ {:,.0f}"
            }), use_container_width=True, height=600)
        else:
            st.warning("Selecione ao menos uma coluna para exibir na tabela.")

# ==========================================
# 7. LÓGICA E TELAS - FIIs
# ==========================================
else:
    with st.spinner("Carregando base de FIIs..."): 
        df_dados = carregar_dados_fiis()
        
    if not df_dados.empty:
        st.sidebar.header("🏢 Filtros de FIIs")
        
        col1, col2 = st.sidebar.columns(2)
        with col1:
            st.button("🧹 Limpar Tudo", on_click=limpar_filtros_fiis, use_container_width=True)
        with col2:
            st.button("🎯 Padrão CNPI", on_click=aplicar_setup_cnpi_fiis, type="primary", use_container_width=True)
        
        busca = st.sidebar.text_input("Buscar FII (ex: MXRF11)", key='f_busca').upper()
        opcoes_seg = st.sidebar.multiselect("Filtrar por Segmento", sorted(df_dados['Segmento'].unique().tolist()), key='f_fii_segmento')
        
        with st.sidebar.expander("📈 Rastreador de Tendências", expanded=False):
            opcoes_tv = st.multiselect("Sinal Geral (TradingView)", ["Compra", "Venda", "Manter"], key='f_tv')
            p_diario = st.selectbox("Período da Média Diária", [20, 50, 200], index=0)
            t_diario = st.multiselect("Tendência Diária", ["🟢 Alta", "🔴 Baixa"], key='f_tend_d')
            p_semanal = st.selectbox("Período da Média Semanal", [20, 50], index=0)
            t_semanal = st.multiselect("Tendência Semanal", ["🟢 Alta", "🔴 Baixa"], key='f_tend_s')
            p_mensal = st.selectbox("Período da Média Mensal", [20, 50], index=0)
            t_mensal = st.multiselect("Tendência Mensal", ["🟢 Alta", "🔴 Baixa"], key='f_tend_m')

        st.sidebar.subheader("🎯 Metodologias e Indicadores")
        filtro_barsi = st.sidebar.checkbox("Cotação Abaixo do Preço Teto (Barsi)", key='f_fii_barsi')
        
        min_pvp = st.sidebar.number_input("P/VP Mínimo", step=0.05, key='f_fii_pvp_min')
        max_pvp = st.sidebar.number_input("P/VP Máximo (0=desativa)", step=0.05, key='f_fii_pvp_max')
        min_dy = st.sidebar.number_input("Dividend Yield Mín. (%)", step=0.5, key='f_fii_dy_min')
        max_vac = st.sidebar.number_input("Vacância Máxima (%)", step=1.0, key='f_fii_vacancia_max')

        df_dados['Tend. Diária'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_diario}', 0)), axis=1)
        df_dados['Tend. Semanal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_semanal}|1W', 0)), axis=1)
        df_dados['Tend. Mensal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_mensal}|1M', 0)), axis=1)

        df_f = df_dados.copy()
        
        # Aplicação do Filtro Permanente de Liquidez
        if filtro_liq_permanente > 0:
            df_f = df_f[df_f['Liq. Diária'] >= filtro_liq_permanente]
            
        if busca: df_f = df_f[df_f['Ticker'].str.contains(busca)]
        if opcoes_seg: df_f = df_f[df_f['Segmento'].isin(opcoes_seg)]
        if opcoes_tv: df_f = df_f[df_f['Sinal Técnico'].isin(opcoes_tv)]
        if t_diario: df_f = df_f[df_f['Tend. Diária'].isin(t_diario)]
        if t_semanal: df_f = df_f[df_f['Tend. Semanal'].isin(t_semanal)]
        if t_mensal: df_f = df_f[df_f['Tend. Mensal'].isin(t_mensal)]
        if filtro_barsi: df_f = df_f[df_f['Cotação'] < df_f['Preço Teto (Barsi)']]
        
        if max_pvp > 0: df_f = df_f[(df_f['P/VP'] >= min_pvp) & (df_f['P/VP'] <= max_pvp)]
        if min_dy > 0: df_f = df_f[df_f['Div. Yield (%)'] >= min_dy]
        if max_vac > 0: df_f = df_f[df_f['Vacância Média (%)'] <= max_vac]

        st.subheader(f"🏢 FIIs Encontrados: {len(df_f)}")
        
        colunas_disponiveis_fii = {
            'Ticker': 'Ticker', 'Segmento': 'Segmento', 'Tend. Mensal': 'T. Mês', 
            'Tend. Semanal': 'T. Sem', 'Tend. Diária': 'T. Dia', 'Sinal Técnico': 'Sinal', 
            'Cotação': 'Preço', 'Preço Teto (Barsi)': 'T. Barsi', 'Margem Barsi (%)': 'M. Barsi', 
            'Div. Yield (%)': 'DY', 'DY Mensal Est. (%)': 'DY Mês', 'P/VP': 'P/VP', 
            'Vacância Média (%)': 'Vacância', 'Liq. Diária': 'Liq. Diária'
        }
        
        colunas_padrao_fii = ['Ticker', 'Segmento', 'Preço', 'T. Barsi', 'M. Barsi', 'DY', 'DY Mês', 'P/VP', 'Vacância', 'Liq. Diária']
        
        colunas_escolhidas_fii = st.sidebar.multiselect(
            "👁️ Ocultar/Exibir Colunas", 
            options=list(colunas_disponiveis_fii.values()), 
            default=[colunas_disponiveis_fii[c] for c in colunas_padrao_fii if c in colunas_disponiveis_fii]
        )
        
        chaves_reais_fii = [k for k, v in colunas_disponiveis_fii.items() if v in colunas_escolhidas_fii]

        if chaves_reais_fii:
            st.dataframe(df_f[chaves_reais_fii].rename(columns=colunas_disponiveis_fii).style.format({
                "Preço": "R$ {:.2f}", "T. Barsi": "R$ {:.2f}", "M. Barsi": "{:+.1f}%",
                "DY": "{:.1f}%", "DY Mês": "{:.2f}%", "P/VP": "{:.2f}", 
                "Vacância": "{:.1f}%", "Liq. Diária": "R$ {:,.0f}"
            }), use_container_width=True, height=600)
        else:
            st.warning("Selecione ao menos uma coluna para exibir na tabela.")
