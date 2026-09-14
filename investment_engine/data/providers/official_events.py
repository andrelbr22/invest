"""Official investor-event sources used by the asynchronous V1.23 jobs.

Only metadata and public links are persisted for CVM filings.  B3 cash-event
records are normalized without estimating missing dates or amounts.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from threading import Lock, local

from ...infrastructure.http import HttpClient
from .market_dashboard import (
    FEC_ELECTION_CALENDAR_URL,
    TSE_ELECTION_CALENDAR_URL,
    MarketDashboardService,
    b3_holidays,
    us_exchange_holidays,
)


B3_API_ROOT = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall"
B3_PUBLIC_ROOT = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesPage/main"
CVM_IPE_ROOT = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS"
CVM_IPE_DATASET = "https://dados.cvm.gov.br/dataset/cia_aberta-doc-ipe"
CVM_IPE_CKAN_API = "https://dados.cvm.gov.br/api/3/action/package_show?id=cia_aberta-doc-ipe"
ANBIMA_OAUTH_URL = "https://api.anbima.com.br/oauth/access-token"
ANBIMA_IMA_RESULTS_URL = "https://api.anbima.com.br/feed/precos-indices/v1/indices/resultados-ima"
ANBIMA_IMA_DOCUMENTATION_URL = (
    "https://developers.anbima.com.br/pt/documentacao/precos-indices/"
    "apis-de-indices/indices/"
)


def _plain(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char)).strip().lower()


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _plain(value)).strip("_")


def _first(mapping: dict, *keys: str):
    normalized = {_key(key): value for key, value in mapping.items()}
    for key in keys:
        value = normalized.get(_key(key))
        if value not in (None, ""):
            return value
    return None


def _parse_date(value: object) -> date | None:
    clean = str(value or "").strip()[:10]
    if not clean:
        return None
    for pattern in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(clean, pattern).date()
        except ValueError:
            continue
    return None


def _parse_datetime(value: object) -> datetime | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(clean, pattern)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_decimal(value: object) -> Decimal | None:
    clean = re.sub(r"[^0-9,.-]", "", str(value or "").strip())
    if not clean:
        return None
    if "," in clean and "." in clean:
        clean = clean.replace(".", "").replace(",", ".") if clean.rfind(",") > clean.rfind(".") else clean.replace(",", "")
    else:
        clean = clean.replace(",", ".")
    try:
        return Decimal(clean)
    except InvalidOperation:
        return None


def _token(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return base64.b64encode(raw).decode("ascii")


def _external_id(parts: list[object]) -> str:
    raw = "|".join(str(value or "").strip() for value in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _next_b3_business_day(value: date) -> date:
    """Return the next regular B3 session after an official data-com date.

    B3's ``lastDatePrior`` field explicitly means the last trading day with
    entitlement.  Only that field is eligible for this derivation; callers
    must leave ``ex_date`` empty when the source does not provide that
    semantic anchor.
    """
    current = value + timedelta(days=1)
    while True:
        holidays = {day for day, _label in b3_holidays(current.year)}
        if current.weekday() < 5 and current not in holidays:
            return current
        current += timedelta(days=1)


def _ticker_share_class(ticker: str) -> str | None:
    clean = re.sub(r"[^A-Z0-9]", "", str(ticker or "").upper())
    suffix = re.search(r"(\d{1,2})$", clean)
    if suffix is None:
        return None
    code = suffix.group(1)
    return {
        "3": "on", "4": "pn", "5": "pna", "6": "pnb",
        "7": "pnc", "8": "pnd", "11": "unit",
    }.get(code, "bdr" if code.startswith("3") and len(code) == 2 else None)


def _record_share_class(record: dict) -> str | None:
    value = _plain(_first(
        record, "typeStock", "stockType", "shareClass", "classAsset",
        "tipoAcao", "tipo_acao", "especie", "specification",
    ))
    compact = re.sub(r"[^a-z0-9]", "", value)
    if not compact:
        return None
    if "bdr" in compact or compact.startswith("dr"):
        return "bdr"
    if "unit" in compact or compact.startswith("unt") or compact in {"ci", "cota", "cotas"}:
        return "unit"
    for marker, normalized in (
        ("pnd", "pnd"), ("pnc", "pnc"), ("pnb", "pnb"),
        ("pna", "pna"), ("pn", "pn"), ("on", "on"),
    ):
        if re.search(rf"(?:^|[^a-z]){marker}(?:$|[^a-z])", value) or compact == marker:
            return normalized
    return None


def _issuer_name_key(value: object) -> str:
    """Create a conservative exact-match key for issuer legal names."""
    words = re.findall(r"[a-z0-9]+", _plain(value))
    removable = {
        "sa", "s", "a", "companhia", "cia", "aberta", "sociedade",
        "anonima", "ltda", "holding", "holdings",
    }
    meaningful = [word for word in words if word not in removable]
    return " ".join(meaningful)


class B3CorporateEventsProvider:
    """Read confirmed cash distributions from B3's listed-company service."""

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient(timeout=20, retries=3)

    def _request(self, method: str, payload: dict) -> tuple[dict, str]:
        url = f"{B3_API_ROOT}/{method}/{_token(payload)}"
        response = self.http.get(url, headers={"Accept": "application/json"})
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("b3_response_not_object")
        return data, url

    def trading_name(self, ticker: str) -> tuple[str, dict]:
        company = re.sub(r"[^A-Z0-9]", "", str(ticker).upper())[:4]
        data, _url = self._request("GetInitialCompanies", {
            "language": "pt-br", "pageNumber": 1, "pageSize": 20, "company": company,
        })
        rows = list(data.get("results") or [])
        exact = next((row for row in rows if str(row.get("issuingCompany") or "").upper() == company), None)
        row = exact or (rows[0] if rows else None)
        if not isinstance(row, dict):
            raise ValueError("b3_company_not_found")
        name = str(row.get("tradingName") or "").replace("/", "").replace(".", "").strip()
        if not name:
            raise ValueError("b3_trading_name_missing")
        return name, row

    @staticmethod
    def issuer_identity(company: dict) -> dict:
        """Normalize identifiers returned by B3 without persisting raw payloads."""
        cnpj = _digits(_first(
            company, "cnpj", "cnpjCompany", "cnpjCorporate", "companyCnpj",
        )) or None
        return {
            "issuer_cnpj": cnpj,
            "cvm_code": str(_first(company, "codeCVM", "cvmCode", "codigoCVM") or "").strip() or None,
            "issuing_company": str(_first(company, "issuingCompany", "issuerCode") or "").strip().upper() or None,
            "issuer_name": str(_first(
                company, "companyName", "corporateName", "tradingName",
            ) or "").strip() or None,
        }

    @staticmethod
    def record_matches_ticker(
        record: dict,
        *,
        ticker: str,
        expected_isin: str | None = None,
    ) -> bool:
        """Attribute an issuer event only when security identity is defensible.

        The B3 endpoint is issuer-scoped and can return ON, PN and units in the
        same response.  A requested ticker alone is therefore not evidence
        that every returned row belongs to that security.  Exact ISIN wins;
        otherwise the B3 share-class field must agree with the ticker suffix.
        Ambiguous rows are deliberately ignored instead of creating a false
        portfolio entitlement.
        """
        row_isin = str(_first(record, "isinCode", "isin", "codigo isin") or "").strip().upper()
        target_isin = str(expected_isin or "").strip().upper()
        if row_isin and target_isin:
            return row_isin == target_isin

        expected_class = _ticker_share_class(ticker)
        row_class = _record_share_class(record)
        if expected_class is None or row_class is None:
            return False
        if expected_class == row_class:
            return True
        # Some feeds identify class A/B/C/D simply as PN.  That label is too
        # broad to assign safely to a specific numbered preferred class.
        return expected_class in {"pna", "pnb", "pnc", "pnd"} and row_class == expected_class

    @staticmethod
    def normalize_record(
        record: dict,
        *,
        ticker: str,
        source_url: str,
        expected_isin: str | None = None,
    ) -> dict | None:
        if not B3CorporateEventsProvider.record_matches_ticker(
            record, ticker=ticker, expected_isin=expected_isin,
        ):
            return None
        label = str(_first(record, "corporateAction", "provento", "type", "eventType") or "").strip()
        event_map = {
            "dividendo": "dividend", "jrs cap proprio": "jcp", "juros sobre capital proprio": "jcp",
            "rendimento": "income", "restituicao de capital": "capital_return",
        }
        event_type = event_map.get(_plain(label), "cash_distribution")
        isin = str(_first(record, "isinCode", "isin", "codigo isin") or "").strip().upper() or None
        announced = _parse_date(_first(record, "dateApproval", "approvedOn", "deliberado em"))
        explicit_ex_date = _parse_date(_first(record, "exDate", "dateEx", "data ex", "data_ex"))
        official_cum_value = _first(record, "lastDatePrior", "lastDatePriorEx")
        cum_date = _parse_date(official_cum_value or _first(record, "negocios com ate"))
        payment = _parse_date(_first(record, "datePayment", "paymentDate", "inicio de pagamento"))
        amount = _parse_decimal(_first(record, "rate", "valueCash", "valor", "rateValue"))
        if not any((isin, announced, cum_date, payment, amount is not None)):
            return None
        # Derive only from B3's semantically explicit "last day prior to ex"
        # field, and use the B3 business calendar rather than calendar + 1.
        ex_date = explicit_ex_date or (
            _next_b3_business_day(cum_date)
            if cum_date is not None and official_cum_value not in (None, "")
            else None
        )
        external = _external_id([ticker, label, isin, announced, cum_date, payment, amount])
        return {
            "external_id": external, "ticker": ticker, "event_type": event_type,
            "isin": isin, "announced_on": announced, "last_cum_date": cum_date,
            "ex_date": ex_date, "payment_date": payment, "amount": amount,
            "currency": "BRL", "related_period": _first(record, "relatedTo", "relativo a"),
            "source": "B3", "source_url": source_url, "status": "confirmed",
            "metadata": {"original_label": label, "remarks": _first(record, "remarks", "observacoes")},
            "retrieved_at": datetime.now(timezone.utc),
        }

    def fetch_ticker(self, ticker: str, *, expected_isin: str | None = None) -> dict:
        clean = str(ticker or "").strip().upper()
        trading_name, company = self.trading_name(clean)
        data, api_url = self._request("GetListedCashDividends", {
            "language": "pt-br", "pageNumber": 1, "pageSize": 99999,
            "tradingName": trading_name,
        })
        public_url = f"{B3_PUBLIC_ROOT}/{company.get('codeCVM') or ''}/{company.get('issuingCompany') or clean[:4]}/corporate-actions?language=pt-BR"
        items = []
        ignored_records = 0
        for record in data.get("results") or []:
            if isinstance(record, dict):
                normalized = self.normalize_record(
                    record, ticker=clean, source_url=public_url,
                    expected_isin=expected_isin,
                )
                if normalized is not None:
                    items.append(normalized)
                else:
                    ignored_records += 1
        return {
            "ticker": clean, "items": items, "api_url": api_url,
            "source_url": public_url, "issuer": self.issuer_identity(company),
            "ignored_records": ignored_records,
        }

    def fetch(self, tickers: list[str | dict], *, max_assets: int = 500) -> dict:
        identities: dict[str, dict] = {}
        for value in tickers:
            if isinstance(value, dict):
                ticker = str(value.get("ticker") or "").strip().upper()
                identity = dict(value)
            else:
                ticker = str(value or "").strip().upper()
                identity = {"ticker": ticker}
            if ticker and ticker not in identities:
                identities[ticker] = identity
        unique = list(identities)
        safety_limit = max(1, min(2000, int(max_assets)))
        selected = unique[:safety_limit]
        items, errors, issuers = [], [], {}
        ignored_records = 0
        for ticker in selected:
            try:
                expected_isin = str(identities[ticker].get("isin") or "").strip().upper() or None
                result = (
                    self.fetch_ticker(ticker, expected_isin=expected_isin)
                    if expected_isin else self.fetch_ticker(ticker)
                )
                items.extend(result["items"])
                ignored_records += int(result.get("ignored_records") or 0)
                if result.get("issuer"):
                    issuers[ticker] = dict(result["issuer"])
            except Exception as exc:
                errors.append({"ticker": ticker, "error": type(exc).__name__})
        return {
            "items": items,
            "errors": errors,
            "issuers": issuers,
            "ignored_ambiguous_or_mismatched_records": ignored_records,
            "requested_total": len(unique),
            "requested": len(selected),
            "safety_limit": safety_limit,
            "truncated": len(selected) < len(unique),
            "not_processed": max(0, len(unique) - len(selected)),
            "source": "B3",
        }


