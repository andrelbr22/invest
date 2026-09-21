from investment_engine.core.strategies.presets import STOCK_STRATEGIES


def test_alb_v11_has_the_measured_selective_criteria_without_an_artificial_cap():
    strategy = STOCK_STRATEGIES["alb"]
    filters = strategy.filters

    assert strategy.version == "1.1"
    assert filters.roe_min == 15
    assert filters.net_margin_min == 8
    assert filters.pe_min == 0.1
    assert filters.pe_max == 15
    assert filters.pbv_max == 2.5
    assert filters.dividend_yield_min == 5
    assert filters.current_ratio_min == 1
    assert filters.daily_liquidity_min == 2_000_000
    assert filters.require_below_graham is True
