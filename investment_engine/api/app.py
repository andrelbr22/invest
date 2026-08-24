from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from time import monotonic
from uuid import UUID
from typing import Literal
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.valuation.graham import graham_number, add_upside
from ..core.valuation.dividend_target import dividend_yield_target_price
from ..core.strategies.presets import STOCK_STRATEGIES, FII_STRATEGIES
from ..core.screening.filters import stock_passes, fii_passes
from ..core.screening.advanced import advanced_screen
from ..core.screening.universe import COMPANY_SIZE_LABELS, company_size_category
from ..core.repositories.assets import AssetRepository
from ..core.repositories.portfolio import PortfolioRepository
from ..core.repositories.screening_filters import SavedScreeningFilterRepository
from ..core.repositories.backtests import BacktestRepository, backtest_market_date, run_summary
from ..core.repositories.access import AccessPolicyRepository, PERMISSION_FIELDS, full_owner_policy, policy_dict
from ..core.portfolio.service import build_portfolio_snapshot, classification_for, localize_classification
from ..core.backtesting.service import BacktestService, PERIOD_LABELS
from ..core.backtesting.strategies import STRATEGIES, strategy_catalog
from ..core.backtesting.batch import BacktestBatchService, OFFICIAL_OWNER
from ..core.backtesting.study import build_strategy_study
from ..infrastructure.db.models import AssetORM
from ..core.models.strategy import StockFilterSet, FiiFilterSet
from ..infrastructure.db.session import get_session_factory
from ..core.services_v14 import calculate_asset_intelligence
from ..data.ingestion.prices import PriceIngestionService
from ..data.ingestion.pipeline import MarketIngestionPipeline
from ..data.providers.b3_indices import B3IndexProvider
from ..data.providers.news import MarketNewsService
from ..infrastructure.config import settings

app = FastAPI(
    title="Investment Engine V1.11.0",
    version="0.12.0",
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

_INDEX_PORTFOLIO_CACHE: dict[str, tuple[float, dict]] = {}
_INDEX_PORTFOLIO_TTL_SECONDS = 6 * 60 * 60
_MARKET_NEWS = MarketNewsService()


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    private_path = request.url.path.startswith(("/portfolios", "/backtests", "/access", "/insights"))
    response.headers["Cache-Control"] = "no-store" if private_path else "no-cache"
    return response


def get_db():
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def _request_email(x_app_user_email: str = Header(default="")) -> str:
    email = str(x_app_user_email or "").strip().lower()
    if email:
        return email
    if not settings.app_auth_required:
        return "local-owner@localhost"
    raise HTTPException(401, "authenticated_google_account_required")


def _access_policy(db: Session, email: str) -> dict:
    is_owner = email in settings.owner_emails or (email == "local-owner@localhost" and not settings.app_auth_required)
    row = AccessPolicyRepository(db).get(email)
    if is_owner:
        return full_owner_policy(email, row.display_name if row else None)
    if row is None:
        return {
            "email": email,
            "display_name": None,
            "role": "visitor",
            "status": "pending",
            "can_view_market": True,
            "custom_filter_limit": 0,
            **{field: False for field in PERMISSION_FIELDS if field != "can_view_market"},
            "is_owner": False,
        }
    return policy_dict(row)


def require_permission(permission: str):
    def dependency(
        email: str = Depends(_request_email),
        db: Session = Depends(get_db),
    ):
        policy = _access_policy(db, email)
        if not policy.get(permission, False):
            raise HTTPException(403, detail={"permission_required": permission})
        return policy
    return dependency


def require_owner(
    email: str = Depends(_request_email),
    db: Session = Depends(get_db),
):
    policy = _access_policy(db, email)
    if not policy.get("is_owner", False):
        raise HTTPException(403, "owner_access_required")
    return policy


def _num(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _company_size_fields(asset) -> dict:
    metadata = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
    size = company_size_category({
        "market_cap_category": asset.market_cap_category,
        "metadata_json": metadata,
    })
    return {
        "company_size": size,
        "company_size_label": COMPANY_SIZE_LABELS.get(size),
        "market_cap": _num(metadata.get("last_market_cap")),
        "market_cap_category_label": COMPANY_SIZE_LABELS.get(size) or localize_classification(asset.market_cap_category),
    }


def _index_portfolio(index_code: str) -> dict:
    code = index_code.upper()
    now = monotonic()
    cached = _INDEX_PORTFOLIO_CACHE.get(code)
    if cached and now - cached[0] < _INDEX_PORTFOLIO_TTL_SECONDS:
        return cached[1]
    try:
        result = B3IndexProvider().fetch(code)
        result["stale"] = False
        _INDEX_PORTFOLIO_CACHE[code] = (now, result)
        return result
    except Exception:
        if cached:
            stale = {**cached[1], "stale": True}
            return stale
        raise


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
    asset_type: str = Field(default="stock", pattern="^(stock|fii|etf|bdr|future|fixed_income|crypto|other)$")
    stage: str = Field(default="position", pattern="^(position|target|analysis)$")
    quantity: float = Field(default=0.0, ge=0)
    average_price: float | None = Field(default=None, ge=0)
    target_weight_pct: float = Field(default=0.0, ge=0, le=100)
    classification_override: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class PortfolioPurchaseRequest(BaseModel):
    asset_type: str = Field(default="stock", pattern="^(stock|fii|etf|bdr|future|fixed_income|crypto|other)$")
    quantity: float = Field(gt=0)
    unit_price: float = Field(gt=0)
    stage: str = Field(default="position", pattern="^(position|target|analysis)$")
    target_weight_pct: float | None = Field(default=None, ge=0, le=100)
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
    asset_type: str = Field(default="stock", pattern="^(stock|fii|etf|bdr|future|other)$")
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
    asset_type: str = Field(default="stock", pattern="^(stock|fii|etf|bdr|future|other)$")
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
    asset_type: str = Field(default="stock", pattern="^(stock|fii|etf|bdr|future|other)$")
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


class BacktestBatchCreateRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=100)
    max_combinations: int = Field(default=200, ge=1, le=200)


class BacktestBatchFailureRequest(BaseModel):
    code: str = Field(default="external_failure", max_length=80)
    message: str = Field(max_length=500)
    details: dict = Field(default_factory=dict)


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
    asset_type: str = Field(default="stock", pattern="^(stock|fii|other_b3)$")
    fundamental_filters: dict[str, NumericRangeRequest] = Field(default_factory=dict)
    score_filters: dict[str, NumericRangeRequest] = Field(default_factory=dict)
    valuation_flags: dict[str, bool] = Field(default_factory=dict)
    technical_filters: AdvancedTechnicalFiltersRequest = Field(default_factory=AdvancedTechnicalFiltersRequest)
    trend_period: int = Field(default=21, ge=20, le=21)
    pivot_timeframe: str = Field(default="daily", pattern="^(daily|weekly|monthly)$")
    include_technical_columns: bool = True
    limit: int = Field(default=100, ge=1, le=300)
    allowed_tickers: list[str] | None = Field(default=None, max_length=1200)


class MarketSyncRequest(BaseModel):
    asset_type: Literal["stock", "fii", "other_b3"] = "stock"


class AccessRegisterRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=180)


