"""Aggregated economic and market dashboard data.

The service deliberately separates official economic sources from quoted market
data.  Every returned item carries its source and whether it is a transparent
proxy, so the UI never presents an ETF as though it were the underlying index.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from email.utils import parsedate_to_datetime
import math
import re
from threading import Lock
from time import sleep
import unicodedata
from xml.etree import ElementTree

import pandas as pd
from bs4 import BeautifulSoup

from ...infrastructure.http import HttpClient
from .prices import YahooPriceProvider


BCB_SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados"
BCB_FOCUS_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
    "ExpectativasMercadoAnuais"
)
ANBIMA_CURVE_URL = "https://www.anbima.com.br/informacoes/est-termo/CZ.asp"
ANBIMA_IMA_URL = "https://www.anbima.com.br/informacoes/ima/ima.asp"
ANBIMA_IMA_COMPLETE_URL = "https://www.anbima.com.br/informacoes/ima/arqs/ima_completo.xml"
BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0"
BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
BLS_CPI_SCHEDULE_URL = "https://www.bls.gov/schedule/news_release/cpi.htm"
BLS_PAYROLL_SCHEDULE_URL = "https://www.bls.gov/schedule/news_release/empsit.htm"
FRED_RATES_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2,DGS5,DGS10,DGS30"
TREASURY_RATES_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
AGENCIA_BRASIL_ECONOMY_RSS = "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml"
ADVFN_MARKET_NEWS_URL = "https://br.advfn.com/noticias/empresas"
B3_BDI_WORKDAY_URL = "https://arquivos.b3.com.br/bdi/table/workday"
B3_BDI_TABLE_URL = "https://arquivos.b3.com.br/bdi/table/ConsolidatedTradesDerivatives"
TSE_ELECTION_CALENDAR_URL = (
    "https://www.tse.jus.br/comunicacao/noticias/2026/Marco/"
    "eleicoes-2026-confira-as-principais-datas-do-calendario-eleitoral"
)
FEC_ELECTION_CALENDAR_URL = (
    "https://www.fec.gov/introduction-campaign-finance/"
    "election-results-and-voting-information/"
)

# Keep this order in one authoritative place. The web interface renders the
# series exactly as supplied by the service, so new indicators cannot silently
# reorder the investor's comparison panel.
HISTORICAL_COMPARISON_ORDER = [
    "CDI", "IBOV", "IFIX", "SP500", "NYSE", "NASDAQ", "DOW_JONES",
    "NIKKEI225", "SHANGHAI_SSE", "EURO_STOXX50", "STOXX_EUROPE600",
    "MSCI_EUROPE", "USD_BRL", "BTC", "ETH", "IMAB", "IRFM", "POUPANCA", "OURO",
    "PRATA", "IPCA", "INPC", "IGPM", "IGPDI", "INCC", "IPCFIPE",
    "VIX", "DXY",
]

HISTORICAL_PRICE_SPECS = [
    ("IBOV", "Ibovespa", ["^BVSP"], False, None),
    ("IFIX", "IFIX", ["^IFIX", "XFIX11"], False, None),
    ("SP500", "S&P 500", ["^GSPC"], False, None),
    ("NYSE", "NYSE", ["^NYA"], False, None),
    ("NASDAQ", "NASDAQ", ["^IXIC"], False, None),
    ("DOW_JONES", "Dow Jones", ["^DJI"], False, None),
    ("NIKKEI225", "Nikkei 225", ["^N225"], False, None),
    ("SHANGHAI_SSE", "Shanghai SSE", ["000001.SS"], False, None),
    ("EURO_STOXX50", "Euro Stoxx 50", ["^STOXX50E"], False, None),
    (
        "STOXX_EUROPE600", "STOXX Europe 600", ["^STOXX", "EXSA.DE"],
        False, "O ETF EXSA é usado somente quando o índice não responde.",
    ),
    (
        "MSCI_EUROPE", "MSCI Europe", ["IEUR"], True,
        "ETF IEUR usado como proxy transparente do MSCI Europe.",
    ),
    ("USD_BRL", "Dólar", ["BRL=X"], False, None),
    ("BTC", "Bitcoin", ["BTC-USD"], False, None),
    ("ETH", "Ethereum", ["ETH-USD"], False, None),
    (
        "IMAB", "IMA-B", ["IMAB11"], True,
        "ETF IMAB11 usado como proxy transparente do índice IMA-B.",
    ),
    (
        "IRFM", "IRF-M", ["IRFM11"], True,
        "ETF IRFM11 usado como proxy transparente do IRF-M P2.",
    ),
    ("OURO", "Ouro", ["GC=F"], False, None),
    ("PRATA", "Prata", ["SI=F"], False, None),
    ("VIX", "VIX", ["^VIX"], False, None),
    ("DXY", "DXY", ["DX-Y.NYB"], False, None),
]

HISTORICAL_RATE_SPECS = [
    ("CDI", "CDI", 12, False, "Banco Central • SGS 12"),
    ("POUPANCA", "Poupança", 25, True, "Banco Central • SGS 25"),
    ("IPCA", "IPCA", 433, False, "IBGE via Banco Central • SGS 433"),
    ("INPC", "INPC", 188, False, "IBGE via Banco Central • SGS 188"),
    ("IGPM", "IGP-M", 189, False, "FGV via Banco Central • SGS 189"),
    ("IGPDI", "IGP-DI", 190, False, "FGV via Banco Central • SGS 190"),
    ("INCC", "INCC", 192, False, "FGV via Banco Central • SGS 192"),
    ("IPCFIPE", "IPC-Fipe", 193, False, "Fipe via Banco Central • SGS 193"),
]


def _plain(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).strip().lower()


def parse_number(value: object) -> float | None:
    """Parse Brazilian or international numeric text without guessing dates."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip().replace("%", "").replace("\xa0", "")
    text = re.sub(r"[^0-9,.-]", "", text)
    if not text or text in {"-", ".", ","}:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        number = float(text)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def _bar_value(bar: dict) -> float | None:
    return parse_number(bar.get("adjusted_close")) or parse_number(bar.get("close"))


def series_snapshot(bars: list[dict]) -> dict:
    """Current value and standard market-window returns using trading sessions."""
    observations = []
    for bar in sorted(bars or [], key=lambda item: item.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc)):
        value = _bar_value(bar)
        if value is not None and value > 0:
            observations.append((bar.get("timestamp"), value))
    if not observations:
        return {"current": None, "as_of": None, "variations": {key: None for key in ("1d", "1w", "1m", "1y")}}
    current = observations[-1][1]
    variations = {}
    for label, sessions in (("1d", 1), ("1w", 5), ("1m", 21), ("1y", 252)):
        previous = observations[-1 - sessions][1] if len(observations) > sessions else None
        variations[label] = ((current / previous) - 1) * 100 if previous else None
    as_of = observations[-1][0]
    return {
        "current": current,
        "as_of": as_of.isoformat() if isinstance(as_of, datetime) else str(as_of or ""),
        "variations": variations,
    }


def compound_percentages(values: list[float], periods: int) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if len(clean) < periods:
        return None
    factor = 1.0
    for value in clean[-periods:]:
        factor *= 1.0 + value / 100.0
    return (factor - 1.0) * 100.0


