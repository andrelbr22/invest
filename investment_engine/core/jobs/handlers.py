from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import select

from ...data.providers.market_dashboard import MarketDashboardService
from ...data.providers.intraday import IntradayQuoteProvider
from ...data.providers.news import MarketNewsService
from ...data.ingestion.pipeline import MarketIngestionPipeline
from ...data.ingestion.prices import PriceIngestionService
from ...core.repositories.assets import AssetRepository
from ...core.repositories.portfolio import PortfolioRepository
from ...core.repositories.news_cache import NewsCacheRepository
from ...core.services_v14 import calculate_asset_intelligence
from ...core.instruments import is_supported_ticker
from ...infrastructure.db.models import (
    AssetORM, BacktestRequestUsageORM, PortfolioPositionORM, PriceAlertORM,
    UserNewsCacheORM,
)
from ...infrastructure.db.session import get_session_factory
from ..repositories.economic_series import InterestCurveHistoryRepository, SharedSnapshotRepository, utcnow
from ..repositories.background_jobs import BackgroundJobRepository
from ..backtesting.service import BacktestService


def handle_noop(payload: dict) -> dict:
    """Health-check handler used by deployment and queue tests."""
    return {"ok": True, "echo": dict(payload or {})}


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _record_refresh_failure(snapshot_key: str, exc: Exception) -> None:
    """Keep the last valid payload while recording a safe refresh failure code."""
    session = get_session_factory()()
    try:
        SharedSnapshotRepository(session).mark_refresh_failed(snapshot_key, type(exc).__name__)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def handle_market_dashboard_refresh(payload: dict) -> dict:
    """Fetch and persist the shared dashboard without blocking a browser request."""
    snapshot_key = str(payload.get("snapshot_key") or "market-dashboard:main")
    try:
        result = MarketDashboardService().build()
    except Exception as exc:
        _record_refresh_failure(snapshot_key, exc)
        raise
    session = get_session_factory()()
    try:
        row = SharedSnapshotRepository(session).save_valid(
            snapshot_key=snapshot_key,
            snapshot_kind="market_dashboard",
            payload=_json_safe(result),
            source="configured-market-providers",
            as_of=utcnow(),
            valid_until=utcnow() + timedelta(hours=6),
        )
        session.commit()
        return {"snapshot_key": row.snapshot_key, "payload_hash": row.payload_hash}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def handle_economy_headlines_refresh(payload: dict) -> dict:
    snapshot_key = str(payload.get("snapshot_key") or "economy-headlines:main")
    try:
        result = MarketDashboardService().economy_headlines(limit=max(1, min(10, int(payload.get("limit") or 5))))
    except Exception as exc:
        _record_refresh_failure(snapshot_key, exc)
        raise
    session = get_session_factory()()
    try:
        row = SharedSnapshotRepository(session).save_valid(
            snapshot_key=snapshot_key,
            snapshot_kind="economy_headlines",
            payload=_json_safe(result),
            source="configured-news-providers",
            as_of=utcnow(),
            valid_until=utcnow() + timedelta(hours=1),
        )
        session.commit()
        return {"snapshot_key": row.snapshot_key, "payload_hash": row.payload_hash}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _save_snapshot(*, snapshot_key: str, snapshot_kind: str, result: dict,
                   source: str, valid_for: timedelta) -> dict:
    session = get_session_factory()()
    try:
        row = SharedSnapshotRepository(session).save_valid(
            snapshot_key=snapshot_key,
            snapshot_kind=snapshot_kind,
            payload=_json_safe(result),
            source=source,
            as_of=utcnow(),
            valid_until=utcnow() + valid_for,
        )
        session.commit()
        return {"snapshot_key": row.snapshot_key, "payload_hash": row.payload_hash}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _previous_snapshot_payload(snapshot_key: str) -> dict:
    session = get_session_factory()()
    try:
        row = SharedSnapshotRepository(session).get(snapshot_key)
        return dict(row.payload_json or {}) if row is not None else {}
    finally:
        session.close()


