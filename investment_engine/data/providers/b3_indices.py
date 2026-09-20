from __future__ import annotations

import base64
import json

from ...infrastructure.http import HttpClient


class B3IndexProvider:
    """Read the current theoretical portfolio from B3's public index portal."""

    BASE_URL = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/"

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient(timeout=20.0)

    @staticmethod
    def _payload(index_code: str) -> str:
        params = {
            "language": "pt-br",
            "pageNumber": 1,
            "pageSize": 200,
            "index": index_code.upper(),
            "segment": "1",
        }
        raw = json.dumps(params, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    @staticmethod
    def _first(row: dict, *keys):
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return value
        return None

    def fetch(self, index_code: str = "IBOV") -> dict:
        code = str(index_code or "").strip().upper()
        if code != "IBOV":
            raise ValueError("unsupported_b3_index")
        response = self.http.get(self.BASE_URL + self._payload(code))
        data = response.json()
        rows = data.get("results") or data.get("result") or []
        members = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = self._first(row, "cod", "code", "ticker", "symbol")
            if not ticker:
                continue
            members.append({
                "ticker": str(ticker).strip().upper(),
                "name": self._first(row, "asset", "name", "company"),
                "type": self._first(row, "type", "assetType", "specification"),
                "weight_pct": self._first(row, "part", "weight", "participation"),
            })
        if not members:
            raise ValueError("b3_index_portfolio_empty")
        header = data.get("header") if isinstance(data.get("header"), dict) else {}
        return {
            "index": code,
            "name": "Ibovespa",
            "as_of": self._first(header, "date", "refDate", "referenceDate") or data.get("date"),
            "source": "B3",
            "source_url": f"https://sistemaswebb3-listados.b3.com.br/indexPage/day/{code}?language=pt-br",
            "members": members,
        }
