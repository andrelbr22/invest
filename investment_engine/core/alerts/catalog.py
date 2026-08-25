from __future__ import annotations


MARKET_ALERT_CATALOG = (
    {"key": "IBOV", "label": "Ibovespa", "group": "Brasil", "symbols": ["^BVSP"], "unit": "pontos"},
    {"key": "IFIX", "label": "IFIX", "group": "Brasil", "symbols": ["^IFIX", "IFIX.SA", "XFIX11.SA"], "unit": "pontos"},
    {"key": "NYSE", "label": "NYSE Composite", "group": "Índices globais", "symbols": ["^NYA"], "unit": "pontos"},
    {"key": "NASDAQ", "label": "NASDAQ Composite", "group": "Índices globais", "symbols": ["^IXIC"], "unit": "pontos"},
    {"key": "SP500", "label": "S&P 500", "group": "Índices globais", "symbols": ["^GSPC"], "unit": "pontos"},
    {"key": "DOW", "label": "Dow Jones Industrial Average", "group": "Índices globais", "symbols": ["^DJI"], "unit": "pontos"},
    {"key": "NIKKEI", "label": "Nikkei 225", "group": "Índices globais", "symbols": ["^N225"], "unit": "pontos"},
    {"key": "SSE", "label": "Shanghai SSE", "group": "Índices globais", "symbols": ["000001.SS"], "unit": "pontos"},
    {"key": "EUROSTOXX50", "label": "Euro Stoxx 50", "group": "Índices globais", "symbols": ["^STOXX50E"], "unit": "pontos"},
    {"key": "STOXX600", "label": "STOXX Europe 600", "group": "Índices globais", "symbols": ["^STOXX", "EXSA.DE"], "unit": "pontos"},
    {"key": "MSCIEUROPE", "label": "MSCI Europe (proxy IEUR)", "group": "Índices globais", "symbols": ["IEUR"], "unit": "USD", "proxy": True},
    {"key": "VIX", "label": "VIX", "group": "Risco", "symbols": ["^VIX"], "unit": "pontos"},
    {"key": "DXY", "label": "Índice Dólar DXY", "group": "Risco", "symbols": ["DX-Y.NYB"], "unit": "pontos"},
    {"key": "GOLD", "label": "Ouro", "group": "Commodities", "symbols": ["GC=F"], "unit": "USD"},
    {"key": "SILVER", "label": "Prata", "group": "Commodities", "symbols": ["SI=F"], "unit": "USD"},
    {"key": "BRENT", "label": "Petróleo Brent", "group": "Commodities", "symbols": ["BZ=F"], "unit": "USD"},
    {"key": "WTI", "label": "Petróleo WTI", "group": "Commodities", "symbols": ["CL=F"], "unit": "USD"},
    {"key": "BTCUSD", "label": "Bitcoin / Dólar", "group": "Criptoativos", "symbols": ["BTC-USD"], "unit": "USD"},
    {"key": "BTCBRL", "label": "Bitcoin / Real", "group": "Criptoativos", "symbols": ["BTC-BRL"], "unit": "R$"},
    {"key": "ETHUSD", "label": "Ethereum / Dólar", "group": "Criptoativos", "symbols": ["ETH-USD"], "unit": "USD"},
    {"key": "ETHBRL", "label": "Ethereum / Real", "group": "Criptoativos", "symbols": ["ETH-BRL"], "unit": "R$"},
    {"key": "USDBRL", "label": "Dólar / Real", "group": "Câmbio", "symbols": ["BRL=X"], "unit": "R$"},
    {"key": "EURUSD", "label": "Euro / Dólar", "group": "Câmbio", "symbols": ["EURUSD=X"], "unit": "USD"},
)


def market_alert_catalog() -> list[dict]:
    return [
        {
            **item,
            "market_scope": "market",
            "interval_minutes": 30,
            "continuous_monitoring": True,
        }
        for item in MARKET_ALERT_CATALOG
    ]


def market_alert_item(key: str | None) -> dict | None:
    clean = str(key or "").strip().upper()
    return next((dict(item) for item in MARKET_ALERT_CATALOG if item["key"] == clean), None)