class AccessPolicyUpdateRequest(BaseModel):
    role: str | None = Field(default=None, pattern="^(visitor|member|admin)$")
    status: str | None = Field(default=None, pattern="^(pending|approved|blocked)$")
    can_view_market: bool | None = None
    can_use_advanced_filters: bool | None = None
    can_view_portfolio: bool | None = None
    can_write_portfolio: bool | None = None
    can_view_backtests: bool | None = None
    can_run_backtests: bool | None = None
    can_refresh_backtest_signals: bool | None = None
    can_view_backtest_studies: bool | None = None
    can_view_news_insights: bool | None = None
    can_sync_market: bool | None = None
    custom_filter_limit: int | None = Field(default=None, ge=0, le=3)


class SavedScreeningFilterCreateRequest(BaseModel):
    asset_type: Literal["stock", "fii"]
    name: str | None = Field(default=None, max_length=120)
    filters: dict = Field(default_factory=dict)


class SavedScreeningFilterUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    filters: dict | None = None


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.12.0", "environment": settings.app_environment}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception as exc:
        raise HTTPException(503, detail={"database": "unreachable", "error": str(exc)})


@app.get("/debug/db-counts")
def debug_db_counts(_access=Depends(require_owner), db: Session = Depends(get_db)):
    names = ["assets", "fundamental_snapshots", "technical_snapshots", "score_snapshots", "valuation_snapshots", "price_bars", "portfolios", "portfolio_positions", "backtest_runs", "backtest_trades", "backtest_batch_jobs"]
    counts = {}
    for name in names:
        counts[name] = db.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one()
    return counts


@app.post("/access/register")
def register_access(
    req: AccessRegisterRequest,
    email: str = Depends(_request_email),
    db: Session = Depends(get_db),
):
    is_owner = email in settings.owner_emails or (email == "local-owner@localhost" and not settings.app_auth_required)
    row = AccessPolicyRepository(db).register(email, req.display_name, is_owner=is_owner)
    db.commit()
    return policy_dict(row, is_owner=is_owner)


@app.get("/access/me")
def my_access(email: str = Depends(_request_email), db: Session = Depends(get_db)):
    return _access_policy(db, email)


@app.get("/access/users")
def list_access_users(
    _access=Depends(require_owner),
    db: Session = Depends(get_db),
):
    repo = AccessPolicyRepository(db)
    return [policy_dict(row, is_owner=row.email in settings.owner_emails) for row in repo.list_all()]


@app.put("/access/users/{email}")
def update_access_user(
    email: str,
    req: AccessPolicyUpdateRequest,
    _access=Depends(require_owner),
    db: Session = Depends(get_db),
):
    clean = email.strip().lower()
    if clean in settings.owner_emails:
        raise HTTPException(400, "owner_permissions_are_permanent")
    changes = req.model_dump(exclude_none=True)
    if changes.get("can_use_advanced_filters") or changes.get("can_sync_market") or int(changes.get("custom_filter_limit") or 0)>0:
        changes["can_view_market"] = True
    if changes.get("can_write_portfolio") or changes.get("can_view_news_insights"):
        changes["can_view_portfolio"] = True
    if changes.get("can_run_backtests") or changes.get("can_refresh_backtest_signals") or changes.get("can_view_backtest_studies"):
        changes["can_view_backtests"] = True
    if changes.get("can_view_market") is False:
        changes["can_use_advanced_filters"] = False
        changes["can_sync_market"] = False
        changes["custom_filter_limit"] = 0
    if changes.get("can_view_portfolio") is False:
        changes["can_write_portfolio"] = False
        changes["can_view_news_insights"] = False
    if changes.get("can_view_backtests") is False:
        changes["can_run_backtests"] = False
        changes["can_refresh_backtest_signals"] = False
        changes["can_view_backtest_studies"] = False
    row = AccessPolicyRepository(db).update(clean, **changes)
    if row is None:
        raise HTTPException(404, "user_not_found")
    db.commit()
    return policy_dict(row)


def _saved_filter_dict(row):
    return {
        "id": str(row.id), "name": row.name, "asset_type": row.asset_type,
        "filters": row.filters_json or {}, "created_at": row.created_at, "updated_at": row.updated_at,
    }


def _validated_saved_filters(asset_type: str, payload: dict) -> dict:
    model = StockFilterSet if asset_type == "stock" else FiiFilterSet
    return model(**(payload or {})).model_dump()


def _require_custom_filter_access(access: dict):
    if int(access.get("custom_filter_limit") or 0) <= 0:
        raise HTTPException(403, detail={"permission_required": "custom_filter_limit"})