def _save_interest_curve_history(curve: dict) -> None:
    session = get_session_factory()()
    try:
        InterestCurveHistoryRepository(session).save(curve)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def handle_market_group_refresh(payload: dict) -> dict:
    group = str(payload.get("group") or "").strip().lower()
    snapshot_key = str(payload.get("snapshot_key") or f"market:{group}")
    service = MarketDashboardService()
    operation_names = {
        "selic_current": {"selic": "selic_current"},
        "selic_focus": {"selic": "selic_focus"},
        "macro": {"fixed_income": "fixed_income", "inflation": "inflation"},
        "global_markets": {"quoted": "quoted_markets"},
        "rates_calendar": {
            "us_rates": "us_rates", "curve": "interest_curve", "calendar": "calendar",
        },
        "crypto": {"crypto": "crypto"},
        "fx": {"fx": "fx"},
    }
    if group not in operation_names:
        raise ValueError("market_refresh_group_not_supported")
    try:
        previous = _previous_snapshot_payload(snapshot_key)
        result = {"generated_at": utcnow().isoformat()}
        warnings: list[dict] = []
        refreshed: list[str] = []
        for field, operation_name in operation_names[group].items():
            try:
                result[field] = getattr(service, operation_name)()
                refreshed.append(field)
            except Exception as exc:
                if field in previous:
                    result[field] = previous[field]
                warnings.append({"field": field, "error": type(exc).__name__})
        if group == "rates_calendar" and "curve" in refreshed:
            try:
                _save_interest_curve_history(dict(result.get("curve") or {}))
            except Exception as exc:
                warnings.append({"field": "curve_history", "error": type(exc).__name__})
        if not refreshed and not any(field in result for field in operation_names[group]):
            raise RuntimeError("market_refresh_group_all_sources_failed")
        result["refresh"] = {
            "status": "partial" if warnings else "complete",
            "refreshed": refreshed,
            "warnings": warnings,
        }
        return _save_snapshot(
            snapshot_key=snapshot_key,
            snapshot_kind=f"market_{group}",
            result=result,
            source="configured-market-providers",
            valid_for=timedelta(hours=24),
        )
    except Exception as exc:
        _record_refresh_failure(snapshot_key, exc)
        raise


def handle_historical_comparison_refresh(payload: dict) -> dict:
    snapshot_key = str(payload.get("snapshot_key") or "market-comparison:main")
    try:
        result = MarketDashboardService().historical_comparison(years=20)
        return _save_snapshot(
            snapshot_key=snapshot_key,
            snapshot_kind="historical_comparison",
            result=result,
            source="BCB e Yahoo Finance",
            valid_for=timedelta(hours=24),
        )
    except Exception as exc:
        _record_refresh_failure(snapshot_key, exc)
        raise


def _summary(result) -> dict:
    return {
        "pipeline": result.pipeline,
        "received": result.rows_received,
        "saved": result.rows_valid,
        "rejected": result.rows_rejected,
        "warnings": result.warnings,
    }


def _refresh_scores(session, asset_type: str) -> int:
    repository = AssetRepository(session)
    processed = 0
    for asset in repository.list_assets(asset_type=asset_type, limit=5000):
        fundamental = repository.latest_fundamentals(asset.id)
        if fundamental is None:
            continue
        technical = repository.latest_technical(asset.id, source="internal") or repository.latest_technical(asset.id)
        result = calculate_asset_intelligence(asset, fundamental, technical)
        repository.upsert_scores(
            asset,
            as_of=fundamental.reference_date,
            model_version=result["model_version"],
            scores={
                "quality_score": result["quality"].score,
                "value_score": result["value"].score,
                "growth_score": result["growth"].score if result["growth"] else None,
                "technical_score": result["technical"].score,
                "risk_score": result["risk"].score,
                "liquidity_score": result["liquidity"].score,
                "alb_score": result["alb_score"],
            },
            coverage_pct=result["coverage"],
            data_quality_score=result["data_quality"].score,
            details={
                "profile": {
                    "key": result["profile"].key, "label": result["profile"].label,
                    "notes": result["profile"].notes, "weights": result["profile"].alb_weights,
                },
                "quality": result["quality"].as_dict(), "value": result["value"].as_dict(),
                "growth": result["growth"].as_dict() if result["growth"] else None,
                "technical": result["technical"].as_dict(), "risk": result["risk"].as_dict(),
                "liquidity": result["liquidity"].as_dict(), "explanation": result["explanation"],
            },
        )
        processed += 1
    return processed


