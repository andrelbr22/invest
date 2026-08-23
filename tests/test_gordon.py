import pytest
from investment_engine.core.valuation.gordon import gordon_growth_value, price_ceiling_with_margin


def test_gordon_growth_value():
    r=gordon_growth_value(2.0, required_return_pct=12.0, growth_pct=4.0)
    assert r.valid
    assert r.value == pytest.approx(26.0)


def test_gordon_rejects_growth_not_below_return():
    r=gordon_growth_value(2.0, required_return_pct=8.0, growth_pct=8.0)
    assert not r.valid
    assert r.value is None


def test_gordon_price_ceiling_margin():
    r=price_ceiling_with_margin(100.0,20.0)
    assert r.valid
    assert r.value == pytest.approx(80.0)


def test_gordon_rejects_invalid_margin():
    r=price_ceiling_with_margin(100.0,100.0)
    assert not r.valid
