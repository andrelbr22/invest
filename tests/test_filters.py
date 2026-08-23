from investment_engine.core.strategies.presets import STOCK_STRATEGIES, FII_STRATEGIES
from investment_engine.core.screening.filters import stock_passes, fii_passes


def test_missing_value_never_passes_active_threshold():
    stock = {"roe_pct": None, "ebit_margin_pct": 10, "pbv": 2, "pe": 10, "current_ratio": 2, "daily_liquidity": 2_000_000}
    assert not stock_passes(stock, STOCK_STRATEGIES["default"].filters)


def test_fii_missing_vacancy_does_not_look_like_zero():
    fii = {"pbv": .9, "dividend_yield_pct": 11, "ffo_yield_pct": 11, "cap_rate_pct": 10,
           "vacancy_pct": None, "daily_liquidity": 3_000_000, "price": 90, "dividend_target_price": 110}
    assert not fii_passes(fii, FII_STRATEGIES["alb"].filters)
