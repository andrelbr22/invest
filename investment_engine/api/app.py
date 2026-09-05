from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone
from secrets import compare_digest, token_urlsafe
from pathlib import Path
import csv
import io
import logging
import math
import re
import threading
from time import monotonic
from uuid import UUID, uuid4
from typing import Literal
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth, OAuthError
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..core.valuation.graham import graham_number, add_upside
from ..core.valuation.dividend_target import dividend_yield_target_price
from ..core.strategies.presets import STOCK_STRATEGIES, FII_STRATEGIES
from ..core.screening.filters import stock_passes, fii_passes
from ..core.screening.advanced import advanced_screen, row_from_orm, technical_features
from ..core.screening.universe import COMPANY_SIZE_LABELS, company_size_category
from ..core.repositories.assets import AssetRepository
from ..core.repositories.portfolio import PortfolioRepository
from ..core.repositories.screening_filters import SavedScreeningFilterRepository
from ..core.repositories.backtests import BacktestRepository, backtest_market_date, run_summary
from ..core.repositories.access import AccessPolicyRepository, PERMISSION_FIELDS, full_owner_policy, policy_dict
from ..core.repositories.news_cache import NewsCacheRepository, news_cache_dict, news_market_date
from ..core.repositories.alerts import AlertRepository, alert_dict, event_dict
from ..core.repositories.background_jobs import BackgroundJobRepository, background_job_dict
from ..core.repositories.economic_series import InterestCurveHistoryRepository, SharedSnapshotRepository
from ..core.jobs.schedules import (
    REFRESH_SCHEDULES,
    all_refresh_statuses,
    enqueue_refresh,
    refresh_status,
)
from ..core.jobs.worker import BackgroundWorker
from ..core.portfolio.service import build_portfolio_snapshot, classification_for, localize_classification
from ..core.portfolio.custom_investments import (
    CUSTOM_INVESTMENT_CATEGORIES,
    CustomInvestmentRepository,
    custom_investment_dict,
)
from ..core.finance.service import FINANCE_CATEGORIES, FinanceRepository, month_start, transaction_dict
from ..core.backtesting.service import BacktestService, PERIOD_LABELS
from ..core.backtesting.strategies import STRATEGIES, strategy_catalog
from ..core.backtesting.batch import BacktestBatchService, OFFICIAL_OWNER
from ..integrations.backtest_delivery import CALLBACK_API_VERSION, delivery_checksum
from ..core.backtesting.study import build_strategy_configuration_catalog, build_strategy_study
from ..core.alerts.catalog import market_alert_catalog, market_alert_item
from ..core.alerts.service import AlertMonitor, AlertService, valid_email
from ..integrations.email_delivery import AlertEmailSender
from ..integrations.github_actions import GitHubActionsError, dispatch_official_backtests
from ..infrastructure.db.models import AssetORM, BacktestRequestUsageORM, UserNewsCacheORM
from ..core.instruments import is_alertable_b3_asset, is_supported_ticker
from ..core.models.strategy import StockFilterSet, FiiFilterSet
from ..infrastructure.db.session import get_session_factory
from ..core.services_v14 import calculate_asset_intelligence
from ..data.ingestion.prices import PriceIngestionService
from ..data.ingestion.pipeline import MarketIngestionPipeline
from ..data.providers.b3_indices import B3IndexProvider
from ..data.providers.news import MarketNewsService
from ..infrastructure.config import settings
from .. import __version__


_ALERT_MONITOR = AlertMonitor()
_REQUEST_LOGGER = logging.getLogger("investment_engine.http")
_IN_PROCESS_WORKER_STOP = threading.Event()
_IN_PROCESS_WORKER_THREAD: threading.Thread | None = None


@asynccontextmanager
async def _application_lifespan(_application: FastAPI):
    global _IN_PROCESS_WORKER_THREAD
    if settings.alert_monitor_enabled:
        _ALERT_MONITOR.start()
    if settings.in_process_background_worker_enabled:
        _IN_PROCESS_WORKER_STOP.clear()
        worker = BackgroundWorker(
            poll_seconds=settings.background_worker_poll_seconds,
            lease_timeout_seconds=settings.background_job_lease_timeout_seconds,
            scheduler_enabled=settings.background_scheduler_enabled,
            scheduler_tick_seconds=settings.background_scheduler_tick_seconds,
        )
        _IN_PROCESS_WORKER_THREAD = threading.Thread(
            target=worker.run_forever,
            args=(_IN_PROCESS_WORKER_STOP,),
            name="staging-background-worker",
            daemon=True,
        )
        _IN_PROCESS_WORKER_THREAD.start()
    try:
        yield
    finally:
        _ALERT_MONITOR.stop()
        _IN_PROCESS_WORKER_STOP.set()
        if _IN_PROCESS_WORKER_THREAD and _IN_PROCESS_WORKER_THREAD.is_alive():
            _IN_PROCESS_WORKER_THREAD.join(timeout=5)
        _IN_PROCESS_WORKER_THREAD = None


app = FastAPI(
    title="Formação do Investidor",
    version=__version__,
    lifespan=_application_lifespan,
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)
if settings.app_environment in {"production", "staging"} and settings.app_auth_required and len(settings.session_secret) < 32:
    raise RuntimeError("SESSION_SECRET deve ter ao menos 32 caracteres em produção.")
_SESSION_SECRET = settings.session_secret or token_urlsafe(48)
app.add_middleware(
    SessionMiddleware,
    secret_key=_SESSION_SECRET,
    same_site="lax",
    https_only=bool(settings.secure_cookies),
    max_age=60 * 60 * 12,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

_WEB_ROOT = Path(__file__).resolve().parents[1] / "web"
app.mount("/ui-assets", StaticFiles(directory=str(_WEB_ROOT / "static")), name="ui-assets")

_OAUTH = OAuth()
if settings.google_client_id and settings.google_client_secret:
    _OAUTH.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url=settings.google_server_metadata_url,
        client_kwargs={"scope": "openid email profile"},
    )

_INDEX_PORTFOLIO_CACHE: dict[str, tuple[float, dict]] = {}
_INDEX_PORTFOLIO_TTL_SECONDS = 6 * 60 * 60
_MARKET_NEWS = MarketNewsService()
_NEWS_QUEUE_LOCK = threading.Lock()
_MARKET_DASHBOARD_OWNER = "market-dashboard@system.local"
_MARKET_DASHBOARD_CACHE_KEY = "main-v6"
def _portfolio_news_assets(db: Session, portfolio_id) -> list[dict]:
    assets = []
    for position, asset in PortfolioRepository(db).positions(portfolio_id):
        if (
            asset.asset_type == "stock"
            and is_supported_ticker(asset.ticker, asset.asset_type)
            and float(position.quantity or 0) > 0
        ):
            assets.append({"ticker": asset.ticker, "name": asset.name})
    assets.sort(key=lambda item: item["ticker"])
    return assets


@app.middleware("http")
async def security_headers(request, call_next):
    supplied_request_id = str(request.headers.get("X-Request-ID") or "").strip()
    request_id = supplied_request_id if re.fullmatch(r"[A-Za-z0-9_.:-]{8,80}", supplied_request_id) else str(uuid4())
    request.state.request_id = request_id
    started = monotonic()
    try:
        response = await call_next(request)
    except Exception:
        _REQUEST_LOGGER.exception(
            "http_request_failed request_id=%s method=%s path=%s",
            request_id, request.method, request.url.path,
        )
        raise
    duration_ms = round((monotonic() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; form-action 'self' https://accounts.google.com; "
        "frame-ancestors 'none'; object-src 'none'; img-src 'self' data: https:; "
        "style-src 'self'; script-src 'self'; connect-src 'self'"
    )
    private_path = request.url.path.startswith((
        "/session", "/search", "/alerts", "/portfolios", "/backtests",
        "/access", "/insights", "/automation", "/market-dashboard", "/admin/jobs",
    ))
    response.headers["Cache-Control"] = "no-store" if private_path else "no-cache"
    _REQUEST_LOGGER.info(
        "http_request request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id, request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


def get_db():
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def _request_email(request: Request, x_app_user_email: str = Header(default="")) -> str:
    session_user = request.session.get("user") if hasattr(request, "session") else None
    if isinstance(session_user, dict):
        email = str(session_user.get("email") or "").strip().lower()
        if email:
            return email
    if not settings.app_auth_required:
        return str(x_app_user_email or "").strip().lower() or "local-owner@localhost"
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


def require_backtest_callback(
    authorization: str = Header(default=""),
    callback_version: str = Header(default="", alias="X-Backtest-Callback-Version"),
):
    expected = str(settings.backtest_callback_token or "").strip()
    if len(expected) < 32:
        raise HTTPException(503, "backtest_callback_not_configured")
    scheme, separator, supplied = str(authorization or "").partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not compare_digest(supplied.strip(), expected):
        raise HTTPException(401, "invalid_backtest_callback_credential")
    if callback_version != CALLBACK_API_VERSION:
        raise HTTPException(400, "unsupported_backtest_callback_version")
    return True


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
    sector_override: str | None = Field(default=None, max_length=120)
    segment_override: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class PortfolioPurchaseRequest(BaseModel):
    asset_type: str = Field(default="stock", pattern="^(stock|fii|etf|bdr|future|fixed_income|crypto|other)$")
    quantity: float = Field(gt=0)
    unit_price: float = Field(gt=0)
    stage: str = Field(default="position", pattern="^(position|target|analysis)$")
    target_weight_pct: float | None = Field(default=None, ge=0, le=100)
    classification_override: str | None = Field(default=None, max_length=120)
    sector_override: str | None = Field(default=None, max_length=120)
    segment_override: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class PortfolioCustomInvestmentCreateRequest(BaseModel):
    category: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    institution: str | None = Field(default=None, max_length=160)
    sector: str | None = Field(default=None, max_length=120)
    segment: str | None = Field(default=None, max_length=120)
    application_date: date
    maturity_date: date | None = None
    invested_value: float = Field(gt=0)
    current_value: float = Field(ge=0)
    current_value_as_of: date = Field(default_factory=date.today)
    benchmark: str | None = Field(default=None, max_length=80)
    liquidity: str | None = Field(default=None, max_length=120)
    notes: str | None = None

    @field_validator("category")
    @classmethod
    def valid_category(cls, value):
        if value not in CUSTOM_INVESTMENT_CATEGORIES:
            raise ValueError("invalid_custom_investment_category")
        return value


class PortfolioCustomInvestmentUpdateRequest(BaseModel):
    category: str | None = Field(default=None, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    institution: str | None = Field(default=None, max_length=160)
    sector: str | None = Field(default=None, max_length=120)
    segment: str | None = Field(default=None, max_length=120)
    application_date: date | None = None
    maturity_date: date | None = None
    invested_value: float | None = Field(default=None, gt=0)
    current_value: float | None = Field(default=None, ge=0)
    current_value_as_of: date | None = None
    benchmark: str | None = Field(default=None, max_length=80)
    liquidity: str | None = Field(default=None, max_length=120)
    notes: str | None = None

    @field_validator("category")
    @classmethod
    def valid_category(cls, value):
        if value is not None and value not in CUSTOM_INVESTMENT_CATEGORIES:
            raise ValueError("invalid_custom_investment_category")
        return value


class FinanceTransactionCreateRequest(BaseModel):
    transaction_date: date
    competence_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    kind: Literal["income", "expense"]
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0)
    status: Literal["planned", "paid", "received", "overdue"] = "planned"
    institution: str | None = Field(default=None, max_length=120)
    payment_method: str | None = Field(default=None, max_length=80)
    notes: str | None = None


class FinanceTransactionUpdateRequest(BaseModel):
    transaction_date: date | None = None
    competence_month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    kind: Literal["income", "expense"] | None = None
    category: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, min_length=1, max_length=200)
    amount: float | None = Field(default=None, gt=0)
    status: Literal["planned", "paid", "received", "overdue"] | None = None
    institution: str | None = Field(default=None, max_length=120)
    payment_method: str | None = Field(default=None, max_length=80)
    notes: str | None = None


class FinanceBudgetRequest(BaseModel):
    competence_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    values: dict[str, float] = Field(default_factory=dict)


class BacktestNumericRangeRequest(BaseModel):
    min: float | None = None
    max: float | None = None


class BacktestTrendFilterRequest(BaseModel):
    enabled: bool = False
    direction: str = Field(default="up", pattern="^(up|down)$")
    ma_type: Literal["sma", "ema"] = "sma"
    period: Literal[8, 9, 21, 50, 200] = 21
    mode: str = Field(default="price_above", pattern="^(price_above|sma_rising|price_above_or_sma_rising|price_above_and_sma_rising)$")
    slope_lookback: int = Field(default=5, ge=1, le=100)

    @model_validator(mode="after")
    def valid_moving_average(self):
        if (self.ma_type, self.period) not in {
            ("sma", 8), ("ema", 9), ("sma", 21), ("sma", 50), ("sma", 200),
        }:
            raise ValueError("unsupported_trend_moving_average")
        return self


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
    strategy_ids: list[str] = Field(min_length=1, max_length=5)
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


class BacktestMatrixRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=10)
    strategy_ids: list[str] = Field(min_length=1, max_length=5)
    execution_mode: Literal["compare", "combined"] = "compare"
    combination_rule: Literal["all", "any", "majority"] = "all"
    asset_type: str = Field(default="stock", pattern="^(stock|fii|etf|bdr|future|other)$")
    period: str = Field(default="5y", pattern="^(6m|1y|2y|3y|5y|10y|15y|20y|custom)$")
    start: datetime | None = None
    end: datetime | None = None
    initial_capital: float = Field(default=10000.0, gt=0)
    fee_pct: float = Field(default=0.03, ge=0, le=5)
    slippage_pct: float = Field(default=0.05, ge=0, le=5)
    risk_free_rate_pct: float = Field(default=0.0, ge=-20, le=100)
    apply_cash_yield: bool = False
    cash_yield_rate_pct: float = Field(default=0.0, gt=-100, le=100)
    filters: BacktestFiltersRequest = Field(default_factory=BacktestFiltersRequest)


class BacktestBatchCreateRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=100)
    max_combinations: int = Field(default=200, ge=1, le=200)


class BacktestBatchFailureRequest(BaseModel):
    code: str = Field(default="external_failure", max_length=80)
    message: str = Field(max_length=500)
    details: dict = Field(default_factory=dict)


class BacktestBatchCancellationRequest(BaseModel):
    reason: str = Field(default="Cancelamento solicitado pelo administrador.", max_length=500)
    details: dict = Field(default_factory=dict)


class BacktestAutomationStartRequest(BaseModel):
    source: Literal["manual", "scheduled"] = "manual"
    job_id: UUID | None = None
    tickers: list[str] = Field(default_factory=list, max_length=100)
    max_combinations: int = Field(default=200, ge=1, le=200)


class BacktestAutomationAssetRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    checksum: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    completed_runs: int = Field(ge=0, le=200)
    failed_runs: int = Field(ge=0, le=200)
    chunk_index: int = Field(default=1, ge=1, le=200)
    chunk_count: int = Field(default=1, ge=1, le=200)
    errors: list[dict] = Field(default_factory=list, max_length=200)
    results: list[dict] = Field(default_factory=list, max_length=200)


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
    volume_daily_above_ma9: bool = False
    volume_monthly_above_ma9: bool = False


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
    company_sizes: list[str] = Field(default_factory=list, max_length=3)
    ibov_membership: Literal["any", "inside", "outside"] = "any"

    @field_validator("company_sizes", mode="before")
    @classmethod
    def normalize_company_sizes(cls, value):
        aliases = {"blue_chip": "large", "large_cap": "large", "mid_cap": "mid", "middle_cap": "mid", "small_cap": "small"}
        normalized = []
        for item in value or []:
            key = aliases.get(str(item), str(item))
            if key not in COMPANY_SIZE_LABELS:
                raise ValueError("invalid_company_size")
            if key not in normalized:
                normalized.append(key)
        return normalized


class MarketSyncRequest(BaseModel):
    asset_type: Literal["stock", "fii", "other_b3"] = "stock"
    include_technicals: bool = True


class AccessRegisterRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=180)


class AccessPolicyUpdateRequest(BaseModel):
    role: str | None = Field(default=None, pattern="^(visitor|member|admin)$")
    status: str | None = Field(default=None, pattern="^(pending|approved|blocked)$")
    can_view_market: bool | None = None
    can_use_advanced_filters: bool | None = None
    can_use_fdi_analysis: bool | None = None
    can_use_alb_analysis: bool | None = None
    can_use_graham_valuation: bool | None = None
    can_use_dividend_ceiling: bool | None = None
    can_view_portfolio: bool | None = None
    can_write_portfolio: bool | None = None
    can_view_finances: bool | None = None
    can_write_finances: bool | None = None
    can_view_backtests: bool | None = None
    can_run_backtests: bool | None = None
    can_refresh_backtest_signals: bool | None = None
    can_view_backtest_studies: bool | None = None
    can_view_news_insights: bool | None = None
    can_use_price_alerts: bool | None = None
    can_alert_price_above: bool | None = None
    can_alert_price_below: bool | None = None
    can_alert_change_positive: bool | None = None
    can_alert_change_negative: bool | None = None
    can_sync_market: bool | None = None
    custom_filter_limit: int | None = Field(default=None, ge=0, le=3)
    alert_asset_limit: int | None = Field(default=None)
    backtest_asset_limit: int | None = Field(default=None)
    backtest_daily_limit: int | None = Field(default=None)
    backtest_strategy_limit: int | None = Field(default=None)
    backtest_cooldown_seconds: int | None = Field(default=None, ge=60, le=3600)


class AlertPreferenceRequest(BaseModel):
    secondary_email: str | None = Field(default=None, max_length=320)


class PriceAlertCreateRequest(BaseModel):
    market_scope: Literal["b3", "market"]
    symbol: str = Field(min_length=1, max_length=32)
    price_above: float | None = Field(default=None, gt=0)
    price_below: float | None = Field(default=None, gt=0)
    change_positive_pct: float | None = Field(default=None, gt=0, le=1000)
    change_negative_pct: float | None = Field(default=None, gt=0, le=1000)


class PriceAlertStatusRequest(BaseModel):
    status: Literal["active", "disabled"]


class SavedScreeningFilterCreateRequest(BaseModel):
    asset_type: Literal["stock", "fii"]
    name: str | None = Field(default=None, max_length=120)
    filters: dict = Field(default_factory=dict)


class SavedScreeningFilterUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    filters: dict | None = None


@app.get("/", include_in_schema=False)
def web_application():
    return FileResponse(_WEB_ROOT / "index.html")


@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    return FileResponse(_WEB_ROOT / "static" / "favicon.svg", media_type="image/svg+xml")


@app.get("/login", include_in_schema=False)
async def login(request: Request):
    if not settings.app_auth_required:
        return RedirectResponse("/")
    client = _OAUTH.create_client("google")
    if client is None or not settings.google_auth_configured:
        raise HTTPException(503, "google_auth_not_configured")
    destination = str(request.query_params.get("next") or "/")
    request.session["oauth_next"] = destination if destination == "/testefdi/" else "/"
    redirect_uri = settings.oauth_redirect_uri.strip() or str(request.url_for("oauth2callback"))
    return await client.authorize_redirect(request, redirect_uri)


@app.get("/oauth2callback", include_in_schema=False, name="oauth2callback")
async def oauth2callback(request: Request):
    client = _OAUTH.create_client("google")
    if client is None:
        return RedirectResponse("/?auth_error=not_configured", status_code=303)
    try:
        token = await client.authorize_access_token(request)
        userinfo = token.get("userinfo") or await client.userinfo(token=token)
    except OAuthError:
        return RedirectResponse("/?auth_error=authorization_failed", status_code=303)
    email = str((userinfo or {}).get("email") or "").strip().lower()
    verified = (userinfo or {}).get("email_verified")
    if not email or verified is False:
        return RedirectResponse("/?auth_error=email_not_verified", status_code=303)
    display_name = str((userinfo or {}).get("name") or email.split("@", 1)[0]).strip()[:160]
    destination = request.session.get("oauth_next") if request.session.get("oauth_next") == "/testefdi/" else "/"
    request.session.clear()
    request.session["user"] = {
        "email": email,
        "name": display_name,
        "picture": str((userinfo or {}).get("picture") or "")[:500],
    }
    db = get_session_factory()()
    try:
        AccessPolicyRepository(db).register(email, display_name, is_owner=email in settings.owner_emails)
        db.commit()
    finally:
        db.close()
    return RedirectResponse(destination, status_code=303)


@app.post("/logout", include_in_schema=False)
def logout(request: Request):
    request.session.clear()
    return {"status": "signed_out"}


@app.get("/session/me", include_in_schema=False)
def session_me(request: Request, db: Session = Depends(get_db)):
    session_user = request.session.get("user") if hasattr(request, "session") else None
    if not settings.app_auth_required and not isinstance(session_user, dict):
        session_user = {"email": "local-owner@localhost", "name": "Ambiente local", "picture": ""}
    if not isinstance(session_user, dict) or not session_user.get("email"):
        return {
            "authenticated": False,
            "auth_required": settings.app_auth_required,
            "google_configured": settings.google_auth_configured,
        }
    email = str(session_user["email"]).strip().lower()
    return {
        "authenticated": True,
        "auth_required": settings.app_auth_required,
        "user": session_user,
        "access": _access_policy(db, email),
    }


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__, "environment": settings.app_environment}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception:
        raise HTTPException(503, detail={"database": "unreachable"})


@app.get("/ready")
def readiness(db: Session = Depends(get_db)):
    """Report whether this process can safely receive application traffic."""
    try:
        db.execute(text("SELECT 1"))
        revision = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
    except Exception:
        raise HTTPException(503, detail={"status": "not_ready", "database": "unreachable"})
    if not revision:
        raise HTTPException(503, detail={"status": "not_ready", "migration": "unknown"})
    return {
        "status": "ready",
        "version": __version__,
        "environment": settings.app_environment,
        "database": "reachable",
        "migration": revision,
    }


@app.get("/admin/jobs")
def list_background_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    _access=Depends(require_owner),
    db: Session = Depends(get_db),
):
    return [background_job_dict(row) for row in BackgroundJobRepository(db).list_recent(limit)]


@app.get("/admin/jobs/{job_id}")
def get_background_job(
    job_id: UUID,
    _access=Depends(require_owner),
    db: Session = Depends(get_db),
):
    row = BackgroundJobRepository(db).get(job_id)
    if row is None:
        raise HTTPException(404, "background_job_not_found")
    return background_job_dict(row, include_payload=True)


@app.post("/admin/jobs/{job_id}/retry")
def retry_background_job(
    job_id: UUID,
    access=Depends(require_owner),
    db: Session = Depends(get_db),
):
    repository = BackgroundJobRepository(db)
    row = repository.get(job_id)
    if row is None:
        raise HTTPException(404, "background_job_not_found")
    try:
        repository.retry(row, requested_by=access["email"])
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))
    return background_job_dict(row)


