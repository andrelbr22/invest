"""Rules for the investable B3 catalog exposed by the application.

Operational negotiation variants are useful to brokers, but they duplicate the
economic asset in an analysis database.  This module keeps one canonical code
per instrument and rejects temporary or special-book symbols before storage.
"""

from __future__ import annotations

import re


B3_CATALOG_TYPES = frozenset({"stock", "fii", "etf", "bdr", "future"})
ALERTABLE_B3_TYPES = frozenset({"stock", "fii", "etf", "bdr"})

_REGULAR_STOCK = re.compile(r"^[A-Z]{3,5}(?:[3-8]|11)$")
_FII_OR_ETF = re.compile(r"^[A-Z]{3,5}11$")
_BDR = re.compile(r"^[A-Z]{3,5}3[1-9]$")
_CONTINUOUS_FUTURE = re.compile(r"^[A-Z0-9]{2,12}1!$")
_SUBSCRIPTION_OR_RECEIPT = re.compile(r"^[A-Z]{3,5}(?:1|2|9|10)$")
_SPECIAL_BOOK = re.compile(r".*\d[MQR]$")
_ORGANIZED_OTC = re.compile(r".*\dB$")


def normalize_ticker(ticker: str | None) -> str:
    return str(ticker or "").strip().upper()


def ticker_exclusion_reason(ticker: str | None, asset_type: str | None) -> str | None:
    """Return a stable reason code when a ticker is outside the user catalog."""
    code = normalize_ticker(ticker)
    kind = str(asset_type or "").strip().lower()
    if not code:
        return "ticker_missing"
    if kind not in B3_CATALOG_TYPES:
        return None
    if code.endswith("F"):
        return "fractional_market_duplicate"
    if _SPECIAL_BOOK.fullmatch(code):
        return "special_large_lot_book"
    if _ORGANIZED_OTC.fullmatch(code):
        return "organized_otc_variant"
    if kind == "stock":
        if _SUBSCRIPTION_OR_RECEIPT.fullmatch(code):
            return "subscription_right_or_receipt"
        return None if _REGULAR_STOCK.fullmatch(code) else "unsupported_stock_code"
    if kind in {"fii", "etf"}:
        return None if _FII_OR_ETF.fullmatch(code) else f"unsupported_{kind}_code"
    if kind == "bdr":
        return None if _BDR.fullmatch(code) else "unsupported_bdr_code"
    if kind == "future":
        return None if _CONTINUOUS_FUTURE.fullmatch(code) else "duplicate_future_maturity"
    return None


def is_supported_ticker(ticker: str | None, asset_type: str | None) -> bool:
    return ticker_exclusion_reason(ticker, asset_type) is None


def is_alertable_b3_asset(ticker: str | None, asset_type: str | None) -> bool:
    """Accept canonical B3 instruments independently of the provider's exchange alias."""
    kind = str(asset_type or "").strip().lower()
    return kind in ALERTABLE_B3_TYPES and is_supported_ticker(ticker, kind)


def require_supported_ticker(ticker: str | None, asset_type: str | None) -> str:
    code = normalize_ticker(ticker)
    reason = ticker_exclusion_reason(code, asset_type)
    if reason is not None:
        raise ValueError(f"unsupported_b3_ticker:{code or 'EMPTY'}:{reason}")
    return code


def provider_catalog_type(provider_type: str, type_specs: list[str] | None = None) -> str | None:
    """Translate TradingView groups into the catalog rule that applies to them."""
    provider_type = str(provider_type or "").strip().lower()
    if provider_type == "stock":
        return "stock"
    if provider_type == "fund":
        return "etf" if "etf" in {str(item).lower() for item in (type_specs or [])} else "fii"
    if provider_type == "dr":
        return "bdr"
    if provider_type == "futures":
        return "future"
    return None
