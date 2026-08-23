import base64
import json

import pytest

from investment_engine.data.providers.b3_indices import B3IndexProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.url = None

    def get(self, url):
        self.url = url
        return FakeResponse(self.payload)


def test_b3_ibov_provider_builds_official_request_and_normalizes_members():
    http = FakeHttp({
        "header": {"date": "05/08/26"},
        "results": [
            {"cod": "PETR4", "asset": "PETROBRAS", "type": "PN N2", "part": "7,500"},
            {"cod": "VALE3", "asset": "VALE", "type": "ON NM", "part": "12,000"},
        ],
    })
    result = B3IndexProvider(http).fetch("ibov")
    encoded = http.url.rsplit("/", 1)[-1]
    request = json.loads(base64.b64decode(encoded))
    assert request["index"] == "IBOV"
    assert request["pageSize"] == 200
    assert [row["ticker"] for row in result["members"]] == ["PETR4", "VALE3"]
    assert result["as_of"] == "05/08/26"


def test_b3_provider_rejects_unsupported_or_empty_portfolios():
    with pytest.raises(ValueError, match="unsupported_b3_index"):
        B3IndexProvider(FakeHttp({})).fetch("IDIV")
    with pytest.raises(ValueError, match="b3_index_portfolio_empty"):
        B3IndexProvider(FakeHttp({"results": []})).fetch("IBOV")