@app.get("/debug/db-counts")
def debug_db_counts(_access=Depends(require_owner), db: Session = Depends(get_db)):
    names = ["assets", "fundamental_snapshots", "technical_snapshots", "score_snapshots", "valuation_snapshots", "price_bars", "portfolios", "portfolio_positions", "portfolio_custom_investments", "finance_transactions", "finance_monthly_budgets", "interest_curve_snapshots", "backtest_runs", "backtest_trades", "backtest_batch_jobs"]
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
    if any(changes.get(field) for field in (
        "can_use_advanced_filters", "can_use_fdi_analysis", "can_use_alb_analysis",
        "can_use_graham_valuation", "can_use_dividend_ceiling", "can_sync_market",
    )) or int(changes.get("custom_filter_limit") or 0)>0:
        changes["can_view_market"] = True
    if changes.get("can_use_alb_analysis"):
        changes["can_use_graham_valuation"] = True
        changes["can_use_dividend_ceiling"] = True
    if changes.get("can_write_portfolio") or changes.get("can_view_news_insights") or changes.get("can_use_price_alerts"):
        changes["can_view_portfolio"] = True
    if changes.get("can_write_finances"):
        changes["can_view_finances"] = True
    if changes.get("can_run_backtests") or changes.get("can_refresh_backtest_signals") or changes.get("can_view_backtest_studies"):
        changes["can_view_backtests"] = True
    if changes.get("can_run_backtests"):
        changes.setdefault("backtest_asset_limit", 1)
        changes.setdefault("backtest_daily_limit", 1)
        changes.setdefault("backtest_strategy_limit", 1)
        changes.setdefault("backtest_cooldown_seconds", 60)
    if changes.get("can_view_market") is False:
        changes["can_use_advanced_filters"] = False
        changes["can_use_fdi_analysis"] = False
        changes["can_use_alb_analysis"] = False
        changes["can_use_graham_valuation"] = False
        changes["can_use_dividend_ceiling"] = False
        changes["can_sync_market"] = False
        changes["custom_filter_limit"] = 0
    if changes.get("can_view_portfolio") is False:
        changes["can_write_portfolio"] = False
        changes["can_view_news_insights"] = False
        changes["can_use_price_alerts"] = False
        changes["alert_asset_limit"] = 0
    if changes.get("can_view_finances") is False:
        changes["can_write_finances"] = False
    if (
        changes.get("can_use_price_alerts") is False
        or ("alert_asset_limit" in changes and int(changes.get("alert_asset_limit") or 0) == 0)
    ):
        changes["can_use_price_alerts"] = False
        changes["alert_asset_limit"] = 0
        changes["can_alert_price_above"] = False
        changes["can_alert_price_below"] = False
        changes["can_alert_change_positive"] = False
        changes["can_alert_change_negative"] = False
    if changes.get("alert_asset_limit") is not None and int(changes["alert_asset_limit"]) not in {0, 1, 3, 5, 10}:
        raise HTTPException(422, "invalid_alert_asset_limit")
    if changes.get("can_view_backtests") is False:
        changes["can_run_backtests"] = False
        changes["can_refresh_backtest_signals"] = False
        changes["can_view_backtest_studies"] = False
        changes["backtest_asset_limit"] = 0
        changes["backtest_daily_limit"] = 0
        changes["backtest_strategy_limit"] = 0
    if changes.get("can_run_backtests") is False:
        changes["backtest_asset_limit"] = 0
        changes["backtest_daily_limit"] = 0
        changes["backtest_strategy_limit"] = 0
    if changes.get("backtest_asset_limit") is not None and int(changes["backtest_asset_limit"]) not in {0, 1, 3, 5, 10}:
        raise HTTPException(422, "invalid_backtest_asset_limit")
    if changes.get("backtest_daily_limit") is not None and int(changes["backtest_daily_limit"]) not in {0, 1, 5, 10, 20}:
        raise HTTPException(422, "invalid_backtest_daily_limit")
    if changes.get("backtest_strategy_limit") is not None and int(changes["backtest_strategy_limit"]) not in {0, 1, 2, 3, 5}:
        raise HTTPException(422, "invalid_backtest_strategy_limit")
    row = AccessPolicyRepository(db).update(clean, **changes)
    if row is None:
        raise HTTPException(404, "user_not_found")
    updated_policy = policy_dict(row)
    AlertRepository(db).enforce_policy(
        clean,
        limit=int(updated_policy.get("alert_asset_limit") or 0) if updated_policy.get("can_use_price_alerts") else 0,
        permissions=_alert_rule_permissions(updated_policy),
    )
    db.commit()
    return updated_policy


def _saved_filter_dict(row):
    return {
        "id": str(row.id), "name": row.name, "asset_type": row.asset_type,
        "filters": row.filters_json or {}, "created_at": row.created_at, "updated_at": row.updated_at,
    }


def _validated_saved_filters(asset_type: str, payload: dict) -> dict:
    payload = payload or {}
    if payload.get("schema_version") == 2:
        raw_configuration = payload.get("configuration") or {}
    elif any(key in payload for key in (
        "fundamental_filters", "score_filters", "valuation_flags", "technical_filters",
        "company_sizes", "ibov_membership", "pivot_timeframe", "trend_period",
    )):
        raw_configuration = payload
    else:
        model = StockFilterSet if asset_type == "stock" else FiiFilterSet
        return model(**payload).model_dump()

    configuration = dict(raw_configuration)
    configuration["asset_type"] = asset_type
    validated = AdvancedScreenRequest(**configuration)
    return {
        "schema_version": 2,
        "configuration": validated.model_dump(mode="json"),
    }


def _preset_screen_configuration(asset_type: str, strategy) -> dict:
    """Expose system criteria in the same shape used by the advanced screener UI."""
    values = strategy.filters.model_dump()
    fundamental_filters: dict[str, dict] = {}

    def add_range(field: str, *, minimum=None, maximum=None):
        if minimum is not None or maximum is not None:
            fundamental_filters[field] = {"min": minimum, "max": maximum}

    if asset_type == "stock":
        add_range("roe_pct", minimum=values.get("roe_min"))
        add_range("net_margin_pct", minimum=values.get("net_margin_min"))
        add_range("ebit_margin_pct", minimum=values.get("ebit_margin_min"))
        add_range("revenue_cagr_5y_pct", minimum=values.get("revenue_cagr_5y_min"))
        add_range("pe", minimum=values.get("pe_min"), maximum=values.get("pe_max"))
        add_range("pbv", maximum=values.get("pbv_max"))
        add_range("dividend_yield_pct", minimum=values.get("dividend_yield_min"))
        add_range("ev_ebitda", maximum=values.get("ev_ebitda_max"))
        add_range("gross_debt_to_equity", maximum=values.get("gross_debt_to_equity_max"))
        add_range("current_ratio", minimum=values.get("current_ratio_min"))
        add_range("daily_liquidity", minimum=values.get("daily_liquidity_min"))
        valuation_flags = {"below_graham": bool(values.get("require_below_graham"))}
    else:
        add_range("pbv", maximum=values.get("pbv_max"))
        add_range("dividend_yield_pct", minimum=values.get("dividend_yield_min"))
        add_range("ffo_yield_pct", minimum=values.get("ffo_yield_min"))
        add_range("cap_rate_pct", minimum=values.get("cap_rate_min"))
        add_range("vacancy_pct", maximum=values.get("vacancy_max"))
        add_range("daily_liquidity", minimum=values.get("daily_liquidity_min"))
        valuation_flags = {"below_barsi_6pct": bool(values.get("require_below_dividend_target"))}

    return AdvancedScreenRequest(
        asset_type=asset_type,
        fundamental_filters=fundamental_filters,
        valuation_flags=valuation_flags,
        limit=50,
    ).model_dump(mode="json")


@app.get("/screen/presets")
def screening_presets(
    asset_type: Literal["stock", "fii"] = "stock",
    _access=Depends(require_permission("can_view_market")),
):
    strategies = STOCK_STRATEGIES if asset_type == "stock" else FII_STRATEGIES
    return {
        "asset_type": asset_type,
        "items": [
            {
                "id": strategy.id,
                "name": strategy.name,
                "system": True,
                "configuration": _preset_screen_configuration(asset_type, strategy),
                "weights": strategy.weights.model_dump() if asset_type == "stock" else None,
            }
            for strategy in strategies.values()
        ],
    }


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
    deactivated = pipeline.repo.deactivate_unsupported_assets()
    if deactivated:
        db.commit()
    steps["catalog_cleanup"] = {"status": "ok", "deactivated": len(deactivated)}

    def run_step(name, operation):
        try:
            result = operation()
            db.commit()
            steps[name] = {
                "status": "ok",
                "received": result.rows_received,
                "saved": result.rows_valid,
                "rejected": result.rows_rejected,
                "filtered": max(0, result.rows_received - result.rows_valid - result.rows_rejected),
                "warnings": result.warnings,
            }
        except Exception as exc:
            db.rollback()
            steps[name] = {"status": "error", "message": str(exc)}

    if req.asset_type == "stock":
        run_step("fundamentals", pipeline.ingest_stocks)
        if req.include_technicals:
            run_step("catalog_and_technicals", lambda: pipeline.ingest_technicals("stock"))
    elif req.asset_type == "fii":
        run_step("fundamentals", pipeline.ingest_fiis)
        if req.include_technicals:
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


@app.get("/data/catalog-summary")
def market_catalog_summary(_access=Depends(require_permission("can_sync_market")), db: Session = Depends(get_db)):
    """Small administrative summary; never transfers the full asset catalog."""
    rows = db.execute(
        select(AssetORM.asset_type, func.count(AssetORM.id))
        .where(AssetORM.is_active.is_(True))
        .group_by(AssetORM.asset_type)
        .order_by(AssetORM.asset_type)
    ).all()
    counts = {str(asset_type): int(quantity) for asset_type, quantity in rows}
    return {
        "counts": counts,
        "groups": {
            "stock": counts.get("stock", 0),
            "fii": counts.get("fii", 0),
            "other_b3": sum(counts.get(item, 0) for item in ("etf", "bdr", "future")),
        },
    }


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


@app.get("/search")
def global_search(
    q: str = Query(min_length=1, max_length=80),
    _access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    clean = str(q or "").strip().upper()
    panel_by_type = {
        "stock": "stocks", "fii": "fiis", "etf": "etfs",
        "bdr": "bdrs", "future": "futures",
    }
    items = [
        {
            "symbol": asset.ticker, "label": asset.name or asset.ticker,
            "asset_type": asset.asset_type, "area": "analysis",
            "panel": panel_by_type.get(asset.asset_type, "other"),
        }
        for asset in AssetRepository(db).search_assets(clean, limit=15)
    ]
    market_tab_by_group = {
        "Brasil": "overview",
        "Índices globais": "global",
        "Risco": "global",
        "Commodities": "global",
        "Criptoativos": "crypto",
        "Câmbio": "crypto",
    }
    for market_item in market_alert_catalog():
        haystack = f"{market_item['key']} {market_item['label']}".upper()
        if clean in haystack:
            items.append({
                "symbol": market_item["key"], "label": market_item["label"],
                "asset_type": "market_indicator", "area": "dashboard",
                "panel": "market", "group": market_item.get("group"),
                "target_tab": market_tab_by_group.get(market_item.get("group"), "overview"),
            })
    return {"query": clean, "items": items[:20]}


@app.get("/assets/{ticker}")
def asset_detail(ticker: str, access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db)):
    repo = AssetRepository(db)
    asset = repo.get_by_ticker(ticker.upper())
    if asset is None:
        raise HTTPException(404, "asset_not_found")
    fundamentals = repo.latest_fundamentals(asset.id)
    technical = repo.latest_technical(asset.id)
    score = repo.latest_scores(asset.id)
    derived = row_from_orm(asset, fundamentals, technical, score)
    history = repo.price_history(asset.id, limit=760)
    features = technical_features(history, trend_period=21, pivot_timeframe="daily")
    leaders = []
    if access.get("can_view_backtests"):
        leaders = [run_summary(run, leader_asset) for run, leader_asset in BacktestRepository(db).leaderboard(
            tickers=[asset.ticker], per_asset=3,
        ).get(asset.ticker, [])]
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
        "derived": derived.get("fundamentals") or {},
        "technical_analysis": features,
        "scores": derived.get("scores") or {},
        "backtests": leaders,
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
    price = _num(fundamental.price) if fundamental else None
    pe = _num(fundamental.pe) if fundamental else None
    pbv = _num(fundamental.pbv) if fundamental else None
    graham = add_upside(
        graham_number(
            price / pe if price is not None and pe not in (None, 0) else None,
            price / pbv if price is not None and pbv not in (None, 0) else None,
        ),
        price,
    )
    dy = _num(fundamental.dividend_yield_pct) if fundamental else None
    barsi = price * dy / 6.0 if price is not None and price > 0 and dy is not None and dy >= 0 else None
    return {
        **_screen_identity(asset),
        "price": price,
        "pe": pe,
        "pbv": pbv,
        "dy": dy,
        "roe": _num(fundamental.roe_pct) if fundamental else None,
        "graham_number": graham.value,
        "graham_upside_pct": graham.upside_pct,
        "barsi_ceiling_price": barsi,
        "barsi_upside_pct": ((barsi / price) - 1.0) * 100.0 if barsi is not None and price else None,
        **_screen_scores(score),
    }