class CvmRelevantFactsProvider:
    """Read Fato Relevante metadata from the official annual IPE archive."""

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient(timeout=45, retries=3)

    def resource_urls(self) -> dict[int, str]:
        """Discover the exact current CVM resources instead of guessing years."""
        payload = self.http.get(CVM_IPE_CKAN_API, timeout=20).json()
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise ValueError("cvm_ipe_catalog_invalid")
        result = payload.get("result")
        resources = result.get("resources") if isinstance(result, dict) else None
        if not isinstance(resources, list):
            raise ValueError("cvm_ipe_resources_missing")
        found: dict[int, str] = {}
        for resource in resources:
            if not isinstance(resource, dict) or str(resource.get("format") or "").upper() != "ZIP":
                continue
            url = str(resource.get("url") or "").strip()
            match = re.search(r"ipe_cia_aberta_(\d{4})\.zip(?:$|\?)", url, re.IGNORECASE)
            if match and url.startswith("https://dados.cvm.gov.br/"):
                found[int(match.group(1))] = url
        if not found:
            raise ValueError("cvm_ipe_zip_resources_missing")
        return found

    @staticmethod
    def _csv_rows(content: bytes) -> Iterator[dict]:
        """Yield the archive one row at a time so annual IPE files fit a micro VM."""
        if len(content) > 30 * 1024 * 1024:
            raise ValueError("cvm_ipe_archive_too_large")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not names:
                raise ValueError("cvm_ipe_csv_missing")
            member = archive.getinfo(names[0])
            if member.file_size > 250 * 1024 * 1024:
                raise ValueError("cvm_ipe_csv_too_large")
            with archive.open(member, "r") as raw:
                with io.TextIOWrapper(raw, encoding="latin-1", newline="") as text:
                    yield from csv.DictReader(text, delimiter=";")

    @staticmethod
    def normalize_record(
        record: dict,
        *,
        source_url: str,
        tickers_by_cnpj: dict[str, list[str]] | None = None,
        issuer_mapping: dict[str, dict[str, list[str]]] | None = None,
    ) -> dict | None:
        category = str(_first(record, "Categoria", "Categoria_Doc") or "")
        if _plain(category) != "fato relevante":
            return None
        cnpj = re.sub(r"\D", "", str(_first(record, "CNPJ_Companhia", "CNPJ") or "")) or None
        delivered = _parse_datetime(_first(record, "Data_Entrega", "Data_Recebimento", "Data_Hora_Entrega"))
        document_url = str(_first(record, "Link_Download", "URL_Documento", "Link") or "").strip()
        if delivered is None or not document_url.startswith("https://"):
            return None
        protocol = str(_first(record, "Protocolo_Entrega", "Protocolo") or "").strip() or None
        external = protocol or _external_id([
            cnpj, delivered.isoformat(), document_url,
            _first(record, "Versao", "Tipo_Apresentacao"),
        ])
        cvm_code = str(_first(record, "Codigo_CVM", "CD_CVM") or "").strip() or None
        cvm_mapping_key = (_digits(cvm_code).lstrip("0") or _digits(cvm_code)) if cvm_code else ""
        issuer_name = str(
            _first(record, "Nome_Companhia", "Denominacao_Social")
            or "Emissor não identificado"
        )
        mapping = issuer_mapping or {}
        by_cnpj = mapping.get("by_cnpj") or tickers_by_cnpj or {}
        by_cvm_code = mapping.get("by_cvm_code") or {}
        by_name = mapping.get("by_name") or {}
        tickers = list(by_cnpj.get(cnpj or "", []))
        mapping_method = "cnpj" if tickers else None
        if not tickers and cvm_mapping_key:
            tickers = list(by_cvm_code.get(cvm_mapping_key, []))
            mapping_method = "cvm_code" if tickers else None
        if not tickers:
            name_key = _issuer_name_key(issuer_name)
            tickers = list(by_name.get(name_key, [])) if name_key else []
            mapping_method = "issuer_name" if tickers else None
        return {
            "external_id": external, "issuer_cnpj": cnpj,
            "issuer_name": issuer_name,
            "cvm_code": cvm_code,
            "reference_date": _parse_date(_first(record, "Data_Referencia")),
            "delivered_at": delivered, "subject": _first(record, "Assunto", "Especie"),
            "document_url": document_url, "protocol": protocol,
            "version": _first(record, "Versao"), "tickers": sorted(set(tickers)),
            "source": "CVM IPE", "source_url": source_url,
            "metadata": {
                "category": category,
                "type": _first(record, "Tipo", "Tipo_Apresentacao"),
                "ticker_mapping_method": mapping_method,
            },
            "retrieved_at": datetime.now(timezone.utc),
        }

    def fetch(
        self,
        *,
        years: list[int] | None = None,
        tickers_by_cnpj: dict[str, list[str]] | None = None,
        issuer_mapping: dict[str, dict[str, list[str]]] | None = None,
    ) -> dict:
        current = datetime.now(timezone.utc).year
        requested_years = sorted(set(years or [current - 1, current]))
        mapping = tickers_by_cnpj or {}
        items, errors, warnings = [], [], []
        try:
            resources = self.resource_urls()
            discovered = True
        except Exception as exc:
            # The exact historical URL convention remains a safe fallback if
            # CKAN metadata itself is temporarily unavailable.
            resources = {
                year: f"{CVM_IPE_ROOT}/ipe_cia_aberta_{year}.zip"
                for year in requested_years
            }
            discovered = False
            warnings.append({"scope": "resource_catalog", "error": type(exc).__name__})
        for year in requested_years:
            url = resources.get(year)
            if not url:
                errors.append({"year": year, "error": "cvm_ipe_resource_not_published"})
                continue
            try:
                for record in self._csv_rows(self.http.get(url).content):
                    item = self.normalize_record(
                        record, source_url=url, tickers_by_cnpj=mapping,
                        issuer_mapping=issuer_mapping,
                    )
                    if item is not None:
                        items.append(item)
            except Exception as exc:
                errors.append({"year": year, "error": type(exc).__name__})
        if not items and errors:
            raise RuntimeError("cvm_ipe_all_archives_failed")
        return {
            "items": items, "errors": errors, "warnings": warnings,
            "years": requested_years, "source": "CVM IPE",
            "source_url": CVM_IPE_DATASET, "resource_catalog_discovered": discovered,
        }


