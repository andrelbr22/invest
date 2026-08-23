from __future__ import annotations
from bs4 import BeautifulSoup
from .base import StockFundamentalsProvider, FiiFundamentalsProvider
from ...infrastructure.http import HttpClient
from ..normalization.numbers import parse_br_number


class FundamentusStockProvider(StockFundamentalsProvider):
    URL = "https://www.fundamentus.com.br/resultado.php"

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient()

    def fetch(self) -> list[dict]:
        response = self.http.get(self.URL)
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", id="resultado")
        if table is None:
            raise ValueError("Fundamentus stock table not found")
        rows = []
        for tr in table.find_all("tr")[1:]:
            c = tr.find_all("td")
            if len(c) < 21:
                continue
            rows.append({
                "ticker": c[0].get_text(strip=True),
                "price": parse_br_number(c[1]),
                "pe": parse_br_number(c[2]),
                "pbv": parse_br_number(c[3]),
                "dividend_yield_pct": parse_br_number(c[5]),
                "ev_ebitda": parse_br_number(c[11]),
                "ebit_margin_pct": parse_br_number(c[12]),
                "net_margin_pct": parse_br_number(c[13]),
                "current_ratio": parse_br_number(c[14]),
                "roe_pct": parse_br_number(c[16]),
                "daily_liquidity": parse_br_number(c[17]),
                "gross_debt_to_equity": parse_br_number(c[19]),
                "revenue_cagr_5y_pct": parse_br_number(c[20]),
            })
        return rows


class FundamentusFiiProvider(FiiFundamentalsProvider):
    URL = "https://www.fundamentus.com.br/fii_resultado.php"

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient()

    def fetch(self) -> list[dict]:
        response = self.http.get(self.URL)
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", id="tabelaResultado") or soup.find("table")
        if table is None:
            raise ValueError("Fundamentus FII table not found")
        rows = []
        for tr in table.find_all("tr")[1:]:
            c = tr.find_all("td")
            if len(c) < 13:
                continue
            rows.append({
                "ticker": c[0].get_text(strip=True),
                "segment": c[1].get_text(strip=True) or None,
                "price": parse_br_number(c[2]),
                "ffo_yield_pct": parse_br_number(c[3]),
                "dividend_yield_pct": parse_br_number(c[4]),
                "pbv": parse_br_number(c[5]),
                "daily_liquidity": parse_br_number(c[7]),
                "cap_rate_pct": parse_br_number(c[11]),
                "vacancy_pct": parse_br_number(c[12]),
            })
        return rows