def _authorized_stock_row(row: dict, access: dict | None) -> dict:
    access = access or {}
    if not (access.get("can_use_graham_valuation") or access.get("can_use_alb_analysis")):
        row.pop("graham_number", None)
        row.pop("graham_upside_pct", None)
    if not (access.get("can_use_dividend_ceiling") or access.get("can_use_alb_analysis")):
        row.pop("barsi_ceiling_price", None)
        row.pop("barsi_upside_pct", None)
    return row


def _stock_screen_result(rows, access: dict | None = None):
    return [_authorized_stock_row(_stock_screen_row(asset, fundamental, score), access) for asset, fundamental, score in rows]


def _require_system_analysis_access(strategy_id: str, access: dict) -> None:
    permission = {"cnpi": "can_use_fdi_analysis", "alb": "can_use_alb_analysis"}.get(strategy_id)
    if permission and not access.get(permission):
        raise HTTPException(403, detail={"permission_required": permission})


def _require_valuation_access(flags: dict[str, bool], access: dict) -> None:
    alb = bool(access.get("can_use_alb_analysis"))
    if flags.get("below_graham") and not (alb or access.get("can_use_graham_valuation")):
        raise HTTPException(403, detail={"permission_required": "can_use_graham_valuation"})
    if flags.get("below_barsi_6pct") and not (alb or access.get("can_use_dividend_ceiling")):
        raise HTTPException(403, detail={"permission_required": "can_use_dividend_ceiling"})


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


def _universe_screen_result(rows, asset_type: str, access: dict | None = None):
    if asset_type == "stock":
        return [_authorized_stock_row(_stock_screen_row(asset, fundamental, score), access) for asset, fundamental, _technical, score in rows]
    if asset_type == "fii":
        return [_fii_screen_row(asset, fundamental, score) for asset, fundamental, _technical, score in rows]
    return [_other_b3_screen_row(asset, technical, score) for asset, _fundamental, technical, score in rows]


def _alb_stock_rows(repo: AssetRepository, *, limit: int, offset: int = 0):
    """Return a useful ALB shortlist without silently turning it into a broad universe.

    The first tier is the published ALB preset.  When sparse provider fields
    leave fewer than five candidates, two explicit relaxation tiers recover
    the best ranked companies while preserving value, profitability,
    dividends and liquidity.  The public shortlist is always capped at 20.
    """
    tiers = [
        STOCK_STRATEGIES["alb"].filters,
        StockFilterSet(
            roe_min=8, net_margin_min=3, pe_min=0.1, pe_max=22, pbv_max=4,
            dividend_yield_min=3, current_ratio_min=0.8,
            daily_liquidity_min=500_000, require_below_graham=True,
        ),
        StockFilterSet(
            roe_min=5, pe_min=0.1, pe_max=25, pbv_max=5,
            dividend_yield_min=2, daily_liquidity_min=250_000,
            require_below_graham=True,
        ),
    ]
    selected, seen = [], set()
    for filters in tiers:
        for row in repo.screen_latest_stocks(filters, limit=40, offset=0):
            asset = row[0]
            if asset.id in seen:
                continue
            seen.add(asset.id)
            selected.append(row)
        if len(selected) >= 5:
            break
    maximum = min(max(int(limit), 1), 20)
    return selected[max(0, int(offset)):max(0, int(offset)) + maximum]

@app.get("/screen/db/stocks/{strategy_id}")
def screen_db_stocks(strategy_id: str, limit:int=50, offset:int=0, access=Depends(require_permission("can_view_market")), db: Session=Depends(get_db)):
    strategy=STOCK_STRATEGIES.get(strategy_id)
    if not strategy: raise HTTPException(404,"strategy_not_found")
    _require_system_analysis_access(strategy_id, access)
    repo = AssetRepository(db)
    rows = _alb_stock_rows(repo, limit=limit, offset=offset) if strategy_id == "alb" else repo.screen_latest_stocks(strategy.filters,limit=limit,offset=offset)
    return _stock_screen_result(rows, access)

@app.get("/screen/db/fiis/{strategy_id}")
def screen_db_fiis(strategy_id: str, limit: int = 50, offset: int = 0, access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db)):
    strategy = FII_STRATEGIES.get(strategy_id)
    if not strategy:
        raise HTTPException(404, "strategy_not_found")
    _require_system_analysis_access(strategy_id, access)
    rows = AssetRepository(db).screen_latest_fiis(strategy.filters, limit=limit, offset=offset)
    return _fii_screen_result(rows)


@app.get("/screen/db/universe/{asset_type}")
def screen_db_universe(
    asset_type: str,
    limit: int = Query(default=500, ge=1, le=1200),
    access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    if asset_type not in {"stock", "fii", "other_b3"}:
        raise HTTPException(422, "invalid_asset_type")
    rows = AssetRepository(db).latest_universe(asset_type=asset_type, limit=limit)
    return _universe_screen_result(rows, asset_type, access)


@app.get("/screen/db/custom/{filter_id}")
def screen_db_custom(
    filter_id: UUID, limit: int = 50, offset: int = 0,
    access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db),
):
    _require_custom_filter_access(access)
    row = SavedScreeningFilterRepository(db).get(filter_id, access["email"])
    if row is None:
        raise HTTPException(404, "custom_filter_not_found")
    stored = row.filters_json or {}
    if stored.get("schema_version") == 2:
        configuration = dict(stored.get("configuration") or {})
        configuration.update({"asset_type": row.asset_type, "limit": limit})
        return screen_advanced(AdvancedScreenRequest(**configuration), _access=access, db=db)
    repo = AssetRepository(db)
    if row.asset_type == "stock":
        filters = StockFilterSet(**stored)
        _require_valuation_access({
            "below_graham": bool(stored.get("require_below_graham")),
            "below_barsi_6pct": bool(stored.get("require_below_dividend_target")),
        }, access)
        return _stock_screen_result(repo.screen_latest_stocks(filters, limit=limit, offset=offset), access)
    filters = FiiFilterSet(**stored)
    return _fii_screen_result(repo.screen_latest_fiis(filters, limit=limit, offset=offset))

@app.post("/screen/advanced")
def screen_advanced(req: AdvancedScreenRequest, _access=Depends(require_permission("can_view_market")), db: Session = Depends(get_db)):
    try:
        _require_valuation_access(req.valuation_flags, _access)
        fundamental_filters = {k: v.model_dump(exclude_none=True) for k, v in req.fundamental_filters.items()}
        score_filters = {k: v.model_dump(exclude_none=True) for k, v in req.score_filters.items()}
        ibov_tickers = None
        effective_ibov_membership = req.ibov_membership
        warnings = []
        if req.ibov_membership != "any":
            try:
                portfolio = _index_portfolio("IBOV")
                ibov_tickers = [item.get("ticker") for item in portfolio.get("members") or [] if item.get("ticker")]
                if not ibov_tickers:
                    raise ValueError("empty_ibov_portfolio")
            except Exception:
                # A indisponibilidade momentânea da B3 não deve derrubar todo o
                # screener. Os demais critérios continuam ativos e a resposta deixa
                # explícito que o recorte do IBOV não foi aplicado.
                effective_ibov_membership = "any"
                warnings.append("O filtro de participação no IBOV não foi aplicado porque a B3 não respondeu.")
        result = advanced_screen(
            AssetRepository(db), asset_type=req.asset_type, fundamental_filters=fundamental_filters,
            score_filters=score_filters, valuation_flags=req.valuation_flags,
            technical_filters=req.technical_filters.model_dump(exclude_none=True), trend_period=req.trend_period,
            pivot_timeframe=req.pivot_timeframe, include_technical_columns=req.include_technical_columns, limit=req.limit,
            allowed_tickers=req.allowed_tickers,
            company_sizes=req.company_sizes, ibov_membership=effective_ibov_membership, ibov_tickers=ibov_tickers,
        )
        result.setdefault("meta", {})["warnings"] = warnings
        result["meta"]["requested_ibov_membership"] = req.ibov_membership
        result["meta"]["effective_ibov_membership"] = effective_ibov_membership
        if req.asset_type == "stock":
            result["rows"] = [_authorized_stock_row(dict(row), _access) for row in result.get("rows", [])]
        return result
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
    intraday_row = SharedSnapshotRepository(db).get(REFRESH_SCHEDULES["technical_intraday"].snapshot_key)
    intraday_quotes = dict((intraday_row.payload_json or {}).get("quotes") or {}) if intraday_row else {}
    raw = []
    for pos, asset in repo.positions(portfolio.id):
        price_info = repo.latest_price_info(asset.id)
        live_quote = dict(intraday_quotes.get(asset.ticker) or {})
        if live_quote.get("price") is not None:
            price_info = {
                "price": live_quote.get("price"),
                "as_of": live_quote.get("quote_at") or intraday_row.as_of,
                "source": live_quote.get("source") or "Yahoo Finance",
            }
        raw.append({
            "position_id": str(pos.id), "asset_id": str(asset.id), "ticker": asset.ticker, "name": asset.name,
            "asset_type": asset.asset_type, "sector": pos.sector_override or asset.sector,
            "industry": asset.industry, "segment": pos.segment_override or asset.segment,
            "market_cap_category": asset.market_cap_category,
            "stage": pos.stage, "quantity": _num(pos.quantity), "average_price": _num(pos.average_price),
            "target_weight_pct": _num(pos.target_weight_pct), "classification_override": pos.classification_override,
            "sector_override": pos.sector_override, "segment_override": pos.segment_override, "notes": pos.notes,
            "current_price": price_info["price"], "current_price_as_of": price_info["as_of"], "price_source": price_info["source"],
        })
    snap = build_portfolio_snapshot(raw, cash_balance=_num(portfolio.cash_balance), target_cash_pct=_num(portfolio.target_cash_pct))
    custom_repository = CustomInvestmentRepository(db)
    custom_rows = custom_repository.list(portfolio.id)
    custom = [custom_investment_dict(row) for row in custom_rows]
    custom_total = sum(float(row.current_value) for row in custom_rows)
    custom_invested = sum(float(row.invested_value) for row in custom_rows)
    base_known = float((snap.get("summary") or {}).get("known_market_value") or 0)
    consolidated_known = base_known + custom_total
    allocation_values: dict[str, float] = {}
    for item in snap.get("class_allocation") or []:
        value = float(item.get("known_current_value") or 0)
        if value > 0:
            allocation_values[item.get("asset_class_label") or item.get("asset_class") or "Outros"] = value
    for row in custom:
        allocation_values[row["allocation_group"]] = allocation_values.get(row["allocation_group"], 0.0) + float(row["current_value"])
    consolidated_allocation = [{
        "label": label, "value": round(value, 2),
        "weight_pct": round(value / consolidated_known * 100, 4) if consolidated_known > 0 else None,
    } for label, value in sorted(allocation_values.items(), key=lambda item: item[1], reverse=True)]
    snap["custom_investments"] = custom
    snap["custom_summary"] = {
        "count": len(custom), "invested_value": round(custom_invested, 2),
        "current_value": round(custom_total, 2),
        "variation_pct": round((custom_total / custom_invested - 1) * 100, 4) if custom_invested > 0 else None,
    }
    snap["consolidated_summary"] = {
        "known_total_value": round(consolidated_known, 2),
        "total_value": round(consolidated_known, 2) if (snap.get("summary") or {}).get("allocation_complete") else None,
        "allocation_complete": bool((snap.get("summary") or {}).get("allocation_complete")),
        "custom_value": round(custom_total, 2),
    }
    snap["consolidated_allocation"] = consolidated_allocation
    return {
        "portfolio": _portfolio_header(portfolio), **snap,
        "price_update": refresh_status(db, "technical_intraday"),
    }


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