@app.get("/screen/custom-filters")
def list_saved_filters(
    asset_type: Literal["stock", "fii"] | None = None,
    access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    _require_custom_filter_access(access)
    rows = SavedScreeningFilterRepository(db).list_for_owner(access["email"], asset_type)
    return {
        "items": [_saved_filter_dict(row) for row in rows],
        "limit": int(access.get("custom_filter_limit") or 0),
        "used": SavedScreeningFilterRepository(db).count_for_owner(access["email"]),
    }


@app.post("/screen/custom-filters")
def create_saved_filter(
    req: SavedScreeningFilterCreateRequest,
    access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    _require_custom_filter_access(access)
    repo = SavedScreeningFilterRepository(db)
    limit = int(access.get("custom_filter_limit") or 0)
    if repo.count_for_owner(access["email"]) >= limit:
        raise HTTPException(409, detail={"custom_filter_limit_reached": limit})
    row = repo.create(
        owner_email=access["email"], asset_type=req.asset_type,
        filters=_validated_saved_filters(req.asset_type, req.filters), name=req.name,
        display_name=access.get("display_name") or access["email"].split("@", 1)[0],
    )
    db.commit()
    return _saved_filter_dict(row)


@app.put("/screen/custom-filters/{filter_id}")
def update_saved_filter(
    filter_id: UUID, req: SavedScreeningFilterUpdateRequest,
    access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db),
):
    _require_custom_filter_access(access)
    repo = SavedScreeningFilterRepository(db)
    row = repo.get(filter_id, access["email"])
    if row is None:
        raise HTTPException(404, "custom_filter_not_found")
    filters = _validated_saved_filters(row.asset_type, req.filters) if req.filters is not None else None
    repo.update(row, name=req.name, filters=filters)
    db.commit()
    return _saved_filter_dict(row)


@app.delete("/screen/custom-filters/{filter_id}")
def delete_saved_filter(
    filter_id: UUID, access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db),
):
    _require_custom_filter_access(access)
    repo = SavedScreeningFilterRepository(db)
    row = repo.get(filter_id, access["email"])
    if row is None:
        raise HTTPException(404, "custom_filter_not_found")
    repo.delete(row)
    db.commit()
    return {"status": "deleted", "id": str(filter_id)}


def _refresh_intelligence_scores(db: Session, asset_type: str) -> int:
    """Recalculate the cards shown by the UI after a market synchronization."""
    repo = AssetRepository(db)
    processed = 0
    for asset in repo.list_assets(asset_type=asset_type, limit=5000):
        fundamental = repo.latest_fundamentals(asset.id)
        if fundamental is None:
            continue
        technical = repo.latest_technical(asset.id, source="internal") or repo.latest_technical(asset.id)
        result = calculate_asset_intelligence(asset, fundamental, technical)
        scores = {
            "quality_score": result["quality"].score,
            "value_score": result["value"].score,
            "growth_score": result["growth"].score if result["growth"] else None,
            "technical_score": result["technical"].score,
            "risk_score": result["risk"].score,
            "liquidity_score": result["liquidity"].score,
            "alb_score": result["alb_score"],
        }
        details = {
            "profile": {
                "key": result["profile"].key,
                "label": result["profile"].label,
                "notes": result["profile"].notes,
                "weights": result["profile"].alb_weights,
            },
            "quality": result["quality"].as_dict(),
            "value": result["value"].as_dict(),
            "growth": result["growth"].as_dict() if result["growth"] else None,
            "technical": result["technical"].as_dict(),
            "risk": result["risk"].as_dict(),
            "liquidity": result["liquidity"].as_dict(),
            "explanation": result["explanation"],
        }
        repo.upsert_scores(
            asset,
            as_of=fundamental.reference_date,
            model_version=result["model_version"],
            scores=scores,
            coverage_pct=result["coverage"],
            data_quality_score=result["data_quality"].score,
            details=details,
        )
        processed += 1
    return processed


@app.post("/data/sync-market")
def sync_market(req: MarketSyncRequest, _access=Depends(require_permission("can_sync_market")), db: Session = Depends(get_db)):
    """Populate a new cloud database without requiring shell access."""
    pipeline = MarketIngestionPipeline(db)
    steps: dict[str, dict] = {}

    def run_step(name, operation):
        try:
            result = operation()
            db.commit()
            steps[name] = {
                "status": "ok",
                "received": result.rows_received,
                "saved": result.rows_valid,
                "rejected": result.rows_rejected,
                "warnings": result.warnings,
            }
        except Exception as exc:
            db.rollback()
            steps[name] = {"status": "error", "message": str(exc)}

    if req.asset_type == "stock":
        run_step("fundamentals", pipeline.ingest_stocks)
        run_step("catalog_and_technicals", lambda: pipeline.ingest_technicals("stock"))
    elif req.asset_type == "fii":
        run_step("fundamentals", pipeline.ingest_fiis)
        run_step("catalog_and_technicals", lambda: pipeline.ingest_technicals("fii"))
    else:
        run_step("catalog_and_technicals", pipeline.ingest_other_b3)

    if req.asset_type in {"stock", "fii"}:
        try:
            score_count = _refresh_intelligence_scores(db, req.asset_type)
            db.commit()
            steps["scores"] = {"status": "ok", "saved": score_count}
        except Exception as exc:
            db.rollback()
            steps["scores"] = {"status": "error", "message": str(exc)}
    else:
        steps["scores"] = {"status": "ok", "saved": 0, "note": "not_applicable_to_other_b3"}

    if req.asset_type == "other_b3":
        catalog_count = sum(len(AssetRepository(db).list_assets(asset_type=value, limit=5000)) for value in ("etf", "bdr", "future"))
    else:
        catalog_count = len(AssetRepository(db).list_assets(asset_type=req.asset_type, limit=5000))
    if catalog_count == 0:
        raise HTTPException(502, detail={"market_sync_failed": steps})
    return {"asset_type": req.asset_type, "catalog_count": catalog_count, "steps": steps}


@app.get("/market/index-members/{index_code}")
def market_index_members(
    index_code: str,
    _access=Depends(require_permission("can_view_market")),
):
    code = str(index_code or "").strip().upper()
    if code != "IBOV":
        raise HTTPException(422, "unsupported_market_index")
    try:
        return _index_portfolio(code)
    except Exception as exc:
        raise HTTPException(502, detail={"b3_index_unavailable": str(exc)})


