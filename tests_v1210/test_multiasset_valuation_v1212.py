from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from investment_engine.core.screening.advanced import advanced_screen
from investment_engine.core.valuation import (
    bdr_pbv_relative,
    bdr_underlying_parity,
    etf_nav_reference,
    etf_relative_nav_premium,
    future_cost_of_carry,
)
from investment_engine.data.providers.tradingview import TV_COLUMNS, TradingViewScannerProvider
from investment_engine.data.ingestion.pipeline import MarketIngestionPipeline


def test_etf_nav_and_peer_premium_use_reported_provider_inputs():
    target = {
        "ticker": "BOVA11", "asset_type": "etf", "price": 102,
        "nav_discount_premium_pct": 2, "fundamental_currency_code": "BRL",
    }
    nav = etf_nav_reference(target)
    assert nav.status == "valid"
    assert nav.scenarios["base"].value == pytest.approx(100)
    assert nav.scenarios["base"].upside_pct == pytest.approx(-1.960784, rel=1e-5)

    peers = [
        {"ticker": f"ETF{i}11", "asset_type": "etf", "fundamental_currency_code": "BRL", "nav_discount_premium_pct": premium}
        for i, premium in enumerate((-4, -2, 0, 2, 4, 6), start=1)
    ]
    relative = etf_relative_nav_premium(target, peers, min_peers=5)
    assert relative.status == "valid"
    assert relative.quality.sample_size == 6
    assert relative.scenarios["conservative"].value < relative.scenarios["base"].value < relative.scenarios["optimistic"].value


def test_bdr_uses_pbv_only_inside_a_comparable_group_and_parity_fails_closed():
    target = {
        "ticker": "TEST34", "asset_type": "bdr", "price": 50,
        "pbv": 2, "sector": "Technology", "industry": "Software",
    }
    peers = [
        {"ticker": f"BDR{i}34", "asset_type": "bdr", "pbv": multiple, "sector": "Technology", "industry": "Software"}
        for i, multiple in enumerate((2.2, 2.6, 3.0, 3.4, 3.8), start=1)
    ] + [{"ticker": "BANK34", "asset_type": "bdr", "pbv": 8, "sector": "Finance", "industry": "Banks"}]
    result = bdr_pbv_relative(target, peers, min_peers=5)
    assert result.status == "valid"
    assert result.scenarios["base"].value == pytest.approx(75)
    assert result.quality.sample_size == 5

    parity = bdr_underlying_parity(target)
    assert parity.status == "insufficient_data"
    assert parity.reason == "bdr_underlying_price_fx_and_ratio_required"


def test_future_cost_of_carry_requires_observable_spot_rate_and_expiry():
    result = future_cost_of_carry({
        "price": 109,
        "front_contract_price": 109,
        "underlying_spot_price": 100,
        "carry_rate_pct": 10,
        "underlying_income_yield_pct": 0,
        "days_to_expiry": 365,
        "front_contract": "TESTZ2027",
    })
    assert result.status == "valid"
    assert result.scenarios["base"].value == pytest.approx(110)
    missing = future_cost_of_carry({"price": 109, "days_to_expiry": 30})
    assert missing.status == "insufficient_data"
    assert missing.reason == "future_spot_carry_and_expiry_required"


def test_future_carry_interpolates_the_di_curve_for_the_contract_term():
    points = [
        {"business_days": 21, "di_rate": 10},
        {"business_days": 63, "di_rate": 12},
    ]
    # 60.833 calendar days correspond to 42 business days, halfway between
    # the two official curve vertices.
    rate = MarketIngestionPipeline._carry_rate_for_days(points, 60.8333333333)
    assert rate == pytest.approx(11)


def _scanner_item(**fields):
    values = {column: None for column in TV_COLUMNS}
    values.update(fields)
    return {"d": [values[column] for column in TV_COLUMNS]}


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class _FuturesHttp:
    def __init__(self):
        self.calls = []

    def post(self, url, json):
        self.calls.append((url, json))
        continuous = any(item.get("left") == "typespecs" for item in json["filter"])
        if continuous:
            return _Response({"data": [_scanner_item(
                name="PETRP1!", description="PETR4 Futures", exchange="BMFBOVESPA",
                type="futures", typespecs=["continuous"], currency="BRL", close=47,
                root="PETRP", **{"Recommend.All": 0.4},
            )]})
        return _Response({"data": [
            _scanner_item(name="PETPU2026", exchange="BMFBOVESPA", type="futures", close=46, root="PETRP", expiration=20260901),
            _scanner_item(name="PETPV2026", exchange="BMFBOVESPA", type="futures", close=48, root="PETRP", expiration=20260918, open_interest=1234),
            _scanner_item(name="PETPX2026", exchange="BMFBOVESPA", type="futures", close=49, root="PETRP", expiration=20261016),
        ]})


def test_futures_scanner_uses_correct_endpoint_and_nearest_live_contract():
    http = _FuturesHttp()
    provider = TradingViewScannerProvider(http, today=lambda: date(2026, 9, 6))
    rows = provider.fetch("futures")
    assert len(rows) == 1
    assert all(url == provider.FUTURES_URL for url, _payload in http.calls)
    assert rows[0]["ticker"] == "PETRP1!"
    assert rows[0]["underlying_ticker"] == "PETR4"
    assert rows[0]["front_contract"] == "PETPV2026"
    assert rows[0]["expiration_date"] == "2026-09-18"
    assert rows[0]["days_to_expiry"] == 12


def _asset(ticker, asset_type, *, sector=None, industry=None):
    return SimpleNamespace(
        id=uuid4(), ticker=ticker, name=ticker, asset_type=asset_type,
        sector=sector, industry=industry, segment="ETF" if asset_type == "etf" else None,
        market_cap_category=None, metadata_json={}, currency="BRL",
    )


def _tech(close, **raw):
    return SimpleNamespace(close=close, raw_payload={"close": close, "valuation_source": "test", **raw})


def test_advanced_screen_exposes_real_etf_values_instead_of_global_nd():
    universe = []
    premiums = (-4, -2, 0, 2, 4, 6)
    for index, premium in enumerate(premiums):
        asset = _asset(f"ETF{index}11", "etf")
        universe.append((asset, None, _tech(100 + index, nav_discount_premium_pct=premium, fundamental_currency_code="BRL"), None))

    class Repository:
        def latest_universe(self, *, asset_type, limit):
            assert asset_type == "etf"
            return universe

        def price_histories_batch(self, _ids):
            raise AssertionError("history is unnecessary when technical columns are disabled")

    result = advanced_screen(Repository(), asset_type="etf", include_technical_columns=False, limit=10)
    assert len(result["rows"]) == 6
    assert all(row["valuation_methods"]["economic_value"]["status"] == "valid" for row in result["rows"])
    assert all(row["valuation_methods"]["relative_peers"]["status"] == "valid" for row in result["rows"])


def test_browser_enables_only_class_appropriate_multiasset_methods():
    source = (__import__("pathlib").Path(__file__).resolve().parents[1] / "investment_engine" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'data-valuation-types="stock,fii,etf,bdr"' in source
    assert 'data-valuation-types="stock,etf,bdr,future"' in source
    assert 'request.asset_type!=="stock"' in source
    assert "Referência patrimonial do ETF (NAV)" in source
    assert "Preço teórico por custo de carregamento" in source
