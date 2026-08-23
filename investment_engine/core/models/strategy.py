from pydantic import BaseModel, Field


class StockFilterSet(BaseModel):
    roe_min: float | None = None
    net_margin_min: float | None = None
    ebit_margin_min: float | None = None
    revenue_cagr_5y_min: float | None = None
    pe_min: float | None = None
    pe_max: float | None = None
    pbv_max: float | None = None
    dividend_yield_min: float | None = None
    ev_ebitda_max: float | None = None
    gross_debt_to_equity_max: float | None = None
    current_ratio_min: float | None = None
    daily_liquidity_min: float | None = None
    require_below_graham: bool = False


class FiiFilterSet(BaseModel):
    pbv_max: float | None = None
    dividend_yield_min: float | None = None
    ffo_yield_min: float | None = None
    cap_rate_min: float | None = None
    vacancy_max: float | None = None
    daily_liquidity_min: float | None = None
    require_below_dividend_target: bool = False


class StrategyWeights(BaseModel):
    quality: float = 0.25
    value: float = 0.25
    growth: float = 0.15
    technical: float = 0.10
    risk: float = 0.15
    liquidity: float = 0.10

    def normalized(self) -> "StrategyWeights":
        total = sum(self.model_dump().values())
        if total <= 0:
            raise ValueError("Strategy weights must sum to a positive value")
        return StrategyWeights(**{k: v / total for k, v in self.model_dump().items()})


class StockStrategy(BaseModel):
    id: str
    name: str
    filters: StockFilterSet
    weights: StrategyWeights = Field(default_factory=StrategyWeights)
    version: str = "1.0"


class FiiStrategy(BaseModel):
    id: str
    name: str
    filters: FiiFilterSet
    version: str = "1.0"
