from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...infrastructure.db.models import BacktestRunORM, BacktestTradeORM, AssetORM


def _d(v):
    return None if v is None else Decimal(str(v))


class BacktestRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_run(self, *, asset: AssetORM, strategy_id: str, strategy_name: str, requested_start: datetime,
                 requested_end: datetime, actual_start: datetime | None, actual_end: datetime | None,
                 initial_capital: float, fee_pct: float, slippage_pct: float, risk_free_rate_pct: float,
                 parameters: dict, metrics: dict, equity_curve: list, trades: list, data_source="yahoo",
                 status="valid") -> BacktestRunORM:
        run = BacktestRunORM(
            asset_id=asset.id,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            requested_start=requested_start,
            requested_end=requested_end,
            actual_start=actual_start,
            actual_end=actual_end,
            initial_capital=_d(initial_capital),
            fee_pct=_d(fee_pct) or Decimal("0"),
            slippage_pct=_d(slippage_pct) or Decimal("0"),
            risk_free_rate_pct=_d(risk_free_rate_pct) or Decimal("0"),
            parameters_json=parameters or {},
            metrics_json=metrics or {},
            equity_curve_json=equity_curve or [],
            data_source=data_source,
            status=status,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.flush()
        for i, t in enumerate(trades, start=1):
            self.session.add(BacktestTradeORM(
                run_id=run.id,
                sequence=i,
                entry_date=t["entry_date"],
                entry_price=_d(t["entry_price"]),
                exit_date=t.get("exit_date"),
                exit_price=_d(t.get("exit_price")),
                return_pct=_d(t.get("return_pct")),
                pnl_value=_d(t.get("pnl_value")),
                holding_days=t.get("holding_days"),
                exit_reason=t.get("exit_reason"),
            ))
        self.session.flush()
        return run

    def list_runs(self, *, ticker: str | None = None, limit: int = 50):
        stmt = select(BacktestRunORM, AssetORM).join(AssetORM, AssetORM.id == BacktestRunORM.asset_id)
        if ticker:
            stmt = stmt.where(AssetORM.ticker == ticker.upper())
        stmt = stmt.order_by(BacktestRunORM.created_at.desc()).limit(limit)
        return list(self.session.execute(stmt).all())

    def get_run(self, run_id):
        return self.session.scalar(select(BacktestRunORM).where(BacktestRunORM.id == run_id))

    def trades(self, run_id):
        return list(self.session.scalars(select(BacktestTradeORM).where(BacktestTradeORM.run_id == run_id).order_by(BacktestTradeORM.sequence)))
