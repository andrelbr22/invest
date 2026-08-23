from __future__ import annotations

import unicodedata
from collections.abc import Iterable


BESST_LABELS = {
    "all": "Todos os setores BESST",
    "banks": "Bancos",
    "energy": "Energia",
    "insurance": "Seguridade",
    "sanitation": "Saneamento",
    "telecom": "Telecomunicações",
}

COMPANY_SIZE_LABELS = {
    "large": "Blue Chip / Large Cap",
    "mid": "Mid Cap",
    "small": "Small Cap",
}

COMPANY_SIZE_THRESHOLDS = {
    "large_min": 20_000_000_000.0,
    "mid_min": 2_000_000_000.0,
}


_BESST_KEYWORDS = {
    # More specific groups come first so that, for example, BB Seguridade is
    # classified as insurance instead of banking because of its name.
    "sanitation": (
        "saneamento", "agua e saneamento", "water util", "water supply",
        "sewerage", "servicos de agua",
    ),
    "insurance": (
        "seguridade", "seguradora", "seguradoras", "seguro", "seguros",
        "insurance", "reinsurance", "resseguro", "previdencia",
    ),
    "banks": (
        "banco", "bancos", "bank", "banks", "banking",
        "intermediacao financeira",
    ),
    "telecom": (
        "telecom", "telefonia", "telecomunicacoes", "telecommunications",
        "wireless", "servicos de comunicacao",
    ),
    "energy": (
        "energia", "energetic", "energy", "electric", "eletrica", "eletrico",
        "power generation", "power transmission", "power distribution",
        "petroleo", "oil", "gas", "utilities", "utilidade publica",
    ),
}


def normalize_text(value: object) -> str:
    """Normalize catalog text for stable comparisons across data providers."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).casefold().split())


def _asset_search_text(asset: dict) -> str:
    fields = (
        "ticker", "name", "sector", "industry", "segment", "classification",
        "market_cap_category",
    )
    return " | ".join(normalize_text(asset.get(field)) for field in fields)


def besst_category(asset: dict) -> str | None:
    """Return the BESST group inferred from the asset catalog metadata."""
    search_text = _asset_search_text(asset)
    for category in ("sanitation", "insurance", "banks", "telecom", "energy"):
        if any(keyword in search_text for keyword in _BESST_KEYWORDS[category]):
            return category
    return None


def company_size_from_market_cap(value: object) -> str | None:
    """Classify market value using explicit, stable BRL thresholds."""
    try:
        market_cap = float(value)
    except (TypeError, ValueError):
        return None
    if market_cap <= 0:
        return None
    if market_cap >= COMPANY_SIZE_THRESHOLDS["large_min"]:
        return "large"
    if market_cap >= COMPANY_SIZE_THRESHOLDS["mid_min"]:
        return "mid"
    return "small"


def company_size_category(asset: dict) -> str | None:
    """Resolve size from a saved category or the latest TradingView market cap."""
    explicit = normalize_text(asset.get("company_size") or asset.get("market_cap_category"))
    aliases = {
        "large": "large", "large cap": "large", "grande capitalizacao": "large",
        "blue chip": "large", "blue chip / large cap": "large",
        "mid": "mid", "mid cap": "mid", "middle cap": "mid", "media capitalizacao": "mid",
        "small": "small", "small cap": "small", "micro cap": "small",
        "pequena capitalizacao": "small", "microcapitalizacao": "small",
    }
    if explicit in aliases:
        return aliases[explicit]
    metadata = asset.get("metadata_json") if isinstance(asset.get("metadata_json"), dict) else {}
    return company_size_from_market_cap(asset.get("market_cap") or metadata.get("last_market_cap"))


def universe_tickers(
    catalog: Iterable[dict],
    mode: str,
    *,
    selected_tickers: Iterable[str] | None = None,
    besst_group: str = "all",
    classification: str | None = None,
    classification_field: str = "classification",
    company_size: str | None = None,
) -> list[str]:
    """Resolve a UI universe to catalog tickers while preserving catalog order."""
    assets = list(catalog or [])
    if mode == "all":
        return [str(asset.get("ticker") or "").upper() for asset in assets if asset.get("ticker")]

    if mode in {"portfolio", "specific", "index"}:
        selected = {str(ticker).strip().upper() for ticker in (selected_tickers or []) if str(ticker).strip()}
        return [str(asset["ticker"]).upper() for asset in assets if str(asset.get("ticker") or "").upper() in selected]

    if mode == "besst":
        if besst_group not in BESST_LABELS:
            raise ValueError("invalid_besst_group")
        return [
            str(asset["ticker"]).upper()
            for asset in assets
            if asset.get("ticker") and (besst_group == "all" and besst_category(asset) is not None
                                        or besst_category(asset) == besst_group)
        ]

    if mode == "company_size":
        if company_size not in COMPANY_SIZE_LABELS:
            raise ValueError("invalid_company_size")
        return [
            str(asset["ticker"]).upper()
            for asset in assets
            if asset.get("ticker") and company_size_category(asset) == company_size
        ]

    if mode == "classification":
        allowed_fields = {"classification", "sector_label", "segment_label", "market_cap_category_label"}
        if classification_field not in allowed_fields:
            raise ValueError("invalid_classification_field")
        requested = normalize_text(classification)
        return [
            str(asset["ticker"]).upper()
            for asset in assets
            if asset.get("ticker") and normalize_text(asset.get(classification_field)) == requested
        ]

    raise ValueError("invalid_universe_mode")


def filter_rows_by_tickers(rows: Iterable[dict], tickers: Iterable[str], *, limit: int | None = None) -> list[dict]:
    """Intersect screener rows with an already resolved asset universe."""
    allowed = {str(ticker).strip().upper() for ticker in tickers or [] if str(ticker).strip()}
    result = [row for row in (rows or []) if str(row.get("ticker") or "").upper() in allowed]
    return result if limit is None else result[: max(int(limit), 0)]


def apply_universe_subfilters(
    catalog: Iterable[dict],
    base_tickers: Iterable[str],
    *,
    company_sizes: Iterable[str] | None = None,
    ibov_members: Iterable[str] | None = None,
    ibov_inside: bool = True,
    classification_field: str | None = None,
    classification_values: Iterable[str] | None = None,
) -> list[str]:
    """Apply cumulative Porte/IBOV/classification constraints to a base universe."""
    base = {str(value).strip().upper() for value in (base_tickers or []) if str(value).strip()}
    sizes = None if company_sizes is None else {str(value) for value in company_sizes}
    members = None if ibov_members is None else {str(value).strip().upper() for value in ibov_members}
    classes = None if classification_values is None else {normalize_text(value) for value in classification_values}
    allowed_fields = {"classification", "sector_label", "segment_label", "market_cap_category_label"}
    if classification_field is not None and classification_field not in allowed_fields:
        raise ValueError("invalid_classification_field")

    result = []
    for asset in catalog or []:
        ticker = str(asset.get("ticker") or "").strip().upper()
        if not ticker or ticker not in base:
            continue
        if sizes is not None and company_size_category(asset) not in sizes:
            continue
        if members is not None and ((ticker in members) != bool(ibov_inside)):
            continue
        if classes is not None and normalize_text(asset.get(classification_field or "classification")) not in classes:
            continue
        result.append(ticker)
    return result
