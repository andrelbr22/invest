from investment_engine.core.valuation.dividend_target import implied_dividend_per_share, dividend_yield_target_price


def test_dividend_target():
    dps = implied_dividend_per_share(20, 12)
    assert round(dps, 2) == 2.40
    result = dividend_yield_target_price(dps, 6)
    assert round(result.value, 2) == 40.00