@app.get("/portfolios/{portfolio_id}/custom-investments/catalog")
def custom_investment_catalog(
    portfolio_id: UUID,
    access=Depends(require_permission("can_view_portfolio")),
    db: Session = Depends(get_db),
):
    portfolio = PortfolioRepository(db).get_portfolio(portfolio_id, access["email"])
    if portfolio is None:
        raise HTTPException(404, "portfolio_not_found")
    return [{"id": key, "label": value[0], "group": value[1]} for key, value in CUSTOM_INVESTMENT_CATEGORIES.items()]


@app.get("/portfolios/{portfolio_id}/custom-investments")
def list_custom_investments(
    portfolio_id: UUID,
    access=Depends(require_permission("can_view_portfolio")),
    db: Session = Depends(get_db),
):
    portfolio = PortfolioRepository(db).get_portfolio(portfolio_id, access["email"])
    if portfolio is None:
        raise HTTPException(404, "portfolio_not_found")
    repository = CustomInvestmentRepository(db)
    return [custom_investment_dict(row, history=repository.history(row.id)) for row in repository.list(portfolio.id)]


@app.post("/portfolios/{portfolio_id}/custom-investments")
def create_custom_investment(
    portfolio_id: UUID, request: PortfolioCustomInvestmentCreateRequest,
    access=Depends(require_permission("can_write_portfolio")),
    db: Session = Depends(get_db),
):
    portfolio = PortfolioRepository(db).get_portfolio(portfolio_id, access["email"])
    if portfolio is None:
        raise HTTPException(404, "portfolio_not_found")
    if request.maturity_date is not None and request.maturity_date < request.application_date:
        raise HTTPException(422, "maturity_before_application")
    row = CustomInvestmentRepository(db).create(portfolio.id, **request.model_dump())
    db.commit()
    return custom_investment_dict(row)


@app.patch("/portfolios/{portfolio_id}/custom-investments/{investment_id}")
def update_custom_investment(
    portfolio_id: UUID, investment_id: UUID, request: PortfolioCustomInvestmentUpdateRequest,
    access=Depends(require_permission("can_write_portfolio")),
    db: Session = Depends(get_db),
):
    portfolio = PortfolioRepository(db).get_portfolio(portfolio_id, access["email"])
    if portfolio is None:
        raise HTTPException(404, "portfolio_not_found")
    repository = CustomInvestmentRepository(db)
    row = repository.get(investment_id, portfolio.id)
    if row is None or not row.is_active:
        raise HTTPException(404, "custom_investment_not_found")
    changes = request.model_dump(exclude_unset=True)
    application_date = changes.get("application_date", row.application_date)
    maturity_date = changes.get("maturity_date", row.maturity_date)
    if maturity_date is not None and maturity_date < application_date:
        raise HTTPException(422, "maturity_before_application")
    repository.update(row, **changes)
    db.commit()
    return custom_investment_dict(row, history=repository.history(row.id))


@app.delete("/portfolios/{portfolio_id}/custom-investments/{investment_id}")
def delete_custom_investment(
    portfolio_id: UUID, investment_id: UUID,
    access=Depends(require_permission("can_write_portfolio")),
    db: Session = Depends(get_db),
):
    portfolio = PortfolioRepository(db).get_portfolio(portfolio_id, access["email"])
    if portfolio is None:
        raise HTTPException(404, "portfolio_not_found")
    repository = CustomInvestmentRepository(db)
    row = repository.get(investment_id, portfolio.id)
    if row is None or not row.is_active:
        raise HTTPException(404, "custom_investment_not_found")
    repository.deactivate(row)
    db.commit()
    return {"status": "archived", "id": str(row.id)}


# -----------------------------
# V1.20 Personal finances
# -----------------------------

@app.get("/finances/catalog")
def finance_catalog(_access=Depends(require_permission("can_view_finances"))):
    return {
        "categories": {key: list(values) for key, values in FINANCE_CATEGORIES.items()},
        "statuses": {
            "planned": "Previsto", "paid": "Pago", "received": "Recebido", "overdue": "Atrasado",
        },
    }


@app.get("/finances/summary")
def finance_summary(
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
    access=Depends(require_permission("can_view_finances")),
    db: Session = Depends(get_db),
):
    try:
        return FinanceRepository(db, access["email"]).summary(month)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/finances/transactions")
def create_finance_transaction(
    request: FinanceTransactionCreateRequest,
    access=Depends(require_permission("can_write_finances")),
    db: Session = Depends(get_db),
):
    try:
        row = FinanceRepository(db, access["email"]).create_transaction(**request.model_dump())
        db.commit()
        return transaction_dict(row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc))


@app.patch("/finances/transactions/{transaction_id}")
def update_finance_transaction(
    transaction_id: UUID, request: FinanceTransactionUpdateRequest,
    access=Depends(require_permission("can_write_finances")),
    db: Session = Depends(get_db),
):
    repository = FinanceRepository(db, access["email"])
    row = repository.get_transaction(transaction_id)
    if row is None or not row.is_active:
        raise HTTPException(404, "finance_transaction_not_found")
    try:
        repository.update_transaction(row, **request.model_dump(exclude_unset=True))
        db.commit()
        return transaction_dict(row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc))


@app.delete("/finances/transactions/{transaction_id}")
def archive_finance_transaction(
    transaction_id: UUID,
    access=Depends(require_permission("can_write_finances")),
    db: Session = Depends(get_db),
):
    repository = FinanceRepository(db, access["email"])
    row = repository.get_transaction(transaction_id)
    if row is None or not row.is_active:
        raise HTTPException(404, "finance_transaction_not_found")
    repository.archive_transaction(row)
    db.commit()
    return {"status": "archived", "id": str(row.id)}


@app.put("/finances/budgets")
def update_finance_budgets(
    request: FinanceBudgetRequest,
    access=Depends(require_permission("can_write_finances")),
    db: Session = Depends(get_db),
):
    repository = FinanceRepository(db, access["email"])
    try:
        repository.replace_budgets(request.competence_month, request.values)
        db.commit()
        return repository.summary(request.competence_month)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc))


# -----------------------------
# V1.14 Multi-user price alerts
# -----------------------------

def _alert_rule_permissions(access: dict) -> dict:
    return {
        "price_above": bool(access.get("can_alert_price_above")),
        "price_below": bool(access.get("can_alert_price_below")),
        "change_positive_pct": bool(access.get("can_alert_change_positive")),
        "change_negative_pct": bool(access.get("can_alert_change_negative")),
    }


@app.get("/alerts/catalog")
def alert_catalog(
    access=Depends(require_permission("can_use_price_alerts")),
    db: Session = Depends(get_db),
):
    b3 = []
    for asset in AssetRepository(db).list_assets(limit=5000):
        if not is_alertable_b3_asset(asset.ticker, asset.asset_type):
            continue
        b3.append({
            "key": asset.ticker, "label": asset.name or asset.ticker,
            "asset_type": asset.asset_type, "market_scope": "b3",
            "interval_minutes": 5,
        })
    return {
        "b3": b3,
        "market": market_alert_catalog(),
        "unsupported": [
            "Selic", "CDI", "IMA-B", "IRF-M", "IPCA", "INPC", "IGP-M", "CPI",
        ],
        "b3_schedule": "Dias úteis, das 10h às 18h (horário de Brasília), a cada 5 minutos.",
        "market_schedule": "A cada 30 minutos, continuamente; novas cotações dependem do mercado de origem.",
        "quote_notice": "Cotações indicativas do Yahoo Finance podem apresentar atraso. Confirme o preço na corretora.",
        "permissions": _alert_rule_permissions(access),
    }


@app.get("/alerts")
def list_price_alerts(
    access=Depends(require_permission("can_use_price_alerts")),
    db: Session = Depends(get_db),
):
    return AlertService(db).dashboard(
        access["email"], limit=int(access.get("alert_asset_limit") or 0),
        permissions=_alert_rule_permissions(access), smtp_configured=settings.smtp_configured,
    )


@app.put("/alerts/preferences")
def update_alert_preferences(
    request: AlertPreferenceRequest,
    access=Depends(require_permission("can_use_price_alerts")),
    db: Session = Depends(get_db),
):
    if not valid_email(request.secondary_email):
        raise HTTPException(422, "invalid_secondary_email")
    row = AlertRepository(db).update_preference(access["email"], request.secondary_email)
    db.commit()
    return {"primary_email": access["email"], "secondary_email": row.secondary_email}


@app.post("/alerts")
def create_price_alert(
    request: PriceAlertCreateRequest,
    access=Depends(require_permission("can_use_price_alerts")),
    db: Session = Depends(get_db),
):
    if not settings.smtp_configured:
        raise HTTPException(503, "alert_email_delivery_not_configured")
    limit = int(access.get("alert_asset_limit") or 0)
    if limit not in {1, 3, 5, 10}:
        raise HTTPException(403, "price_alert_limit_not_granted")
    permissions = _alert_rule_permissions(access)
    rules = {
        "price_above": request.price_above,
        "price_below": request.price_below,
        "change_positive_pct": request.change_positive_pct,
        "change_negative_pct": request.change_negative_pct,
    }
    configured = {key: value for key, value in rules.items() if value is not None}
    if not configured:
        raise HTTPException(422, "price_alert_requires_condition")
    denied = [key for key in configured if not permissions.get(key)]
    if denied:
        raise HTTPException(403, detail={"alert_conditions_not_granted": denied})

    symbol = request.symbol.strip().upper()
    if request.market_scope == "market":
        catalog_item = market_alert_item(symbol)
        if catalog_item is None:
            raise HTTPException(422, "unsupported_market_alert_symbol")
        display_name = catalog_item["label"]
        provider_symbol = "|".join(catalog_item["symbols"])
    else:
        asset = AssetRepository(db).get_by_ticker(symbol)
        if asset is None or not is_alertable_b3_asset(asset.ticker, asset.asset_type):
            raise HTTPException(422, "b3_alert_asset_not_found")
        display_name = asset.name or asset.ticker
        provider_symbol = asset.ticker

    repository = AlertRepository(db)
    existing = repository.get_by_symbol(access["email"], symbol)
    if (existing is None or existing.status != "active") and repository.active_count(access["email"]) >= limit:
        raise HTTPException(409, detail={"price_alert_limit_reached": limit})
    row = repository.upsert(
        owner_email=access["email"], symbol=symbol, provider_symbol=provider_symbol,
        display_name=display_name, market_scope=request.market_scope, rules=rules,
    )
    db.commit()
    return alert_dict(row)


