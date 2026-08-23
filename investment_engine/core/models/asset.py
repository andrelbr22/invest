from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from .common import AssetType, DataStatus, Signal


class Asset(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    ticker: str
    name: str | None = None
    asset_type: AssetType
    exchange: str = "B3"
    currency: str = "BRL"
    sector: str | None = None
    industry: str | None = None
    segment: str | None = None
    market_cap_category: str | None = None
    is_active: bool = True
    metadata: dict = Field(default_factory=dict)


class StockFundamentals(BaseModel):
    price: float | None = None
    pe: float | None = None
    pbv: float | None = None
    dividend_yield_pct: float | None = None
    ev_ebitda: float | None = None
    ebit_margin_pct: float | None = None
    net_margin_pct: float | None = None
    current_ratio: float | None = None
    roe_pct: float | None = None
    roic_pct: float | None = None
    gross_debt_to_equity: float | None = None
    net_debt_to_ebitda: float | None = None
    revenue_cagr_5y_pct: float | None = None
    earnings_cagr_5y_pct: float | None = None


class FiiFundamentals(BaseModel):
    price: float | None = None
    pbv: float | None = None
    dividend_yield_pct: float | None = None
    ffo_yield_pct: float | None = None
    cap_rate_pct: float | None = None
    vacancy_pct: float | None = None
    financial_vacancy_pct: float | None = None
    ltv_pct: float | None = None
    wale_years: float | None = None
    daily_liquidity: float | None = None


class FundamentalSnapshot(BaseModel):
    ticker: str
    asset_type: AssetType
    source: str
    reference_date: datetime
    retrieved_at: datetime
    status: DataStatus = DataStatus.VALID
    quality_score: float | None = None
    data: StockFundamentals | FiiFundamentals
    raw_payload: dict = Field(default_factory=dict)


class TechnicalSnapshot(BaseModel):
    ticker: str | None = None
    source: str = "tradingview"
    timeframe: str = "1D"
    score_tv: float | None = None
    signal_tv: Signal = Signal.NO_DATA
    market_cap: float | None = None
    daily_liquidity: float | None = None
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    sma20_1w: float | None = None
    sma50_1w: float | None = None
    sma20_1m: float | None = None
    sma50_1m: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    rsi14: float | None = None
    bb_lower: float | None = None
    bb_upper: float | None = None
    as_of: datetime | None = None
    retrieved_at: datetime | None = None
    status: DataStatus = DataStatus.VALID
    raw_payload: dict = Field(default_factory=dict)


class AssetSnapshot(BaseModel):
    asset: Asset
    fundamentals: FundamentalSnapshot | None = None
    technical: TechnicalSnapshot | None = None