@app.get("/assets")
def assets(
    asset_type: str | None = Query(default=None, pattern="^(stock|fii|etf|bdr|future|fixed_income|crypto|other)$"),
    limit: int = Query(default=100, ge=1, le=1200),
    offset: int = Query(default=0, ge=0),
    _access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    repo = AssetRepository(db)
    rows = repo.list_assets(asset_type=asset_type, limit=limit, offset=offset)
    return [
        {
            "id": str(a.id), "ticker": a.ticker, "name": a.name, "asset_type": a.asset_type,
            "exchange": a.exchange, "currency": a.currency, "sector": a.sector, "industry": a.industry,
            "segment": a.segment, "market_cap_category": a.market_cap_category, "is_active": a.is_active,
            "classification": classification_for(a.asset_type, a.sector, a.segment, industry=a.industry, category=a.market_cap_category),
            "sector_label": localize_classification(a.sector), "industry_label": localize_classification(a.industry),
            "segment_label": localize_classification(a.segment),
            **_company_size_fields(a),
        }
        for a in rows
    ]


@app.get("/assets/{ticker}")
def asset_detail(ticker: str, _access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db)):
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
            "classification": classification_for(asset.asset_type, asset.sector, asset.segment, industry=asset.industry, category=asset.market_cap_category),
            "sector_label": localize_classification(asset.sector), "industry_label": localize_classification(asset.industry),
            "segment_label": localize_classification(asset.segment),
            **_company_size_fields(asset),
            "metadata": asset.metadata_json,
        },
        "fundamentals": _fundamental_dict(fundamentals),
        "technical": _technical_dict(technical),
    }


@app.get("/strategies/stocks")
def stock_strategies(_access=Depends(require_permission("can_view_market"))):
    return [s.model_dump() for s in STOCK_STRATEGIES.values()]


@app.get("/strategies/fiis")
def fii_strategies(_access=Depends(require_permission("can_view_market"))):
    return [s.model_dump() for s in FII_STRATEGIES.values()]


@app.post("/valuation/graham")
def valuation_graham(req: GrahamRequest, _access=Depends(require_permission("can_view_market"))):
    return add_upside(graham_number(req.eps, req.bvps), req.market_price)


@app.post("/valuation/dividend-target")
def valuation_dividend_target(req: DividendTargetRequest, _access=Depends(require_permission("can_view_market"))):
    result = dividend_yield_target_price(req.dividend_per_share, req.target_yield_pct)
    return add_upside(result, req.market_price)


@app.post("/screen/stocks")
def screen_stocks(req: ScreenRequest, _access=Depends(require_permission("can_view_market"))):
    strategy = STOCK_STRATEGIES.get(req.strategy_id)
    if not strategy:
        raise HTTPException(404, "strategy_not_found")
    return [a for a in req.assets if stock_passes(a, strategy.filters)]


@app.post("/screen/fiis")
def screen_fiis(req: ScreenRequest, _access=Depends(require_permission("can_view_market"))):
    strategy = FII_STRATEGIES.get(req.strategy_id)
    if not strategy:
        raise HTTPException(404, "strategy_not_found")
    return [a for a in req.assets if fii_passes(a, strategy.filters)]


@app.get("/assets/{ticker}/intelligence")
def asset_intelligence(ticker: str, _access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db)):
    repo=AssetRepository(db); asset=repo.get_by_ticker(ticker)
    if asset is None: raise HTTPException(404,"asset_not_found")
    f=repo.latest_fundamentals(asset.id)
    if f is None: raise HTTPException(404,"fundamentals_not_found")
    t=repo.latest_technical(asset.id, source="internal") or repo.latest_technical(asset.id)
    x=calculate_asset_intelligence(asset,f,t)
    details={
        "profile":{"key":x["profile"].key,"label":x["profile"].label,"notes":x["profile"].notes,"weights":x["profile"].alb_weights},
        "quality":x["quality"].as_dict(),"value":x["value"].as_dict(),
        "growth":x["growth"].as_dict() if x["growth"] else None,
        "technical":x["technical"].as_dict(),"risk":x["risk"].as_dict(),
        "liquidity":x["liquidity"].as_dict(),"explanation":x["explanation"],
    }
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
def ingest_prices(ticker: str, _access=Depends(require_permission("can_sync_market")), db: Session = Depends(get_db)):
    repo=AssetRepository(db); a=repo.get_by_ticker(ticker); asset_type=a.asset_type if a else "stock"
    try:
        result=PriceIngestionService(db).ingest_asset(ticker,asset_type=asset_type); db.commit(); return result
    except Exception as exc:
        db.rollback(); raise HTTPException(502,detail={"price_ingestion_failed":str(exc)})


def _screen_identity(asset):
    return {
        "ticker": asset.ticker, "name": asset.name,
        "sector": asset.sector, "industry": asset.industry, "segment": asset.segment,
        "market_cap_category": asset.market_cap_category,
        "classification": classification_for(
            asset.asset_type, asset.sector, asset.segment,
            industry=asset.industry, category=asset.market_cap_category,
        ),
        "sector_label": localize_classification(asset.sector),
        "industry_label": localize_classification(asset.industry),
        "segment_label": localize_classification(asset.segment),
        **_company_size_fields(asset),
    }


def _screen_scores(score):
    return {
        "alb_score": _num(score.alb_score) if score else None,
        "quality_score": _num(score.quality_score) if score else None,
        "value_score": _num(score.value_score) if score else None,
        "growth_score": _num(score.growth_score) if score else None,
        "technical_score": _num(score.technical_score) if score else None,
        "risk_score": _num(score.risk_score) if score else None,
        "liquidity_score": _num(score.liquidity_score) if score else None,
        "data_quality_score": _num(score.data_quality_score) if score else None,
    }


def _stock_screen_row(asset, fundamental, score):
    return {
        **_screen_identity(asset),
        "price": _num(fundamental.price) if fundamental else None,
        "pe": _num(fundamental.pe) if fundamental else None,
        "pbv": _num(fundamental.pbv) if fundamental else None,
        "dy": _num(fundamental.dividend_yield_pct) if fundamental else None,
        "roe": _num(fundamental.roe_pct) if fundamental else None,
        **_screen_scores(score),
    }