def handle_market_catalog_refresh(payload: dict) -> dict:
    snapshot_key = str(payload.get("snapshot_key") or "market-catalog:main")
    session = get_session_factory()()
    try:
        pipeline = MarketIngestionPipeline(session)
        deactivated = len(pipeline.repo.deactivate_unsupported_assets())
        result = pipeline.ingest_other_b3()
        summary = {"deactivated": deactivated, "other_b3": _summary(result)}
        SharedSnapshotRepository(session).save_valid(
            snapshot_key=snapshot_key, snapshot_kind="market_catalog", payload=summary,
            source="TradingView", as_of=utcnow(), valid_until=utcnow() + timedelta(hours=24),
        )
        session.commit()
        return summary
    except Exception as exc:
        session.rollback()
        _record_refresh_failure(snapshot_key, exc)
        raise
    finally:
        session.close()


def handle_market_fundamentals_refresh(payload: dict) -> dict:
    snapshot_key = str(payload.get("snapshot_key") or "market-fundamentals:main")
    session = get_session_factory()()
    try:
        pipeline = MarketIngestionPipeline(session)
        stocks = pipeline.ingest_stocks()
        fiis = pipeline.ingest_fiis()
        scores = {"stock": _refresh_scores(session, "stock"), "fii": _refresh_scores(session, "fii")}
        result = {"stocks": _summary(stocks), "fiis": _summary(fiis), "scores": scores}
        SharedSnapshotRepository(session).save_valid(
            snapshot_key=snapshot_key, snapshot_kind="market_fundamentals", payload=result,
            source="Fundamentus", as_of=utcnow(), valid_until=utcnow() + timedelta(hours=24),
        )
        session.commit()
        return result
    except Exception as exc:
        session.rollback()
        _record_refresh_failure(snapshot_key, exc)
        raise
    finally:
        session.close()


def handle_market_technicals_refresh(payload: dict) -> dict:
    snapshot_key = str(payload.get("snapshot_key") or "market-technicals:daily")
    session = get_session_factory()()
    try:
        pipeline = MarketIngestionPipeline(session)
        stocks = pipeline.ingest_technicals("stock")
        fiis = pipeline.ingest_technicals("fii")
        result = {"stocks": _summary(stocks), "fiis": _summary(fiis)}
        SharedSnapshotRepository(session).save_valid(
            snapshot_key=snapshot_key, snapshot_kind="market_technicals", payload=result,
            source="TradingView", as_of=utcnow(), valid_until=utcnow() + timedelta(hours=24),
        )
        session.commit()
        return result
    except Exception as exc:
        session.rollback()
        _record_refresh_failure(snapshot_key, exc)
        raise
    finally:
        session.close()


def handle_market_intraday_refresh(payload: dict) -> dict:
    snapshot_key = str(payload.get("snapshot_key") or "market-technicals:intraday")
    session = get_session_factory()()
    try:
        supported_types = {"stock", "fii", "etf", "bdr", "future"}
        tickers = set(session.scalars(
            select(AssetORM.ticker)
            .join(PortfolioPositionORM, PortfolioPositionORM.asset_id == AssetORM.id)
            .where(AssetORM.asset_type.in_(supported_types), AssetORM.is_active.is_(True))
        ))
        tickers.update(session.scalars(select(PriceAlertORM.symbol).where(PriceAlertORM.status == "active")))
        tickers = sorted(item for item in tickers if item)[:100]
    finally:
        session.close()
    quotes, failures = {}, []
    def quote(ticker):
        return IntradayQuoteProvider().snapshot([ticker], market_scope="b3")
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(quote, ticker): ticker for ticker in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                quotes[ticker] = future.result()
            except Exception:
                failures.append(ticker)
    result = {"quotes": quotes, "requested": len(tickers), "received": len(quotes), "failed": failures}
    return _save_snapshot(
        snapshot_key=snapshot_key, snapshot_kind="market_intraday", result=result,
        source="Yahoo Finance", valid_for=timedelta(hours=6),
    )