@app.patch("/alerts/{alert_id}/status")
def update_price_alert_status(
    alert_id: UUID, request: PriceAlertStatusRequest,
    access=Depends(require_permission("can_use_price_alerts")),
    db: Session = Depends(get_db),
):
    repository = AlertRepository(db)
    row = repository.get_for_owner(alert_id, access["email"])
    if row is None:
        raise HTTPException(404, "price_alert_not_found")
    if request.status == "active":
        limit = int(access.get("alert_asset_limit") or 0)
        configured = {
            "price_above": row.price_above,
            "price_below": row.price_below,
            "change_positive_pct": row.change_positive_pct,
            "change_negative_pct": row.change_negative_pct,
        }
        configured = {key: value for key, value in configured.items() if value is not None}
        if not configured:
            raise HTTPException(422, "price_alert_requires_condition")
        denied = [key for key in configured if not _alert_rule_permissions(access).get(key)]
        if denied:
            raise HTTPException(403, detail={"alert_conditions_not_granted": denied})
        if row.status != "active" and repository.active_count(access["email"]) >= limit:
            raise HTTPException(409, detail={"price_alert_limit_reached": limit})
    repository.set_status(row, request.status)
    db.commit()
    return alert_dict(row)


@app.get("/alerts/history")
def price_alert_history(
    limit: int = Query(default=100, ge=1, le=500),
    access=Depends(require_permission("can_use_price_alerts")),
    db: Session = Depends(get_db),
):
    return [event_dict(row) for row in AlertRepository(db).history(access["email"], limit)]


@app.post("/alerts/test-email")
def send_price_alert_test_email(
    access=Depends(require_permission("can_use_price_alerts")),
    db: Session = Depends(get_db),
):
    sender = AlertEmailSender()
    if not sender.configured:
        raise HTTPException(503, "alert_email_delivery_not_configured")
    preference = AlertRepository(db).preference(access["email"])
    recipients = [access["email"]]
    if preference and preference.secondary_email:
        recipients.append(preference.secondary_email)
    try:
        sender.send(
            recipients=recipients,
            subject="Teste de alertas - Formação do Investidor",
            text_body="O envio de alertas do Formação do Investidor foi configurado corretamente.",
            html_body="<p>O envio de alertas do <strong>Formação do Investidor</strong> foi configurado corretamente.</p>",
        )
    except Exception as exc:
        raise HTTPException(502, detail={"alert_email_test_failed": str(exc)[:300]})
    return {"status": "sent", "recipients": recipients}


@app.post("/alerts/monitor/run")
def run_alert_monitor_now(_access=Depends(require_owner)):
    return _ALERT_MONITOR.run_once()


@app.put("/portfolios/{portfolio_id}/positions/{ticker}")
def upsert_portfolio_position(portfolio_id: UUID, ticker: str, req: PortfolioPositionRequest, access=Depends(require_permission("can_write_portfolio")), db: Session = Depends(get_db)):
    prepo = PortfolioRepository(db); p = prepo.get_portfolio(portfolio_id, access["email"])
    if p is None: raise HTTPException(404, "portfolio_not_found")
    arepo = AssetRepository(db); asset = arepo.get_by_ticker(ticker.upper())
    target_type = asset.asset_type if asset is not None else req.asset_type
    if not is_supported_ticker(ticker, target_type):
        raise HTTPException(422, "unsupported_or_duplicate_ticker")
    if asset is None:
        asset = arepo.upsert_asset(ticker=ticker.upper(), asset_type=req.asset_type)
    prepo.upsert_position(p, asset, stage=req.stage, quantity=req.quantity, average_price=req.average_price,
                          target_weight_pct=req.target_weight_pct, classification_override=req.classification_override,
                          sector_override=req.sector_override, segment_override=req.segment_override, notes=req.notes)
    db.commit(); return _portfolio_snapshot(db, p)


