from __future__ import annotations
import re
from datetime import date, datetime
from ...infrastructure.http import HttpClient
from ...core.valuation.technical import tradingview_signal
from ...core.instruments import is_supported_ticker, provider_catalog_type

# Keep fields named and map by key instead of positional indexes. This makes
# the adapter much less fragile when new descriptive fields are added.
TV_COLUMNS = [
    "name", "description", "exchange", "sector", "industry", "type", "typespecs", "currency",
    "Recommend.All", "market_cap_basic", "Value.Traded",
    "SMA20", "SMA50", "SMA200", "SMA20|1W", "SMA50|1W", "SMA20|1M", "SMA50|1M",
    "high", "low", "close", "RSI", "BB.lower", "BB.upper",
    "nav_discount_premium", "expense_ratio", "fundamental_currency_code",
    "price_book_fq", "book_value_per_share_fq", "dividends_yield_current",
    "root", "expiration", "open_interest", "minmov", "pricescale",
]


class TradingViewScannerProvider:
    URL = "https://scanner.tradingview.com/brazil/scan"
    FUTURES_URL = "https://scanner.tradingview.com/futures/scan"

    def __init__(self, http: HttpClient | None = None, *, today=None):
        self.http = http or HttpClient()
        self.today = today or date.today

    def _scan(self, url: str, filters: list[dict], *, limit: int = 5000) -> list[dict]:
        payload = {
            "filter": filters,
            "options": {"lang": "pt"},
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": TV_COLUMNS,
            "range": [0, max(1, int(limit))],
        }
        data = self.http.post(url, json=payload).json()
        rows = []
        for item in data.get("data", []):
            values = item.get("d")
            if not isinstance(values, list) or len(values) < len(TV_COLUMNS):
                continue
            rows.append(dict(zip(TV_COLUMNS, values)))
        return rows

    @staticmethod
    def _expiration(value) -> date | None:
        clean = str(value or "").strip()
        if clean.endswith(".0"):
            clean = clean[:-2]
        try:
            return datetime.strptime(clean, "%Y%m%d").date()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _underlying_ticker(description: str | None) -> str | None:
        match = re.search(r"\b([A-Z]{3,5}(?:[3-8]|11))\s+(?:STOCK\s+)?FUTURES?\b", str(description or "").upper())
        ticker = match.group(1) if match else None
        return ticker if ticker and is_supported_ticker(ticker, "stock") else None

    def _front_contracts(self) -> dict[str, dict]:
        rows = self._scan(
            self.FUTURES_URL,
            [{"left": "exchange", "operation": "equal", "right": "BMFBOVESPA"}],
        )
        today = self.today()
        selected: dict[str, tuple[date, dict]] = {}
        for row in rows:
            name = str(row.get("name") or "").split(":")[-1].upper()
            root = str(row.get("root") or "").strip().upper()
            expiration = self._expiration(row.get("expiration"))
            if not root or name.endswith("1!") or expiration is None or expiration < today:
                continue
            previous = selected.get(root)
            if previous is None or expiration < previous[0]:
                selected[root] = (expiration, row)
        return {
            root: {
                "front_contract": str(row.get("name") or "").split(":")[-1].upper(),
                "front_contract_price": row.get("close"),
                "expiration_date": expiration.isoformat(),
                "days_to_expiry": (expiration - today).days,
                "front_open_interest": row.get("open_interest"),
            }
            for root, (expiration, row) in selected.items()
        }

    def fetch(self, asset_type: str = "stock", *, type_specs: list[str] | None = None) -> list[dict]:
        is_future = str(asset_type).strip().lower() == "futures"
        if is_future:
            filters = [
                {"left": "exchange", "operation": "equal", "right": "BMFBOVESPA"},
                {"left": "typespecs", "operation": "has", "right": ["continuous"]},
            ]
            rows = self._scan(self.FUTURES_URL, filters)
            try:
                front_contracts = self._front_contracts()
            except Exception:
                # A temporary failure in the maturity request must not erase
                # the canonical continuous-contract catalog.
                front_contracts = {}
        else:
            filters = [{"left": "type", "operation": "equal", "right": asset_type}]
            if type_specs:
                filters.append({"left": "typespecs", "operation": "has", "right": list(type_specs)})
            rows = self._scan(self.URL, filters)
            front_contracts = {}
        result = []
        catalog_type = provider_catalog_type(asset_type, type_specs)
        for row in rows:
            raw_name = row.get("name")
            if not raw_name:
                continue
            ticker = str(raw_name).split(":")[-1].upper()
            if catalog_type is not None and not is_supported_ticker(ticker, catalog_type):
                continue
            score = row.get("Recommend.All")
            root = str(row.get("root") or "").strip().upper() or None
            description = row.get("description") or None
            result.append({
                "ticker": ticker,
                "name": description,
                "exchange": row.get("exchange") or None,
                "sector": row.get("sector") or None,
                "industry": row.get("industry") or None,
                "instrument_type": row.get("type") or asset_type,
                "type_specs": row.get("typespecs") if isinstance(row.get("typespecs"), list) else [],
                "currency": row.get("currency") or "BRL",
                "score_tv": score,
                "signal_tv": tradingview_signal(score).value,
                "market_cap": row.get("market_cap_basic"),
                "daily_liquidity": row.get("Value.Traded"),
                "sma20": row.get("SMA20"), "sma50": row.get("SMA50"), "sma200": row.get("SMA200"),
                "sma20_1w": row.get("SMA20|1W"), "sma50_1w": row.get("SMA50|1W"),
                "sma20_1m": row.get("SMA20|1M"), "sma50_1m": row.get("SMA50|1M"),
                "high": row.get("high"), "low": row.get("low"), "close": row.get("close"),
                "rsi14": row.get("RSI"), "bb_lower": row.get("BB.lower"), "bb_upper": row.get("BB.upper"),
                "nav_discount_premium_pct": row.get("nav_discount_premium"),
                "expense_ratio_pct": row.get("expense_ratio"),
                "fundamental_currency_code": row.get("fundamental_currency_code") or None,
                "price_book_fq": row.get("price_book_fq"),
                "book_value_per_share": row.get("book_value_per_share_fq"),
                "dividend_yield_current_pct": row.get("dividends_yield_current"),
                "root_symbol": root,
                "open_interest": row.get("open_interest"),
                "min_tick": row.get("minmov"),
                "price_scale": row.get("pricescale"),
                "underlying_ticker": self._underlying_ticker(description) if is_future else None,
                "valuation_source": "TradingView scanner",
                **front_contracts.get(root or "", {}),
            })
        return result
