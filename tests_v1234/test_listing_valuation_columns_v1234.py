from types import SimpleNamespace
from uuid import uuid4

import pytest

from investment_engine.api.app import (
    _enrich_listing_valuations,
    _stock_screen_row,
)


def _asset(ticker: str):
    return SimpleNamespace(
        id=uuid4(),
        ticker=ticker,
        name=f"Companhia {ticker}",
        asset_type="stock",
        exchange="B3",
        currency="BRL",
        sector="Consumo",
        industry="Bens de consumo",
        segment="Consumo",
        market_cap_category="large_cap",
        metadata_json={},
    )


def _fundamental(*, price: float, pe: float, pbv: float, dy: float):
    return SimpleNamespace(
        price=price,
        pe=pe,
        pbv=pbv,
        dividend_yield_pct=dy,
        roe_pct=18,
        raw_payload={},
    )


class _Repository:
    def __init__(self, universe):
        self.universe = universe

    def latest_universe(self, *, asset_type: str, limit: int):
        assert asset_type == "stock"
        return self.universe[:limit]


def _valuation_access():
    return {
        "can_use_graham_valuation": True,
        "can_use_dividend_ceiling": True,
        "can_use_relative_valuation": True,
        "can_use_economic_valuation": True,
    }


def test_fast_stock_row_exposes_canonical_dividend_ceiling_fields():
    row = _stock_screen_row(
        _asset("TEST3"),
        _fundamental(price=20, pe=10, pbv=1.5, dy=8),
        None,
    )

    assert row["dividend_yield_ceiling_value"] == pytest.approx(26.6666667)
    assert row["dividend_yield_ceiling_upside_pct"] == pytest.approx(33.3333333)
    assert row["dividend_yield_ceiling_status"] == "valid"
    assert row["barsi_ceiling_price"] == row["dividend_yield_ceiling_value"]


def test_system_listing_gets_relative_value_from_full_local_peer_universe():
    assets = [_asset(f"TST{number}3") for number in range(6)]
    universe = [
        (
            asset,
            _fundamental(
                price=20 + index,
                pe=8 + index,
                pbv=1.0 + index / 10,
                dy=6 + index / 2,
            ),
            None,
            None,
        )
        for index, asset in enumerate(assets)
    ]
    repository = _Repository(universe)
    base = [_stock_screen_row(universe[0][0], universe[0][1], None)]

    enriched = _enrich_listing_valuations(
        repository,
        base,
        asset_type="stock",
        access=_valuation_access(),
    )

    assert [row["ticker"] for row in enriched] == [assets[0].ticker]
    row = enriched[0]
    assert row["dividend_yield_ceiling_status"] == "valid"
    assert row["relative_peers_status"] == "valid"
    assert row["relative_peers_value"] is not None
    assert row["valuation_methods"]["relative_peers"]["quality"]["sample_size"] == 5


def test_listing_enrichment_keeps_valuation_permissions_fail_closed():
    assets = [_asset(f"SEC{number}3") for number in range(6)]
    universe = [
        (asset, _fundamental(price=30, pe=10 + index, pbv=1.2, dy=7), None, None)
        for index, asset in enumerate(assets)
    ]
    repository = _Repository(universe)
    base = [_stock_screen_row(universe[0][0], universe[0][1], None)]

    row = _enrich_listing_valuations(
        repository,
        base,
        asset_type="stock",
        access={},
    )[0]

    assert "dividend_yield_ceiling_value" not in row
    assert "relative_peers_value" not in row
    assert row.get("valuation_methods") == {}