class AnbimaImaHistoryProvider:
    """Authenticated official daily IMA-B and IRF-M index levels.

    The ANBIMA Feed uses OAuth2 client credentials.  Credentials remain only
    in request headers and are never included in returned diagnostics.
    """

    INDEX_CODES = {"ima_b": ("IMAB", "IMA-B"), "irf_m": ("IRFM", "IRF-M")}

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        http: HttpClient | None = None,
        now=None,
        range_workers: int = 4,
    ):
        self.client_id = str(client_id or "").strip()
        self.client_secret = str(client_secret or "").strip()
        self.http = http or HttpClient(timeout=35, retries=3)
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._access_token = ""
        self._token_expires_at: datetime | None = None
        self._token_lock = Lock()
        self._thread_local = local()
        self._range_workers = max(1, min(6, int(range_workers)))
        # Tests and specialized callers may inject a deterministic client.
        # Production range workers receive one Session each because
        # requests.Session must not be shared concurrently.
        self._http_factory = (
            (lambda: self.http)
            if http is not None
            else (lambda: HttpClient(timeout=35, retries=3))
        )

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _token(self) -> str:
        current = self.now()
        if self._access_token and self._token_expires_at and current < self._token_expires_at:
            return self._access_token
        with self._token_lock:
            current = self.now()
            if self._access_token and self._token_expires_at and current < self._token_expires_at:
                return self._access_token
            if not self.configured:
                raise RuntimeError("anbima_credentials_not_configured")
            basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
            response = self.http.post(
                ANBIMA_OAUTH_URL,
                headers={"Authorization": f"Basic {basic}", "Content-Type": "application/json"},
                json={"grant_type": "client_credentials"},
            )
            payload = response.json()
            token = str(payload.get("access_token") or "").strip() if isinstance(payload, dict) else ""
            if not token:
                raise RuntimeError("anbima_access_token_missing")
            try:
                expires_in = max(120, int(payload.get("expires_in") or 3600))
            except (TypeError, ValueError):
                expires_in = 3600
            self._access_token = token
            self._token_expires_at = current + timedelta(seconds=max(60, expires_in - 60))
            return token

    def _headers(self) -> dict[str, str]:
        return {"client_id": self.client_id, "access_token": self._token(), "Accept": "application/json"}

    @classmethod
    def _records(cls, value: object) -> Iterator[dict]:
        """Accept current and legacy ANBIMA envelope shapes without guessing values."""
        if isinstance(value, list):
            for item in value:
                yield from cls._records(item)
            return
        if not isinstance(value, dict):
            return
        if _first(value, "indice") is not None and _first(value, "data_referencia") is not None:
            yield value
            return
        for key in ("content", "data", "items", "results", "resultado"):
            nested = value.get(key)
            if nested is not None:
                yield from cls._records(nested)

    @staticmethod
    def normalize_record(record: dict) -> dict | None:
        identity = _key(_first(record, "indice"))
        selected = AnbimaImaHistoryProvider.INDEX_CODES.get(identity)
        reference_date = _parse_date(_first(record, "data_referencia"))
        level = _parse_decimal(_first(record, "numero_indice"))
        if selected is None or reference_date is None or level is None:
            return None
        code, name = selected
        metadata = {}
        for source, target in (
            ("variacao_diaria", "daily_return_pct"),
            ("variacao_mensal", "monthly_return_pct"),
            ("variacao_anual", "year_return_pct"),
            ("variacao_ult12m", "return_12m_pct"),
            ("variacao_ult24m", "return_24m_pct"),
            ("duration", "duration"),
            ("yield", "yield_pct"),
        ):
            parsed = _parse_decimal(_first(record, source))
            if parsed is not None:
                metadata[target] = float(parsed)
        checksum = hashlib.sha256(
            json.dumps(record, ensure_ascii=True, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return {
            "code": code,
            "name": name,
            "observed_at": datetime.combine(reference_date, time.min, tzinfo=timezone.utc),
            "reference_period": reference_date.isoformat(),
            "value": level,
            "source_payload_hash": checksum,
            "metadata": metadata,
        }

    def _fetch_date_with_http(self, http, reference_date: date | None, headers: dict[str, str]) -> dict:
        params = {"data": reference_date.isoformat()} if reference_date is not None else None
        response = http.get(ANBIMA_IMA_RESULTS_URL, headers=headers, params=params)
        payload = response.json()
        unique: dict[tuple[str, datetime], dict] = {}
        for record in self._records(payload):
            normalized = self.normalize_record(record)
            if normalized is not None:
                unique[(normalized["code"], normalized["observed_at"])] = normalized
        return {
            "items": list(unique.values()),
            "requested_date": reference_date.isoformat() if reference_date else None,
            "source": "ANBIMA Feed • Índices",
            "source_url": ANBIMA_IMA_DOCUMENTATION_URL,
        }

    def fetch_date(self, reference_date: date | None = None) -> dict:
        return self._fetch_date_with_http(self.http, reference_date, self._headers())

    def _range_http(self):
        client = getattr(self._thread_local, "http", None)
        if client is None:
            client = self._http_factory()
            self._thread_local.http = client
        return client

    @staticmethod
    def _is_expected_trading_day(value: date) -> bool:
        return value.weekday() < 5 and value not in {
            holiday for holiday, _label in b3_holidays(value.year)
        }

    def fetch_range(self, start: date, end: date, *, max_calendar_days: int = 31) -> dict:
        if end < start:
            return {"items": [], "errors": [], "start": start.isoformat(), "end": end.isoformat()}
        safety_limit = max(1, min(120, int(max_calendar_days)))
        bounded_end = min(end, start + timedelta(days=safety_limit - 1))
        trading_days = []
        current = start
        while current <= bounded_end:
            if self._is_expected_trading_day(current):
                trading_days.append(current)
            current += timedelta(days=1)

        items: list[dict] = []
        errors: list[dict] = []
        results: dict[date, dict] = {}
        failures: dict[date, Exception] = {}
        if trading_days:
            # Authenticate once. Four bounded workers make the decades-long
            # backfill practical while avoiding a burst large enough to abuse
            # the official service. Each production worker owns its Session.
            headers = self._headers()

            def fetch_one(day: date) -> dict:
                return self._fetch_date_with_http(self._range_http(), day, headers)

            with ThreadPoolExecutor(max_workers=min(self._range_workers, len(trading_days))) as executor:
                pending = {executor.submit(fetch_one, day): day for day in trading_days}
                for future in as_completed(pending):
                    day = pending[future]
                    try:
                        results[day] = future.result()
                    except Exception as exc:
                        failures[day] = exc

        for day in trading_days:
            failure = failures.get(day)
            if failure is not None:
                status = getattr(getattr(failure, "response", None), "status_code", None)
                if status in {401, 403}:
                    raise RuntimeError("anbima_authentication_or_plan_denied") from failure
                errors.append({
                    "date": day.isoformat(), "error": type(failure).__name__,
                    "http_status": status,
                })
                continue
            day_items = list((results.get(day) or {}).get("items") or [])
            received_codes = {str(item.get("code") or "") for item in day_items}
            missing_codes = sorted({"IMAB", "IRFM"} - received_codes)
            if missing_codes:
                errors.append({
                    "date": day.isoformat(),
                    "error": "anbima_expected_indices_missing",
                    "missing_codes": missing_codes,
                })
                continue
            items.extend(day_items)

        failed_dates = sorted(
            datetime.strptime(item["date"], "%Y-%m-%d").date()
            for item in errors if item.get("date")
        )
        next_date = failed_dates[0] if failed_dates else bounded_end + timedelta(days=1)
        complete_through = next_date - timedelta(days=1)
        unique = {(item["code"], item["observed_at"]): item for item in items}
        return {
            "items": list(unique.values()), "errors": errors,
            "start": start.isoformat(), "end": bounded_end.isoformat(),
            "attempted_through": bounded_end.isoformat(),
            "complete_through": complete_through.isoformat(),
            "next_date": next_date.isoformat(),
            "attempted_trading_days": len(trading_days),
            "successful_trading_days": len(trading_days) - len(failed_dates),
            "truncated": bounded_end < end, "source": "ANBIMA Feed • Índices",
            "source_url": ANBIMA_IMA_DOCUMENTATION_URL,
        }


def _first_weekday_of_month(year: int, month: int, weekday: int) -> date:
    current = date(year, month, 1)
    return current + timedelta(days=(weekday - current.weekday()) % 7)


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    current = next_month - timedelta(days=1)
    return current - timedelta(days=(current.weekday() - weekday) % 7)


class OfficialCalendarProvider:
    """Renew official agendas annually, keeping rule-derived dates explicit."""

    def __init__(self, market_service: MarketDashboardService | None = None):
        self.market_service = market_service or MarketDashboardService()

    @staticmethod
    def _elections(year: int) -> list[dict]:
        events = []
        if year % 2 == 0:
            first_round = _first_weekday_of_month(year, 10, 6)
            second_round = _last_weekday_of_month(year, 10, 6)
            events.extend([
                {
                    "category": "Eleições", "title": "Eleições brasileiras • 1º turno",
                    "event_date": first_round, "region": "Brasil", "source": "Tribunal Superior Eleitoral",
                    "source_url": TSE_ELECTION_CALENDAR_URL, "official": True,
                    "metadata": {"generation": "constitutional_calendar_rule"},
                },
                {
                    "category": "Eleições", "title": "Eleições brasileiras • eventual 2º turno",
                    "event_date": second_round, "region": "Brasil", "source": "Tribunal Superior Eleitoral",
                    "source_url": TSE_ELECTION_CALENDAR_URL, "official": True,
                    "metadata": {"generation": "constitutional_calendar_rule", "conditional": True},
                },
            ])
            first_monday = _first_weekday_of_month(year, 11, 0)
            us_day = first_monday + timedelta(days=1)
            title = "Eleições presidenciais e federais dos EUA" if year % 4 == 0 else "Eleições federais de meio de mandato dos EUA"
            events.append({
                "category": "Eleições", "title": title, "event_date": us_day,
                "region": "Estados Unidos", "source": "Federal Election Commission",
                "source_url": FEC_ELECTION_CALENDAR_URL, "official": True,
                "metadata": {"generation": "federal_election_date_rule"},
            })
        return events

    def fetch(self, *, start_year: int | None = None, years: int = 3) -> dict:
        initial = start_year or datetime.now(timezone.utc).year
        items: list[dict] = []
        errors: list[dict] = []
        try:
            for item in self.market_service.calendar():
                # Elections and exchange holidays are generated for every year
                # below.  Import only the source-specific monetary/labour
                # calendars here so that the same event is not stored twice
                # under slightly different titles.
                if item.get("category") not in {
                    "Decisão do Copom", "Decisão do Fed", "Super Quarta",
                    "CPI dos EUA", "Payroll dos EUA",
                }:
                    continue
                event_date = _parse_date(item.get("date"))
                if event_date and initial <= event_date.year < initial + years:
                    items.append({
                        **item, "event_date": event_date, "title": item.get("event"),
                        "source_url": item.get("url"), "official": bool(item.get("url")),
                        "metadata": {
                            "observation": item.get("observation"),
                            "fallback": bool(item.get("fallback")),
                            "generation": "official_source_adapter",
                        },
                    })
        except Exception as exc:
            errors.append({"scope": "live_market_calendar", "error": type(exc).__name__})
        for year in range(initial, initial + max(1, min(6, int(years)))):
            items.extend(self._elections(year))
            for day, name in b3_holidays(year):
                items.append({
                    "category": "Feriado B3", "title": name, "event_date": day,
                    "region": "Brasil", "source": "B3",
                    "source_url": "https://www.b3.com.br/pt_br/noticias/calendario-de-negociacao-da-b3.htm",
                    "official": True, "metadata": {"generation": "exchange_calendar_rule"},
                })
            for day, name in us_exchange_holidays(year):
                items.append({
                    "category": "Feriado EUA", "title": name, "event_date": day,
                    "region": "Estados Unidos", "source": "NYSE",
                    "source_url": "https://www.nyse.com/trade/hours-calendars",
                    "official": True, "metadata": {"generation": "exchange_calendar_rule"},
                })
        unique: dict[tuple, dict] = {}
        for item in items:
            key = (item.get("source"), item.get("event_date"), item.get("category"), item.get("title"))
            item["external_id"] = _external_id(list(key))
            unique[key] = item
        return {
            "items": sorted(unique.values(), key=lambda item: (item["event_date"], item["category"])),
            "errors": errors, "start_year": initial, "end_year": initial + years - 1,
        }
