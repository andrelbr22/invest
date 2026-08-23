from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AssetORM(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(24), nullable=False, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(32), default="B3", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="BRL", nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128), index=True)
    industry: Mapped[str | None] = mapped_column(String(128))
    segment: Mapped[str | None] = mapped_column(String(128), index=True)
    market_cap_category: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    fundamentals: Mapped[list["FundamentalSnapshotORM"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    technicals: Mapped[list["TechnicalSnapshotORM"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    prices: Mapped[list["PriceBarORM"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    valuations: Mapped[list["ValuationSnapshotORM"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    scores: Mapped[list["ScoreSnapshotORM"]] = relationship(back_populates="asset", cascade="all, delete-orphan")


class FundamentalSnapshotORM(Base):
    __tablename__ = "fundamental_snapshots"
    __table_args__ = (
        UniqueConstraint("asset_id", "reference_date", "source", name="uq_fundamental_asset_ref_source"),
        Index("ix_fundamental_asset_retrieved", "asset_id", "retrieved_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    reference_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="valid", nullable=False)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    pe: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    pbv: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    dividend_yield_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    ev_ebitda: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    ebit_margin_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    net_margin_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    current_ratio: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    roe_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    roic_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    gross_debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    net_debt_to_ebitda: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    revenue_cagr_5y_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    earnings_cagr_5y_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))

    ffo_yield_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    cap_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    vacancy_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    financial_vacancy_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    ltv_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    wale_years: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    daily_liquidity: Mapped[Decimal | None] = mapped_column(Numeric(22, 2))

    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    asset: Mapped[AssetORM] = relationship(back_populates="fundamentals")


class TechnicalSnapshotORM(Base):
    __tablename__ = "technical_snapshots"
    __table_args__ = (
        UniqueConstraint("asset_id", "timeframe", "as_of", "source", name="uq_technical_asset_tf_asof_source"),
        Index("ix_technical_asset_asof", "asset_id", "as_of"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), default="1D", nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="valid", nullable=False)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    score_tv: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    signal_tv: Mapped[str | None] = mapped_column(String(24))
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    daily_liquidity: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    sma20: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    sma50: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    sma200: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    sma20_1w: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    sma50_1w: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    sma20_1m: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    sma50_1m: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    close: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    rsi14: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    bb_lower: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    bb_upper: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    bb_middle: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    macd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    atr14: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    volatility_annual_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    max_drawdown_1y_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    return_1m_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    return_3m_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    return_12m_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    asset: Mapped[AssetORM] = relationship(back_populates="technicals")


class PriceBarORM(Base):
    __tablename__ = "price_bars"
    __table_args__ = (
        UniqueConstraint("asset_id", "timeframe", "timestamp", "source", name="uq_price_asset_tf_ts_source"),
        Index("ix_price_asset_timestamp", "asset_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), default="1D", nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    close: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="valid", nullable=False)
    asset: Mapped[AssetORM] = relationship(back_populates="prices")


class IngestionRunORM(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    pipeline: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="running", nullable=False)
    rows_received: Mapped[int] = mapped_column(default=0, nullable=False)
    rows_valid: Mapped[int] = mapped_column(default=0, nullable=False)
    rows_rejected: Mapped[int] = mapped_column(default=0, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ValuationSnapshotORM(Base):
    __tablename__="valuation_snapshots"
    __table_args__=(UniqueConstraint("asset_id","method","as_of","method_version",name="uq_valuation_asset_method_asof_version"),)
    id: Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("assets.id",ondelete="CASCADE"),nullable=False,index=True)
    method: Mapped[str]=mapped_column(String(48),nullable=False)
    method_version: Mapped[str]=mapped_column(String(24),nullable=False,default="1.0")
    as_of: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    calculated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
    value: Mapped[Decimal|None]=mapped_column(Numeric(18,6))
    upside_pct: Mapped[Decimal|None]=mapped_column(Numeric(18,6))
    status: Mapped[str]=mapped_column(String(24),default="valid",nullable=False)
    inputs_json: Mapped[dict]=mapped_column(JSON,default=dict,nullable=False)
    asset: Mapped[AssetORM]=relationship(back_populates="valuations")

class ScoreSnapshotORM(Base):
    __tablename__="score_snapshots"
    __table_args__=(UniqueConstraint("asset_id","as_of","model_version",name="uq_score_asset_asof_version"),)
    id: Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("assets.id",ondelete="CASCADE"),nullable=False,index=True)
    as_of: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    calculated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
    model_version: Mapped[str]=mapped_column(String(24),nullable=False,default="1.0")
    quality_score: Mapped[Decimal|None]=mapped_column(Numeric(5,2))
    value_score: Mapped[Decimal|None]=mapped_column(Numeric(5,2))
    growth_score: Mapped[Decimal|None]=mapped_column(Numeric(5,2))
    technical_score: Mapped[Decimal|None]=mapped_column(Numeric(5,2))
    risk_score: Mapped[Decimal|None]=mapped_column(Numeric(5,2))
    liquidity_score: Mapped[Decimal|None]=mapped_column(Numeric(5,2))
    alb_score: Mapped[Decimal|None]=mapped_column(Numeric(5,2))
    coverage_pct: Mapped[Decimal|None]=mapped_column(Numeric(5,2))
    data_quality_score: Mapped[Decimal|None]=mapped_column(Numeric(5,2))
    details_json: Mapped[dict]=mapped_column(JSON,default=dict,nullable=False)
    asset: Mapped[AssetORM]=relationship(back_populates="scores")


class UserAccessPolicyORM(Base):
    """Authorization policy for a Google account.

    Authentication remains with Google/Streamlit.  This table only controls
    what an authenticated account may see or change inside the application.
    """
    __tablename__ = "user_access_policies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(180))
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="visitor")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    can_view_market: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_use_advanced_filters: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_view_portfolio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_write_portfolio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_view_backtests: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_run_backtests: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_sync_market: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_manage_users: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PortfolioORM(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    base_currency: Mapped[str] = mapped_column(String(8), default="BRL", nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(22, 2), default=0, nullable=False)
    target_cash_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    positions: Mapped[list["PortfolioPositionORM"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")


class PortfolioPositionORM(Base):
    __tablename__ = "portfolio_positions"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "asset_id", name="uq_portfolio_asset"),
        Index("ix_portfolio_positions_portfolio", "portfolio_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[str] = mapped_column(String(24), default="position", nullable=False)  # position | target | analysis
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=0, nullable=False)
    average_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    target_weight_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0, nullable=False)
    classification_override: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    portfolio: Mapped[PortfolioORM] = relationship(back_populates="positions")
    asset: Mapped[AssetORM] = relationship()


class BacktestRunORM(Base):
    __tablename__ = "backtest_runs"
    __table_args__ = (Index("ix_backtest_runs_asset_created", "asset_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    strategy_name: Mapped[str] = mapped_column(String(160), nullable=False)
    requested_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(22, 2), nullable=False)
    fee_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0, nullable=False)
    slippage_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0, nullable=False)
    risk_free_rate_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0, nullable=False)
    parameters_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    equity_curve_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    data_source: Mapped[str] = mapped_column(String(64), default="yahoo", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="valid", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    asset: Mapped[AssetORM] = relationship()
    trades: Mapped[list["BacktestTradeORM"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class BacktestTradeORM(Base):
    __tablename__ = "backtest_trades"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_backtest_run_sequence"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    exit_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    return_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    pnl_value: Mapped[Decimal | None] = mapped_column(Numeric(22, 2))
    holding_days: Mapped[int | None] = mapped_column(Integer)
    exit_reason: Mapped[str | None] = mapped_column(String(64))

    run: Mapped[BacktestRunORM] = relationship(back_populates="trades")
