from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .engine import run_backtest
from .filters import filter_warmup_calendar_days
from .grid import DEFAULT_MAX_COMBINATIONS, OFFICIAL_GRID_VERSION, official_grid
from .ranking import enrich_result
from .service import ENGINE_VERSION, BacktestService, _bar_dict, _fundamental_dict, resolve_period
from .strategies import STRATEGIES, warmup_bars
from ..repositories.backtests import BacktestRepository
from ..repositories.assets import AssetRepository
from ..strategies.presets import STOCK_STRATEGIES
from ...infrastructure.db.models import BacktestBatchJobORM


OFFICIAL_OWNER = "official-catalog@system.local"
MAX_BATCH_ASSETS = 100
DEFAULT_BATCH_ASSETS = 50


class BacktestBatchService:
    def __init__(self, session):
        self.session = session
        self.assets = AssetRepository(session)
        self.backtests = BacktestRepository(session)
        self.service = BacktestService(session)

    def default_tickers(self) -> list[str]:
        rows = self.assets.screen_latest_stocks(STOCK_STRATEGIES["default"].filters, limit=DEFAULT_BATCH_ASSETS)
        tickers = [asset.ticker for asset, _fundamental, _score in rows]
        if not tickers:
            tickers = [asset.ticker for asset in self.assets.list_assets("stock", limit=DEFAULT_BATCH_ASSETS)]
        return tickers[:DEFAULT_BATCH_ASSETS]

    def create_job(self, *, requested_by: str, source: str, tickers: list[str] | None, max_combinations: int):
        clean = []
        for ticker in tickers or self.default_tickers():
            value = str(ticker).strip().upper()
            if value and value not in clean:
                clean.append(value)
        if not clean:
            raise ValueError("batch_requires_tickers")
        if len(clean) > MAX_BATCH_ASSETS:
            raise ValueError("batch_asset_limit_100")
        job = BacktestBatchJobORM(
            requested_by=requested_by.strip().lower(), source=source, status="queued",
            requested_tickers_json=clean, grid_version=OFFICIAL_GRID_VERSION,
            max_combinations=max(1, min(int(max_combinations), DEFAULT_MAX_COMBINATIONS)),
        )
        self.session.add(job)
        self.session.flush()
        return job

    def list_jobs(self, limit: int = 20):
        return list(self.session.scalars(
            select(BacktestBatchJobORM).order_by(BacktestBatchJobORM.created_at.desc()).limit(limit)
        ))

    def get_job(self, job_id):
        return self.session.get(BacktestBatchJobORM, job_id)

    def mark_failed(self, job, *, code: str, message: str, details: dict | None = None):
        if job.status in {"completed", "completed_with_errors"}:
            return job
        error = {"code": str(code)[:80], "message": str(message)[:500]}
        if details:
            error["details"] = details
        job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        job.error_json = [*(job.error_json or []), error][-200:]
        self.session.flush()
        return job

    def run_job(self, job) -> dict:
        if job.status in {"completed", "completed_with_errors"}:
            return self.job_dict(job)
        if job.status == "running":
            raise ValueError("batch_job_already_running")
        configurations = official_grid(job.max_combinations)
        tickers = list(job.requested_tickers_json or [])[:MAX_BATCH_ASSETS]
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.total_runs = len(configurations) * len(tickers)
        self.session.flush()
        errors = []
        for ticker in tickers:
            try:
                completed, failed, asset_errors = self._run_asset(ticker, configurations, job.id)
                job.completed_runs += completed
                job.failed_runs += failed
                errors.extend(asset_errors)
                self.session.commit()
            except Exception as exc:
                self.session.rollback()
                job = self.session.get(BacktestBatchJobORM, job.id)
                job.failed_runs += len(configurations)
                errors.append({"ticker": ticker, "error": str(exc)})
                job.error_json = errors[-200:]
                self.session.commit()
        job = self.session.get(BacktestBatchJobORM, job.id)
        job.status = "completed_with_errors" if job.failed_runs else "completed"
        job.finished_at = datetime.now(timezone.utc)
        job.error_json = errors[-200:]
        self.session.commit()
        return self.job_dict(job)

    def _run_asset(self, ticker: str, configurations: list[dict], batch_job_id):
        requested_start, requested_end = resolve_period("5y")
        max_warm = max(warmup_bars(row["strategy_id"], row["params"]) for row in configurations)
        max_filter_days = max(filter_warmup_calendar_days(row["filters"]) for row in configurations)
        warmup_start = requested_start - timedelta(days=max(60, max_warm * 2, max_filter_days))
        asset, price_rows = self.service.ensure_history(ticker, asset_type="stock", start=warmup_start, end=requested_end)
        bars = [_bar_dict(row) for row in price_rows]
        fundamentals = [_fundamental_dict(row) for row in self.assets.fundamental_history_until(asset.id, end=requested_end)]
        completed = failed = 0
        errors = []
        for configuration in configurations:
            sid = configuration["strategy_id"]
            params = configuration["params"]
            filters = configuration["filters"]
            config_hash = self.service._configuration_hash(
                ticker=asset.ticker, asset_type="stock", strategy_id=sid, period="5y",
                requested_start=requested_start, requested_end=requested_end, initial_capital=10000.0,
                fee_pct=0.03, slippage_pct=0.05, risk_free_rate_pct=0.0,
                cash_yield_rate_pct=0.0, apply_cash_yield=False, params=params, filters=filters,
            )
            if self.backtests.find_daily_cached(owner_email=OFFICIAL_OWNER, scope="official", config_hash=config_hash):
                completed += 1
                continue
            try:
                with self.session.begin_nested():
                    result = run_backtest(
                        bars, strategy_id=sid, requested_start=requested_start, requested_end=requested_end,
                        initial_capital=10000.0, fee_pct=0.03, slippage_pct=0.05,
                        risk_free_rate_pct=0.0, params=params, filters=filters,
                        fundamental_snapshots=fundamentals,
                    )
                    result.update({
                        "ticker": asset.ticker, "asset_name": asset.name, "asset_type": asset.asset_type,
                        "period": "5y", "period_label": "5 anos", "engine_version": ENGINE_VERSION,
                        "scope": "official", "config_hash": config_hash,
                    })
                    enrich_result(result)
                    run = self.backtests.save_run(
                        asset=asset, owner_email=OFFICIAL_OWNER, scope="official", config_hash=config_hash,
                        strategy_id=sid, strategy_name=STRATEGIES[sid].name,
                        requested_start=requested_start, requested_end=requested_end,
                        actual_start=datetime.fromisoformat(result["actual_start"]),
                        actual_end=datetime.fromisoformat(result["actual_end"]), initial_capital=10000.0,
                        fee_pct=0.03, slippage_pct=0.05, risk_free_rate_pct=0.0,
                        parameters={"strategy": result["parameters"], "filters": result.get("filters") or {},
                                    "financial": {"apply_cash_yield": False, "cash_yield_rate_pct": 0.0}},
                        metrics=result["metrics"], equity_curve=result["equity_curve"], trades=result["trades"],
                        snapshot=result, ranking_score=result["ranking_score"], sample_status=result["sample_status"],
                        current_signal=result.get("current_signal"), engine_version=ENGINE_VERSION,
                        batch_job_id=batch_job_id, compact_curve=True,
                    )
                    result["run_id"] = str(run.id)
                completed += 1
            except Exception as exc:
                failed += 1
                errors.append({"ticker": ticker, "strategy_id": sid, "error": str(exc)})
        return completed, failed, errors

    @staticmethod
    def job_dict(job) -> dict:
        return {
            "id": str(job.id), "requested_by": job.requested_by, "source": job.source,
            "status": job.status, "tickers": job.requested_tickers_json,
            "grid_version": job.grid_version, "max_combinations": job.max_combinations,
            "total_runs": job.total_runs, "completed_runs": job.completed_runs,
            "failed_runs": job.failed_runs, "errors": job.error_json,
            "started_at": job.started_at, "finished_at": job.finished_at, "created_at": job.created_at,
        }