def _stock_screen_result(rows):
    return [_stock_screen_row(asset, fundamental, score) for asset, fundamental, score in rows]


def _fii_screen_row(asset, fundamental, score):
    return {
        **_screen_identity(asset),
        "price": _num(fundamental.price) if fundamental else None,
        "pbv": _num(fundamental.pbv) if fundamental else None,
        "dy": _num(fundamental.dividend_yield_pct) if fundamental else None,
        "ffo_yield": _num(fundamental.ffo_yield_pct) if fundamental else None,
        "cap_rate": _num(fundamental.cap_rate_pct) if fundamental else None,
        "vacancy": _num(fundamental.vacancy_pct) if fundamental else None,
        "daily_liquidity": _num(fundamental.daily_liquidity) if fundamental else None,
        **_screen_scores(score),
    }


def _fii_screen_result(rows):
    return [_fii_screen_row(asset, fundamental, score) for asset, fundamental, score in rows]


def _other_b3_screen_row(asset, technical, score):
    metadata=asset.metadata_json if isinstance(asset.metadata_json,dict) else {}
    category_labels={"etf":"ETF","bdr":"BDR","future":"Futuro / derivativo"}
    return {
        **_screen_identity(asset),
        "asset_type":asset.asset_type,
        "asset_type_label":category_labels.get(asset.asset_type,"Outro ativo B3"),
        "classification":category_labels.get(asset.asset_type) or metadata.get("b3_category") or asset.segment,
        "price":_num(technical.close) if technical else None,
        "daily_liquidity":_num(technical.daily_liquidity) if technical else None,
        "signal_tv":technical.signal_tv if technical else None,
        "rsi14_screen":_num(technical.rsi14) if technical else None,
        "sma20":_num(technical.sma20) if technical else None,
        "sma50":_num(technical.sma50) if technical else None,
        "sma200":_num(technical.sma200) if technical else None,
        **_screen_scores(score),
    }


def _universe_screen_result(rows, asset_type: str):
    if asset_type == "stock":
        return [_stock_screen_row(asset, fundamental, score) for asset, fundamental, _technical, score in rows]
    if asset_type == "fii":
        return [_fii_screen_row(asset, fundamental, score) for asset, fundamental, _technical, score in rows]
    return [_other_b3_screen_row(asset, technical, score) for asset, _fundamental, technical, score in rows]

@app.get("/screen/db/stocks/{strategy_id}")
def screen_db_stocks(strategy_id: str, limit:int=50, offset:int=0, _access=Depends(require_permission("can_view_market")), db: Session=Depends(get_db)):
    strategy=STOCK_STRATEGIES.get(strategy_id)
    if not strategy: raise HTTPException(404,"strategy_not_found")
    rows=AssetRepository(db).screen_latest_stocks(strategy.filters,limit=limit,offset=offset)
    return _stock_screen_result(rows)

@app.get("/screen/db/fiis/{strategy_id}")
def screen_db_fiis(strategy_id: str, limit: int = 50, offset: int = 0, _access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db)):
    strategy = FII_STRATEGIES.get(strategy_id)
    if not strategy:
        raise HTTPException(404, "strategy_not_found")
    rows = AssetRepository(db).screen_latest_fiis(strategy.filters, limit=limit, offset=offset)
    return _fii_screen_result(rows)


@app.get("/screen/db/universe/{asset_type}")
def screen_db_universe(
    asset_type: str,
    limit: int = Query(default=500, ge=1, le=1200),
    _access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    if asset_type not in {"stock", "fii", "other_b3"}:
        raise HTTPException(422, "invalid_asset_type")
    rows = AssetRepository(db).latest_universe(asset_type=asset_type, limit=limit)
    return _universe_screen_result(rows, asset_type)


@app.get("/screen/db/custom/{filter_id}")
def screen_db_custom(
    filter_id: UUID, limit: int = 50, offset: int = 0,
    access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db),
):
    _require_custom_filter_access(access)
    row = SavedScreeningFilterRepository(db).get(filter_id, access["email"])
    if row is None:
        raise HTTPException(404, "custom_filter_not_found")
    repo = AssetRepository(db)
    if row.asset_type == "stock":
        filters = StockFilterSet(**(row.filters_json or {}))
        return _stock_screen_result(repo.screen_latest_stocks(filters, limit=limit, offset=offset))
    filters = FiiFilterSet(**(row.filters_json or {}))
    return _fii_screen_result(repo.screen_latest_fiis(filters, limit=limit, offset=offset))

@app.post("/screen/advanced")
def screen_advanced(req: AdvancedScreenRequest, _access=Depends(require_permission("can_use_advanced_filters")), db: Session = Depends(get_db)):
    try:
        fundamental_filters = {k: v.model_dump(exclude_none=True) for k, v in req.fundamental_filters.items()}
        score_filters = {k: v.model_dump(exclude_none=True) for k, v in req.score_filters.items()}
        return advanced_screen(
            AssetRepository(db), asset_type=req.asset_type, fundamental_filters=fundamental_filters,
            score_filters=score_filters, valuation_flags=req.valuation_flags,
            technical_filters=req.technical_filters.model_dump(exclude_none=True), trend_period=req.trend_period,
            pivot_timeframe=req.pivot_timeframe, include_technical_columns=req.include_technical_columns, limit=req.limit,
            allowed_tickers=req.allowed_tickers,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc))


@app.get("/assets/{ticker}/prices")
def asset_prices(ticker: str, limit: int = Query(default=260, ge=1, le=2000), _access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db)):
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
def asset_score_history(ticker: str, limit: int = Query(default=120, ge=1, le=1000), _access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db)):
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
def asset_valuations(ticker: str, method: str | None = None, limit: int = Query(default=120, ge=1, le=1000), _access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db)):
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
            "market_cap_category": asset.market_cap_category,
            "stage": pos.stage, "quantity": _num(pos.quantity), "average_price": _num(pos.average_price),
            "target_weight_pct": _num(pos.target_weight_pct), "classification_override": pos.classification_override, "notes": pos.notes,
            "current_price": price_info["price"], "current_price_as_of": price_info["as_of"], "price_source": price_info["source"],
        })
    snap = build_portfolio_snapshot(raw, cash_balance=_num(portfolio.cash_balance), target_cash_pct=_num(portfolio.target_cash_pct))
    return {"portfolio": _portfolio_header(portfolio), **snap}


