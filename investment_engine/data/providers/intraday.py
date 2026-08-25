from __future__ import annotations

from datetime import datetime, timezone

from ...infrastructure.http import HttpClient


class IntradayQuoteProvider:
    """Small Yahoo chart adapter used only for alert observations.

    The latest one-minute B3 candle provides the high/low crossing evidence.
    Market-dashboard instruments use a thirty-minute candle. Yahoo quotations
    may be delayed and are therefore identified as indicative in every alert.
    """

    source = "Yahoo Finance (cotação indicativa, possivelmente atrasada)"

    def __init__(self, http=None):
        self.http = http or HttpClient(timeout=12)

    @staticmethod
    def _provider_symbol(symbol: str, market_scope: str) -> str:
        clean = str(symbol or "").strip().upper()
        if market_scope == "b3" and not clean.endswith(".SA"):
            return f"{clean}.SA"
        return clean

    def snapshot(self, symbols: list[str], *, market_scope: str) -> dict:
        last_error = "cotacao_intradiaria_indisponivel"
        for candidate in symbols:
            provider_symbol = self._provider_symbol(candidate, market_scope)
            interval = "1m" if market_scope == "b3" else "30m"
            range_ = "1d" if market_scope == "b3" else "5d"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{provider_symbol}"
            try:
                payload = self.http.get(url, params={
                    "interval": interval,
                    "range": range_,
                    "includeAdjustedClose": "true",
                    "events": "div,splits",
                }).json()
                result = ((payload.get("chart") or {}).get("result") or [])
                if not result:
                    continue
                chart = result[0]
                meta = chart.get("meta") or {}
                timestamps = chart.get("timestamp") or []
                quote = (((chart.get("indicators") or {}).get("quote") or [{}])[0])
                closes = quote.get("close") or []
                valid = [index for index, value in enumerate(closes) if value is not None and index < len(timestamps)]
                if not valid:
                    continue
                index = valid[-1]

                def value(name: str):
                    values = quote.get(name) or []
                    return values[index] if index < len(values) else None

                close = float(closes[index])
                high = float(value("high") if value("high") is not None else close)
                low = float(value("low") if value("low") is not None else close)
                previous = meta.get("chartPreviousClose") or meta.get("previousClose")
                previous = float(previous) if previous not in (None, 0) else None
                change_pct = ((close / previous) - 1.0) * 100.0 if previous else None
                return {
                    "provider_symbol": provider_symbol,
                    "price": close,
                    "high": high,
                    "low": low,
                    "previous_close": previous,
                    "change_pct": change_pct,
                    "quote_at": datetime.fromtimestamp(int(timestamps[index]), tz=timezone.utc),
                    "currency": meta.get("currency"),
                    "exchange_timezone": meta.get("exchangeTimezoneName"),
                    "interval": interval,
                    "source": self.source,
                }
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {str(exc)[:180]}"
        raise RuntimeError(last_error)
