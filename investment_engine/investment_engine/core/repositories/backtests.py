from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...infrastructure.db.models import AssetORM, BacktestRunORM, BacktestTradeORM


SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def _d(value):
    return None if value is None else Decimal(str(value))


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _compact_curve(curve: list[dict], maximum_points: int = 80) -> list[dict]:
    rows = list(curve or [])
    if len(rows) <= maximum_points:
        return rows
    indexes = {0, len(rows) - 1}
    for position in range(1, maximum_points - 1):
        indexes.add(round(position * (len(rows) - 1) / (maximum_points - 1)))
    return [rows[index] for index in sorted(indexes)]


def backtest_market_date(now: datetime | None = None) -> date:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(SAO_PAULO).date()


def build_config_hash(payload: dict) -> str:
    encoded = json.dumps(_json_safe(payload), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class BacktestRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_run(
        self, *, asset: AssetORM, owner_email: str, scope: str, config_hash: str,
        strategy_id: str, strategy_name: str, requested_start: datetime, requested_end: datetime,
        actual_start: datetime | None, actual_end: datetime | None, initial_capital: float,
        fee_pct: float, slippage_pct: float, risk_free_rate_pct: float, parameters: dict,
        metrics: dict, equity_curve: list, trades: list, snapshot: dict | None = None,
        ranking_score: float | None = None, sample_status: str = "insufficient",
        current_signal: dict | None = None, data_source: str = "yahoo", status: str = "valid",
        engine_version: str = "0.11.4", sector_label: str | None = None, batch_job_id=None,
        compact_curve: bool = False,
    ) -> BacktestRunORM:
        signal = current_signal or {}
        signal_as_of = signal.get("as_of")
        if isinstance(signal_as_of, str):
            signal_as_of = datetime.fromisoformat(signal_as_of)
        metadata = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
        stored_curve = _compact_curve(equity_curve) if compact_curve else list(equity_curve or [])
        stored_snapshot = dict(snapshot or {})
        for bulky_field in ("equity_curve", "trades", "events"):
            stored_snapshot.pop(bulky_field, None)
        stored_snapshot["curve_granularity"] = "compact" if compact_curve else "daily"
        run = BacktestRunORM(
            asset_id=asset.id, owner_email=str(owner_email).strip().lower(), scope=scope,
            config_hash=config_hash, market_date=backtest_market_date(), engine_version=engine_version,
            strategy_id=strategy_id, strategy_name=strategy_name,
            requested_start=requested_start, requested_end=requested_end,
            actual_start=actual_start, actual_end=actual_end, initial_capital=_d(initial_capital),
            fee_pct=_d(fee_pct) or Decimal("0"), slippage_pct=_d(slippage_pct) or Decimal("0"),
            risk_free_rate_pct=_d(risk_free_rate_pct) or Decimal("0"),
            parameters_json=_json_safe(parameters or {}), metrics_json=_json_safe(metrics or {}),
            equity_curve_json=_json_safe(stored_curve), result_json=_json_safe(stored_snapshot),
            ranking_score=_d(ranking_score), sample_status=sample_status,
            current_signal=str(signal.get("status") or "neutral"), signal_as_of=signal_as_of,
            sector_label=sector_label or metadata.get("sector_label") or asset.sector,
            batch_job_id=batch_job_id, data_source=data_source, status=status,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.flush()
        for sequence, trade in enumerate(trades, start=1):
            self.session.add(BacktestTradeORM(
                run_id=run.id, sequence=sequence, entry_date=trade["entry_date"],
                entry_price=_d(trade["entry_price"]), exit_date=trade.get("exit_date"),
                exit_price=_d(trade.get("exit_price")), return_pct=_d(trade.get("return_pct")),
                pnl_value=_d(trade.get("pnl_value")), holding_days=trade.get("holding_days"),
                exit_reason=trade.get("exit_reason"),
            ))
        self.session.flush()
        return run

    def find_daily_cached(self, *, owner_email: str, scope: str, config_hash: str, market_date: date | None = None):
        return self.session.scalar(
            select(BacktestRunORM).where(
                BacktestRunORM.owner_email == owner_email.strip().lower(), BacktestRunORM.scope == scope,
                BacktestRunORM.config_hash == config_hash,
                BacktestRunORM.market_date == (market_date or backtest_market_date()),
                BacktestRunORM.status == "valid",
            ).order_by(BacktestRunORM.created_at.desc()).limit(1)
        )

    def list_runs(
        self, *, owner_email: str, is_owner: bool = False, ticker: str | None = None,
        sector: str | None = None, scope: str | None = None, limit: int = 100,
    ):
        stmt = select(BacktestRunORM, AssetORM).join(AssetORM, AssetORM.id == BacktestRunORM.asset_id)
        if not is_owner:
            stmt = stmt.where(or_(BacktestRunORM.owner_email == owner_email.strip().lower(), BacktestRunORM.scope == "official"))
        if ticker:
            stmt = stmt.where(AssetORM.ticker == ticker.upper())
        if sector:
            stmt = stmt.where(BacktestRunORM.sector_label.ilike(f"%{sector.strip()}%"))
        if scope:
            stmt = stmt.where(BacktestRunORM.scope == scope)
        return list(self.session.execute(stmt.order_by(BacktestRunORM.created_at.desc()).limit(limit)).all())

    def get_run(self, run_id, *, owner_email: str, is_owner: bool = False):
        stmt = select(BacktestRunORM).where(BacktestRunORM.id == run_id)
        if not is_owner:
            stmt = stmt.where(or_(BacktestRunORM.owner_email == owner_email.strip().lower(), BacktestRunORM.scope == "official"))
        return self.session.scalar(stmt)

    def trades(self, run_id):
        return list(self.session.scalars(
            select(BacktestTradeORM).where(BacktestTradeORM.run_id == run_id).order_by(BacktestTradeORM.sequence)
        ))

    def leaderboard(self, *, tickers: list[str] | None = None, sector: str | None = None, per_asset: int = 3, limit: int = 5000):
        stmt = (
            select(BacktestRunORM, AssetORM).join(AssetORM, AssetORM.id == BacktestRunORM.asset_id)
            .where(BacktestRunORM.scope == "official", BacktestRunORM.status == "valid")
            .order_by(BacktestRunORM.created_at.desc()).limit(limit)
        )
        if tickers:
            clean = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
            if not clean:
                return {}
            stmt = stmt.where(AssetORM.ticker.in_(clean))
        if sector:
            stmt = stmt.where(BacktestRunORM.sector_label.ilike(f"%{sector.strip()}%"))
        newest_by_configuration = {}
        for run, asset in self.session.execute(stmt):
            newest_by_configuration.setdefault((run.asset_id, run.config_hash), (run, asset))
        grouped: dict[str, list[tuple]] = {}
        for run, asset in newest_by_configuration.values():
            grouped.setdefault(asset.ticker, []).append((run, asset))
        for ticker, rows in grouped.items():
            rows.sort(key=lambda item: (float(item[0].ranking_score or 0), item[0].created_at), reverse=True)
            grouped[ticker] = rows[: max(1, per_asset)]
        return grouped


def run_summary(run: BacktestRunORM, asset: AssetORM) -> dict:
    return {
        "id": str(run.id), "ticker": asset.ticker, "asset_name": asset.name,
        "sector": run.sector_label, "strategy_id": run.strategy_id, "strategy_name": run.strategy_name,
        "requested_start": run.requested_start, "requested_end": run.requested_end,
        "actual_start": run.actual_start, "actual_end": run.actual_end, "created_at": run.created_at,
        "market_date": run.market_date, "engine_version": run.engine_version, "scope": run.scope,
        "owner_email": run.owner_email, "metrics": run.metrics_json, "parameters": run.parameters_json,
        "status": run.status, "ranking_score": float(run.ranking_score) if run.ranking_score is not None else None,
        "sample_status": run.sample_status, "current_signal": run.current_signal,
        "signal_as_of": run.signal_as_of, "config_hash": run.config_hash,
    }