@app.get("/portfolios")
def list_portfolios(access=Depends(require_permission("can_view_portfolio")), db: Session = Depends(get_db)):
    return [_portfolio_header(p) for p in PortfolioRepository(db).list_portfolios(access["email"])]


@app.post("/portfolios")
def create_portfolio(req: PortfolioCreateRequest, access=Depends(require_permission("can_write_portfolio")), db: Session = Depends(get_db)):
    repo = PortfolioRepository(db)
    p = repo.create_portfolio(owner_email=access["email"], name=req.name, base_currency=req.base_currency, cash_balance=req.cash_balance,
                              target_cash_pct=req.target_cash_pct, notes=req.notes)
    db.commit()
    return _portfolio_snapshot(db, p)


@app.patch("/portfolios/{portfolio_id}")
def update_portfolio(portfolio_id: UUID, req: PortfolioUpdateRequest, access=Depends(require_permission("can_write_portfolio")), db: Session = Depends(get_db)):
    repo = PortfolioRepository(db); p = repo.get_portfolio(portfolio_id, access["email"])
    if p is None: raise HTTPException(404, "portfolio_not_found")
    repo.update_portfolio(p, name=req.name, cash_balance=req.cash_balance, target_cash_pct=req.target_cash_pct, notes=req.notes)
    db.commit(); return _portfolio_snapshot(db, p)


@app.get("/portfolios/{portfolio_id}")
def portfolio_detail(portfolio_id: UUID, access=Depends(require_permission("can_view_portfolio")), db: Session = Depends(get_db)):
    p = PortfolioRepository(db).get_portfolio(portfolio_id, access["email"])
    if p is None: raise HTTPException(404, "portfolio_not_found")
    return _portfolio_snapshot(db, p)


@app.put("/portfolios/{portfolio_id}/positions/{ticker}")
def upsert_portfolio_position(portfolio_id: UUID, ticker: str, req: PortfolioPositionRequest, access=Depends(require_permission("can_write_portfolio")), db: Session = Depends(get_db)):
    prepo = PortfolioRepository(db); p = prepo.get_portfolio(portfolio_id, access["email"])
    if p is None: raise HTTPException(404, "portfolio_not_found")
    arepo = AssetRepository(db); asset = arepo.get_by_ticker(ticker.upper())
    if asset is None:
        asset = arepo.upsert_asset(ticker=ticker.upper(), asset_type=req.asset_type)
    prepo.upsert_position(p, asset, stage=req.stage, quantity=req.quantity, average_price=req.average_price,
                          target_weight_pct=req.target_weight_pct, classification_override=req.classification_override, notes=req.notes)
    db.commit(); return _portfolio_snapshot(db, p)


