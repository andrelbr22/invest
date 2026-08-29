from datetime import date, datetime, timedelta, timezone
from threading import Lock
from time import sleep

from investment_engine.data.providers.market_dashboard import MarketDashboardService


class _Response:
    def __init__(self, payload=None, *, content_type="application/json; charset=utf-8"):
        self.payload = payload
        self.headers = {"Content-Type": content_type}

    def json(self):
        return self.payload


class _TransientHtmlHttp:
    def __init__(self):
        self.calls = 0

    def get(self, _url, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return _Response(content_type="text/html; charset=utf-8")
        return _Response([{"data": "29/08/2026", "valor": "0.055131"}])


def test_sgs_retries_http_200_html_instead_of_caching_an_empty_series():
    http = _TransientHtmlHttp()
    service = MarketDashboardService(
        http=http,
        now=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )

    rows = service._sgs_between(12, date(2026, 8, 29), date(2026, 8, 29))

    assert rows == [(date(2026, 8, 29), 0.055131)]
    assert http.calls == 2


def test_historical_economic_series_are_queried_sequentially(monkeypatch):
    service = MarketDashboardService(now=datetime(2026, 8, 29, tzinfo=timezone.utc))
    state = {"active": 0, "maximum": 0}
    guard = Lock()

    def guarded_sgs(_series, start, _end):
        with guard:
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
        sleep(0.005)
        with guard:
            state["active"] -= 1
        return [(start + timedelta(days=30 * offset), 0.5) for offset in range(8)]

    monkeypatch.setattr(service, "_sgs_between", guarded_sgs)
    monkeypatch.setattr(
        service,
        "prices",
        type(
            "OfflinePrices",
            (),
            {
                "fetch": lambda _self, _ticker, *, start, end: [
                    {
                        "timestamp": end - timedelta(days=30 * offset),
                        "adjusted_close": 100 + offset,
                        "close": 100 + offset,
                    }
                    for offset in reversed(range(8))
                ]
            },
        )(),
    )

    payload = service.historical_comparison(years=1)

    assert state["maximum"] == 1
    assert all(item["points"] for item in payload["series"])
