from ..models.strategy import (
    StockStrategy, FiiStrategy, StockFilterSet, FiiFilterSet, StrategyWeights
)

STOCK_STRATEGIES = {
    "default": StockStrategy(
        id="default", name="Padrão",
        filters=StockFilterSet(roe_min=8, ebit_margin_min=5, pbv_max=5, pe_min=0.1, pe_max=20,
                               current_ratio_min=1, daily_liquidity_min=1_000_000),
    ),
    "cnpi": StockStrategy(
        id="cnpi", name="FDI - CNPI",
        filters=StockFilterSet(roe_min=10, net_margin_min=5, pe_min=0.1, pe_max=20, pbv_max=3,
                               dividend_yield_min=4, current_ratio_min=1, daily_liquidity_min=1_000_000),
    ),
    "alb": StockStrategy(
        id="alb", name="ALB",
        # Mantém o viés de qualidade, valor e dividendos sem exigir CAGR,
        # campo que costuma faltar em parte relevante do universo brasileiro.
        filters=StockFilterSet(roe_min=10, net_margin_min=5, pe_min=0.1, pe_max=18, pbv_max=3,
                               dividend_yield_min=4, current_ratio_min=1,
                               daily_liquidity_min=1_000_000, require_below_graham=True),
        weights=StrategyWeights(quality=.25, value=.25, growth=.15, technical=.10, risk=.15, liquidity=.10),
    ),
}

FII_STRATEGIES = {
    "default": FiiStrategy(
        id="default", name="FII Padrão",
        filters=FiiFilterSet(pbv_max=1.10, dividend_yield_min=8, ffo_yield_min=7,
                             vacancy_max=15, daily_liquidity_min=500_000),
    ),
    "cnpi": FiiStrategy(
        id="cnpi", name="FII FDI - CNPI",
        filters=FiiFilterSet(pbv_max=1.05, dividend_yield_min=9, ffo_yield_min=9, cap_rate_min=8,
                             vacancy_max=10, daily_liquidity_min=1_000_000),
    ),
    "alb": FiiStrategy(
        id="alb", name="FII ALB",
        filters=FiiFilterSet(pbv_max=.95, dividend_yield_min=10, ffo_yield_min=10, cap_rate_min=9,
                             vacancy_max=5, daily_liquidity_min=2_000_000, require_below_dividend_target=True),
    ),
}