def handle_portfolio_prices_refresh(payload: dict) -> dict:
    portfolio_id = str(payload.get("portfolio_id") or "").strip()
    owner_email = str(payload.get("owner_email") or "").strip().lower()
    if not portfolio_id or not owner_email:
        raise ValueError("portfolio_refresh_identification_required")
    session = get_session_factory()()
    try:
        repository = PortfolioRepository(session)
        portfolio = repository.get_portfolio(UUID(portfolio_id), owner_email)
        if portfolio is None:
            raise ValueError("portfolio_not_found")
        assets = [(asset.ticker, asset.asset_type) for _position, asset in repository.positions(portfolio.id)]
    finally:
        session.close()
    results = []
    for ticker, asset_type in assets:
        if asset_type in {"fixed_income", "crypto"}:
            results.append({"ticker": ticker, "status": "skipped", "reason": "provider_not_configured"})
            continue
        asset_session = get_session_factory()()
        try:
            ingestion = PriceIngestionService(asset_session)
            saved = ingestion.ingest_asset(ticker, asset_type=asset_type, range_="1mo")
            asset_session.commit()
            results.append({"ticker": ticker, "status": "ok", "bars": saved.get("bars", 0)})
        except Exception as exc:
            asset_session.rollback()
            results.append({"ticker": ticker, "status": "error", "error": type(exc).__name__})
        finally:
            asset_session.close()
    return {"portfolio_id": portfolio_id, "results": results, "finished_at": utcnow().isoformat()}


def _portfolio_news_assets(session, portfolio_id) -> list[dict]:
    assets = []
    for position, asset in PortfolioRepository(session).positions(portfolio_id):
        if (
            asset.asset_type == "stock"
            and is_supported_ticker(asset.ticker, asset.asset_type)
            and float(position.quantity or 0) > 0
        ):
            assets.append({"ticker": asset.ticker, "name": asset.name})
    return sorted(assets, key=lambda item: item["ticker"])


def handle_user_news_refresh(payload: dict) -> dict:
    cache_id = UUID(str(payload.get("cache_id") or ""))
    session = get_session_factory()()
    try:
        row = session.get(UserNewsCacheORM, cache_id)
        if row is None:
            raise ValueError("news_cache_not_found")
        repository = NewsCacheRepository(session)
        repository.mark_running(row)
        session.commit()

        if row.cache_kind == "portfolio":
            portfolio = PortfolioRepository(session).get_portfolio(UUID(row.cache_key), row.owner_email)
            if portfolio is None:
                raise ValueError("portfolio_not_found")
            assets = _portfolio_news_assets(session, portfolio.id)
            result = MarketNewsService().portfolio_news(assets[:50], limit_per_asset=3)
            result.update({
                "portfolio_id": str(portfolio.id), "portfolio_name": portfolio.name,
                "total_stocks": len(assets), "truncated": len(assets) > 50,
            })
        elif row.cache_kind == "recommendations":
            category = row.cache_key if row.cache_key in {"all", "brazil", "global"} else "all"
            assets = AssetRepository(session).list_assets("stock", limit=1200)
            result = MarketNewsService().recommendations(
                category=category, limit=50,
                asset_names={asset.ticker: asset.name or "" for asset in assets},
            )
        else:
            raise ValueError("unsupported_news_cache_kind")

        row = session.get(UserNewsCacheORM, cache_id)
        repository.mark_completed(row, _json_safe(result))
        session.commit()
        return {"cache_id": str(cache_id), "cache_kind": row.cache_kind, "status": "completed"}
    except Exception as exc:
        session.rollback()
        row = session.get(UserNewsCacheORM, cache_id)
        if row is not None:
            NewsCacheRepository(session).mark_failed(row, f"{type(exc).__name__}: {str(exc)[:500]}")
            session.commit()
        raise
    finally:
        session.close()


def _payload_datetime(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=utcnow().tzinfo)


