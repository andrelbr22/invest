from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

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
from ...infrastructure.db.models import BacktestBatchDeliveryORM, BacktestBatchJobORM


OFFICIAL_OWNER = "official-catalog@system.local"
MAX_BATCH_ASSETS = 100
DEFAULT_BATCH_ASSETS = 50
TERMINAL_BATCH_STATUSES = {"completed", "completed_with_errors", "failed", "cancelled"}


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

    def normalize_job_tickers(self, tickers: list[str] | None) -> list[str]:
        clean = []
        for ticker in tickers or self.default_tickers():
            value = str(ticker).strip().upper()
            if value and value not in clean:
                clean.append(value)
        if not clean:
            raise ValueError("batch_requires_tickers")
        if len(clean) > MAX_BATCH_ASSETS:
            raise ValueError("batch_asset_limit_100")
        return clean

    def create_job(
        self, *, requested_by: str, source: str, tickers: list[str] | None,
        max_combinations: int, job_id: UUID | None = None,
    ):
        clean = self.normalize_job_tickers(tickers)
        job = BacktestBatchJobORM(
            id=job_id,
            requested_by=requested_by.strip().lower(), source=source, status="queued",
            requested_tickers_json=clean, grid_version=OFFICIAL_GRID_VERSION,
            max_combinations=max(1, min(int(max_combinations), DEFAULT_MAX_COMBINATIONS)),
        )
        self.session.add(job)
        self.session.flush()
        return job

    def active_job(self):
        return self.session.scalar(
            select(BacktestBatchJobORM)
            .where(BacktestBatchJobORM.status.in_(("queued", "running")))
            .order_by(BacktestBatchJobORM.created_at.desc())
            .limit(1)
        )

    def create_site_job(
        self, *, requested_by: str, tickers: list[str], max_combinations: int,
        source: str = "site",
    ):
        clean = self.normalize_job_tickers(tickers)
        combinations = max(1, min(int(max_combinations), DEFAULT_MAX_COMBINATIONS))
        active = self.active_job()
        if active is not None:
            equal_request = (
                list(active.requested_tickers_json or []) == clean
                and int(active.max_combinations) == combinations
            )
            if equal_request:
                return active, False
            raise ValueError(f"batch_job_active:{active.id}")
        return self.create_job(
            requested_by=requested_by,
            source=source,
            tickers=clean,
            max_combinations=combinations,
        ), True

    def create_retry_job(self, source_job, *, requested_by: str):
        if source_job.status not in TERMINAL_BATCH_STATUSES:
            raise ValueError("batch_retry_requires_terminal_job")
        retry_tickers = self.job_dict(source_job)["retry_tickers"]
        if not retry_tickers:
            raise ValueError("batch_retry_has_no_assets")
        return self.create_site_job(
            requested_by=requested_by,
            source="retry",
            tickers=retry_tickers,
            max_combinations=source_job.max_combinations,
        )

    def list_jobs(self, limit: int = 20):
        return list(self.session.scalars(
            select(BacktestBatchJobORM).order_by(BacktestBatchJobORM.created_at.desc()).limit(limit)
        ))

    def get_job(self, job_id):
        return self.session.get(BacktestBatchJobORM, job_id)

    def deliveries(self, job_id) -> list[BacktestBatchDeliveryORM]:
        return list(self.session.scalars(
            select(BacktestBatchDeliveryORM)
            .where(BacktestBatchDeliveryORM.batch_job_id == job_id)
            .order_by(BacktestBatchDeliveryORM.received_at, BacktestBatchDeliveryORM.ticker)
        ))

    def start_existing_job(self, job) -> dict:
        if job.status == "failed":
            raise ValueError("batch_job_failed")
        if job.status == "cancelled":
            raise ValueError("batch_job_cancelled")
        if job.status not in TERMINAL_BATCH_STATUSES:
            job.status = "running"
            job.started_at = job.started_at or datetime.now(timezone.utc)
            job.total_runs = len(official_grid(job.max_combinations)) * len(job.requested_tickers_json or [])
            self.session.flush()
        return self.job_dict(job)

    def start_scheduled_job(self, *, max_combinations: int, tickers: list[str] | None = None):
        clean = self.normalize_job_tickers(tickers)
        combinations = max(1, min(int(max_combinations), DEFAULT_MAX_COMBINATIONS))
        active = self.active_job()
        if active is not None:
            equal_request = (
                active.source == "scheduled"
                and list(active.requested_tickers_json or []) == clean
                and int(active.max_combinations) == combinations
            )
            if equal_request:
                return active, False
            raise ValueError(f"batch_job_active:{active.id}")
        recent = self.session.scalar(
            select(BacktestBatchJobORM)
            .where(
                BacktestBatchJobORM.source == "scheduled",
                BacktestBatchJobORM.status.in_(("completed", "completed_with_errors")),
                BacktestBatchJobORM.created_at >= datetime.now(timezone.utc) - timedelta(hours=20),
            )
            .order_by(BacktestBatchJobORM.created_at.desc())
            .limit(1)
        )
        if recent is not None and (
            list(recent.requested_tickers_json or []) == clean
            and int(recent.max_combinations) == combinations
        ):
            return recent, False
        job = self.create_job(
            requested_by="github-actions@system.local",
            source="scheduled",
            tickers=clean,
            max_combinations=combinations,
        )
        return job, True

    def mark_failed(self, job, *, code: str, message: str, details: dict | None = None):
        if job.status in {"completed", "completed_with_errors", "cancelled"}:
            return job
        error = {"code": str(code)[:80], "message": str(message)[:500]}
        if details:
            error["details"] = details
        job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        job.error_json = [*(job.error_json or []), error][-200:]
        self.session.flush()
        return job

    def mark_cancelled(
        self, job, *, requested_by: str,
        reason: str = "Cancelamento solicitado pelo administrador.", details: dict | None = None,
    ):
        if job.status == "cancelled":
            return job
        if job.status in {"completed", "completed_with_errors", "failed"}:
            raise ValueError("batch_job_not_active")
        audit = {
            "code": "cancelled_by_owner",
            "message": str(reason or "Cancelamento solicitado pelo administrador.")[:500],
            "requested_by": str(requested_by or "").strip().lower()[:320],
        }
        if details:
            audit["details"] = details
        job.status = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
        job.error_json = [*(job.error_json or []), audit][-200:]
        self.session.flush()
        return job

    def receive_asset_delivery(
        self, job, *, ticker: str, checksum: str, completed_runs: int,
        failed_runs: int, results: list[dict], errors: list[dict],
    ) -> tuple[BacktestBatchDeliveryORM, bool]:
        clean_ticker = str(ticker).strip().upper()
        if clean_ticker not in set(job.requested_tickers_json or []):
            raise ValueError("batch_delivery_ticker_not_requested")
        expected_runs = len(official_grid(job.max_combinations))
        if completed_runs < 0 or failed_runs < 0 or completed_runs + failed_runs != expected_runs:
            raise ValueError("batch_delivery_incomplete_asset")
        if len(results) > completed_runs:
            raise ValueError("batch_delivery_result_count_invalid")
        existing = self.session.scalar(
            select(BacktestBatchDeliveryORM).where(
                BacktestBatchDeliveryORM.batch_job_id == job.id,
                BacktestBatchDeliveryORM.ticker == clean_ticker,
            )
        )
        if existing is not None:
            if existing.checksum != checksum:
                raise ValueError("batch_delivery_checksum_conflict")
            return existing, False
        if job.status == "failed":
            raise ValueError("batch_job_failed")
        if job.status == "cancelled":
            raise ValueError("batch_job_cancelled")
        if job.status in {"completed", "completed_with_errors"}:
            raise ValueError("batch_job_already_completed")

        imported = skipped = 0
        for package in results:
            _run, created = self.backtests.import_official_result(
                package,
                batch_job_id=job.id,
                asset_repository=self.assets,
            )
            if created:
                imported += 1
            else:
                skipped += 1
        delivery = BacktestBatchDeliveryORM(
            batch_job_id=job.id,
            ticker=clean_ticker,
            checksum=checksum,
            status="received_with_errors" if failed_runs else "received",
            completed_runs=completed_runs,
            failed_runs=failed_runs,
            imported_runs=imported,
            skipped_runs=skipped,
            received_at=datetime.now(timezone.utc),
        )
        self.session.add(delivery)
        self.session.flush()
        all_deliveries = self.deliveries(job.id)
        job.status = "running"
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.total_runs = expected_runs * len(job.requested_tickers_json or [])
        job.completed_runs = sum(item.completed_runs for item in all_deliveries)
        job.failed_runs = sum(item.failed_runs for item in all_deliveries)
        if errors:
            safe_errors = [{
                "ticker": clean_ticker,
                "strategy_id": str(item.get("strategy_id") or "")[:64] or None,
                "error": str(item.get("error") or item.get("message") or "Falha no backtest")[:500],
            } for item in errors[:200]]
            job.error_json = [*(job.error_json or []), *safe_errors][-200:]
        if len(all_deliveries) == len(job.requested_tickers_json or []):
            job.status = "completed_with_errors" if job.failed_runs else "completed"
            job.finished_at = datetime.now(timezone.utc)
        self.session.flush()
        return delivery, True

    def finalize_job(self, job):
        if job.status == "failed":
            raise ValueError("batch_job_failed")
        if job.status == "cancelled":
            raise ValueError("batch_job_cancelled")
        if job.status in {"completed", "completed_with_errors"}:
            return job
        deliveries = self.deliveries(job.id)
        delivered = {item.ticker for item in deliveries}
        requested = set(job.requested_tickers_json or [])
        if delivered != requested:
            raise ValueError("batch_job_has_pending_assets")
        job.completed_runs = sum(item.completed_runs for item in deliveries)
        job.failed_runs = sum(item.failed_runs for item in deliveries)
        job.status = "completed_with_errors" if job.failed_runs else "completed"
        job.finished_at = datetime.now(timezone.utc)
        self.session.flush()
        return job

    def run_job(self, job, *, asset_callback: Callable[[dict], None] | None = None) -> dict:
        if job.status in {"completed", "completed_with_errors"}:
            return self.job_dict(job)
        if job.status == "cancelled":
            raise ValueError("batch_job_cancelled")
        if job.status == "running":
            raise ValueError("batch_job_already_running")
        configurations = official_grid(job.max_combinations)
        tickers = list(job.requested_tickers_json or [])[:MAX_BATCH_ASSETS]
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.total_runs = len(configurations) * len(tickers)
        self.session.flush()
        errors: list[dict] = []
        for ticker in tickers:
            asset_errors: list[dict] = []
            try:
                completed, failed, asset_errors = self._run_asset(ticker, configurations, job.id)
                job.completed_runs += completed
                job.failed_runs += failed
                errors.extend(asset_errors)
                self.session.commit()
            except Exception as exc:
                self.session.rollback()
                job = self.session.get(BacktestBatchJobORM, job.id)
                completed = 0
                failed = len(configurations)
                asset_errors = [{"ticker": ticker, "error": str(exc)}]
                job.failed_runs += failed
                errors.extend(asset_errors)
                job.error_json = errors[-200:]
                self.session.commit()
            if asset_callback is not None:
                asset_callback(self.asset_delivery_payload(
                    job_id=job.id,
                    ticker=ticker,
                    completed_runs=completed,
                    failed_runs=failed,
                    errors=asset_errors,
                ))
        job = self.session.get(BacktestBatchJobORM, job.id)
        job.status = "completed_with_errors" if job.failed_runs else "completed"
        job.finished_at = datetime.now(timezone.utc)
        job.error_json = errors[-200:]
        self.session.commit()
        return self.job_dict(job)

    def asset_delivery_payload(
        self, *, job_id, ticker: str, completed_runs: int,
        failed_runs: int, errors: list[dict],
    ) -> dict:
        return {
            "ticker": str(ticker).strip().upper(),
            "completed_runs": int(completed_runs),
            "failed_runs": int(failed_runs),
            "errors": list(errors or [])[:200],
            "results": self.backtests.export_batch_asset(batch_job_id=job_id, ticker=ticker),
        }

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

    def job_dict(self, job) -> dict:
        deliveries = self.deliveries(job.id)
        processed = len(deliveries)
        total_assets = len(job.requested_tickers_json or [])
        delivered_tickers = [item.ticker for item in deliveries]
        delivered_set = set(delivered_tickers)
        pending_tickers = [ticker for ticker in (job.requested_tickers_json or []) if ticker not in delivered_set]
        failed_set = {item.ticker for item in deliveries if int(item.failed_runs or 0) > 0}
        failed_tickers = [ticker for ticker in (job.requested_tickers_json or []) if ticker in failed_set]
        retry_set = set(pending_tickers) | failed_set
        retry_tickers = [ticker for ticker in (job.requested_tickers_json or []) if ticker in retry_set]
        last_delivery = deliveries[-1] if deliveries else None
        return {
            "id": str(job.id), "requested_by": job.requested_by, "source": job.source,
            "status": job.status, "tickers": job.requested_tickers_json,
            "grid_version": job.grid_version, "max_combinations": job.max_combinations,
            "total_runs": job.total_runs, "completed_runs": job.completed_runs,
            "failed_runs": job.failed_runs, "errors": job.error_json,
            "processed_assets": processed, "total_assets": total_assets,
            "progress_pct": round((processed / total_assets) * 100, 1) if total_assets else 0.0,
            "delivered_tickers": delivered_tickers, "pending_tickers": pending_tickers,
            "failed_tickers": failed_tickers, "retry_tickers": retry_tickers,
            "last_ticker": last_delivery.ticker if last_delivery else None,
            "last_update_at": last_delivery.received_at if last_delivery else job.started_at,
            "started_at": job.started_at, "finished_at": job.finished_at, "created_at": job.created_at,
        }
