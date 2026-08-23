from __future__ import annotations

LABELS={
 "roe":"ROE","roic":"ROIC","ebit_margin":"Margem EBIT","net_margin":"Margem líquida","debt":"Endividamento",
 "current_ratio":"Liquidez corrente","earnings_growth":"Crescimento do lucro","revenue_growth":"Crescimento da receita",
 "revenue_cagr_5y":"CAGR da receita","earnings_cagr_5y":"CAGR do lucro","pe":"P/L","pbv":"P/VP","ev_ebitda":"EV/EBITDA",
 "dy":"Dividend Yield","graham_upside":"Graham","ffo_yield":"FFO Yield","cap_rate":"Cap Rate","vacancy":"Vacância",
 "ltv":"LTV","wale":"WALE","price_vs_sma20":"Preço vs M20","price_vs_sma50":"Preço vs M50","price_vs_sma200":"Preço vs M200",
 "ma_alignment":"Alinhamento das médias","rsi":"RSI","macd":"MACD","momentum_3m":"Momentum 3 meses","volatility":"Volatilidade",
 "drawdown":"Drawdown","net_debt_ebitda":"Dívida líquida/EBITDA","daily_liquidity":"Liquidez diária"
}


def explain_components(component_map):
    positives=[]; attention=[]; missing=[]
    for group_name, comp in component_map.items():
        if comp is None: continue
        for key,val in comp.details.items():
            label=LABELS.get(key,key)
            if val is None: missing.append(f"{label} ({group_name})")
            elif val >= 75: positives.append({"item":label,"group":group_name,"score":round(val,1)})
            elif val < 40: attention.append({"item":label,"group":group_name,"score":round(val,1)})
    positives=sorted(positives,key=lambda x:x["score"],reverse=True)[:6]
    attention=sorted(attention,key=lambda x:x["score"])[:6]
    return {"positives":positives,"attention":attention,"missing":missing[:10]}