def _date_from_sgs(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return None


def _easter(year: int) -> date:
    """Gregorian Easter (Anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last = next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def us_exchange_holidays(year: int) -> list[tuple[date, str]]:
    easter = _easter(year)
    return sorted([
        (_observed(date(year, 1, 1)), "Ano-Novo"),
        (_nth_weekday(year, 1, 0, 3), "Martin Luther King Jr. Day"),
        (_nth_weekday(year, 2, 0, 3), "Presidents' Day"),
        (easter - timedelta(days=2), "Sexta-feira Santa"),
        (_last_weekday(year, 5, 0), "Memorial Day"),
        (_observed(date(year, 6, 19)), "Juneteenth"),
        (_observed(date(year, 7, 4)), "Independence Day"),
        (_nth_weekday(year, 9, 0, 1), "Labor Day"),
        (_nth_weekday(year, 11, 3, 4), "Thanksgiving"),
        (_observed(date(year, 12, 25)), "Natal"),
    ])


def b3_holidays(year: int) -> list[tuple[date, str]]:
    easter = _easter(year)
    days = [
        (date(year, 1, 1), "Confraternização Universal"),
        (easter - timedelta(days=48), "Carnaval"),
        (easter - timedelta(days=47), "Carnaval"),
        (easter - timedelta(days=2), "Sexta-feira Santa"),
        (date(year, 4, 21), "Tiradentes"),
        (date(year, 5, 1), "Dia do Trabalho"),
        (easter + timedelta(days=60), "Corpus Christi"),
        (date(year, 9, 7), "Independência do Brasil"),
        (date(year, 10, 12), "Nossa Senhora Aparecida"),
        (date(year, 11, 2), "Finados"),
        (date(year, 11, 15), "Proclamação da República"),
        (date(year, 11, 20), "Consciência Negra"),
        (date(year, 12, 24), "Véspera de Natal"),
        (date(year, 12, 25), "Natal"),
        (date(year, 12, 31), "Véspera de Ano-Novo"),
    ]
    return sorted((day, label) for day, label in days if day.weekday() < 5)


class MarketDashboardService:
    def __init__(self, http=None, prices=None, now=None):
        # Dashboard sources must fail fast. A stale completed snapshot remains
        # visible while individual providers are retried on the next refresh.
        self.http = http or HttpClient(timeout=8, retries=1)
        # SGS receives long-running historical requests. Keep it isolated from
        # the shared session used concurrently by market quotes and serialize
        # calls because requests.Session is not thread-safe.
        self.sgs_http = http or HttpClient(timeout=20, retries=3)
        self._sgs_lock = Lock()
        self.prices = prices or YahooPriceProvider(self.http)
        self.now = now or datetime.now(timezone.utc)

    def _safe(self, name: str, fn, default):
        try:
            return fn(), None
        except Exception as exc:  # one unavailable source must not blank the panel
            return default, f"{name}: {type(exc).__name__}: {str(exc)[:180]}"

    def _sgs_payload(self, series: int, start: date, end: date) -> list[dict]:
        """Fetch one official SGS interval with content validation and retry.

        The public gateway occasionally answers HTTP 200 with a temporary HTML
        page. Treat that as a failed attempt instead of exposing JSONDecodeError
        or caching an empty economic series for the rest of the day.
        """
        last_error: Exception | None = None
        params = {
            "formato": "json",
            "dataInicial": start.strftime("%d/%m/%Y"),
            "dataFinal": end.strftime("%d/%m/%Y"),
        }
        for attempt in range(3):
            try:
                # A single lock protects the dedicated Session even when two
                # dashboard refresh requests arrive at the same time.
                with self._sgs_lock:
                    response = self.sgs_http.get(
                        BCB_SGS_URL.format(series=series),
                        params=params,
                        timeout=20,
                    )
                content_type = str((getattr(response, "headers", {}) or {}).get("Content-Type", ""))
                if content_type and "json" not in content_type.lower():
                    raise ValueError(f"resposta SGS não JSON ({content_type.split(';', 1)[0]})")
                payload = response.json()
                if not isinstance(payload, list):
                    raise ValueError("formato inesperado na resposta SGS")
                return payload
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    sleep(0.4 * (2 ** attempt))
        raise RuntimeError(
            f"BCB SGS {series} indisponível após 3 tentativas: "
            f"{type(last_error).__name__ if last_error else 'erro desconhecido'}"
        ) from last_error

    def _sgs(self, series: int, days: int = 450) -> list[tuple[date, float]]:
        start = self.now.date() - timedelta(days=days)
        end = self.now.date()
        payload = self._sgs_payload(series, start, end)
        out = []
        for row in payload or []:
            observed, value = _date_from_sgs(row.get("data")), parse_number(row.get("valor"))
            if observed and value is not None:
                out.append((observed, value))
        return sorted(out)

    def _sgs_between(self, series: int, start: date, end: date) -> list[tuple[date, float]]:
        """Read long SGS histories in chunks accepted by the public BCB API."""
        rows: dict[date, float] = {}
        cursor = start
        # Daily CDI and savings histories are much denser than monthly price
        # indices. Smaller chunks avoid gateway resets without changing data.
        chunk_days = 700 if series in {12, 25} else 3500
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=chunk_days), end)
            payload = self._sgs_payload(series, cursor, chunk_end)
            for row in payload or []:
                observed = _date_from_sgs(row.get("data"))
                value = parse_number(row.get("valor"))
                if observed and value is not None:
                    rows[observed] = value
            cursor = chunk_end + timedelta(days=1)
        return sorted(rows.items())

    def selic_current(self) -> dict:
        try:
            current_rows = self._sgs(432, days=45)
        except Exception as exc:
            current_rows = []
            error = f"Selic atual: {type(exc).__name__}"
        else:
            error = None
        current = current_rows[-1][1] if current_rows else None
        return {
            "current": current,
            "current_as_of": current_rows[-1][0].isoformat() if current_rows else None,
            "source": "Banco Central do Brasil • SGS 432",
            "url": "https://www.bcb.gov.br/controleinflacao/taxaselic",
            "errors": [error] if error else [],
        }

    def selic_focus(self) -> dict:
        errors = []
        year = self.now.year
        # The service currently rejects equality filters on its string fields
        # with an internal Boolean/String type error. Prefix matching works,
        # but its default sequence is historical. A late page plus a reduced
        # field set stays small and contains the current Focus observations;
        # the final reference-year selection remains explicit below.
        params = {
            "$format": "json",
            "$filter": "startswith(Indicador,'Sel')",
            "$select": "Indicador,Data,DataReferencia,Mediana,baseCalculo",
            "$skip": 35000,
            "$top": 10000,
        }
        try:
            values = self.http.get(BCB_FOCUS_URL, params=params).json().get("value") or []
        except Exception as exc:
            values = []
            errors.append(f"Focus: {type(exc).__name__}")
        projections = {}
        candidates = sorted(
            (row for row in values if isinstance(row, dict)),
            key=lambda row: (
                str(row.get("Data") or ""),
                1 if parse_number(row.get("baseCalculo")) == 0 else 0,
            ),
            reverse=True,
        )
        for row in candidates:
            if _plain(row.get("Indicador")) != "selic":
                continue
            reference_match = re.search(r"20\d{2}", str(row.get("DataReferencia") or ""))
            reference = reference_match.group(0) if reference_match else ""
            value = parse_number(row.get("Mediana"))
            if reference in {str(year), str(year + 1)} and reference not in projections and value is not None:
                projections[reference] = {
                    "value": value,
                    "survey_date": row.get("Data"),
                    "reference_year": int(reference),
                }
        if not projections:
            errors.append("Focus: projeções anuais da Selic não foram localizadas")
        return {
            "current_year": projections.get(str(year), {}),
            "next_year": projections.get(str(year + 1), {}),
            "source": "Banco Central do Brasil • Relatório Focus",
            "url": "https://www.bcb.gov.br/publicacoes/focus",
            "projection_note": (
                "Mediana das expectativas do Relatório Focus para a meta da taxa Selic "
                "no encerramento de cada ano. Não se trata de projeção do CDI."
            ),
            "errors": errors,
        }

    def selic(self) -> dict:
        current = self.selic_current()
        focus = self.selic_focus()
        return {
            **current,
            **{key: value for key, value in focus.items() if key != "errors"},
            "errors": [*(current.get("errors") or []), *(focus.get("errors") or [])],
        }

    def cdi(self) -> dict:
        rows = self._sgs(12, days=450)
        values = [value for _day, value in rows]
        return {
            "label": "CDI", "current": None, "unit": "%", "source": "Banco Central do Brasil • SGS 12",
            "url": "https://www.bcb.gov.br/estatisticas/txjuros", "proxy": False,
            "as_of": rows[-1][0].isoformat() if rows else None,
            "monthly_return_pct": compound_percentages(values, 21),
            "annual_return_pct": compound_percentages(values, 252),
        }

    def inflation(self) -> list[dict]:
        specifications = [
            (433, "IPCA", "IBGE via Banco Central • SGS 433"),
            (188, "INPC", "IBGE via Banco Central • SGS 188"),
            (189, "IGP-M", "FGV via Banco Central • SGS 189"),
            (190, "IGP-DI", "FGV via Banco Central • SGS 190"),
            (193, "IPC-Fipe", "Fipe via Banco Central • SGS 193"),
            (192, "INCC", "FGV via Banco Central • SGS 192"),
        ]
        out = []
        for series, label, source in specifications:
            error = None
            try:
                rows = self._sgs(series, days=520)
                value = compound_percentages([value for _day, value in rows], 12)
            except Exception as exc:
                rows, value = [], None
                error = f"{type(exc).__name__}: {str(exc)[:120]}"
            out.append({
                "label": label, "value_12m": value,
                "as_of": rows[-1][0].isoformat() if rows else None,
                "source": source, "url": f"https://www.ibge.gov.br/indicadores" if label != "IGP-M" else "https://portalibre.fgv.br/igp-m",
                "error": error,
            })
        cpi_error = None
        try:
            payload = self.http.get(BLS_API_URL).json()
            series = (((payload.get("Results") or {}).get("series") or [{}])[0]).get("data") or []
        except Exception as exc:
            series = []
            cpi_error = f"{type(exc).__name__}: {str(exc)[:120]}"
        values = {}
        for row in series:
            try:
                values[(int(row["year"]), int(str(row["period"]).replace("M", "")))] = float(row["value"])
            except (KeyError, TypeError, ValueError):
                continue
        ordered = sorted(values)
        cpi = None
        as_of = None
        if len(ordered) >= 13:
            latest = ordered[-1]
            previous = (latest[0] - 1, latest[1])
            if previous in values and values[previous]:
                cpi = (values[latest] / values[previous] - 1) * 100
                as_of = f"{latest[0]:04d}-{latest[1]:02d}-01"
        out.append({
            "label": "CPI EUA", "value_12m": cpi, "as_of": as_of,
            "source": "U.S. Bureau of Labor Statistics", "url": "https://www.bls.gov/cpi/",
            "error": cpi_error,
        })
        return out

    def _yahoo_metric(self, label: str, symbols: list[str], *, unit: str = "pontos",
                      currency: str | None = None, proxy: bool = False,
                      proxy_label: str | None = None) -> dict:
        last_error = None
        fallback_proxies = {
            "XFIX11": "ETF XFIX11, referência líquida do segmento imobiliário (acompanha o IFIX L)",
            "BRAX11": "ETF BRAX11, referência do IBrX 100",
            "PIBB11": "ETF PIBB11, referência do IBrX 50",
            "DIVO11": "ETF DIVO11, referência do IDIV",
            "SMAL11": "ETF SMAL11, referência do SMLL",
            "EXSA.DE": "ETF iShares STOXX Europe 600 (EXSA)",
        }
        partial = None
        for symbol in symbols:
            try:
                snapshot = series_snapshot(self.prices.fetch(symbol, range_="2y"))
                if snapshot["current"] is not None:
                    effective_proxy = proxy or symbol in fallback_proxies
                    candidate = {
                        "label": label, "ticker": symbol, "unit": unit, "currency": currency,
                        "proxy": effective_proxy,
                        "proxy_label": proxy_label or fallback_proxies.get(symbol),
                        "source": "Yahoo Finance",
                        "url": f"https://finance.yahoo.com/quote/{YahooPriceProvider.symbol(symbol)}",
                        **snapshot,
                    }
                    variations = candidate.get("variations") or {}
                    if partial is not None and effective_proxy:
                        # Preserve the official index level when available, but complete
                        # missing returns with the explicitly identified liquid proxy.
                        partial_variations = dict(partial.get("variations") or {})
                        partial_variations.update({
                            key: partial_variations.get(key) if partial_variations.get(key) is not None else variations.get(key)
                            for key in ("1d", "1w", "1m", "1y")
                        })
                        partial["variations"] = partial_variations
                        partial["proxy"] = True
                        partial["proxy_label"] = f"Variações complementadas por {fallback_proxies.get(symbol, proxy_label or symbol)}"
                        return partial
                    if all(variations.get(key) is not None for key in ("1d", "1w", "1m", "1y")):
                        return candidate
                    if partial is None:
                        partial = candidate
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {str(exc)[:120]}"
        if partial is not None:
            return partial
        return {
            "label": label, "ticker": symbols[0], "unit": unit, "currency": currency,
            "proxy": proxy, "proxy_label": proxy_label, "source": "Yahoo Finance",
            "current": None, "as_of": None, "variations": {key: None for key in ("1d", "1w", "1m", "1y")},
            "error": last_error or "cotacao_indisponivel",
        }

    def quoted_markets(self) -> dict:
        specifications = {
            "brazil": [
                ("IBOV", ["^BVSP"], "pontos", None, False, None),
                ("IFIX", ["^IFIX", "XFIX11"], "pontos", None, False, None),
                ("IBrX 100", ["^IBXX", "BRAX11"], "pontos", None, False, None),
                ("IBrX 50", ["^IBXL", "PIBB11"], "pontos", None, False, None),
                ("IDIV", ["^IDIV", "DIVO11"], "pontos", None, False, None),
                ("SMLL", ["^SMLL", "SMAL11"], "pontos", None, False, None),
            ],
            "global": [
                ("NYSE Composite", ["^NYA"], "pontos", None, False, None),
                ("NASDAQ Composite", ["^IXIC"], "pontos", None, False, None),
                ("S&P 500", ["^GSPC"], "pontos", None, False, None),
                ("Dow Jones", ["^DJI"], "pontos", None, False, None),
                ("Nikkei 225", ["^N225"], "pontos", None, False, None),
                ("Shanghai SSE", ["000001.SS"], "pontos", None, False, None),
                ("Euro Stoxx 50", ["^STOXX50E"], "pontos", None, False, None),
                ("STOXX Europe 600", ["^STOXX", "EXSA.DE"], "pontos", None, False, None),
                ("MSCI Europe", ["IEUR"], "USD", "USD", True, "ETF iShares Core MSCI Europe (IEUR)"),
            ],
            "risk": [("VIX", ["^VIX"], "pontos", None, False, None), ("DXY", ["DX-Y.NYB"], "pontos", None, False, None)],
            "commodities": [
                ("Ouro", ["GC=F"], "USD", "USD", False, None),
                ("Prata", ["SI=F"], "USD", "USD", False, None),
                ("Petróleo Brent", ["BZ=F"], "USD", "USD", False, None),
                ("Petróleo WTI", ["CL=F"], "USD", "USD", False, None),
            ],
        }
        tasks, result = {}, {group: [] for group in specifications}
        with ThreadPoolExecutor(max_workers=8) as executor:
            for group, items in specifications.items():
                for spec in items:
                    future = executor.submit(self._yahoo_metric, spec[0], spec[1], unit=spec[2], currency=spec[3], proxy=spec[4], proxy_label=spec[5])
                    tasks[future] = group
            for future in as_completed(tasks):
                result[tasks[future]].append(future.result())
        desired_order = {group: {item[0]: pos for pos, item in enumerate(items)} for group, items in specifications.items()}
        for group in result:
            result[group].sort(key=lambda row: desired_order[group].get(row["label"], 999))
        return result

    def fixed_income(self) -> list[dict]:
        try:
            cdi = self.cdi()
        except Exception as exc:
            cdi = {
                "label": "CDI", "current": None, "unit": "%", "source": "Banco Central do Brasil • SGS 12",
                "proxy": False, "as_of": None,
                "monthly_return_pct": None, "annual_return_pct": None,
                "error": f"{type(exc).__name__}: {str(exc)[:120]}",
            }
        try:
            response = self.http.get(ANBIMA_IMA_COMPLETE_URL)
            root = ElementTree.fromstring(response.content)
            official = {}
            for family in root.findall("FAMILIA"):
                label = str(family.attrib.get("INDICE") or "").strip()
                if label not in {"IMA-B", "IRF-M"}:
                    continue
                totals = family.find("TOTAIS")
                total = family.find("TOTAIS/TOTAL")
                if total is None:
                    continue
                official[label] = {
                    "label": label,
                    "unit": "%",
                    "proxy": False,
                    "source": "ANBIMA • Índice de Mercado ANBIMA",
                    "url": ANBIMA_IMA_URL,
                    "as_of": datetime.strptime(
                        str((totals.attrib if totals is not None else {}).get("DT_REF") or ""),
                        "%d/%m/%Y",
                    ).date().isoformat(),
                    # Doze meses mantém a coluna anual comparável ao CDI.
                    "annual_return_pct": parse_number(total.attrib.get("T_Var_Ult12M")),
                    "monthly_return_pct": parse_number(total.attrib.get("T_Var_Mensal")),
                }
            imab, irfm = official["IMA-B"], official["IRF-M"]
        except Exception as exc:
            failure = f"{type(exc).__name__}: {str(exc)[:120]}"
            imab = {
                "label": "IMA-B", "unit": "%", "proxy": False,
                "source": "ANBIMA • Índice de Mercado ANBIMA", "url": ANBIMA_IMA_URL,
                "as_of": None, "annual_return_pct": None, "monthly_return_pct": None,
                "error": failure,
            }
            irfm = {**imab, "label": "IRF-M"}
        return [cdi, imab, irfm]

    def crypto(self) -> list[dict]:
        usd_brl = self._yahoo_metric("Dólar / Real", ["BRL=X"], unit="R$", currency="BRL")
        conversion = parse_number(usd_brl.get("current"))
        out = []
        for label, base in (
            ("Bitcoin", "BTC"), ("Ethereum", "ETH"), ("Solana", "SOL"),
            ("Ripple (XRP)", "XRP"), ("BNB", "BNB"),
        ):
            usd = self._yahoo_metric(label, [f"{base}-USD"], unit="USD", currency="USD")
            brl = self._yahoo_metric(label, [f"{base}-BRL"], unit="R$", currency="BRL")
            value_brl = brl.get("current")
            derived_brl = False
            if value_brl is None and usd.get("current") is not None and conversion is not None:
                value_brl = float(usd["current"]) * conversion
                derived_brl = True
            out.append({
                "label": label, "ticker": base, "value_usd": usd.get("current"),
                "value_brl": value_brl, "brl_derived_from_fx": derived_brl,
                "as_of": usd.get("as_of") or brl.get("as_of"),
                "variations": usd.get("variations") or {}, "source": "Yahoo Finance",
                "url": usd.get("url"),
            })
        return out

    def fx(self) -> list[dict]:
        specifications = (
            ("Dólar / Real", ["BRL=X"], "R$ / USD", 1.0),
            ("Euro / Real", ["EURBRL=X"], "R$ / EUR", 1.0),
            ("Libra / Real", ["GBPBRL=X"], "R$ / GBP", 1.0),
            ("Iene / Real", ["JPYBRL=X"], "R$ / 100 JPY", 100.0),
        )
        with ThreadPoolExecutor(max_workers=5) as executor:
            metrics = list(executor.map(
                lambda spec: self._yahoo_metric(spec[0], spec[1], unit=spec[2], currency="BRL"),
                specifications,
            ))
            eur_usd = executor.submit(
                self._yahoo_metric, "Euro / Dólar", ["EURUSD=X"], unit="USD / EUR", currency="USD",
            ).result()
        for metric, spec in zip(metrics, specifications):
            multiplier = spec[3]
            if multiplier != 1 and metric.get("current") is not None:
                metric["current"] = float(metric["current"]) * multiplier
                metric["display_multiplier"] = multiplier
        # Yahoo's EURUSD is USD per EUR. The requested quotation is EUR per USD,
        # therefore both the level and every return must be inverted.
        if eur_usd.get("current"):
            eur_usd["current"] = 1.0 / float(eur_usd["current"])
            eur_usd["label"] = "Dólar / Euro"
            eur_usd["ticker"] = "EURUSD=X (invertido)"
            eur_usd["unit"] = "EUR / USD"
            eur_usd["currency"] = "EUR"
            eur_usd["orientation_note"] = "Euros por dólar; calculado pelo inverso de USD por euro."
            eur_usd["variations"] = {
                key: ((1.0 / (1.0 + float(value) / 100.0)) - 1.0) * 100.0
                if value is not None else None
                for key, value in (eur_usd.get("variations") or {}).items()
            }
        return [metrics[0], eur_usd, metrics[1], metrics[2], metrics[3]]

    def _treasury_yields(self) -> tuple[dict, str, str, str]:
        """Fetch the latest official U.S. Treasury par-yield observation."""
        month = self.now.strftime("%Y%m")
        response = self.http.get(
            TREASURY_RATES_URL,
            params={
                "data": "daily_treasury_yield_curve",
                "field_tdr_date_value_month": month,
            },
        )
        root = ElementTree.fromstring(response.content)
        data_namespace = "{http://schemas.microsoft.com/ado/2007/08/dataservices}"
        metadata_namespace = "{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}"
        observations = []
        for properties in root.iter(f"{metadata_namespace}properties"):
            values = {
                child.tag.replace(data_namespace, ""): parse_number(child.text)
                for child in properties
            }
            date_node = properties.find(f"{data_namespace}NEW_DATE")
            observed = str(date_node.text or "") if date_node is not None else ""
            values["date"] = observed[:10]
            if values.get("BC_2YEAR") is not None and values.get("BC_10YEAR") is not None:
                observations.append(values)
        if not observations:
            raise ValueError("official_treasury_yields_unavailable")
        latest = max(observations, key=lambda item: item.get("date") or "")
        return latest, latest["date"], "U.S. Department of the Treasury", (
            "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            "TextView?type=daily_treasury_yield_curve"
        )

    def _fred_yields(self) -> tuple[dict, str, str, str]:
        columns = ("DGS2", "DGS5", "DGS10", "DGS30")
        start = (self.now.date() - timedelta(days=45)).isoformat()
        frame = pd.read_csv(StringIO(self.http.get(FRED_RATES_URL, params={"cosd": start}).text))
        for column in columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        valid = frame.dropna(subset=["DGS2", "DGS10"])
        if valid.empty:
            raise ValueError("fred_treasury_yields_unavailable")
        row = valid.iloc[-1]
        return dict(row), str(row.iloc[0]), "Federal Reserve Bank of St. Louis • FRED", "https://fred.stlouisfed.org/series/DGS10"

    def us_rates(self) -> dict:
        try:
            row, observed_at, source, source_url = self._treasury_yields()
            field_map = {"DGS2": "BC_2YEAR", "DGS5": "BC_5YEAR", "DGS10": "BC_10YEAR", "DGS30": "BC_30YEAR"}
        except Exception:
            row, observed_at, source, source_url = self._fred_yields()
            field_map = {key: key for key in ("DGS2", "DGS5", "DGS10", "DGS30")}
        yields = [
            {"maturity": label, "years": years, "yield_pct": parse_number(row.get(field_map[column]))}
            for label, years, column in (
                ("2 anos", 2, "DGS2"), ("5 anos", 5, "DGS5"),
                ("10 anos", 10, "DGS10"), ("30 anos", 30, "DGS30"),
            )
        ]
        bond_specs = (
            ("Treasuries curtos", "SHY", "ETF de títulos do Tesouro de 1–3 anos"),
            ("Treasuries intermediários", "IEF", "ETF de títulos do Tesouro de 7–10 anos"),
            ("Treasuries longos", "TLT", "ETF de títulos do Tesouro acima de 20 anos"),
        )

        def bond_return(spec):
            label, symbol, description = spec
            metric = self._yahoo_metric(
                label, [symbol], unit="USD", currency="USD",
                proxy=True, proxy_label=description,
            )
            variations = metric.get("variations") or {}
            return {
                "label": label, "ticker": symbol, "proxy": True,
                "proxy_label": description, "monthly_return_pct": variations.get("1m"),
                "annual_return_pct": variations.get("1y"), "as_of": metric.get("as_of"),
                "source": metric.get("source"), "url": metric.get("url"),
            }

        with ThreadPoolExecutor(max_workers=3) as executor:
            bond_returns = list(executor.map(bond_return, bond_specs))
        two_year = parse_number(row.get(field_map["DGS2"]))
        ten_year = parse_number(row.get(field_map["DGS10"]))
        spread = ten_year - two_year if two_year is not None and ten_year is not None else None
        return {
            "yields": yields, "two_year": two_year, "ten_year": ten_year,
            "spread_10y_2y": spread, "bond_returns": bond_returns,
            "spread_explanation": (
                "O spread de 10 anos menos 2 anos mede a inclinação da curva americana. "
                "Positivo sugere prêmio maior no longo prazo; negativo indica curva invertida "
                "e costuma sinalizar expectativa de desaceleração e cortes de juros."
            ),
            "as_of": observed_at, "source": source, "url": source_url,
        }

    @staticmethod
    def _flat_columns(frame: pd.DataFrame) -> list[str]:
        columns = []
        for column in frame.columns:
            if isinstance(column, tuple):
                column = " ".join(str(value) for value in column if str(value) != "nan")
            columns.append(_plain(column))
        return columns

    @staticmethod
    def _di_expiry(symbol: str) -> date | None:
        match = re.fullmatch(r"DI1([FGHJKMNQUVXZ])(\d{2})", str(symbol or "").upper())
        if not match:
            return None
        months = {code: month for month, code in enumerate("FGHJKMNQUVXZ", start=1)}
        expiry = date(2000 + int(match.group(2)), months[match.group(1)], 1)
        holidays = {day for day, _name in b3_holidays(expiry.year)}
        while expiry.weekday() >= 5 or expiry in holidays:
            expiry += timedelta(days=1)
        return expiry

    @staticmethod
    def _business_days(start: date, end: date) -> int:
        if end <= start:
            return 0
        holidays = {
            day
            for year in range(start.year, end.year + 1)
            for day, _name in b3_holidays(year)
        }
        cursor, total = start + timedelta(days=1), 0
        while cursor <= end:
            if cursor.weekday() < 5 and cursor not in holidays:
                total += 1
            cursor += timedelta(days=1)
        return total

    def _b3_di_curve(self) -> dict:
        workday_text = str(self.http.get(B3_BDI_WORKDAY_URL).json() or "")
        observed = datetime.fromisoformat(workday_text.replace("Z", "+00:00")).date()
        observed_text = observed.isoformat()
        base = f"{B3_BDI_TABLE_URL}/{observed_text}/{observed_text}"
        first = self.http.post(f"{base}/1/1000", json={}).json().get("table") or {}
        page_count = max(1, int(first.get("pageCount") or 1))
        pages = {1: first}
        # DI1 contracts are sorted near the end of the official consolidated
        # derivatives table. Reading the last two pages protects boundary moves.
        for page in sorted({max(1, page_count - 1), page_count} - {1}):
            pages[page] = self.http.post(f"{base}/{page}/1000", json={}).json().get("table") or {}
        points = []
        for table in pages.values():
            columns = [str(item.get("name") or "") for item in table.get("columns") or []]
            positions = {name: index for index, name in enumerate(columns)}
            for row in table.get("values") or []:
                symbol = str(row[positions.get("TckrSymb", 1)] or "")
                if not symbol.startswith("DI1"):
                    continue
                expiry = self._di_expiry(symbol)
                days = self._business_days(observed, expiry) if expiry else 0
                rate_index = positions.get("AdjstdQtTax")
                rate = parse_number(row[rate_index]) if rate_index is not None else None
                if expiry is None or days <= 0 or rate is None:
                    continue
                points.append({
                    "business_days": days,
                    "years": round(days / 252.0, 3),
                    "nominal_rate": rate,
                    "di_rate": rate,
                    "contract": symbol,
                    "expiry": expiry.isoformat(),
                    "origin": "b3_di1",
                    "observed": True,
                })
        unique = {point["contract"]: point for point in points}
        return {
            "as_of": observed_text,
            "points": sorted(unique.values(), key=lambda item: item["business_days"]),
            "source": "B3 • Ajustes de referência dos contratos futuros DI1",
            "url": "https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/juros/"
                   "futuro-de-taxa-media-de-depositos-interfinanceiros-de-um-dia.htm",
        }

    def interest_curve(self) -> dict:
        b3_error = None
        try:
            b3_curve = self._b3_di_curve()
        except Exception as exc:
            b3_curve = {"points": []}
            b3_error = f"{type(exc).__name__}: {str(exc)[:140]}"
        response = self.http.get(ANBIMA_CURVE_URL)
        # The page declares ISO-8859-1 in an XML preamble. Passing an already
        # decoded Unicode string with that declaration to lxml raises a
        # ValueError, which was why the curve disappeared in production.
        html = re.sub(r"^\s*<\?xml[^>]*\?>", "", response.text, count=1, flags=re.IGNORECASE)
        tables = pd.read_html(StringIO(html), decimal=",", thousands=".", flavor="lxml")
        points = []
        as_of = None
        date_match = re.search(r"(\d{2}/\d{2}/\d{4})", response.text)
        if date_match:
            as_of = datetime.strptime(date_match.group(1), "%d/%m/%Y").date().isoformat()
        for frame in tables:
            names = self._flat_columns(frame)
            day_idx = next((i for i, name in enumerate(names) if "vertice" in name or name == "dias" or "prazo" in name), None)
            pre_idx = next((i for i, name in enumerate(names) if "ettj pre" in name or "prefix" in name), None)
            ipca_idx = next((i for i, name in enumerate(names) if "ettj ipca" in name or ("ipca" in name and "inflacao" not in name)), None)
            inflation_idx = next((i for i, name in enumerate(names) if "inflacao" in name), None)
            if day_idx is None or (pre_idx is None and ipca_idx is None):
                continue
            for _index, row in frame.iterrows():
                days = parse_number(row.iloc[day_idx])
                if days is None or days <= 0:
                    continue
                point = {
                    "business_days": int(days), "years": round(days / 252.0, 2),
                    "nominal_rate": parse_number(row.iloc[pre_idx]) if pre_idx is not None else None,
                    "real_rate": parse_number(row.iloc[ipca_idx]) if ipca_idx is not None else None,
                    "implied_inflation": parse_number(row.iloc[inflation_idx]) if inflation_idx is not None else None,
                }
                if point["nominal_rate"] is not None or point["real_rate"] is not None:
                    points.append(point)
            if points:
                break
        official_di = b3_curve.get("points") or []
        return {
            "as_of": b3_curve.get("as_of") or as_of,
            "points": official_di or points,
            "di_points": official_di,
            "ettj_points": points,
            "curve_type": "di_pre" if official_di else "anbima_ettj_fallback",
            "title": "Curva de Juros Futuros — DI x Pré" if official_di else "Curva Prefixada — ETTJ ANBIMA",
            "source": b3_curve.get("source") if official_di else "ANBIMA • Estrutura a Termo das Taxas de Juros",
            "url": b3_curve.get("url") if official_di else ANBIMA_CURVE_URL,
            "complement_source": "ANBIMA • ETTJ Prefixada e IPCA",
            "complement_url": ANBIMA_CURVE_URL,
            "methodology": (
                "Taxas de ajuste dos contratos DI1 da B3, expressas como taxa efetiva anual "
                "em base de 252 dias úteis. A ETTJ ANBIMA permanece disponível como complemento."
                if official_di else
                "A B3 não respondeu nesta atualização; exibimos a ETTJ oficial da ANBIMA, "
                "identificada como fonte alternativa e sem extrapolar vértices."
            ),
            "errors": [b3_error] if b3_error else [],
        }

    @staticmethod
    def _monthly_price_points(bars: list[dict]) -> list[dict]:
        monthly: dict[tuple[int, int], tuple[date, float]] = {}
        for bar in sorted(bars or [], key=lambda item: item.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc)):
            stamp = bar.get("timestamp")
            value = _bar_value(bar)
            if not isinstance(stamp, datetime) or value is None or value <= 0:
                continue
            monthly[(stamp.year, stamp.month)] = (stamp.date(), value)
        values = list(monthly.values())
        if not values:
            return []
        base = values[0][1]
        return [{"date": day.isoformat(), "value": round(value / base * 100.0, 6)} for day, value in values]

    @staticmethod
    def _monthly_rate_points(rows: list[tuple[date, float]], *, first_only: bool = False) -> list[dict]:
        monthly: dict[tuple[int, int], list[tuple[date, float]]] = {}
        for observed, value in rows:
            monthly.setdefault((observed.year, observed.month), []).append((observed, value))
        index, points = 100.0, []
        for key in sorted(monthly):
            observations = sorted(monthly[key])
            if first_only:
                monthly_return = observations[0][1]
            else:
                factor = 1.0
                for _day, value in observations:
                    factor *= 1.0 + value / 100.0
                monthly_return = (factor - 1.0) * 100.0
            index *= 1.0 + monthly_return / 100.0
            points.append({"date": observations[-1][0].isoformat(), "value": round(index, 6)})
        return points

    def historical_comparison(self, years: int = 20) -> dict:
        """Monthly, rebased market/economic histories for a responsive comparison chart."""
        years = max(1, min(int(years), 20))
        end = self.now.date()
        start = end - timedelta(days=round(365.25 * years) + 40)
        price_specs = HISTORICAL_PRICE_SPECS
        rate_specs = HISTORICAL_RATE_SPECS

        def price_history(spec):
            code, label, symbols, proxy, note = spec
            last_error = None
            for symbol in symbols:
                try:
                    bars = self.prices.fetch(
                        symbol,
                        start=datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
                        end=self.now,
                    )
                    points = self._monthly_price_points(bars)
                    if len(points) >= 6:
                        actual_proxy = proxy or symbol in {"XFIX11", "EXSA.DE"}
                        return {
                            "code": code, "label": label, "points": points,
                            "source": "Yahoo Finance", "url": f"https://finance.yahoo.com/quote/{YahooPriceProvider.symbol(symbol)}",
                            "proxy": actual_proxy,
                            "note": note or ("ETF XFIX11 usado somente quando o índice IFIX não responde." if actual_proxy else None),
                        }
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {str(exc)[:100]}"
            return {
                "code": code, "label": label, "points": [],
                "source": "Yahoo Finance",
                "error": last_error or "history_unavailable",
            }

        def rate_history(spec):
            code, label, series, first_only, source = spec
            try:
                rows = self._sgs_between(series, start, end)
                return {
                    "code": code, "label": label,
                    "points": self._monthly_rate_points(rows, first_only=first_only),
                    "source": source,
                    "url": f"https://www3.bcb.gov.br/sgspub/consultarvalores/consultarValoresSeries.do?method=consultarSeries&series={series}",
                    "methodology": (
                        "Rentabilidade do período de 30 dias da primeira observação de cada mês."
                        if first_only else "Variações percentuais acumuladas por capitalização composta."
                    ),
                }
            except Exception as exc:
                return {"code": code, "label": label, "points": [], "source": source, "error": f"{type(exc).__name__}: {str(exc)[:100]}"}

        order = HISTORICAL_COMPARISON_ORDER
        series = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(price_history, spec) for spec in price_specs]
            for future in as_completed(futures):
                series.append(future.result())
        # Economic series are intentionally sequential. The public SGS gateway
        # intermittently returns an HTML page under concurrent access, even
        # with HTTP 200, which used to leave several indicators without data.
        for spec in rate_specs:
            series.append(rate_history(spec))
        # Keep a stable catalog even when one upstream source is unavailable.
        # The browser can then display BTC/ETH (and every other option) as
        # temporarily unavailable instead of silently removing the selector.
        by_code = {str(item.get("code")): item for item in series}
        series = [
            by_code.get(code, {
                "code": code,
                "label": code,
                "points": [],
                "source": "Fonte temporariamente indisponível",
                "error": "series_not_returned",
            })
            for code in order
        ]
        available = sum(bool(item.get("points")) for item in series)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "base": 100,
            "max_years": years,
            "periods": [0.5, 1, 2, 3, 5, 10, 15, 20],
            "series": series,
            "status": "complete" if available == len(series) else "partial",
            "available_series": available,
            "total_series": len(series),
            "note": "Cada linha é rebaseada em R$ 100 no primeiro ponto visível do período escolhido.",
        }

    def economy_headlines(self, limit: int = 10) -> dict:
        """Return linked headlines only; article content is never reproduced."""
        items: list[dict] = []
        errors: list[str] = []
        try:
            soup = BeautifulSoup(self.http.get(AGENCIA_BRASIL_ECONOMY_RSS).text, "xml")
            for entry in soup.find_all("item")[:12]:
                title = entry.find("title")
                link = entry.find("link")
                published = entry.find("pubDate")
                if title and link:
                    items.append({
                        "title": title.get_text(" ", strip=True),
                        "url": link.get_text(strip=True), "source": "Agência Brasil",
                        "published_at": self._normalize_published_at(published.get_text(strip=True) if published else None),
                    })
        except Exception as exc:
            errors.append(f"Agência Brasil: {type(exc).__name__}")
        try:
            soup = BeautifulSoup(self.http.get(ADVFN_MARKET_NEWS_URL).text, "html.parser")
            for heading in soup.find_all(["h2", "h3"]):
                anchor = heading.find("a", href=True)
                if anchor is None:
                    continue
                title = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True))
                href = str(anchor.get("href") or "")
                if len(title) < 25 or not href:
                    continue
                if href.startswith("/"):
                    href = "https://br.advfn.com" + href
                time_node = heading.find("time") or (heading.parent.find("time") if heading.parent else None)
                published = (time_node.get("datetime") or time_node.get_text(" ", strip=True)) if time_node else None
                items.append({"title": title, "url": href, "source": "ADVFN", "published_at": self._normalize_published_at(published)})
        except Exception as exc:
            errors.append(f"ADVFN: {type(exc).__name__}")
        unique: dict[str, dict] = {}
        for item in items:
            key = _plain(item["title"])
            if key and key not in unique:
                unique[key] = item
        selected = list(unique.values())[:max(1, min(int(limit), 10))]
        return {
            "items": selected, "updated_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": 3600, "errors": errors,
        }

    @staticmethod
    def _normalize_published_at(value: object) -> str | None:
        clean = str(value or "").strip()
        if not clean:
            return None
        try:
            return parsedate_to_datetime(clean).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc).isoformat()
            except ValueError:
                return None

    @staticmethod
    def _bls_release_date(value: object) -> date | None:
        clean = re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()
        clean = clean.replace("Sept.", "Sep.")
        for pattern in ("%b. %d, %Y", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(clean, pattern).date()
            except ValueError:
                continue
        return None

    def _bls_schedule_html(self, url: str, category: str) -> list[dict]:
        response = self.http.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        events = []
        for row in soup.find_all("tr"):
            cells = [re.sub(r"\s+", " ", cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
            if len(cells) < 2:
                continue
            release_date = self._bls_release_date(cells[1])
            if release_date is None or release_date < self.now.date():
                continue
            release_time = cells[2] if len(cells) > 2 else "08:30 AM"
            events.append({
                "category": category,
                "event": "Divulgação do CPI dos EUA" if category == "CPI dos EUA" else "Divulgação do Payroll dos EUA",
                "date": release_date.isoformat(), "time": f"{release_time} ET",
                "region": "Estados Unidos", "source": "U.S. Bureau of Labor Statistics",
                "url": url,
            })
        return events

    def _known_bls_2026_calendar(self) -> list[dict]:
        """Official 2026 dates used only if both live BLS formats are unavailable."""
        schedules = {
            "CPI dos EUA": (
                BLS_CPI_SCHEDULE_URL,
                [(9, 11), (10, 14), (11, 10), (12, 10)],
            ),
            "Payroll dos EUA": (
                BLS_PAYROLL_SCHEDULE_URL,
                [(9, 4), (10, 2), (11, 6), (12, 4)],
            ),
        }
        events = []
        for category, (url, values) in schedules.items():
            for month, day in values:
                release_date = date(2026, month, day)
                if release_date >= self.now.date():
                    events.append({
                        "category": category,
                        "event": "Divulgação do CPI dos EUA" if category == "CPI dos EUA" else "Divulgação do Payroll dos EUA",
                        "date": release_date.isoformat(), "time": "08:30 AM ET",
                        "region": "Estados Unidos", "source": "U.S. Bureau of Labor Statistics",
                        "url": url, "fallback": True,
                    })
        return events

    @staticmethod
    def _merge_super_wednesday(events: list[dict]) -> list[dict]:
        """Merge coincident Copom/Fed decisions into one unambiguous event."""
        by_date: dict[str, list[dict]] = {}
        for event in events:
            by_date.setdefault(str(event.get("date") or ""), []).append(event)
        merged: list[dict] = []
        for event_date, rows in by_date.items():
            copom = next((row for row in rows if row.get("category") == "Decisão do Copom"), None)
            fed = next((row for row in rows if row.get("category") == "Decisão do Fed"), None)
            if copom and fed:
                merged.append({
                    "category": "Super Quarta",
                    "event": "Decisões de juros do Copom e do Fed",
                    "date": event_date,
                    "time": " • ".join([
                        f"Copom: {copom.get('time') or 'após o fechamento'}",
                        f"Fed: {fed.get('time') or 'horário a confirmar'}",
                    ]),
                    "region": "Brasil e Estados Unidos",
                    "source": "Banco Central do Brasil e Federal Reserve",
                    "url": copom.get("url"),
                    "highlight": "super_wednesday",
                    "observation": "Super Quarta: as duas decisões de juros ocorrem no mesmo dia.",
                })
                rows = [row for row in rows if row is not copom and row is not fed]
            merged.extend(rows)
        return merged

    def _bls_calendar(self) -> list[dict]:
        events = []
        try:
            text = self.http.get(BLS_ICS_URL).text.replace("\r\n ", "").replace("\n ", "")
        except Exception:
            text = ""
        events = []
        for block in text.split("BEGIN:VEVENT")[1:]:
            summary_match = re.search(r"^SUMMARY(?:;[^:]*)?:(.+)$", block, flags=re.MULTILINE | re.IGNORECASE)
            date_match = re.search(r"^DTSTART(?:;[^:]*)?:(\d{8})(?:T(\d{6})Z?)?", block, flags=re.MULTILINE | re.IGNORECASE)
            if not summary_match or not date_match:
                continue
            summary = summary_match.group(1).strip().replace("\\,", ",")
            plain = _plain(summary)
            category = None
            if "consumer price index" in plain:
                category = "CPI dos EUA"
            elif "employment situation" in plain:
                category = "Payroll dos EUA"
            if category is None:
                continue
            event_date = datetime.strptime(date_match.group(1), "%Y%m%d").date()
            if event_date < self.now.date():
                continue
            time_label = None
            if date_match.group(2):
                utc_time = datetime.strptime(date_match.group(1) + date_match.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                try:
                    from zoneinfo import ZoneInfo
                    time_label = utc_time.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M")
                except Exception:
                    time_label = utc_time.strftime("%H:%M UTC")
            events.append({
                "category": category, "event": summary, "date": event_date.isoformat(),
                "time": time_label, "region": "Estados Unidos", "source": "U.S. Bureau of Labor Statistics",
                "url": "https://www.bls.gov/schedule/",
            })
        # The ICS feed is occasionally blocked by hosting providers. Complete
        # each missing category from the official HTML schedules instead.
        present = {item["category"] for item in events}
        for category, url in (("CPI dos EUA", BLS_CPI_SCHEDULE_URL), ("Payroll dos EUA", BLS_PAYROLL_SCHEDULE_URL)):
            if category in present:
                continue
            try:
                events.extend(self._bls_schedule_html(url, category))
            except Exception:
                pass
        present = {item["category"] for item in events}
        if not {"CPI dos EUA", "Payroll dos EUA"}.issubset(present):
            for item in self._known_bls_2026_calendar():
                if item["category"] not in present:
                    events.append(item)

        unique = {}
        for item in events:
            unique[(item["category"], item["date"])] = item
        selected = []
        for category in ("CPI dos EUA", "Payroll dos EUA"):
            selected.extend(sorted((item for item in unique.values() if item["category"] == category), key=lambda item: item["date"])[:3])
        return selected

    def calendar(self) -> list[dict]:
        today, events = self.now.date(), []
        copom_dates = {
            2026: [(1, 28), (3, 18), (4, 29), (6, 17), (8, 5), (9, 16), (11, 4), (12, 9)],
            2027: [(1, 27), (3, 17), (4, 28), (6, 16), (8, 4), (9, 22), (10, 27), (12, 8)],
        }
        upcoming_copom = []
        for year, values in copom_dates.items():
            for month, day in values:
                meeting = date(year, month, day)
                if meeting >= today:
                    upcoming_copom.append(meeting)
        source_by_year = {
            2026: "https://www.bcb.gov.br/detalhenoticia/20739/nota",
            2027: "https://www.bcb.gov.br/detalhenoticia/21173/nota",
        }
        for meeting in sorted(upcoming_copom)[:3]:
            events.append({
                "category": "Decisão do Copom", "event": "Divulgação da taxa Selic pelo Copom",
                "date": meeting.isoformat(), "time": None, "region": "Brasil",
                "source": "Banco Central do Brasil", "url": source_by_year.get(meeting.year, "https://www.bcb.gov.br/controleinflacao/copom"),
            })
        fomc_dates = {
            2026: [(1, 28), (3, 18), (4, 29), (6, 17), (7, 29), (9, 16), (10, 28), (12, 9)],
            2027: [(1, 27), (3, 17), (4, 28), (6, 9), (7, 28), (9, 15), (10, 27), (12, 8)],
        }
        upcoming_fomc = []
        for year, values in fomc_dates.items():
            for month, day in values:
                decision = date(year, month, day)
                if decision >= today:
                    upcoming_fomc.append(decision)
        for decision in sorted(upcoming_fomc)[:3]:
            events.append({
                "category": "Decisão do Fed", "event": "Divulgação da taxa de juros pelo FOMC",
                "date": decision.isoformat(), "time": "14:00 ET", "region": "Estados Unidos",
                "source": "Federal Reserve", "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            })
        try:
            events.extend(self._bls_calendar())
        except Exception:
            # Copom and exchange holidays remain useful when BLS is unavailable.
            pass
        b3 = []
        us = []
        for year in range(today.year, today.year + 2):
            b3.extend((day, name) for day, name in b3_holidays(year) if day >= today)
            us.extend((day, name) for day, name in us_exchange_holidays(year) if day >= today)
        for day, name in sorted(b3)[:3]:
            events.append({
                "category": "Feriado B3", "event": name, "date": day.isoformat(), "time": None,
                "region": "Brasil", "source": "B3", "url": "https://www.b3.com.br/pt_br/noticias/calendario-de-negociacao-da-b3.htm",
            })
        for day, name in sorted(us)[:3]:
            events.append({
                "category": "Feriado EUA", "event": name, "date": day.isoformat(), "time": None,
                "region": "Estados Unidos", "source": "NYSE", "url": "https://www.nyse.com/trade/hours-calendars",
            })
        election_events = [
            {
                "category": "Eleições", "event": "Eleições gerais brasileiras • 1º turno",
                "date": "2026-10-04", "time": None, "region": "Brasil",
                "source": "Tribunal Superior Eleitoral", "url": TSE_ELECTION_CALENDAR_URL,
                "observation": "Presidente, governadores, senadores e deputados.",
            },
            {
                "category": "Eleições", "event": "Eleições gerais brasileiras • eventual 2º turno",
                "date": "2026-10-25", "time": None, "region": "Brasil",
                "source": "Tribunal Superior Eleitoral", "url": TSE_ELECTION_CALENDAR_URL,
                "observation": "Realizado onde houver segundo turno.",
            },
            {
                "category": "Eleições", "event": "Eleições federais de meio de mandato",
                "date": "2026-11-03", "time": None, "region": "Estados Unidos",
                "source": "Federal Election Commission", "url": FEC_ELECTION_CALENDAR_URL,
                "observation": "Data da eleição geral federal dos EUA.",
            },
            {
                "category": "Eleições", "event": "Eleições gerais federais dos EUA",
                "date": "2028-11-07", "time": None, "region": "Estados Unidos",
                "source": "Federal Election Commission", "url": FEC_ELECTION_CALENDAR_URL,
                "observation": "Eleição presidencial e eleições federais.",
            },
        ]
        events.extend(item for item in election_events if item["date"] >= today.isoformat())
        return sorted(self._merge_super_wednesday(events), key=lambda item: (item["date"], item["category"]))

    def build(self) -> dict:
        tasks = {
            "selic": (self.selic, {}), "curve": (self.interest_curve, {"points": []}),
            "fixed_income": (self.fixed_income, []), "quoted": (self.quoted_markets, {}),
            "crypto": (self.crypto, []), "fx": (self.fx, []), "inflation": (self.inflation, []),
            "us_rates": (self.us_rates, {}), "calendar": (self.calendar, []),
        }
        data, warnings = {}, []
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(self._safe, name, fn, default): name for name, (fn, default) in tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                value, warning = future.result()
                data[name] = value
                if warning:
                    warnings.append(warning)
        for error in (data.get("selic") or {}).get("errors") or []:
            warnings.append(error)
        for item in (data.get("inflation") or []) + (data.get("fixed_income") or []):
            if item.get("error"):
                warnings.append(f"{item.get('label')}: {item['error']}")
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "partial" if warnings else "complete", "warnings": sorted(warnings),
            **data,
        }
