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
    
    st.session_state.f_roe = 8.0           # Rentabilidade saudável
    st.session_state.f_mebit = 5.0         # Margem operacional viável
    st.session_state.f_mliq = 0.0 
    st.session_state.f_cagr = 0.0           
    st.session_state.f_evebitda = 0.0 
    st.session_state.f_dy = 0.0
    st.session_state.f_pvp_min = 0.2        # Evita distorções extremas
    st.session_state.f_pvp_max = 5.0        # Permite empresas premium
    st.session_state.f_pl_min = 0.1         # Foco em empresas com lucro
    st.session_state.f_pl_max = 20.0        # Teto razoável de mercado
    st.session_state.f_liq = 1.0            # Liquidez equilibrada

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
    st.session_state.f_fii_liq_min = 1000000.0 

def limpar_filtros_fiis():
    st.session_state.f_busca = ''
    st.session_state.f_tv = []
    st.session_state.f_tend_d = []; st.session_state.f_tend_s = []; st.session_state.f_tend_m = []
    st.session_state.f_fii_segmento = []
    st.session_state.f_fii_barsi = False
    st.session_state.f_fii_pvp_min = 0.0; st.session_state.f_fii_pvp_max = 10.0
    st.session_state.f_fii_dy_min = 0.0; st.session_state.f_fii_vacancia_max = 100.0
    st.session_state.f_fii_liq_min = 0.0

if 'iniciado' not in st.session_state:
    aplicar_setup_cnpi_acoes()
    aplicar_setup_cnpi_fiis()
    st.session_state.tipo_ativo = 'Ações'
    st.session_state.iniciado = True

# ==========================================
# 2. FUNÇÕES AUXILIARES E GLOSSÁRIO DE AJUDA
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

TV_COLS = ["name", "Recommend.All", "market_cap_basic", "SMA20", "SMA50", "SMA200", "SMA20|1W", "SMA50|1W", "SMA20|1M", "SMA50|1M"]

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
                'Score TV': d[1], 'Market Cap': d[2], 'SMA20': d[3], 'SMA50': d[4], 'SMA200': d[5],
                'SMA20|1W': d[6], 'SMA50|1W': d[7], 'SMA20|1M': d[8], 'SMA50|1M': d[9]
            }
        df_tv = pd.DataFrame.from_dict(tv_dict, orient='index').reset_index().rename(columns={'index': 'Ticker'})
        df = pd.merge(df, df_tv, on='Ticker', how='left')
    except:
        for col in TV_COLS[1:]: df[col] = None

    lista_ibov = obter_carteira_ibov()
    df['Sinal Técnico'] = df['Score TV'].apply(classificar_sinal)
    df['Categoria'] = df['Market Cap'].apply(lambda m: "Blue Chip" if m >= 15e9 else ("Small Cap" if m > 0 and m <= 3e9 else "Mid Cap" if m > 0 else "Desconhecido"))
    df['IBOV'] = df['Ticker'].apply(lambda x: "Sim" if x in lista_ibov else "Não")

    df['VPA'] = df.apply(lambda r: r['Cotação'] / r['P/VP'] if r['P/VP'] > 0 else 0, axis=1)
    df['LPA'] = df.apply(lambda r: r['Cotação'] / r['P/L'] if r['P/L'] > 0 else 0, axis=1)
    
    # Cálculos de Valuation e Margens (%) em relação à cotação
    df['Preço Justo (Graham)'] = df.apply(lambda r: math.sqrt(22.5 * r['VPA'] * r['LPA']) if r['VPA'] > 0 and r['LPA'] > 0 else 0, axis=1)
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    
    df['Margem Graham (%)'] = df.apply(lambda r: ((r['Preço Justo (Graham)'] - r['Cotação']) / r['Cotação']) * 100 if r['Cotação'] > 0 and r['Preço Justo (Graham)'] > 0 else 0, axis=1)
    df['Margem Barsi (%)'] = df.apply(lambda r: ((r['Preço Teto (Barsi)'] - r['Cotação']) / r['Cotação']) * 100 if r['Cotação'] > 0 and r['Preço Teto (Barsi)'] > 0 else 0, axis=1)
    df['DY Mensal Est. (%)'] = df['Div. Yield (%)'] / 12
    
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
                'Score TV': d[1], 'SMA20': d[3], 'SMA50': d[4], 'SMA200': d[5],
                'SMA20|1W': d[6], 'SMA50|1W': d[7], 'SMA20|1M': d[8], 'SMA50|1M': d[9]
            }
        df_tv = pd.DataFrame.from_dict(tv_dict, orient='index').reset_index().rename(columns={'index': 'Ticker'})
        df = pd.merge(df, df_tv, on='Ticker', how='left')
    except:
        for col in TV_COLS[1:]: df[col] = None

    df['Sinal Técnico'] = df['Score TV'].apply(classificar_sinal)
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    df['Margem Barsi (%)'] = df.apply(lambda r: ((r['Preço Teto (Barsi)'] - r['Cotação']) / r['Cotação']) * 100 if r['Cotação'] > 0 and r['Preço Teto (Barsi)'] > 0 else 0, axis=1)
    df['DY Mensal Est. (%)'] = df['Div. Yield (%)'] / 12
    
    return df

