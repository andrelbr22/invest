import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import math

# Configuração de Página e Estilo
st.set_page_config(page_title="Screener Avançado de Ações", layout="wide", initial_sidebar_state="expanded")

st.title("📊 Screener Avançado de Ações")
st.markdown("Cruzamento fundamentalista e técnico avançado com Metodologias de Valuation.")

# Função auxiliar para categorizar a recomendação do TradingView
def classificar_tendencia(score):
    if pd.isna(score):
        return "Sem Dados"
    if score > 0.1:
        return "Compra"
    elif score < -0.1:
        return "Venda"
    else:
        return "Manter"

@st.cache_data(ttl=3600)
def carregar_dados():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    # ==========================================
    # 1. EXTRAÇÃO FUNDAMENTUS
    # ==========================================
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
                    
                    # Capturando todas as colunas essenciais
                    dados_fund.append({
                        "Ticker": col[0].text.strip(),
                        "Cotação": limpar(col[1]),
                        "P/L": limpar(col[2]),
                        "P/VP": limpar(col[3]),
                        "Div. Yield (%)": limpar(col[5]),
                        "EV/EBITDA": limpar(col[11]),
                        "Margem Líquida (%)": limpar(col[13]),
                        "Liq. Corrente": limpar(col[14]),
                        "ROE (%)": limpar(col[16]),
                        "Dívida Bruta/Patrimônio": limpar(col[19]),
                        "CAGR Receita 5a (%)": limpar(col[20])
                    })
        df = pd.DataFrame(dados_fund)
    except Exception as e:
        st.error(f"Erro ao carregar Fundamentus: {e}")
        return pd.DataFrame()

    if df.empty: return df

    # ==========================================
    # 2. EXTRAÇÃO TRADINGVIEW
    # ==========================================
    try:
        payload_tv = {
            "filter": [{"left": "type", "operation": "equal", "right": "stock"}],
            "options": {"lang": "pt"},
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name", "Recommend.All"]
        }
        resp_tv = requests.post("https://scanner.tradingview.com/brazil/scan", json=payload_tv, timeout=15)
        res_json = resp_tv.json()
        
        tv_dict = {}
        for item in res_json.get('data', []):
            ticker_limpo = item['d'][0].split(":")[-1]
            tv_dict[ticker_limpo] = item['d'][1] # Pega o score numérico
            
        df_tv = pd.DataFrame(list(tv_dict.items()), columns=['Ticker', 'Score TV'])
        # Mescla preservando todas as ações do Fundamentus
        df = pd.merge(df, df_tv, on='Ticker', how='left')
        
    except Exception as e:
        df['Score TV'] = None

    # Transforma o score numérico em Texto (Compra, Venda, Manter)
    df['Recomendação Técnica'] = df['Score TV'].apply(classificar_tendencia)

    # ==========================================
    # 3. ENGENHARIA DE VALUATION
    # ==========================================
    df['VPA'] = df.apply(lambda r: r['Cotação'] / r['P/VP'] if r['P/VP'] > 0 else 0, axis=1)
    df['LPA'] = df.apply(lambda r: r['Cotação'] / r['P/L'] if r['P/L'] > 0 else 0, axis=1)
    
    df['Preço Justo (Graham)'] = df.apply(lambda r: math.sqrt(22.5 * r['VPA'] * r['LPA']) if r['VPA'] > 0 and r['LPA'] > 0 else 0, axis=1)
    df['Preço Teto (Barsi)'] = df.apply(lambda r: (r['Cotação'] * (r['Div. Yield (%)'] / 100)) / 0.06, axis=1)
    
    return df

with st.spinner("Atualizando base de dados em tempo real..."):
    df_acoes = carregar_dados()

if df_acoes.empty:
    st.warning("Não foi possível carregar os dados no momento.")