@app.post("/portfolios/{portfolio_id}/positions/{ticker}/purchase")
def add_portfolio_purchase(portfolio_id: UUID, ticker: str, req: PortfolioPurchaseRequest,
                           access=Depends(require_permission("can_write_portfolio")), db: Session = Depends(get_db)):
    prepo = PortfolioRepository(db); p = prepo.get_portfolio(portfolio_id, access["email"])
    if p is None: raise HTTPException(404, "portfolio_not_found")
    arepo = AssetRepository(db); asset = arepo.get_by_ticker(ticker.upper())
    target_type = asset.asset_type if asset is not None else req.asset_type
    if not is_supported_ticker(ticker, target_type):
        raise HTTPException(422, "unsupported_or_duplicate_ticker")
    if asset is None:
        asset = arepo.upsert_asset(ticker=ticker.upper(), asset_type=req.asset_type)
    try:
        row = prepo.add_purchase(
            p, asset, quantity=req.quantity, unit_price=req.unit_price, stage=req.stage,
            target_weight_pct=req.target_weight_pct,
            classification_override=req.classification_override, sector_override=req.sector_override,
            segment_override=req.segment_override, notes=req.notes,
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
    repository = BackgroundJobRepository(db)
    deduplication_key = f"portfolio-prices:{p.id}"
    recent = repository.latest_for_deduplication(deduplication_key)
    now = datetime.now(timezone.utc)
    recent_created_at = recent.created_at if recent is not None else None
    if recent_created_at is not None and recent_created_at.tzinfo is None:
        recent_created_at = recent_created_at.replace(tzinfo=timezone.utc)
    if recent is not None and recent_created_at and now - recent_created_at < timedelta(minutes=5):
        return {"portfolio_id": str(p.id), "scheduled": False, "cooldown": True, "job": background_job_dict(recent)}
    row, created = repository.enqueue(
        "portfolio_prices_refresh",
        {"portfolio_id": str(p.id), "owner_email": access["email"]},
        requested_by=access["email"], priority=65, max_attempts=3,
        deduplication_key=deduplication_key,
        idempotency_key=f"portfolio-prices:{p.id}:{int(now.timestamp()) // 300}",
    )
    db.commit()
    return {"portfolio_id": str(p.id), "scheduled": created, "cooldown": not created, "job": background_job_dict(row)}


# -----------------------------
# V1.13 Shared market dashboard
# -----------------------------

def _market_dashboard_payload(db: Session) -> dict:
    snapshots = SharedSnapshotRepository(db)
    updates = all_refresh_statuses(db)
    grouped: dict = {}
    generated = []
    for key in (
        "selic_current", "selic_focus", "macro", "global_markets",
        "rates_calendar", "crypto", "fx",
    ):
        row = snapshots.get(REFRESH_SCHEDULES[key].snapshot_key)
        if row is None or not row.payload_json:
            continue
        generated.append(row.as_of)
        for field, value in dict(row.payload_json or {}).items():
            if field in {"generated_at", "refresh"}:
                continue
            if field == "selic":
                grouped["selic"] = {**(grouped.get("selic") or {}), **dict(value or {})}
            else:
                grouped[field] = value

    # Compatibility during the first rollout: preserve the last complete V1.20
    # payload until every independent group has produced its first snapshot.
    repo = NewsCacheRepository(db)
    current = repo.get(
        owner_email=_MARKET_DASHBOARD_OWNER,
        cache_kind="market_dashboard", cache_key=_MARKET_DASHBOARD_CACHE_KEY,
    )
    displayed = current if current is not None and current.result_json else repo.latest_completed(
        owner_email=_MARKET_DASHBOARD_OWNER,
        cache_kind="market_dashboard", cache_key=_MARKET_DASHBOARD_CACHE_KEY,
    )
    payload = news_cache_dict(displayed)
    legacy = dict(payload.get("data") or {})
    data = {**legacy, **grouped}
    if legacy.get("selic") or grouped.get("selic"):
        data["selic"] = {**dict(legacy.get("selic") or {}), **dict(grouped.get("selic") or {})}
    if generated:
        data["generated_at"] = max(generated).isoformat()
    payload["data"] = data
    visible_updates = [updates[key] for key in (
        "selic_current", "selic_focus", "macro", "global_markets", "rates_calendar", "crypto", "fx",
    )]
    payload.update({
        "refresh_status": (
            "running" if any(item["status"] == "running" for item in visible_updates)
            else "queued" if any(item["status"] == "queued" for item in visible_updates)
            else "completed" if data else "not_requested"
        ),
        "refresh_error": None,
        "refresh_market_date": news_market_date(),
        "automatic_once_per_day": False,
        "updates": updates,
    })
    return payload


@app.get("/market-dashboard")
def market_dashboard(
    _access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    return _market_dashboard_payload(db)


@app.post("/market-dashboard/ensure")
def ensure_market_dashboard(
    _access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    scheduled = []
    for key in ("selic_current", "selic_focus", "macro", "global_markets", "rates_calendar", "crypto", "fx"):
        _row, created = enqueue_refresh(db, key, trigger="access", requested_by=_access.get("email"))
        if created:
            scheduled.append(key)
    db.commit()
    payload = _market_dashboard_payload(db)
    payload["scheduled"] = bool(scheduled)
    payload["scheduled_groups"] = scheduled
    return payload


@app.post("/market-dashboard/refresh")
def refresh_market_dashboard(
    access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    scheduled = []
    for key in ("selic_current", "selic_focus", "macro", "global_markets", "rates_calendar", "crypto", "fx"):
        _row, created = enqueue_refresh(db, key, trigger="manual", requested_by=access.get("email"), force=True)
        if created:
            scheduled.append(key)
    db.commit()
    payload = _market_dashboard_payload(db)
    payload["scheduled"] = bool(scheduled)
    payload["scheduled_groups"] = scheduled
    return payload


@app.get("/market-dashboard/updates")
def market_dashboard_updates(
    _access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    return {"updates": all_refresh_statuses(db), "timezone": "America/Sao_Paulo"}


@app.get("/market-dashboard/interest-curve/history")
def interest_curve_history(
    limit: int = Query(default=12, ge=1, le=60),
    _access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    return [{
        "reference_date": row.reference_date,
        "curve_type": row.curve_type,
        "title": row.title,
        "source": row.source,
        "url": row.source_url,
        "points": row.points_json or [],
        "retrieved_at": row.retrieved_at,
    } for row in InterestCurveHistoryRepository(db).list_recent(limit)]


@app.post("/market-dashboard/groups/{group_key}/refresh")
def refresh_market_dashboard_group(
    group_key: str,
    access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    if group_key not in REFRESH_SCHEDULES:
        raise HTTPException(404, "market_refresh_group_not_found")
    if group_key in {"catalog", "fundamentals", "technical_daily", "technical_intraday"} and not access.get("can_sync_market"):
        raise HTTPException(403, detail={"permission_required": "can_sync_market"})
    row, created = enqueue_refresh(
        db, group_key, trigger="manual", requested_by=access.get("email"), force=True,
    )
    db.commit()
    return {
        "scheduled": created,
        "cooldown": not created,
        "job": background_job_dict(row) if row is not None else None,
        "update": all_refresh_statuses(db).get(group_key),
    }


@app.post("/market-dashboard/groups/{group_key}/ensure")
def ensure_market_dashboard_group(
    group_key: str,
    access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    if group_key not in REFRESH_SCHEDULES:
        raise HTTPException(404, "market_refresh_group_not_found")
    row, created = enqueue_refresh(
        db, group_key, trigger="access", requested_by=access.get("email"), force=False,
    )
    db.commit()
    return {
        "scheduled": created,
        "job": background_job_dict(row) if row is not None else None,
        "update": all_refresh_statuses(db).get(group_key),
    }


@app.get("/market-dashboard/headlines")
def market_dashboard_headlines(
    _access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    row = SharedSnapshotRepository(db).get(REFRESH_SCHEDULES["headlines"].snapshot_key)
    _job, scheduled = enqueue_refresh(db, "headlines", trigger="access", requested_by=_access.get("email"))
    db.commit()
    update = all_refresh_statuses(db)["headlines"]
    return {
        "data": dict(row.payload_json or {}) if row is not None else {},
        "refreshing": update["status"] in {"queued", "running"},
        "error": update.get("last_error_code"), "scheduled": scheduled,
        "ttl_seconds": settings.economy_headlines_ttl_seconds, "update": update,
    }


@app.post("/market-dashboard/headlines/refresh")
def refresh_market_dashboard_headlines(
    access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    row, scheduled = enqueue_refresh(db, "headlines", trigger="manual", requested_by=access.get("email"), force=True)
    db.commit()
    return {"scheduled": scheduled, "refreshing": scheduled, "job": background_job_dict(row)}


@app.get("/market-dashboard/comparison")
def market_dashboard_comparison(
    _access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    row = SharedSnapshotRepository(db).get(REFRESH_SCHEDULES["comparison"].snapshot_key)
    _job, scheduled = enqueue_refresh(db, "comparison", trigger="access", requested_by=_access.get("email"))
    db.commit()
    update = all_refresh_statuses(db)["comparison"]
    return {
        "data": dict(row.payload_json or {}) if row is not None else {},
        "refreshing": update["status"] in {"queued", "running"},
        "error": update.get("last_error_code"), "scheduled": scheduled,
        "ttl_seconds": 24 * 60 * 60, "update": update,
    }


@app.post("/market-dashboard/comparison/refresh")
def refresh_market_dashboard_comparison(
    access=Depends(require_permission("can_view_market")),
    db: Session = Depends(get_db),
):
    job, scheduled = enqueue_refresh(
        db, "comparison", trigger="manual",
        requested_by=access.get("email"), force=True,
    )
    db.commit()
    # A manual request can legitimately reuse a job that is already inside the
    # cooldown window.  Always return the last valid snapshot and the real job
    # status so the browser keeps useful data visible while the refresh runs.
    snapshot = SharedSnapshotRepository(db).get(REFRESH_SCHEDULES["comparison"].snapshot_key)
    update = all_refresh_statuses(db)["comparison"]
    return {
        "data": dict(snapshot.payload_json or {}) if snapshot is not None else {},
        "scheduled": scheduled,
        "refreshing": update["status"] in {"queued", "running"},
        "error": update.get("last_error_code"),
        "job": background_job_dict(job) if job is not None else None,
        "update": update,
    }


# -----------------------------
# V1.11 Restricted research/news
# -----------------------------

def _enqueue_user_news_job(db: Session, row: UserNewsCacheORM, *, requested_by: str) -> bool:
    requested_at = row.requested_at or datetime.now(timezone.utc)
    if requested_at.tzinfo is None:
        requested_at = requested_at.replace(tzinfo=timezone.utc)
    _job, created = BackgroundJobRepository(db).enqueue(
        "user_news_refresh",
        {"cache_id": str(row.id)},
        requested_by=requested_by,
        priority=75,
        max_attempts=3,
        deduplication_key=f"user-news:{row.id}",
        idempotency_key=f"user-news:{row.id}:{int(requested_at.timestamp())}",
    )
    return created

@app.post("/insights/news/refresh-daily")
def refresh_daily_user_news(
    access=Depends(require_permission("can_view_news_insights")),
    db: Session = Depends(get_db),
):
    """Queue each user's news once on their first access of the B3 day."""
    scheduled: list[tuple[str, str]] = []
    existing: list[dict] = []
    with _NEWS_QUEUE_LOCK:
        cache_repo = NewsCacheRepository(db)
        portfolio_repo = PortfolioRepository(db)
        for portfolio in portfolio_repo.list_portfolios(access["email"]):
            if not _portfolio_news_assets(db, portfolio.id):
                continue
            row, should_run = cache_repo.request_refresh(
                owner_email=access["email"], cache_kind="portfolio",
                cache_key=str(portfolio.id), trigger="automatic", force=False,
            )
            existing.append(news_cache_dict(row))
            if should_run and _enqueue_user_news_job(db, row, requested_by=access["email"]):
                scheduled.append((str(row.id), f"portfolio:{portfolio.id}"))

        recommendation_row, should_run = cache_repo.request_refresh(
            owner_email=access["email"], cache_kind="recommendations",
            cache_key="all", trigger="automatic", force=False,
        )
        existing.append(news_cache_dict(recommendation_row))
        if should_run and _enqueue_user_news_job(db, recommendation_row, requested_by=access["email"]):
            scheduled.append((str(recommendation_row.id), "recommendations:all"))
        db.commit()
    return {
        "market_date": news_market_date(),
        "scheduled": [label for _cache_id, label in scheduled],
        "scheduled_count": len(scheduled),
        "automatic_once_per_day": True,
        "entries": existing,
    }


@app.get("/insights/news/cache/portfolios/{portfolio_id}")
def cached_portfolio_news(
    portfolio_id: UUID,
    access=Depends(require_permission("can_view_news_insights")),
    db: Session = Depends(get_db),
):
    portfolio = PortfolioRepository(db).get_portfolio(portfolio_id, access["email"])
    if portfolio is None:
        raise HTTPException(404, "portfolio_not_found")
    row = NewsCacheRepository(db).get(
        owner_email=access["email"], cache_kind="portfolio", cache_key=str(portfolio_id),
    )
    result = news_cache_dict(row)
    result.update({"portfolio_id": str(portfolio.id), "portfolio_name": portfolio.name})
    return result


@app.post("/insights/news/cache/portfolios/{portfolio_id}/refresh")
def refresh_cached_portfolio_news(
    portfolio_id: UUID,
    access=Depends(require_permission("can_view_news_insights")),
    db: Session = Depends(get_db),
):
    portfolio = PortfolioRepository(db).get_portfolio(portfolio_id, access["email"])
    if portfolio is None:
        raise HTTPException(404, "portfolio_not_found")
    if not _portfolio_news_assets(db, portfolio.id):
        raise HTTPException(400, "portfolio_has_no_supported_stocks")
    with _NEWS_QUEUE_LOCK:
        row, should_run = NewsCacheRepository(db).request_refresh(
            owner_email=access["email"], cache_kind="portfolio",
            cache_key=str(portfolio.id), trigger="manual", force=True,
        )
        scheduled = should_run and _enqueue_user_news_job(db, row, requested_by=access["email"])
        db.commit()
    result = news_cache_dict(row)
    result["scheduled"] = scheduled
    return result


@app.get("/insights/news/cache/recommendations")
def cached_bank_recommendation_news(
    category: str = Query(default="all", pattern="^(all|brazil|global)$"),
    access=Depends(require_permission("can_view_news_insights")),
    db: Session = Depends(get_db),
):
    cache_repo = NewsCacheRepository(db)
    row = cache_repo.get(
        owner_email=access["email"], cache_kind="recommendations", cache_key=category,
    )
    derived_from = None
    if row is None and category != "all":
        row = cache_repo.get(
            owner_email=access["email"], cache_kind="recommendations", cache_key="all",
        )
        derived_from = "all" if row is not None else None
    result = news_cache_dict(row)
    if row is not None and category != "all" and row.cache_key == "all" and row.result_json:
        data = dict(row.result_json)
        data["category"] = category
        data["items"] = [
            item for item in (row.result_json.get("items") or [])
            if item.get("bank_group") == category
        ]
        result["data"] = data
    result.update({"category": category, "derived_from": derived_from})
    return result


@app.post("/insights/news/cache/recommendations/refresh")
def refresh_cached_bank_recommendation_news(
    category: str = Query(default="all", pattern="^(all|brazil|global)$"),
    access=Depends(require_permission("can_view_news_insights")),
    db: Session = Depends(get_db),
):
    with _NEWS_QUEUE_LOCK:
        row, should_run = NewsCacheRepository(db).request_refresh(
            owner_email=access["email"], cache_kind="recommendations",
            cache_key=category, trigger="manual", force=True,
        )
        scheduled = should_run and _enqueue_user_news_job(db, row, requested_by=access["email"])
        db.commit()
    result = news_cache_dict(row)
    result["scheduled"] = scheduled
    return result

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
    assets = _portfolio_news_assets(db, portfolio.id)
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


@app.post("/backtests/matrix")
def backtest_matrix(
    req: BacktestMatrixRequest,
    access=Depends(require_permission("can_run_backtests")),
    db: Session = Depends(get_db),
):
    """Validate limits and enqueue a private backtest without blocking the browser."""
    tickers = list(dict.fromkeys(str(value).strip().upper() for value in req.tickers if str(value).strip()))
    strategies = list(dict.fromkeys(req.strategy_ids))
    unknown = [strategy for strategy in strategies if strategy not in STRATEGIES]
    if unknown:
        raise HTTPException(404, detail={"strategies_not_found": unknown})
    asset_limit = int(access.get("backtest_asset_limit") or 0)
    daily_limit = int(access.get("backtest_daily_limit") or 0)
    strategy_limit = int(access.get("backtest_strategy_limit") or 0)
    cooldown_seconds = max(60, int(access.get("backtest_cooldown_seconds") or 60))
    if len(tickers) > asset_limit:
        raise HTTPException(403, detail={"backtest_asset_limit": asset_limit})
    if len(strategies) > strategy_limit:
        raise HTTPException(403, detail={"backtest_strategy_limit": strategy_limit})
    if not asset_limit or not daily_limit or not strategy_limit:
        raise HTTPException(403, "backtest_execution_limit_not_authorized")
    if req.execution_mode == "combined" and len(strategies) < 2:
        raise HTTPException(422, "combined_backtest_requires_two_strategies")

    active = db.scalar(
        select(BacktestRequestUsageORM)
        .where(
            BacktestRequestUsageORM.owner_email == access["email"],
            BacktestRequestUsageORM.status.in_(("queued", "running")),
        )
        .order_by(BacktestRequestUsageORM.created_at.desc())
        .limit(1)
    )
    if active is not None:
        raise HTTPException(409, detail={
            "backtest_request_active": str(active.id),
            "message": "Aguarde a análise em andamento terminar.",
        })

    now = datetime.now(timezone.utc)
    last_finished = db.scalar(
        select(BacktestRequestUsageORM)
        .where(
            BacktestRequestUsageORM.owner_email == access["email"],
            BacktestRequestUsageORM.finished_at.is_not(None),
        )
        .order_by(BacktestRequestUsageORM.finished_at.desc())
        .limit(1)
    )
    if last_finished is not None and last_finished.finished_at is not None:
        allowed_at = last_finished.finished_at + timedelta(seconds=cooldown_seconds)
        if now < allowed_at:
            raise HTTPException(429, detail={
                "backtest_cooldown_seconds": cooldown_seconds,
                "retry_after_seconds": max(1, math.ceil((allowed_at - now).total_seconds())),
                "message": "A próxima análise poderá começar um minuto após a conclusão da anterior.",
            })

    market_day = backtest_market_date()
    used = db.scalar(select(func.count(BacktestRequestUsageORM.id)).where(
        BacktestRequestUsageORM.owner_email == access["email"],
        BacktestRequestUsageORM.market_date == market_day,
    )) or 0
    if used >= daily_limit:
        raise HTTPException(429, detail={"backtest_daily_limit": daily_limit, "used_today": used})

    configuration = req.model_dump(mode="json")
    usage = BacktestRequestUsageORM(
        owner_email=access["email"], market_date=market_day,
        asset_count=len(tickers), strategy_count=len(strategies), status="queued",
        execution_mode=req.execution_mode,
        combination_rule=req.combination_rule if req.execution_mode == "combined" else None,
        configuration_json=configuration,
    )
    db.add(usage)
    db.flush()
    payload = {
        **configuration,
        "usage_id": str(usage.id), "owner_email": access["email"],
        "tickers": tickers, "strategy_ids": strategies,
        "filters": req.filters.model_dump(exclude_none=True, mode="json"),
    }
    job, _created = BackgroundJobRepository(db).enqueue(
        "personal_backtest_matrix", payload,
        requested_by=access["email"], priority=40, max_attempts=2,
        deduplication_key=f"personal-backtest:{access['email']}",
    )
    usage.background_job_id = job.id
    db.commit()
    return {
        "request_id": str(usage.id), "job_id": str(job.id), "status": job.status,
        "assets_requested": len(tickers), "strategies_requested": len(strategies),
        "daily_used": used + 1, "daily_limit": daily_limit,
        "strategy_limit": strategy_limit, "cooldown_seconds": cooldown_seconds,
        "execution_mode": req.execution_mode,
        "combination_rule": req.combination_rule if req.execution_mode == "combined" else None,
    }


@app.get("/backtests/jobs")
def personal_backtest_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    access=Depends(require_permission("can_view_backtests")),
    db: Session = Depends(get_db),
):
    rows = BackgroundJobRepository(db).list_for_requester(
        access["email"], job_type="personal_backtest_matrix", limit=limit,
    )
    return [background_job_dict(row) for row in rows]


@app.get("/backtests/jobs/{job_id}")
def personal_backtest_job(
    job_id: UUID,
    access=Depends(require_permission("can_view_backtests")),
    db: Session = Depends(get_db),
):
    row = BackgroundJobRepository(db).get(job_id)
    if row is None or (not access.get("is_owner") and row.requested_by != access["email"]):
        raise HTTPException(404, "background_job_not_found")
    result = background_job_dict(row)
    result["result"] = dict(row.result_json or {}) if row.status == "succeeded" else {}
    return result


@app.get("/backtests/jobs/{job_id}/export.csv")
def export_personal_backtest_job(
    job_id: UUID,
    access=Depends(require_permission("can_view_backtests")),
    db: Session = Depends(get_db),
):
    job = BackgroundJobRepository(db).get(job_id)
    if job is None or (not access.get("is_owner") and job.requested_by != access["email"]):
        raise HTTPException(404, "background_job_not_found")
    if job.status != "succeeded":
        raise HTTPException(409, "backtest_job_not_completed")

    output = io.StringIO(newline="")
    columns = (
        "registro", "ativo", "estrategia", "regra_combinacao", "data_entrada",
        "preco_entrada", "data_saida", "preco_saida", "retorno_percentual",
        "resultado_financeiro", "dias_na_posicao", "retorno_total_percentual",
        "cagr_percentual", "sharpe", "drawdown_maximo_percentual",
    )
    writer = csv.DictWriter(output, fieldnames=columns, delimiter=";")
    writer.writeheader()
    repository = BacktestRepository(db)
    for item in (job.result_json or {}).get("results", []):
        run_id = item.get("run_id")
        if not run_id:
            continue
        run = repository.get_run(
            UUID(str(run_id)), owner_email=access["email"], is_owner=bool(access.get("is_owner")),
        )
        if run is None:
            continue
        metrics = run.metrics_json or {}
        trades = repository.trades(run.id)
        common = {
            "ativo": item.get("ticker") or item.get("requested_ticker"),
            "estrategia": run.strategy_name,
            "regra_combinacao": (run.parameters_json or {}).get("combination", {}).get("rule"),
            "retorno_total_percentual": metrics.get("total_return_pct"),
            "cagr_percentual": metrics.get("cagr_pct"),
            "sharpe": metrics.get("sharpe_ratio"),
            "drawdown_maximo_percentual": metrics.get("max_drawdown_pct"),
        }
        if not trades:
            writer.writerow({**common, "registro": "resumo"})
        for trade in trades:
            writer.writerow({
                **common, "registro": "operacao",
                "data_entrada": trade.entry_date.isoformat(),
                "preco_entrada": trade.entry_price,
                "data_saida": trade.exit_date.isoformat() if trade.exit_date else "",
                "preco_saida": trade.exit_price if trade.exit_price is not None else "",
                "retorno_percentual": trade.return_pct if trade.return_pct is not None else "",
                "resultado_financeiro": trade.pnl_value if trade.pnl_value is not None else "",
                "dias_na_posicao": trade.holding_days if trade.holding_days is not None else "",
            })
    content = "\ufeff" + output.getvalue()
    return Response(
        content=content, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="backtest-{job_id}.csv"'},
    )


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
    records = BacktestRepository(db).strategy_study_records()
    result = build_strategy_study(records, top_limit=limit)
    result["generated_at"] = datetime.now(timezone.utc)
    return result


@app.get("/backtests/study/{strategy_id}/configurations")
def backtest_strategy_configurations(
    strategy_id: str,
    _access=Depends(require_permission("can_view_backtest_studies")),
    db: Session = Depends(get_db),
):
    if strategy_id not in STRATEGIES:
        raise HTTPException(404, "strategy_not_found")
    records = []
    for run in BacktestRepository(db).strategy_configuration_records(strategy_id):
        records.append({
            "ticker": run["ticker"],
            "strategy_id": run["strategy_id"],
            "strategy_name": run["strategy_name"],
            "ranking_score": _num(run["ranking_score"]),
            "sample_status": run["sample_status"],
            "current_signal": run["current_signal"],
            "metrics": run["metrics"] or {},
            "parameters": run["parameters"] or {},
            "assumptions": {
                "initial_capital": _num(run["initial_capital"]),
                "fee_pct": _num(run["fee_pct"]),
                "slippage_pct": _num(run["slippage_pct"]),
                "risk_free_rate_pct": _num(run["risk_free_rate_pct"]),
            },
            "requested_start": run["requested_start"],
            "requested_end": run["requested_end"],
            "created_at": run["created_at"],
        })
    result = build_strategy_configuration_catalog(records, strategy_id=strategy_id)
    result["strategy_name"] = STRATEGIES[strategy_id].name
    result["strategy_rules"] = STRATEGIES[strategy_id].rules
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
    service = BacktestBatchService(db)
    return [service.job_dict(job) for job in service.list_jobs(limit)]


@app.post("/backtests/batch/jobs")
def create_backtest_batch_job(
    request: BacktestBatchCreateRequest,
    access=Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        service = BacktestBatchService(db)
        job, dispatch_required = service.create_site_job(
            requested_by=access["email"], tickers=request.tickers,
            max_combinations=request.max_combinations,
        )
        db.commit()
        return {**service.job_dict(job), "dispatch_required": dispatch_required}
    except ValueError as exc:
        db.rollback()
        detail = str(exc)
        raise HTTPException(409 if detail.startswith("batch_job_active:") else 400, detail)


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


@app.patch("/backtests/batch/jobs/{job_id}/cancelled")
def cancel_backtest_batch_job(
    job_id: UUID,
    request: BacktestBatchCancellationRequest,
    access=Depends(require_owner),
    db: Session = Depends(get_db),
):
    service = BacktestBatchService(db)
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(404, "backtest_batch_job_not_found")
    try:
        service.mark_cancelled(
            job,
            requested_by=access["email"],
            reason=request.reason,
            details=request.details,
        )
        db.commit()
        return service.job_dict(job)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))


@app.post("/backtests/batch/jobs/{job_id}/retry")
def retry_backtest_batch_job(
    job_id: UUID,
    access=Depends(require_owner),
    db: Session = Depends(get_db),
):
    service = BacktestBatchService(db)
    source_job = service.get_job(job_id)
    if source_job is None:
        raise HTTPException(404, "backtest_batch_job_not_found")
    try:
        job, dispatch_required = service.create_retry_job(
            source_job,
            requested_by=access["email"],
        )
        db.commit()
        dispatch = None
        if dispatch_required:
            try:
                dispatch = dispatch_official_backtests(
                    token=settings.github_actions_token,
                    tickers=job.requested_tickers_json,
                    repository=settings.github_actions_repository,
                    workflow=settings.github_actions_workflow,
                    ref=settings.github_actions_ref,
                    max_combinations=job.max_combinations,
                    job_id=str(job.id),
                    environment=settings.app_environment,
                )
            except GitHubActionsError as exc:
                service.mark_failed(
                    job,
                    code="github_dispatch_failed",
                    message=str(exc),
                    details={"retry_of": str(source_job.id)},
                )
                db.commit()
                raise HTTPException(502, str(exc))
        return {
            **service.job_dict(job),
            "dispatch_required": dispatch_required,
            "dispatch": dispatch,
            "retry_of": str(source_job.id),
        }
    except ValueError as exc:
        db.rollback()
        detail = str(exc)
        raise HTTPException(409 if detail.startswith("batch_job_active:") else 400, detail)


@app.post("/automation/backtests/jobs/start")
def start_automated_backtest_job(
    request: BacktestAutomationStartRequest,
    _callback=Depends(require_backtest_callback),
    db: Session = Depends(get_db),
):
    service = BacktestBatchService(db)
    try:
        if request.source == "manual":
            if request.job_id is None:
                raise ValueError("manual_batch_requires_job_id")
            job = service.get_job(request.job_id)
            if job is None:
                raise HTTPException(404, "backtest_batch_job_not_found")
            result = service.start_existing_job(job)
        else:
            if request.job_id is not None:
                raise ValueError("scheduled_batch_cannot_receive_job_id")
            job, _created = service.start_scheduled_job(
                max_combinations=request.max_combinations,
                tickers=request.tickers or None,
            )
            result = service.start_existing_job(job)
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        detail = str(exc)
        conflicts = {
            "batch_job_failed", "batch_job_cancelled", "batch_job_already_completed",
            "batch_job_already_running",
        }
        raise HTTPException(409 if detail.startswith("batch_job_active:") or detail in conflicts else 400, detail)


@app.post("/automation/backtests/jobs/{job_id}/assets")
def receive_automated_backtest_asset(
    job_id: UUID,
    request: BacktestAutomationAssetRequest,
    _callback=Depends(require_backtest_callback),
    db: Session = Depends(get_db),
):
    service = BacktestBatchService(db)
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(404, "backtest_batch_job_not_found")
    # Keep checksums compatible with the original one-part protocol while new
    # clients explicitly sign their chunk position.
    payload = request.model_dump(exclude={"checksum"}, exclude_unset=True)
    if not compare_digest(delivery_checksum(payload), request.checksum):
        raise HTTPException(422, "backtest_delivery_checksum_invalid")
    try:
        delivery, created = service.receive_asset_delivery(
            job,
            ticker=request.ticker,
            checksum=request.checksum,
            completed_runs=request.completed_runs,
            failed_runs=request.failed_runs,
            chunk_index=request.chunk_index,
            chunk_count=request.chunk_count,
            results=request.results,
            errors=request.errors,
        )
        db.commit()
        return {
            "accepted": True,
            "idempotent": not created,
            **delivery,
            "job": service.job_dict(job),
        }
    except ValueError as exc:
        db.rollback()
        detail = str(exc)
        status = 409 if detail in {
            "batch_job_failed", "batch_job_cancelled", "batch_job_already_completed",
            "batch_delivery_checksum_conflict", "batch_delivery_chunk_manifest_conflict",
        } else 400
        raise HTTPException(status, detail)


@app.post("/automation/backtests/jobs/{job_id}/complete")
def complete_automated_backtest_job(
    job_id: UUID,
    _callback=Depends(require_backtest_callback),
    db: Session = Depends(get_db),
):
    service = BacktestBatchService(db)
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(404, "backtest_batch_job_not_found")
    try:
        service.finalize_job(job)
        db.commit()
        return service.job_dict(job)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))


@app.post("/automation/backtests/jobs/{job_id}/failed")
def fail_automated_backtest_job(
    job_id: UUID,
    request: BacktestBatchFailureRequest,
    _callback=Depends(require_backtest_callback),
    db: Session = Depends(get_db),
):
    service = BacktestBatchService(db)
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(404, "backtest_batch_job_not_found")
    service.mark_failed(job, code=request.code, message=request.message, details=request.details)
    db.commit()
    return service.job_dict(job)
