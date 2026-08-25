from __future__ import annotations
from datetime import datetime, timezone, timedelta
from ...infrastructure.http import HttpClient


class YahooPriceProvider:
    """Historical daily OHLCV provider using Yahoo Finance chart data.

    B3 tickers are translated to Yahoo's `.SA` convention. The provider supports
    both Yahoo `range` requests and explicit start/end dates, which is required
    for long backtests (15/20 years) plus indicator warm-up history.
    """
    source = "yahoo"

    def __init__(self, http=None):
        self.http = http or HttpClient()

    @staticmethod
    def symbol(ticker: str) -> str:
        t = ticker.upper().strip()
        if (
            "." in t or t.startswith("^") or "=" in t
            or t.endswith(("-USD", "-BRL", "-EUR", "-GBP", "-JPY"))
            or t.isalpha()
        ):
            return t
        return f"{t}.SA"

    def fetch(self, ticker: str, *, range_: str = "2y", interval: str = "1d",
              start: datetime | None = None, end: datetime | None = None) -> list[dict]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{self.symbol(ticker)}"
        params = {"interval": interval, "includeAdjustedClose": "true", "events": "div,splits"}
        if start is not None:
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end is None:
                end = datetime.now(timezone.utc)
            elif end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            params["period1"] = int(start.timestamp())
            # Yahoo period2 is effectively exclusive; one day extra protects the requested final bar.
            params["period2"] = int((end + timedelta(days=1)).timestamp())
        else:
            params["range"] = range_

        payload = self.http.get(url, params=params).json()
        result = ((payload.get("chart") or {}).get("result") or [])
        if not result:
            return []
        r = result[0]
        timestamps = r.get("timestamp") or []
        quote = (((r.get("indicators") or {}).get("quote") or [{}])[0])
        adj = (((r.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
        out = []
        for i, ts in enumerate(timestamps):
            def at(name):
                a = quote.get(name) or []
                return a[i] if i < len(a) else None
            out.append({
                "ticker": ticker.upper(), "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
                "open": at("open"), "high": at("high"), "low": at("low"), "close": at("close"),
                "volume": at("volume"), "adjusted_close": adj[i] if i < len(adj) else None,
                "source": self.source, "timeframe": "1D",
            })
        return out