def handle_personal_backtest_matrix(payload: dict) -> dict:
    """Run a private comparison or a true multi-strategy combination off-request."""
    job_id = UUID(str(payload["_background_job_id"]))
    usage_id = UUID(str(payload["usage_id"]))
    owner_email = str(payload["owner_email"]).strip().lower()
    tickers = list(dict.fromkeys(str(item).strip().upper() for item in payload.get("tickers", []) if str(item).strip()))
    strategy_ids = list(dict.fromkeys(str(item).strip() for item in payload.get("strategy_ids", []) if str(item).strip()))
    execution_mode = str(payload.get("execution_mode") or "compare")
    combination_rule = str(payload.get("combination_rule") or "all")
    final_attempt = int(payload.get("_background_job_attempt") or 1) >= int(payload.get("_background_job_max_attempts") or 1)
    total = len(tickers)
    rows: list[dict] = []
    failures: list[dict] = []
    session = get_session_factory()()
    try:
        usage = session.get(BacktestRequestUsageORM, usage_id)
        if usage is None or usage.owner_email != owner_email:
            raise ValueError("backtest_usage_not_found")
        usage.status = "running"
        usage.updated_at = utcnow()
        BackgroundJobRepository(session).report_progress(
            job_id, current=0, total=total, message="Preparando históricos e estratégias.",
        )
        session.commit()

        for index, ticker in enumerate(tickers, start=1):
            try:
                service = BacktestService(session)
                common = {
                    "ticker": ticker,
                    "asset_type": str(payload.get("asset_type") or "stock"),
                    "period": str(payload.get("period") or "5y"),
                    "start": _payload_datetime(payload.get("start")),
                    "end": _payload_datetime(payload.get("end")),
                    "initial_capital": float(payload.get("initial_capital") or 10000.0),
                    "fee_pct": float(payload.get("fee_pct") or 0.03),
                    "slippage_pct": float(payload.get("slippage_pct") or 0.05),
                    "risk_free_rate_pct": float(payload.get("risk_free_rate_pct") or 0.0),
                    "cash_yield_rate_pct": float(payload.get("cash_yield_rate_pct") or 0.0),
                    "apply_cash_yield": bool(payload.get("apply_cash_yield")),
                    "filters": dict(payload.get("filters") or {}),
                    "owner_email": owner_email,
                }
                if execution_mode == "combined":
                    rows.append(service.run_combined(
                        strategy_ids=strategy_ids, combination_rule=combination_rule, **common,
                    ))
                else:
                    rows.extend(service.compare(strategy_ids=strategy_ids, **common))
                session.commit()
            except Exception as exc:
                session.rollback()
                failures.append({
                    "ticker": ticker,
                    "error_code": type(exc).__name__,
                    "message": str(exc)[:300],
                })
            BackgroundJobRepository(session).report_progress(
                job_id, current=index, total=total,
                message=f"{index} de {total} ativo(s) processado(s).",
            )
            session.commit()

        usage = session.get(BacktestRequestUsageORM, usage_id)
        usage.status = "completed" if rows and not failures else "completed_with_errors" if rows else "failed" if final_attempt else "queued"
        usage.error_json = failures
        usage.finished_at = utcnow() if rows or final_attempt else None
        usage.updated_at = utcnow()
        session.commit()
        if not rows:
            raise ValueError("personal_backtest_all_assets_failed")
        return {
            "request_id": str(usage_id), "results": rows, "failures": failures,
            "assets_requested": total, "strategies_requested": len(strategy_ids),
            "execution_mode": execution_mode, "combination_rule": combination_rule if execution_mode == "combined" else None,
        }
    except Exception:
        session.rollback()
        usage = session.get(BacktestRequestUsageORM, usage_id)
        if usage is not None and usage.finished_at is None:
            usage.status = "failed" if final_attempt else "queued"
            usage.finished_at = utcnow() if final_attempt else None
            usage.updated_at = utcnow()
            session.commit()
        raise
    finally:
        session.close()


DEFAULT_JOB_HANDLERS = {
    "noop": handle_noop,
    "market_dashboard_refresh": handle_market_dashboard_refresh,
    "economy_headlines_refresh": handle_economy_headlines_refresh,
    "market_group_refresh": handle_market_group_refresh,
    "historical_comparison_refresh": handle_historical_comparison_refresh,
    "market_catalog_refresh": handle_market_catalog_refresh,
    "market_fundamentals_refresh": handle_market_fundamentals_refresh,
    "market_technicals_refresh": handle_market_technicals_refresh,
    "market_intraday_refresh": handle_market_intraday_refresh,
    "portfolio_prices_refresh": handle_portfolio_prices_refresh,
    "user_news_refresh": handle_user_news_refresh,
    "personal_backtest_matrix": handle_personal_backtest_matrix,
}