else:
    # ==========================================
    # INTERFACE DE FILTROS (BARRA LATERAL)
    # ==========================================
    st.sidebar.header("🔍 Filtros de Busca")
    busca = st.sidebar.text_input("Buscar Ticker (ex: BBAS3)").upper()
    
    # 1. Filtro Técnico (TradingView) - Agora 100% funcional
    st.sidebar.markdown("---")
    st.sidebar.subheader("📈 Análise Técnica")
    opcoes_tv = st.sidebar.multiselect(
        "Sinal do TradingView",
        options=["Compra", "Venda", "Manter", "Sem Dados"],
        default=[] # Deixe vazio para não filtrar nada no início
    )

    # 2. Filtros de Valuation (Metodologias)
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎯 Metodologias de Valuation")
    filtro_barsi = st.sidebar.checkbox("Cotação Abaixo do Preço Teto (Barsi)")
    filtro_graham = st.sidebar.checkbox("Cotação Abaixo do Preço Justo (Graham)")
    
    # 3. Indicadores Fundamentalistas Expansíveis
    st.sidebar.markdown("---")
    st.sidebar.subheader("💼 Filtros Fundamentalistas")
    
    with st.sidebar.expander("Rentabilidade & Margens"):
        min_roe = st.number_input("ROE Mínimo (%)", value=0.0, step=1.0)
        min_mliq = st.number_input("Margem Líquida Mín. (%)", value=0.0, step=1.0)
        min_cagr = st.number_input("CAGR Receita Mínimo (%)", value=0.0, step=1.0)

    with st.sidebar.expander("Preço & Múltiplos"):
        max_pvp = st.number_input("P/VP Máximo (0 = sem limite)", value=0.0, step=0.5)
        max_pl = st.number_input("P/L Máximo (0 = sem limite)", value=0.0, step=1.0)
        max_evebitda = st.number_input("EV/EBITDA Máximo (0 = sem limite)", value=0.0, step=1.0)
        min_dy = st.number_input("Dividend Yield Mín. (%)", value=0.0, step=0.5)

    with st.sidebar.expander("Saúde Financeira"):
        min_liq = st.number_input("Liquidez Corrente Mínima", value=0.0, step=0.1)
        max_div = st.number_input("Dívida/Patrimônio Máxima (0 = sem limite)", value=0.0, step=0.5)

    # ==========================================
    # APLICAÇÃO DOS FILTROS NO DATAFRAME
    # ==========================================
    df_filtrado = df_acoes.copy()
    
    if busca:
        df_filtrado = df_filtrado[df_filtrado['Ticker'].str.contains(busca)]
        
    if opcoes_tv:
        df_filtrado = df_filtrado[df_filtrado['Recomendação Técnica'].isin(opcoes_tv)]
        
    if filtro_barsi:
        df_filtrado = df_filtrado[df_filtrado['Cotação'] < df_filtrado['Preço Teto (Barsi)']]
        
    if filtro_graham:
        df_filtrado = df_filtrado[df_filtrado['Cotação'] < df_filtrado['Preço Justo (Graham)']]

    # Aplicação dos filtros numéricos (somente se o usuário alterou o valor padrão de 0.0)
    if min_roe > 0: df_filtrado = df_filtrado[df_filtrado['ROE (%)'] >= min_roe]
    if min_mliq > 0: df_filtrado = df_filtrado[df_filtrado['Margem Líquida (%)'] >= min_mliq]
    if min_cagr > 0: df_filtrado = df_filtrado[df_filtrado['CAGR Receita 5a (%)'] >= min_cagr]
    if max_pvp > 0: df_filtrado = df_filtrado[df_filtrado['P/VP'] <= max_pvp]
    if max_pl > 0: df_filtrado = df_filtrado[df_filtrado['P/L'] <= max_pl]
    if max_evebitda > 0: df_filtrado = df_filtrado[df_filtrado['EV/EBITDA'] <= max_evebitda]
    if min_dy > 0: df_filtrado = df_filtrado[df_filtrado['Div. Yield (%)'] >= min_dy]
    if min_liq > 0: df_filtrado = df_filtrado[df_filtrado['Liq. Corrente'] >= min_liq]
    if max_div > 0: df_filtrado = df_filtrado[df_filtrado['Dívida Bruta/Patrimônio'] <= max_div]

    # ==========================================
    # RENDERIZAÇÃO DA TABELA
    # ==========================================
    st.subheader(f"Ativos Encontrados: {len(df_filtrado)}")
    
    colunas_exibir = [
        'Ticker', 'Recomendação Técnica', 'Cotação', 'Preço Justo (Graham)', 'Preço Teto (Barsi)', 
        'Div. Yield (%)', 'P/L', 'P/VP', 'EV/EBITDA', 'ROE (%)', 'Margem Líquida (%)', 
        'Liq. Corrente', 'Dívida Bruta/Patrimônio', 'CAGR Receita 5a (%)'
    ]
    
    # Melhorando a exibição visual das colunas na tabela
    st.dataframe(
        df_filtrado[colunas_exibir].style.format({
            "Cotação": "R$ {:.2f}",
            "Preço Justo (Graham)": "R$ {:.2f}",
            "Preço Teto (Barsi)": "R$ {:.2f}",
            "Div. Yield (%)": "{:.1f}%",
            "ROE (%)": "{:.1f}%",
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
