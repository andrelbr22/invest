from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID
from typing import Literal
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.valuation.graham import graham_number, add_upside
from ..core.valuation.dividend_target import dividend_yield_target_price
from ..core.strategies.presets import STOCK_STRATEGIES, FII_STRATEGIES
from ..core.screening.filters import stock_passes, fii_passes
from ..core.screening.advanced import advanced_screen
from ..core.repositories.assets import AssetRepository
from ..core.repositories.portfolio import PortfolioRepository
from ..core.repositories.backtests import BacktestRepository
from ..core.portfolio.service import build_portfolio_snapshot
from ..core.backtesting.service import BacktestService, PERIOD_LABELS
from ..core.backtesting.strategies import STRATEGIES, strategy_catalog
from ..infrastructure.db.models import AssetORM
from ..infrastructure.db.session import get_session_factory
from ..core.services_v14 import calculate_asset_intelligence
from ..data.ingestion.prices import PriceIngestionService
from ..infrastructure.config import settings

app = FastAPI(
    title="Investment Engine V1.6.0",
    version="0.7.0",
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/portfolios") else "no-cache"
    return response


def get_db():
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def _num(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _fundamental_dict(row):
    if row is None:
        return None
    fields = [
        "reference_date", "retrieved_at", "source", "status", "quality_score", "price", "pe", "pbv",
        "dividend_yield_pct", "ev_ebitda", "ebit_margin_pct", "net_margin_pct", "current_ratio", "roe_pct",
        "roic_pct", "gross_debt_to_equity", "net_debt_to_ebitda", "revenue_cagr_5y_pct", "earnings_cagr_5y_pct",
        "ffo_yield_pct", "cap_rate_pct", "vacancy_pct", "financial_vacancy_pct", "ltv_pct", "wale_years",
        "daily_liquidity",
    ]
    return {f: _num(getattr(row, f)) for f in fields}


def _technical_dict(row):
    if row is None:
        return None
    fields = [
        "timeframe", "as_of", "retrieved_at", "source", "status", "quality_score", "score_tv", "signal_tv", "market_cap",
        "daily_liquidity", "sma20", "sma50", "sma200", "sma20_1w", "sma50_1w", "sma20_1m", "sma50_1m",
        "high", "low", "close", "rsi14", "bb_lower", "bb_upper", "bb_middle", "macd", "atr14",
        "volatility_annual_pct", "max_drawdown_1y_pct", "return_1m_pct", "return_3m_pct", "return_12m_pct",
    ]
    return {f: _num(getattr(row, f)) for f in fields}


class GrahamRequest(BaseModel):
    eps: float | None = None
    bvps: float | None = None
    market_price: float | None = None


class DividendTargetRequest(BaseModel):
    dividend_per_share: float | None = None
    target_yield_pct: float = 6.0
    market_price: float | None = None


class ScreenRequest(BaseModel):
    strategy_id: str
    assets: list[dict]


class PortfolioCreateRequest(BaseModel):
    name: str = "Carteira Principal"
    base_currency: str = "BRL"
    cash_balance: float = Field(default=0.0, ge=0)
    target_cash_pct: float = Field(default=0.0, ge=0, le=100)
    notes: str | None = None


class PortfolioUpdateRequest(BaseModel):
    name: str | None = None
    cash_balance: float | None = Field(default=None, ge=0)
    target_cash_pct: float | None = Field(default=None, ge=0, le=100)
    notes: str | None = None


class PortfolioPositionRequest(BaseModel):
    asset_type: str = Field(default="stock", pattern="^(stock|fii|etf|bdr|fixed_income|crypto|other)$")
    stage: str = Field(default="position", pattern="^(position|target|analysis)$")
    quantity: float = Field(default=0.0, ge=0)
    average_price: float | None = Field(default=None, ge=0)
    target_weight_pct: float = Field(default=0.0, ge=0, le=100)
    classification_override: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class BacktestNumericRangeRequest(BaseModel):
    min: float | None = None
    max: float | None = None


class BacktestTrendFilterRequest(BaseModel):
    enabled: bool = False
    direction: str = Field(default="up", pattern="^(up|down)$")
    period: Literal[21, 50] = 21
    mode: str = Field(default="price_above", pattern="^(price_above|sma_rising|price_above_or_sma_rising|price_above_and_sma_rising)$")
    slope_lookback: int = Field(default=5, ge=1, le=100)


class BacktestFiltersRequest(BaseModel):
    daily_trend: BacktestTrendFilterRequest = Field(default_factory=BacktestTrendFilterRequest)
    weekly_trend: BacktestTrendFilterRequest = Field(default_factory=BacktestTrendFilterRequest)
    monthly_trend: BacktestTrendFilterRequest = Field(default_factory=BacktestTrendFilterRequest)
    trend_combination: str = Field(default="all", pattern="^(all|any|majority)$")
    adx_min: float | None = Field(default=None, ge=0, le=100)
    volume_ratio_min: float | None = Field(default=None, ge=0.1, le=10)
    rsi_min: float | None = Field(default=None, ge=0, le=100)
    rsi_max: float | None = Field(default=None, ge=0, le=100)
    atr_pct_min: float | None = Field(default=None, ge=0, le=100)
    atr_pct_max: float | None = Field(default=None, ge=0, le=100)
    exit_on_filter_failure: bool = False
    fundamental_entry: dict[str, BacktestNumericRangeRequest] = Field(default_factory=dict)
    fundamental_exit: dict[str, BacktestNumericRangeRequest] = Field(default_factory=dict)
    fundamental_exit_logic: str = Field(default="any", pattern="^(any|all)$")
    fundamental_min_coverage_pct: float = Field(default=70.0, ge=1, le=100)
    fundamental_max_age_days: int = Field(default=45, ge=1, le=365)


class BacktestRequest(BaseModel):
    ticker: str
    asset_type: str = Field(default="stock", pattern="^(stock|fii|etf|bdr|other)$")
    strategy_id: str
    period: str = Field(default="1y", pattern="^(6m|1y|2y|3y|5y|10y|15y|20y|custom)$")
    start: datetime | None = None
    end: datetime | None = None
    initial_capital: float = Field(default=10000.0, gt=0)
    fee_pct: float = Field(default=0.03, ge=0, le=5)
    slippage_pct: float = Field(default=0.05, ge=0, le=5)
    risk_free_rate_pct: float = Field(default=0.0, ge=-20, le=100)
    apply_cash_yield: bool = False
    cash_yield_rate_pct: float = Field(default=0.0, gt=-100, le=100)
    params: dict = Field(default_factory=dict)
    filters: BacktestFiltersRequest = Field(default_factory=BacktestFiltersRequest)
    persist: bool = True


class BacktestCompareRequest(BaseModel):
    ticker: str
    asset_type: str = Field(default="stock", pattern="^(stock|fii|etf|bdr|other)$")
    strategy_ids: list[str] = Field(min_length=1, max_length=20)
    period: str = Field(default="1y", pattern="^(6m|1y|2y|3y|5y|10y|15y|20y|custom)$")
    start: datetime | None = None
    end: datetime | None = None
    initial_capital: float = Field(default=10000.0, gt=0)
    fee_pct: float = Field(default=0.03, ge=0, le=5)
    slippage_pct: float = Field(default=0.05, ge=0, le=5)
    risk_free_rate_pct: float = Field(default=0.0, ge=-20, le=100)
    apply_cash_yield: bool = False
    cash_yield_rate_pct: float = Field(default=0.0, gt=-100, le=100)
    filters: BacktestFiltersRequest = Field(default_factory=BacktestFiltersRequest)


class BacktestBasketRequest(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=30)
    asset_type: str = Field(default="stock", pattern="^(stock|fii|etf|bdr|other)$")
    strategy_id: str
    period: str = Field(default="5y", pattern="^(6m|1y|2y|3y|5y|10y|15y|20y|custom)$")
    start: datetime | None = None
    end: datetime | None = None
    initial_capital: float = Field(default=100000.0, gt=0)
    fee_pct: float = Field(default=0.03, ge=0, le=5)
    slippage_pct: float = Field(default=0.05, ge=0, le=5)
    risk_free_rate_pct: float = Field(default=0.0, ge=-20, le=100)
    apply_cash_yield: bool = False
    cash_yield_rate_pct: float = Field(default=0.0, gt=-100, le=100)
    params: dict = Field(default_factory=dict)
    filters: BacktestFiltersRequest = Field(default_factory=BacktestFiltersRequest)


class NumericRangeRequest(BaseModel):
    min: float | None = None
    max: float | None = None


class AdvancedTechnicalFiltersRequest(BaseModel):
    daily_trend: str = Field(default="any", pattern="^(any|up|down)$")
    weekly_trend: str = Field(default="any", pattern="^(any|up|down)$")
    monthly_trend: str = Field(default="any", pattern="^(any|up|down)$")
    rsi14: NumericRangeRequest | None = None
    pivot_zone: str = Field(default="any", pattern="^(any|below_s3|s3_s2|s2_s1|s1_pp|pp_r1|r1_r2|r2_r3|above_r3)$")
    near_pivot_level: str = Field(default="none", pattern="^(none|s3|s2|s1|pp|r1|r2|r3)$")
    pivot_tolerance_pct: float = Field(default=0.5, ge=0, le=20)


class AdvancedScreenRequest(BaseModel):
    asset_type: str = Field(default="stock", pattern="^(stock|fii)$")
    fundamental_filters: dict[str, NumericRangeRequest] = Field(default_factory=dict)
    score_filters: dict[str, NumericRangeRequest] = Field(default_factory=dict)
    valuation_flags: dict[str, bool] = Field(default_factory=dict)
    technical_filters: AdvancedTechnicalFiltersRequest = Field(default_factory=AdvancedTechnicalFiltersRequest)
    trend_period: int = Field(default=21, ge=20, le=21)
    pivot_timeframe: str = Field(default="daily", pattern="^(daily|weekly|monthly)$")
    include_technical_columns: bool = True
    limit: int = Field(default=100, ge=1, le=300)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.7.0", "environment": settings.app_environment}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception as exc:
        raise HTTPException(503, detail={"database": "unreachable", "error": str(exc)})


@app.get("/debug/db-counts")
def debug_db_counts(db: Session = Depends(get_db)):
    names = ["assets", "fundamental_snapshots", "technical_snapshots", "score_snapshots", "valuation_snapshots", "price_bars", "portfolios", "portfolio_positions", "backtest_runs", "backtest_trades"]
    counts = {}
    for name in names:
        counts[name] = db.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one()
    return counts


@app.get("/assets")
def assets(
    asset_type: str | None = Query(default=None, pattern="^(stock|fii|etf|bdr|fixed_income|crypto|other)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    repo = AssetRepository(db)
    rows = repo.list_assets(asset_type=asset_type, limit=limit, offset=offset)
    return [
        {
            "id": str(a.id), "ticker": a.ticker, "name": a.name, "asset_type": a.asset_type,
            "exchange": a.exchange, "currency": a.currency, "sector": a.sector, "industry": a.industry,
            "segment": a.segment, "market_cap_category": a.market_cap_category, "is_active": a.is_active,
        }
        for a in rows
    ]


@app.get("/assets/{ticker}")
def asset_detail(ticker: str, db: Session = Depends(get_db)):
    repo = AssetRepository(db)
    asset = repo.get_by_ticker(ticker.upper())
    if asset is None:
        raise HTTPException(404, "asset_not_found")
    fundamentals = repo.latest_fundamentals(asset.id)
    technical = repo.latest_technical(asset.id)
    return {
        "asset": {
            "id": str(asset.id), "ticker": asset.ticker, "name": asset.name, "asset_type": asset.asset_type,
            "exchange": asset.exchange, "currency": asset.currency, "sector": asset.sector, "industry": asset.industry,
            "segment": asset.segment, "market_cap_category": asset.market_cap_category, "is_active": asset.is_active,
            "metadata": asset.metadata_json,
        },
        "fundamentals": _fundamental_dict(fundamentals),
        "technical": _technical_dict(technical),
    }


@app.get("/strategies/stocks")
def stock_strategies():
    return [s.model_dump() for s in STOCK_STRATEGIES.values()]


@app.get("/strategies/fiis")
def fii_strategies():
    return [s.model_dump() for s in FII_STRATEGIES.values()]


@app.post("/valuation/graham")
def valuation_graham(req: GrahamRequest):
    return add_upside(graham_number(req.eps, req.bvps), req.market_price)


@app.post("/valuation/dividend-target")
def valuation_dividend_target(req: DividendTargetRequest):
    result = dividend_yield_target_price(req.dividend_per_share, req.target_yield_pct)
    return add_upside(result, req.market_price)


@app.post("/screen/stocks")
def screen_stocks(req: ScreenRequest):
    strategy = STOCK_STRATEGIES.get(req.strategy_id)
    if not strategy:
        raise HTTPException(404, "strategy_not_found")
    return [a for a in req.assets if stock_passes(a, strategy.filters)]


@app.post("/screen/fiis")
def screen_fiis(req: ScreenRequest):
    strategy = FII_STRATEGIES.get(req.strategy_id)
    if not strategy:
        raise HTTPException(404, "strategy_not_found")
    return [a for a in req.assets if fii_passes(a, strategy.filters)]


@app.get("/assets/{ticker}/intelligence")
def asset_intelligence(ticker: str, db: Session = Depends(get_db)):
    repo=AssetRepository(db); asset=repo.get_by_ticker(ticker)
    if asset is None: raise HTTPException(404,"asset_not_found")
    f=repo.latest_fundamentals(asset.id)
    if f is None: raise HTTPException(404,"fundamentals_not_found")
    t=repo.latest_technical(asset.id, source="internal") or repo.latest_technical(asset.id)
    x=calculate_asset_intelligence(asset,f,t)
    as_of=f.reference_date
    if x["graham_number"] is not None:
        repo.upsert_valuation(asset,method="graham_number",as_of=as_of,method_version="1.4",value=x["graham_number"],upside_pct=x["graham_upside_pct"],inputs={"pe":x["data"].get("pe"),"pbv":x["data"].get("pbv"),"price":x["data"].get("price")})
    scores={
        "quality_score":x["quality"].score,"value_score":x["value"].score,
        "growth_score":x["growth"].score if x["growth"] else None,
        "technical_score":x["technical"].score,"risk_score":x["risk"].score,
        "liquidity_score":x["liquidity"].score,"alb_score":x["alb_score"],
    }
    details={
        "profile":{"key":x["profile"].key,"label":x["profile"].label,"notes":x["profile"].notes,"weights":x["profile"].alb_weights},
        "quality":x["quality"].as_dict(),"value":x["value"].as_dict(),
        "growth":x["growth"].as_dict() if x["growth"] else None,
        "technical":x["technical"].as_dict(),"risk":x["risk"].as_dict(),
        "liquidity":x["liquidity"].as_dict(),"explanation":x["explanation"],
    }
    repo.upsert_scores(asset,as_of=as_of,model_version=x["model_version"],scores=scores,coverage_pct=x["coverage"],data_quality_score=x["data_quality"].score,details=details)
    db.commit()
    return {
        "ticker":asset.ticker,"model_version":x["model_version"],
        "profile":{"key":x["profile"].key,"label":x["profile"].label,"notes":x["profile"].notes,"weights":x["profile"].alb_weights},
        "graham_number":x["graham_number"],"graham_upside_pct":x["graham_upside_pct"],
        "quality_score":x["quality"].score,"quality_coverage_pct":x["quality"].coverage,
        "value_score":x["value"].score,"value_coverage_pct":x["value"].coverage,
        "growth_score":x["growth"].score if x["growth"] else None,"growth_coverage_pct":x["growth"].coverage if x["growth"] else None,
        "technical_score":x["technical"].score,"technical_coverage_pct":x["technical"].coverage,
        "risk_score":x["risk"].score,"risk_coverage_pct":x["risk"].coverage,
        "liquidity_score":x["liquidity"].score,"liquidity_coverage_pct":x["liquidity"].coverage,
        "alb_score":x["alb_score"],"coverage_pct":x["coverage"],
        "data_quality":x["data_quality"].as_dict(),"explanation":x["explanation"],
        "components":details,
    }

@app.post("/assets/{ticker}/prices/ingest")
def ingest_prices(ticker: str, db: Session = Depends(get_db)):
    repo=AssetRepository(db); a=repo.get_by_ticker(ticker); asset_type=a.asset_type if a else "stock"
    try:
        result=PriceIngestionService(db).ingest_asset(ticker,asset_type=asset_type); db.commit(); return result
    except Exception as exc:
        db.rollback(); raise HTTPException(502,detail={"price_ingestion_failed":str(exc)})

@app.get("/screen/db/stocks/{strategy_id}")
def screen_db_stocks(strategy_id: str, limit:int=50, offset:int=0, db: Session=Depends(get_db)):
    strategy=STOCK_STRATEGIES.get(strategy_id)
    if not strategy: raise HTTPException(404,"strategy_not_found")
    rows=AssetRepository(db).screen_latest_stocks(strategy.filters,limit=limit,offset=offset)
    return [{"ticker":a.ticker,"name":a.name,"price":_num(f.price),"pe":_num(f.pe),"pbv":_num(f.pbv),"dy":_num(f.dividend_yield_pct),"roe":_num(f.roe_pct),"alb_score":_num(sc.alb_score) if sc else None,"quality_score":_num(sc.quality_score) if sc else None,"value_score":_num(sc.value_score) if sc else None,"growth_score":_num(sc.growth_score) if sc else None,"technical_score":_num(sc.technical_score) if sc else None,"risk_score":_num(sc.risk_score) if sc else None,"liquidity_score":_num(sc.liquidity_score) if sc else None,"data_quality_score":_num(sc.data_quality_score) if sc else None} for a,f,sc in rows]

@app.get("/screen/db/fiis/{strategy_id}")
def screen_db_fiis(strategy_id: str, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    strategy = FII_STRATEGIES.get(strategy_id)
    if not strategy:
        raise HTTPException(404, "strategy_not_found")
    rows = AssetRepository(db).screen_latest_fiis(strategy.filters, limit=limit, offset=offset)
    return [{
        "ticker": a.ticker, "name": a.name, "segment": a.segment,
        "price": _num(f.price), "pbv": _num(f.pbv), "dy": _num(f.dividend_yield_pct),
        "ffo_yield": _num(f.ffo_yield_pct), "cap_rate": _num(f.cap_rate_pct),
        "vacancy": _num(f.vacancy_pct), "daily_liquidity": _num(f.daily_liquidity),
        "alb_score": _num(sc.alb_score) if sc else None,
        "quality_score": _num(sc.quality_score) if sc else None,
        "value_score": _num(sc.value_score) if sc else None,
        "growth_score": _num(sc.growth_score) if sc else None,
        "technical_score": _num(sc.technical_score) if sc else None,
        "risk_score": _num(sc.risk_score) if sc else None,
        "liquidity_score": _num(sc.liquidity_score) if sc else None,
        "data_quality_score": _num(sc.data_quality_score) if sc else None,
    } for a, f, sc in rows]

@app.post("/screen/advanced")
def screen_advanced(req: AdvancedScreenRequest, db: Session = Depends(get_db)):
    try:
        fundamental_filters = {k: v.model_dump(exclude_none=True) for k, v in req.fundamental_filters.items()}
        score_filters = {k: v.model_dump(exclude_none=True) for k, v in req.score_filters.items()}
        return advanced_screen(
            AssetRepository(db), asset_type=req.asset_type, fundamental_filters=fundamental_filters,
            score_filters=score_filters, valuation_flags=req.valuation_flags,
            technical_filters=req.technical_filters.model_dump(exclude_none=True), trend_period=req.trend_period,
            pivot_timeframe=req.pivot_timeframe, include_technical_columns=req.include_technical_columns, limit=req.limit,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc))


@app.get("/assets/{ticker}/prices")
def asset_prices(ticker: str, limit: int = Query(default=260, ge=1, le=2000), db: Session = Depends(get_db)):
    repo = AssetRepository(db)
    asset = repo.get_by_ticker(ticker)
    if asset is None:
        raise HTTPException(404, "asset_not_found")
    rows = repo.price_history(asset.id, limit=limit)
    return [{
        "timestamp": r.timestamp, "open": _num(r.open), "high": _num(r.high), "low": _num(r.low),
        "close": _num(r.close), "adjusted_close": _num(r.adjusted_close), "volume": _num(r.volume), "source": r.source,
    } for r in rows]

@app.get("/assets/{ticker}/scores/history")
def asset_score_history(ticker: str, limit: int = Query(default=120, ge=1, le=1000), db: Session = Depends(get_db)):
    repo = AssetRepository(db)
    asset = repo.get_by_ticker(ticker)
    if asset is None:
        raise HTTPException(404, "asset_not_found")
    rows = repo.score_history(asset.id, limit=limit)
    return [{
        "as_of": r.as_of, "model_version": r.model_version,
        "quality_score": _num(r.quality_score), "value_score": _num(r.value_score),
        "growth_score": _num(r.growth_score), "technical_score": _num(r.technical_score),
        "risk_score": _num(r.risk_score), "liquidity_score": _num(r.liquidity_score),
        "alb_score": _num(r.alb_score), "coverage_pct": _num(r.coverage_pct),
        "data_quality_score": _num(r.data_quality_score),
    } for r in rows]

@app.get("/assets/{ticker}/valuations")
def asset_valuations(ticker: str, method: str | None = None, limit: int = Query(default=120, ge=1, le=1000), db: Session = Depends(get_db)):
    repo = AssetRepository(db)
    asset = repo.get_by_ticker(ticker)
    if asset is None:
        raise HTTPException(404, "asset_not_found")
    rows = repo.valuation_history(asset.id, method=method, limit=limit)
    return [{
        "method": r.method, "method_version": r.method_version, "as_of": r.as_of,
        "value": _num(r.value), "upside_pct": _num(r.upside_pct), "status": r.status,
        "inputs": r.inputs_json,
    } for r in rows]


# -----------------------------
# V1.5 Portfolio / Allocation
# -----------------------------

def _portfolio_header(p):
    return {
        "id": str(p.id), "name": p.name, "base_currency": p.base_currency,
        "cash_balance": _num(p.cash_balance), "target_cash_pct": _num(p.target_cash_pct),
        "notes": p.notes, "created_at": p.created_at, "updated_at": p.updated_at,
    }


def _portfolio_snapshot(db: Session, portfolio):
    repo = PortfolioRepository(db)
    raw = []
    for pos, asset in repo.positions(portfolio.id):
        price_info = repo.latest_price_info(asset.id)
        raw.append({
            "position_id": str(pos.id), "asset_id": str(asset.id), "ticker": asset.ticker, "name": asset.name,
            "asset_type": asset.asset_type, "sector": asset.sector, "industry": asset.industry, "segment": asset.segment,
            "stage": pos.stage, "quantity": _num(pos.quantity), "average_price": _num(pos.average_price),
            "target_weight_pct": _num(pos.target_weight_pct), "classification_override": pos.classification_override, "notes": pos.notes,
            "current_price": price_info["price"], "current_price_as_of": price_info["as_of"], "price_source": price_info["source"],
        })
    snap = build_portfolio_snapshot(raw, cash_balance=_num(portfolio.cash_balance), target_cash_pct=_num(portfolio.target_cash_pct))
    return {"portfolio": _portfolio_header(portfolio), **snap}


@app.get("/portfolios")
def list_portfolios(db: Session = Depends(get_db)):
    return [_portfolio_header(p) for p in PortfolioRepository(db).list_portfolios()]


@app.post("/portfolios")
def create_portfolio(req: PortfolioCreateRequest, db: Session = Depends(get_db)):
    repo = PortfolioRepository(db)
    p = repo.create_portfolio(name=req.name, base_currency=req.base_currency, cash_balance=req.cash_balance,
                              target_cash_pct=req.target_cash_pct, notes=req.notes)
    db.commit()
    return _portfolio_snapshot(db, p)


@app.patch("/portfolios/{portfolio_id}")
def update_portfolio(portfolio_id: UUID, req: PortfolioUpdateRequest, db: Session = Depends(get_db)):
    repo = PortfolioRepository(db); p = repo.get_portfolio(portfolio_id)
    if p is None: raise HTTPException(404, "portfolio_not_found")
    repo.update_portfolio(p, name=req.name, cash_balance=req.cash_balance, target_cash_pct=req.target_cash_pct, notes=req.notes)
    db.commit(); return _portfolio_snapshot(db, p)


@app.get("/portfolios/{portfolio_id}")
def portfolio_detail(portfolio_id: UUID, db: Session = Depends(get_db)):
    p = PortfolioRepository(db).get_portfolio(portfolio_id)
    if p is None: raise HTTPException(404, "portfolio_not_found")
    return _portfolio_snapshot(db, p)


@app.put("/portfolios/{portfolio_id}/positions/{ticker}")
def upsert_portfolio_position(portfolio_id: UUID, ticker: str, req: PortfolioPositionRequest, db: Session = Depends(get_db)):
    prepo = PortfolioRepository(db); p = prepo.get_portfolio(portfolio_id)
    if p is None: raise HTTPException(404, "portfolio_not_found")
    arepo = AssetRepository(db); asset = arepo.get_by_ticker(ticker.upper())
    if asset is None:
        asset = arepo.upsert_asset(ticker=ticker.upper(), asset_type=req.asset_type)
    prepo.upsert_position(p, asset, stage=req.stage, quantity=req.quantity, average_price=req.average_price,
                          target_weight_pct=req.target_weight_pct, classification_override=req.classification_override, notes=req.notes)
    db.commit(); return _portfolio_snapshot(db, p)


@app.delete("/portfolios/{portfolio_id}/positions/{ticker}")
def delete_portfolio_position(portfolio_id: UUID, ticker: str, db: Session = Depends(get_db)):
    prepo = PortfolioRepository(db); p = prepo.get_portfolio(portfolio_id)
    if p is None: raise HTTPException(404, "portfolio_not_found")
    asset = AssetRepository(db).get_by_ticker(ticker.upper())
    if asset is None or not prepo.delete_position(p.id, asset.id): raise HTTPException(404, "position_not_found")
    db.commit(); return {"status": "deleted", "ticker": ticker.upper()}


@app.post("/portfolios/{portfolio_id}/refresh-prices")
def refresh_portfolio_prices(portfolio_id: UUID, db: Session = Depends(get_db)):
    prepo = PortfolioRepository(db); p = prepo.get_portfolio(portfolio_id)
    if p is None: raise HTTPException(404, "portfolio_not_found")
    svc = PriceIngestionService(db); results = []
    for pos, asset in prepo.positions(p.id):
        if asset.asset_type in {"fixed_income", "crypto"}:
            results.append({"ticker": asset.ticker, "status": "skipped", "reason": "provider_not_configured"}); continue
        try:
            r = svc.ingest_asset(asset.ticker, asset_type=asset.asset_type, range_="1mo")
            results.append({"ticker": asset.ticker, "status": "ok", "bars": r.get("bars", 0)})
        except Exception as exc:
            results.append({"ticker": asset.ticker, "status": "error", "error": str(exc)})
    db.commit(); return {"portfolio_id": str(p.id), "results": results, "snapshot": _portfolio_snapshot(db, p)}


# -----------------------------
# V1.5 Backtesting
# -----------------------------

@app.get("/backtests/strategies")
def backtest_strategies():
    return {"periods": PERIOD_LABELS, "strategies": strategy_catalog()}


@app.post("/backtests/run")
def backtest_run(req: BacktestRequest, db: Session = Depends(get_db)):
    if req.strategy_id not in STRATEGIES: raise HTTPException(404, "strategy_not_found")
    try:
        result = BacktestService(db).run(
            ticker=req.ticker.upper(), asset_type=req.asset_type, strategy_id=req.strategy_id, period=req.period,
            start=req.start, end=req.end, initial_capital=req.initial_capital, fee_pct=req.fee_pct,
            slippage_pct=req.slippage_pct, risk_free_rate_pct=req.risk_free_rate_pct, params=req.params,
            cash_yield_rate_pct=req.cash_yield_rate_pct, apply_cash_yield=req.apply_cash_yield,
            filters=req.filters.model_dump(exclude_none=True), persist=req.persist,
        )
        db.commit(); return result
    except ValueError as exc:
        db.rollback(); raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback(); raise HTTPException(502, detail={"backtest_failed": str(exc)})


@app.post("/backtests/compare")
def backtest_compare(req: BacktestCompareRequest, db: Session = Depends(get_db)):
    unknown = [s for s in req.strategy_ids if s not in STRATEGIES]
    if unknown: raise HTTPException(404, detail={"strategies_not_found": unknown})
    try:
        rows = BacktestService(db).compare(
            ticker=req.ticker.upper(), asset_type=req.asset_type, strategy_ids=req.strategy_ids, period=req.period,
            start=req.start, end=req.end, initial_capital=req.initial_capital, fee_pct=req.fee_pct,
            slippage_pct=req.slippage_pct, risk_free_rate_pct=req.risk_free_rate_pct,
            cash_yield_rate_pct=req.cash_yield_rate_pct, apply_cash_yield=req.apply_cash_yield,
            filters=req.filters.model_dump(exclude_none=True),
        )
        db.commit(); return rows
    except ValueError as exc:
        db.rollback(); raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback(); raise HTTPException(502, detail={"backtest_compare_failed": str(exc)})


@app.post("/backtests/basket")
def backtest_basket(req: BacktestBasketRequest, db: Session = Depends(get_db)):
    if req.strategy_id not in STRATEGIES: raise HTTPException(404, "strategy_not_found")
    try:
        result = BacktestService(db).basket(
            tickers=req.tickers, asset_type=req.asset_type, strategy_id=req.strategy_id, period=req.period,
            start=req.start, end=req.end, initial_capital=req.initial_capital,
            fee_pct=req.fee_pct, slippage_pct=req.slippage_pct, risk_free_rate_pct=req.risk_free_rate_pct,
            cash_yield_rate_pct=req.cash_yield_rate_pct, apply_cash_yield=req.apply_cash_yield,
            params=req.params, filters=req.filters.model_dump(exclude_none=True),
        )
        db.commit(); return result
    except ValueError as exc:
        db.rollback(); raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback(); raise HTTPException(502, detail={"basket_backtest_failed": str(exc)})


@app.get("/backtests/runs")
def backtest_runs(ticker: str | None = None, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    rows = BacktestRepository(db).list_runs(ticker=ticker, limit=limit)
    return [{
        "id": str(run.id), "ticker": asset.ticker, "asset_name": asset.name, "strategy_id": run.strategy_id,
        "strategy_name": run.strategy_name, "requested_start": run.requested_start, "requested_end": run.requested_end,
        "actual_start": run.actual_start, "actual_end": run.actual_end, "created_at": run.created_at,
        "metrics": run.metrics_json, "parameters": run.parameters_json, "status": run.status,
    } for run, asset in rows]


@app.get("/backtests/runs/{run_id}")
def backtest_run_detail(run_id: UUID, db: Session = Depends(get_db)):
    repo = BacktestRepository(db); run = repo.get_run(run_id)
    if run is None: raise HTTPException(404, "backtest_run_not_found")
    asset = db.get(AssetORM, run.asset_id)
    trades = repo.trades(run.id)
    return {
        "id": str(run.id), "ticker": asset.ticker if asset else None, "asset_name": asset.name if asset else None,
        "strategy_id": run.strategy_id, "strategy_name": run.strategy_name, "requested_start": run.requested_start,
        "requested_end": run.requested_end, "actual_start": run.actual_start, "actual_end": run.actual_end,
        "initial_capital": _num(run.initial_capital), "fee_pct": _num(run.fee_pct), "slippage_pct": _num(run.slippage_pct),
        "risk_free_rate_pct": _num(run.risk_free_rate_pct), "parameters": run.parameters_json, "metrics": run.metrics_json,
        "equity_curve": run.equity_curve_json, "status": run.status, "created_at": run.created_at,
        "trades": [{
            "sequence": t.sequence, "entry_date": t.entry_date, "entry_price": _num(t.entry_price),
            "exit_date": t.exit_date, "exit_price": _num(t.exit_price), "return_pct": _num(t.return_pct),
            "pnl_value": _num(t.pnl_value), "holding_days": t.holding_days, "exit_reason": t.exit_reason,
        } for t in trades],
    }
