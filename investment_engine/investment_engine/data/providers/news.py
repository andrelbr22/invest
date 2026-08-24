from __future__ import annotations

import math
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests


GDELT_DOC_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
IMPORTANT_TERMS = (
    "resultado", "lucro", "prejuízo", "prejuizo", "dividendo", "jcp", "guidance",
    "aquisição", "aquisicao", "fusão", "fusao", "venda de ativos", "investimento",
    "rebaixamento", "elevação", "elevacao", "upgrade", "downgrade", "preço-alvo",
    "preco-alvo", "recomendação", "recomendacao", "fraude", "processo", "cade",
    "earnings", "merger", "acquisition", "price target", "buy rating", "sell rating",
)
AUTHORITY_DOMAINS = (
    "reuters.com", "bloomberg.com", "valor.globo.com", "infomoney.com.br",
    "moneytimes.com.br", "investnews.com.br", "exame.com", "neofeed.com.br",
    "braziljournal.com", "estadao.com.br", "folha.uol.com.br", "cnnbrasil.com.br",
)
BANK_GROUPS = {
    "brazil": {
        "label": "Bancos brasileiros",
        "institutions": {
            "Itaú BBA": ("itaú bba", "itau bba"),
            "BTG Pactual": ("btg pactual",),
            "Bradesco BBI": ("bradesco bbi",),
            "Santander Brasil": ("santander brasil", "santander"),
            "Banco do Brasil": ("banco do brasil", "bb investimentos"),
        },
        "terms": (
            "ações recomendadas", "acoes recomendadas", "carteira recomendada",
            "recomendação de ações", "recomendacao de acoes", "preço-alvo", "preco-alvo",
        ),
    },
    "global": {
        "label": "Bancos mundiais",
        "institutions": {
            "JPMorgan": ("jpmorgan", "jp morgan"),
            "Goldman Sachs": ("goldman sachs",),
            "Morgan Stanley": ("morgan stanley",),
            "UBS": ("ubs",),
            "Bank of America": ("bank of america", "bofa"),
            "Citi": ("citigroup", "citi"),
        },
        "terms": ("stock picks", "top stocks", "buy rating", "price target", "upgrade", "downgrade"),
    },
}