@app.post("/portfolios/{portfolio_id}/positions/{ticker}/purchase")
def add_portfolio_purchase(portfolio_id: UUID, ticker: str, req: PortfolioPurchaseRequest,
                           access=Depends(require_permission("can_write_portfolio")), db: Session = Depends(get_db)):
    prepo = PortfolioRepository(db); p = prepo.get_portfolio(portfolio_id, access["email"])
    if p is None: raise HTTPException(404, "portfolio_not_found")
    arepo = AssetRepository(db); asset = arepo.get_by_ticker(ticker.upper())
    if asset is None:
        asset = arepo.upsert_asset(ticker=ticker.upper(), asset_type=req.asset_type)
    try:
        row = prepo.add_purchase(
            p, asset, quantity=req.quantity, unit_price=req.unit_price, stage=req.stage,
            target_weight_pct=req.target_weight_pct,
            classification_override=req.classification_override, notes=req.notes,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    db.commit()
    return {"ticker": asset.ticker, "quantity": _num(row.quantity), "average_price": _num(row.average_price), "snapshot": _portfolio_snapshot(db, p)}


@app.delete("/portfolios/{portfolio_id}/positions/{ticker}")
def delete_portfolio_position(portfolio_id: UUID, ticker: str, access=Depends(require_permission("can_write_portfolio")), db: Session = Depends(get_db)):
    prepo = PortfolioRepository(db); p = prepo.get_portfolio(portfolio_id, access["email"])
    if p is None: raise HTTPException(404, "portfolio_not_found")
    asset = AssetRepository(db).get_by_ticker(ticker.upper())
    if asset is None or not prepo.delete_position(p.id, asset.id): raise HTTPException(404, "position_not_found")
    db.commit(); return {"status": "deleted", "ticker": ticker.upper()}


@app.post("/portfolios/{portfolio_id}/refresh-prices")
def refresh_portfolio_prices(portfolio_id: UUID, access=Depends(require_permission("can_write_portfolio")), db: Session = Depends(get_db)):
    prepo = PortfolioRepository(db); p = prepo.get_portfolio(portfolio_id, access["email"])
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
# V1.11 Restricted research/news
# -----------------------------

@app.get("/insights/news/assets/{ticker}")
def portfolio_asset_news(
    ticker: str,
    portfolio_id: UUID,
    access=Depends(require_permission("can_view_news_insights")),
    db: Session = Depends(get_db),
):
    portfolio_repo = PortfolioRepository(db)
    portfolio = portfolio_repo.get_portfolio(portfolio_id, access["email"])
    if portfolio is None:
        raise HTTPException(404, "portfolio_not_found")
    clean_ticker = ticker.strip().upper()
    asset = next((
        asset for position, asset in portfolio_repo.positions(portfolio.id)
        if asset.ticker == clean_ticker and asset.asset_type == "stock" and float(position.quantity or 0) > 0
    ), None)
    if asset is None:
        raise HTTPException(404, "stock_not_found_in_user_portfolio")
    return _MARKET_NEWS.asset_news(asset.ticker, asset.name, limit=3)


@app.get("/insights/news/portfolios/{portfolio_id}")
def portfolio_all_asset_news(
    portfolio_id: UUID,
    limit_assets: int = Query(default=30, ge=1, le=50),
    access=Depends(require_permission("can_view_news_insights")),
    db: Session = Depends(get_db),
):
    portfolio_repo = PortfolioRepository(db)
    portfolio = portfolio_repo.get_portfolio(portfolio_id, access["email"])
    if portfolio is None:
        raise HTTPException(404, "portfolio_not_found")
    assets = []
    for position, asset in portfolio_repo.positions(portfolio.id):
        if asset.asset_type == "stock" and float(position.quantity or 0) > 0:
            assets.append({"ticker": asset.ticker, "name": asset.name})
    assets.sort(key=lambda item: item["ticker"])
    result = _MARKET_NEWS.portfolio_news(assets[:limit_assets], limit_per_asset=3)
    result.update({
        "portfolio_id": str(portfolio.id),
        "portfolio_name": portfolio.name,
        "total_stocks": len(assets),
        "truncated": len(assets) > limit_assets,
    })
    return result


@app.get("/insights/news/recommendations")
def bank_recommendation_news(
    category: str = Query(default="all", pattern="^(all|brazil|global)$"),
    limit: int = Query(default=20, ge=1, le=50),
    _access=Depends(require_permission("can_view_news_insights")),
    db: Session = Depends(get_db),
):
    assets = AssetRepository(db).list_assets("stock", limit=1200)
    asset_names = {asset.ticker: asset.name or "" for asset in assets}
    return _MARKET_NEWS.recommendations(category=category, limit=limit, asset_names=asset_names)


# -----------------------------
# V1.5 Backtesting
# -----------------------------

@app.get("/backtests/strategies")
def backtest_strategies(_access=Depends(require_permission("can_view_backtests"))):
    return {"periods": PERIOD_LABELS, "strategies": strategy_catalog()}


@app.post("/backtests/run")
def backtest_run(req: BacktestRequest, access=Depends(require_permission("can_run_backtests")), db: Session = Depends(get_db)):
    if req.strategy_id not in STRATEGIES: raise HTTPException(404, "strategy_not_found")
    try:
        result = BacktestService(db).run(
            ticker=req.ticker.upper(), asset_type=req.asset_type, strategy_id=req.strategy_id, period=req.period,
            start=req.start, end=req.end, initial_capital=req.initial_capital, fee_pct=req.fee_pct,
            slippage_pct=req.slippage_pct, risk_free_rate_pct=req.risk_free_rate_pct, params=req.params,
            cash_yield_rate_pct=req.cash_yield_rate_pct, apply_cash_yield=req.apply_cash_yield,
            filters=req.filters.model_dump(exclude_none=True), persist=req.persist,
            owner_email=access["email"], scope="personal", deduplicate_day=True,
        )
        db.commit(); return result
    except ValueError as exc:
        db.rollback(); raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback(); raise HTTPException(502, detail={"backtest_failed": str(exc)})


@app.post("/backtests/compare")
def backtest_compare(req: BacktestCompareRequest, access=Depends(require_permission("can_run_backtests")), db: Session = Depends(get_db)):
    unknown = [s for s in req.strategy_ids if s not in STRATEGIES]
    if unknown: raise HTTPException(404, detail={"strategies_not_found": unknown})
    try:
        rows = BacktestService(db).compare(
            ticker=req.ticker.upper(), asset_type=req.asset_type, strategy_ids=req.strategy_ids, period=req.period,
            start=req.start, end=req.end, initial_capital=req.initial_capital, fee_pct=req.fee_pct,
            slippage_pct=req.slippage_pct, risk_free_rate_pct=req.risk_free_rate_pct,
            cash_yield_rate_pct=req.cash_yield_rate_pct, apply_cash_yield=req.apply_cash_yield,
            filters=req.filters.model_dump(exclude_none=True),
            owner_email=access["email"],
        )
        db.commit(); return rows
    except ValueError as exc:
        db.rollback(); raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback(); raise HTTPException(502, detail={"backtest_compare_failed": str(exc)})


@app.post("/backtests/basket")
def backtest_basket(req: BacktestBasketRequest, _access=Depends(require_permission("can_run_backtests")), db: Session = Depends(get_db)):
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
def backtest_runs(
    ticker: str | None = None, sector: str | None = None, scope: str | None = Query(default=None, pattern="^(personal|official)$"),
    limit: int = Query(default=100, ge=1, le=200), access=Depends(require_permission("can_view_backtests")),
    db: Session = Depends(get_db),
):
    rows = BacktestRepository(db).list_runs(
        owner_email=access["email"], is_owner=bool(access.get("is_owner")), ticker=ticker,
        sector=sector, scope=scope, limit=limit,
    )
    return [run_summary(run, asset) for run, asset in rows]


@app.get("/backtests/runs/{run_id}")
def backtest_run_detail(run_id: UUID, access=Depends(require_permission("can_view_backtests")), db: Session = Depends(get_db)):
    repo = BacktestRepository(db)
    run = repo.get_run(run_id, owner_email=access["email"], is_owner=bool(access.get("is_owner")))
    if run is None: raise HTTPException(404, "backtest_run_not_found")
    asset = db.get(AssetORM, run.asset_id)
    trades = repo.trades(run.id)
    detail = {
        "id": str(run.id), "ticker": asset.ticker if asset else None, "asset_name": asset.name if asset else None,
        "strategy_id": run.strategy_id, "strategy_name": run.strategy_name, "requested_start": run.requested_start,
        "requested_end": run.requested_end, "actual_start": run.actual_start, "actual_end": run.actual_end,
        "initial_capital": _num(run.initial_capital), "fee_pct": _num(run.fee_pct), "slippage_pct": _num(run.slippage_pct),
        "risk_free_rate_pct": _num(run.risk_free_rate_pct), "parameters": run.parameters_json, "metrics": run.metrics_json,
        "equity_curve": run.equity_curve_json, "status": run.status, "created_at": run.created_at,
        "scope": run.scope, "engine_version": run.engine_version, "ranking_score": _num(run.ranking_score),
        "sample_status": run.sample_status,
        "current_signal": {"status": run.current_signal, "as_of": run.signal_as_of},
        "trades": [{
            "sequence": t.sequence, "entry_date": t.entry_date, "entry_price": _num(t.entry_price),
            "exit_date": t.exit_date, "exit_price": _num(t.exit_price), "return_pct": _num(t.return_pct),
            "pnl_value": _num(t.pnl_value), "holding_days": t.holding_days, "exit_reason": t.exit_reason,
        } for t in trades],
    }
    if run.result_json:
        detail = {**detail, **run.result_json}
        detail.update({
            "id": str(run.id), "run_id": str(run.id), "created_at": run.created_at,
            "scope": run.scope, "engine_version": run.engine_version,
        })
    return detail


@app.get("/backtests/leaderboard")
def backtest_leaderboard(
    tickers: str = Query(default="", max_length=2400), sector: str | None = None,
    per_asset: int = Query(default=3, ge=1, le=5),
    _access=Depends(require_permission("can_view_backtests")), db: Session = Depends(get_db),
):
    requested = [item.strip().upper() for item in tickers.replace(";", ",").split(",") if item.strip()]
    if len(requested) > 200:
        raise HTTPException(400, "leaderboard_ticker_limit_200")
    grouped = BacktestRepository(db).leaderboard(
        tickers=requested or None, sector=sector, per_asset=per_asset,
    )
    return {
        "items": {
            ticker: [run_summary(run, asset) for run, asset in rows]
            for ticker, rows in grouped.items()
        },
        "requested": requested, "per_asset": per_asset,
    }


@app.get("/backtests/top")
def top_backtests(
    ticker: str | None = None, sector: str | None = None, limit: int = Query(default=5, ge=1, le=20),
    _access=Depends(require_permission("can_view_backtests")), db: Session = Depends(get_db),
):
    grouped = BacktestRepository(db).leaderboard(
        tickers=[ticker] if ticker else None, sector=sector, per_asset=limit,
    )
    rows = [item for values in grouped.values() for item in values]
    rows.sort(key=lambda item: float(item[0].ranking_score or 0), reverse=True)
    return [run_summary(run, asset) for run, asset in rows[:limit]]


@app.get("/backtests/study")
def backtest_strategy_study(
    limit: int = Query(default=5, ge=1, le=20),
    _access=Depends(require_permission("can_view_backtest_studies")),
    db: Session = Depends(get_db),
):
    records = []
    for run, asset in BacktestRepository(db).strategy_study_runs():
        records.append({
            "ticker": asset.ticker,
            "strategy_id": run.strategy_id,
            "strategy_name": run.strategy_name,
            "ranking_score": _num(run.ranking_score),
            "sample_status": run.sample_status,
            "metrics": run.metrics_json or {},
        })
    result = build_strategy_study(records, top_limit=limit)
    result["generated_at"] = datetime.now(timezone.utc)
    return result


@app.post("/backtests/signals/{ticker}/refresh")
def refresh_backtest_signals(
    ticker: str, access=Depends(require_permission("can_refresh_backtest_signals")), db: Session = Depends(get_db),
):
    grouped = BacktestRepository(db).leaderboard(tickers=[ticker.upper()], per_asset=3)
    leaders = grouped.get(ticker.upper()) or []
    if not leaders:
        raise HTTPException(404, "official_backtests_not_available_for_asset")
    results = []
    try:
        service = BacktestService(db)
        for previous, _asset in leaders:
            if previous.market_date == backtest_market_date():
                results.append({
                    "run_id": str(previous.id), "strategy_name": previous.strategy_name,
                    "current_signal": {"status": previous.current_signal, "as_of": previous.signal_as_of},
                    "cached": True,
                })
                continue
            parameters = previous.parameters_json or {}
            financial = parameters.get("financial") or {}
            result = service.run(
                ticker=ticker.upper(), asset_type="stock", strategy_id=previous.strategy_id, period="5y",
                initial_capital=float(previous.initial_capital), fee_pct=float(previous.fee_pct),
                slippage_pct=float(previous.slippage_pct), risk_free_rate_pct=float(previous.risk_free_rate_pct),
                cash_yield_rate_pct=float(financial.get("cash_yield_rate_pct") or 0),
                apply_cash_yield=bool(financial.get("apply_cash_yield")),
                params=parameters.get("strategy") or {}, filters=parameters.get("filters") or {}, persist=True,
                owner_email=OFFICIAL_OWNER, scope="official", deduplicate_day=True,
            )
            results.append({
                "run_id": result.get("run_id"), "strategy_name": (result.get("strategy") or {}).get("name"),
                "current_signal": result.get("current_signal"), "cached": result.get("cached", False),
            })
        db.commit()
        return {"ticker": ticker.upper(), "updated": results}
    except ValueError as exc:
        db.rollback(); raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback(); raise HTTPException(502, detail={"signal_refresh_failed": str(exc)})


@app.get("/backtests/batch/jobs")
def backtest_batch_jobs(
    limit: int = Query(default=20, ge=1, le=100), _access=Depends(require_owner), db: Session = Depends(get_db),
):
    return [BacktestBatchService.job_dict(job) for job in BacktestBatchService(db).list_jobs(limit)]


@app.post("/backtests/batch/jobs")
def create_backtest_batch_job(
    request: BacktestBatchCreateRequest,
    access=Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        service = BacktestBatchService(db)
        job = service.create_job(
            requested_by=access["email"], source="site", tickers=request.tickers,
            max_combinations=request.max_combinations,
        )
        db.commit()
        return service.job_dict(job)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))


@app.patch("/backtests/batch/jobs/{job_id}/failed")
def fail_backtest_batch_job(
    job_id: UUID,
    request: BacktestBatchFailureRequest,
    _access=Depends(require_owner),
    db: Session = Depends(get_db),
):
    service = BacktestBatchService(db)
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(404, "backtest_batch_job_not_found")
    service.mark_failed(job, code=request.code, message=request.message, details=request.details)
    db.commit()
    return service.job_dict(job)