# ==========================================
# 5. RENDERIZAÇÃO DA BARRA LATERAL E CONTROLES
# ==========================================
st.sidebar.title("Configurações")
tipo_ativo = st.sidebar.radio("1. Selecione o mercado:", ("Ações", "Fundos Imobiliários (FIIs)"), key="tipo_ativo")
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
        
        # Tabela com as informações explicativas solicitadas no título
        colunas = [
            'Ticker', 'Cotação', 'Preço Justo (Graham)', 'Margem Graham (%)', 
            'Preço Teto (Barsi)', 'Margem Barsi (%)', 'Div. Yield (%)', 'DY Mensal Est. (%)', 
            'P/L', 'P/VP', 'ROE (%)', 'Margem EBIT (%)'
        ]
        
        st.dataframe(df_f[colunas].style.format({
            "Cotação": "R$ {:.2f}", 
            "Preço Justo (Graham)": "R$ {:.2f}", 
            "Margem Graham (%)": "{:+.1f}%",
            "Preço Teto (Barsi)": "R$ {:.2f}", 
            "Margem Barsi (%)": "{:+.1f}%",
            "Div. Yield (%)": "{:.1f}%", 
            "DY Mensal Est. (%)": "math.pow((1 + r['Div. Yield (%)'] / 100), 1/12) - 1) * 100",
            "ROE (%)": "{:.1f}%", 
            "Margem EBIT (%)": "{:.1f}%", 
            "P/L": "{:.2f}", 
            "P/VP": "{:.2f}"
        }), use_container_width=True, height=600,
        column_config={
            "Div. Yield (%)": st.column_config.NumberColumn("Div. Yield (Anual)", help="Dividendos pagos nos últimos 12 meses divididos pelo preço. Quanto maior, melhor."),
            "DY Mensal Est. (%)": st.column_config.NumberColumn("DY Mensal (Est.)", help="Média estimada de rendimento proporcional por mês. Quanto maior, melhor."),
            "Margem Graham (%)": st.column_config.NumberColumn("Margem Graham", help="Distância percentual entre o Preço Justo de Graham e a Cotação atual. Positivo indica desconto."),
            "Margem Barsi (%)": st.column_config.NumberColumn("Margem Barsi", help="Distância percentual entre o Preço Teto de Barsi e a Cotação atual. Positivo indica desconto em relação ao teto de dividendos."),
            "P/L": st.column_config.NumberColumn("P/L (Preço/Lucro)", help="Quanto o mercado paga pelo lucro da empresa. Quanto menor (sem ser negativo), mais barata."),
            "P/VP": st.column_config.NumberColumn("P/VP (Preço/Valor Patrimonial)", help="Compara o preço da ação com seu patrimônio líquido real. Abaixo de 1 pode indicar desconto patrimonial."),
            "ROE (%)": st.column_config.NumberColumn("ROE (Retorno s/ Patrimônio)", help="Mede a capacidade da empresa de gerar lucro com o dinheiro dos acionistas. Quanto maior, melhor.")
        })

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
        min_liq = st.sidebar.number_input("Liquidez Mínima (R$)", step=100000.0, format="%f", key='f_fii_liq_min')

        df_dados['Tend. Diária'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_diario}', 0)), axis=1)
        df_dados['Tend. Semanal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_semanal}|1W', 0)), axis=1)
        df_dados['Tend. Mensal'] = df_dados.apply(lambda r: calc_tendencia(r['Cotação'], r.get(f'SMA{p_mensal}|1M', 0)), axis=1)

        df_f = df_dados.copy()
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
        if min_liq > 0: df_f = df_f[df_f['Liquidez Diária (R$)'] >= min_liq]

        st.subheader(f"🏢 FIIs Encontrados: {len(df_f)}")
        colunas = [
            'Ticker', 'Segmento', 'Cotação', 'Preço Teto (Barsi)', 'Margem Barsi (%)', 
            'Div. Yield (%)', 'DY Mensal Est. (%)', 'P/VP', 'Vacância Média (%)', 'Liquidez Diária (R$)'
        ]
        
        st.dataframe(df_f[colunas].style.format({
            "Cotação": "R$ {:.2f}", 
            "Preço Teto (Barsi)": "R$ {:.2f}", 
            "Margem Barsi (%)": "{:+.1f}%",
            "Div. Yield (%)": "{:.1f}%", 
            "DY Mensal Est. (%)": "{:.2f}%",
            "P/VP": "{:.2f}", 
            "Vacância Média (%)": "{:.1f}%", 
            "Liquidez Diária (R$)": "R$ {:,.2f}"
        }), use_container_width=True, height=600,
        column_config={
            "Div. Yield (%)": st.column_config.NumberColumn("Div. Yield (Anual)", help="Rendimento de dividendos pagos pelo FII nos últimos 12 meses. Quanto maior, melhor."),
            "DY Mensal Est. (%)": st.column_config.NumberColumn("DY Mensal (Est.)", help="Média estimada do rendimento proporcional distribuído por mês. Quanto maior, melhor."),
            "Margem Barsi (%)": st.column_config.NumberColumn("Margem Barsi", help="Distância percentual entre o Preço Teto calculado e a Cotação atual do FII. Positivo indica que está abaixo do teto."),
            "P/VP": st.column_config.NumberColumn("P/VP", help="Preço sobre o Valor Patrimonial do FII. Abaixo de 1.0 indica que o fundo está sendo negociado com desconto sobre seus imóveis/ativos."),
            "Vacância Média (%)": st.column_config.NumberColumn("Vacância", help="Percentual do portfólio que está desocupado. Quanto menor, melhor.")
        })