def _plain(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _safe_url(value: str | None) -> str | None:
    url = str(value or "").strip()
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _seen_at(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class MarketNewsService:
    """Small, keyless news adapter backed by GDELT DOC 2.0.

    Only metadata and links are displayed. Article text remains with the original
    publisher. Responses are cached to protect the upstream service and keep the
    Streamlit page responsive.
    """

    def __init__(self, *, http_get=None, cache_ttl_seconds: int = 30 * 60):
        self.http_get = http_get or requests.get
        self.cache_ttl_seconds = max(60, int(cache_ttl_seconds))
        self._cache: dict[tuple, tuple[float, list[dict]]] = {}
        self._lock = threading.RLock()

    def _query(self, query: str, *, max_records: int = 50, timespan: str = "3months") -> list[dict]:
        key = (query, max_records, timespan)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[0] < self.cache_ttl_seconds:
                return [dict(item) for item in cached[1]]
        response = self.http_get(
            GDELT_DOC_ENDPOINT,
            params={
                "query": query,
                "mode": "artlist",
                "maxrecords": max(10, min(250, int(max_records))),
                "format": "json",
                "sort": "datedesc",
                "timespan": timespan,
            },
            headers={"User-Agent": "FormacaoDoInvestidor/1.11 (+market-news-links)"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        normalized = []
        for article in payload.get("articles") or []:
            url = _safe_url(article.get("url"))
            title = str(article.get("title") or "").strip()
            if not url or not title:
                continue
            normalized.append({
                "title": title,
                "url": url,
                "source": str(article.get("domain") or urlparse(url).netloc).removeprefix("www."),
                "published_at": _seen_at(article.get("seendate")),
                "language": article.get("language"),
                "source_country": article.get("sourcecountry"),
                "image_url": _safe_url(article.get("socialimage")),
            })
        with self._lock:
            self._cache[key] = (now, normalized)
        return [dict(item) for item in normalized]

    @staticmethod
    def _importance(article: dict, *, ticker: str, company_name: str | None) -> float:
        title = _plain(article.get("title"))
        score = 0.0
        if _plain(ticker) in title:
            score += 24.0
        meaningful_name = " ".join(_plain(company_name).split()[:3])
        if len(meaningful_name) >= 4 and meaningful_name in title:
            score += 18.0
        score += min(28.0, sum(7.0 for term in IMPORTANT_TERMS if _plain(term) in title))
        domain = _plain(article.get("source"))
        if any(source in domain for source in AUTHORITY_DOMAINS):
            score += 12.0
        published_at = article.get("published_at")
        if isinstance(published_at, datetime):
            age_days = max(0.0, (datetime.now(timezone.utc) - published_at).total_seconds() / 86400.0)
            score += 30.0 * math.exp(-age_days / 21.0)
        return round(score, 2)

    @staticmethod
    def _deduplicate(items: list[dict]) -> list[dict]:
        unique = []
        seen = set()
        for item in items:
            key = re.sub(r"\W+", "", _plain(item.get("title")))[:160]
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    def asset_news(self, ticker: str, company_name: str | None = None, *, limit: int = 3) -> dict:
        clean_ticker = str(ticker or "").strip().upper()
        phrases = [f'"{clean_ticker}"']
        clean_name = " ".join(str(company_name or "").replace('"', "").split())
        if len(clean_name) >= 4:
            phrases.append(f'"{clean_name}"')
        query = "(" + " OR ".join(phrases) + ")"
        try:
            articles = self._query(query, max_records=75, timespan="3months")
            warning = None
        except Exception as exc:
            articles = []
            warning = f"news_provider_unavailable: {type(exc).__name__}"
        for article in articles:
            article["importance_score"] = self._importance(
                article, ticker=clean_ticker, company_name=clean_name,
            )
            article["ticker"] = clean_ticker
        articles = self._deduplicate(articles)
        articles.sort(key=lambda item: (
            item.get("importance_score", 0),
            item.get("published_at") or datetime.min.replace(tzinfo=timezone.utc),
        ), reverse=True)
        return {
            "ticker": clean_ticker,
            "company_name": company_name,
            "items": articles[: max(1, min(10, int(limit)))],
            "warning": warning,
            "provider": "GDELT DOC 2.0",
            "generated_at": datetime.now(timezone.utc),
        }

    def portfolio_news(self, assets: list[dict], *, limit_per_asset: int = 3) -> dict:
        clean_assets = []
        seen = set()
        for item in assets or []:
            ticker = str(item.get("ticker") or "").strip().upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            clean_assets.append({"ticker": ticker, "name": item.get("name")})
        if not clean_assets:
            return {"assets": [], "generated_at": datetime.now(timezone.utc), "provider": "GDELT DOC 2.0"}

        with ThreadPoolExecutor(max_workers=min(6, len(clean_assets))) as executor:
            futures = [
                executor.submit(self.asset_news, item["ticker"], item.get("name"), limit=limit_per_asset)
                for item in clean_assets
            ]
            results = [future.result() for future in futures]
        return {
            "assets": results,
            "asset_count": len(results),
            "generated_at": datetime.now(timezone.utc),
            "provider": "GDELT DOC 2.0",
        }

    @staticmethod
    def _institution(title: str, institutions: dict[str, tuple[str, ...]]) -> str | None:
        normalized = _plain(title)
        for institution, aliases in institutions.items():
            if any(_plain(alias) in normalized for alias in aliases):
                return institution
        return None

    @staticmethod
    def _mentioned_tickers(title: str, asset_names: dict[str, str] | None) -> list[str]:
        normalized = _plain(title)
        found = set(re.findall(r"\b[A-Z]{4}\d{1,2}\b", str(title or "").upper()))
        for ticker, name in (asset_names or {}).items():
            clean_name = " ".join(_plain(name).split()[:3])
            if len(clean_name) >= 5 and clean_name in normalized:
                found.add(str(ticker).upper())
        return sorted(found)[:8]

    def recommendations(self, *, category: str = "all", limit: int = 20, asset_names=None) -> dict:
        categories = [category] if category in BANK_GROUPS else list(BANK_GROUPS)
        collected = []
        warnings = []
        for group_key in categories:
            group = BANK_GROUPS[group_key]
            institutions = [f'"{name}"' for name in group["institutions"]]
            terms = [f'"{term}"' for term in group["terms"]]
            query = f"({' OR '.join(institutions)}) ({' OR '.join(terms)})"
            try:
                rows = self._query(query, max_records=80, timespan="3months")
            except Exception as exc:
                warnings.append(f"{group_key}: {type(exc).__name__}")
                continue
            for article in rows:
                article["bank_group"] = group_key
                article["bank_group_label"] = group["label"]
                article["institution"] = self._institution(article["title"], group["institutions"]) or group["label"]
                article["mentioned_tickers"] = self._mentioned_tickers(article["title"], asset_names)
                collected.append(article)
        collected = self._deduplicate(collected)
        collected.sort(
            key=lambda item: item.get("published_at") or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return {
            "category": category,
            "items": collected[: max(1, min(50, int(limit)))],
            "warnings": warnings,
            "provider": "GDELT DOC 2.0",
            "generated_at": datetime.now(timezone.utc),
        }
