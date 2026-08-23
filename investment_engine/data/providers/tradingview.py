from __future__ import annotations
from ...infrastructure.http import HttpClient
from ...core.valuation.technical import tradingview_signal

# Keep fields named and map by key instead of positional indexes. This makes
# the adapter much less fragile when new descriptive fields are added.
TV_COLUMNS = [
    "name", "description", "exchange", "sector", "industry",
    "Recommend.All", "market_cap_basic", "Value.Traded",
    "SMA20", "SMA50", "SMA200", "SMA20|1W", "SMA50|1W", "SMA20|1M", "SMA50|1M",
    "high", "low", "close", "RSI", "BB.lower", "BB.upper",
]


class TradingViewScannerProvider:
    URL = "https://scanner.tradingview.com/brazil/scan"

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient()

    def fetch(self, asset_type: str = "stock") -> list[dict]:
        payload = {
            "filter": [{"left": "type", "operation": "equal", "right": asset_type}],
            "options": {"lang": "pt"},
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": TV_COLUMNS,
        }
        data = self.http.post(self.URL, json=payload).json()
        result = []
        for item in data.get("data", []):
            values = item.get("d")
            if not isinstance(values, list) or len(values) < len(TV_COLUMNS):
                continue
            row = dict(zip(TV_COLUMNS, values))
            raw_name = row.get("name")
            if not raw_name:
                continue
            ticker = str(raw_name).split(":")[-1]
            score = row.get("Recommend.All")
            result.append({
                "ticker": ticker,
                "name": row.get("description") or None,
                "exchange": row.get("exchange") or None,
                "sector": row.get("sector") or None,
                "industry": row.get("industry") or None,
                "score_tv": score,
                "signal_tv": tradingview_signal(score).value,
                "market_cap": row.get("market_cap_basic"),
                "daily_liquidity": row.get("Value.Traded"),
                "sma20": row.get("SMA20"), "sma50": row.get("SMA50"), "sma200": row.get("SMA200"),
                "sma20_1w": row.get("SMA20|1W"), "sma50_1w": row.get("SMA50|1W"),
                "sma20_1m": row.get("SMA20|1M"), "sma50_1m": row.get("SMA50|1M"),
                "high": row.get("high"), "low": row.get("low"), "close": row.get("close"),
                "rsi14": row.get("RSI"), "bb_lower": row.get("BB.lower"), "bb_upper": row.get("BB.upper"),
            })
        return result
