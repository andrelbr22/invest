from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .engine import run_backtest
from .basket import aggregate_basket
from .aliases import resolve_ticker_alias
from .strategies import STRATEGIES, warmup_bars
from .filters import filter_warmup_calendar_days
from ..repositories.assets import AssetRepository
from ..repositories.backtests import BacktestRepository
from ...data.ingestion.prices import PriceIngestionService


PERIOD_LABELS = {
    "6m": "6 meses",
    "1y": "1 ano",
    "2y": "2 anos",
    "3y": "3 anos",
    "5y": "5 anos",
    "10y": "10 anos",
    "15y": "15 anos",
    "20y": "20 anos",
}

def _minus_months(dt: datetime, months: int) -> datetime:
    total = dt.year * 12 + (dt.month - 1) - months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    import calendar
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _minus_years(dt: datetime, years: int) -> datetime:
    try:
        return dt.replace(year=dt.year - years)
    except ValueError:
        return dt.replace(year=dt.year - years, month=2, day=28)


def resolve_period(period: str, *, end: datetime | None = None, start: datetime | None = None) -> tuple[datetime, datetime]:
    end = end or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if period == "custom":
        if start is None:
            raise ValueError("custom_period_requires_start")
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if start >= end:
            raise ValueError("start_must_be_before_end")
        return start, end
    if period == "6m":
        return _minus_months(end, 6), end
    if period.endswith("y") and period[:-1].isdigit():
        return _minus_years(end, int(period[:-1])), end
    raise ValueError("invalid_period")


def _bar_dict(row):
    return {
        "timestamp": row.timestamp,
        "open": float(row.open) if row.open is not None else None,
        "high": float(row.high) if row.high is not None else None,
        "low": float(row.low) if row.low is not None else None,
        "close": float(row.close) if row.close is not None else None,
        "volume": float(row.volume) if row.volume is not None else None,
        "adjusted_close": float(row.adjusted_close) if row.adjusted_close is not None else None,
    }


def _fundamental_dict(row):
    fields = (
        "pe", "pbv", "dividend_yield_pct", "ev_ebitda", "ebit_margin_pct", "net_margin_pct",
        "current_ratio", "roe_pct", "roic_pct", "gross_debt_to_equity", "net_debt_to_ebitda",
        "revenue_cagr_5y_pct", "earnings_cagr_5y_pct", "ffo_yield_pct", "cap_rate_pct",
        "vacancy_pct", "financial_vacancy_pct", "ltv_pct", "wale_years", "daily_liquidity",
    )
    out = {"reference_date": row.reference_date}
    for field in fields:
        value = getattr(row, field, None)
        out[field] = float(value) if value is not None else None
    return out


class BacktestService:
    def __init__(self, session):
        self.session = session
        self.assets = AssetRepository(session)
        self.runs = BacktestRepository(session)
        self.ingestion = PriceIngestionService(session)

    def ensure_history(self, ticker: str, *, asset_type: str, start: datetime, end: datetime):
        asset = self.assets.get_by_ticker(ticker)
        if asset is None:
            asset = self.assets.upsert_asset(ticker=ticker, asset_type=asset_type)
        existing = self.assets.price_history_range(asset.id, start=start, end=end, source="yahoo")
        needs_fetch = len(existing) < 10
        if existing:
            first, last = existing[0].timestamp, existing[-1].timestamp
            # A tolerance handles weekends/holidays without causing a network fetch on every run.
            needs_fetch = needs_fetch or first > start + timedelta(days=14) or last < end - timedelta(days=10)
        if needs_fetch:
            try:
                self.ingestion.ingest_asset(ticker, asset_type=asset.asset_type or asset_type, start=start, end=end)
            except Exception as exc:
                raise ValueError(
                    f"price_history_unavailable: não foi possível obter histórico para {ticker}. "
                    "Confira o código de negociação atual do ativo."
                ) from exc
            self.session.flush()
            existing = self.assets.price_history_range(asset.id, start=start, end=end, source="yahoo")
        if len(existing) < 10:
            raise ValueError(f"price_history_unavailable: histórico insuficiente para {ticker}")
        return asset, existing

    def run(self, *, ticker: str, strategy_id: str, period: str, asset_type: str = "stock",
            start: datetime | None = None, end: datetime | None = None, initial_capital: float = 10000.0,
            fee_pct: float = 0.03, slippage_pct: float = 0.05, risk_free_rate_pct: float = 0.0,
            cash_yield_rate_pct: float = 0.0, apply_cash_yield: bool = False,
            params: dict | None = None, filters: dict | None = None, persist: bool = True) -> dict:
        requested_start, requested_end = resolve_period(period, start=start, end=end)
        warm = warmup_bars(strategy_id, params)
        filter_warm_days = filter_warmup_calendar_days(filters)
        warmup_start = requested_start - timedelta(days=max(60, warm * 2, filter_warm_days))
        requested_ticker = ticker.upper().strip()
        resolved_ticker, alias = resolve_ticker_alias(requested_ticker)
        asset, rows = self.ensure_history(resolved_ticker, asset_type=asset_type, start=warmup_start, end=requested_end)
        bars = [_bar_dict(r) for r in rows]
        fundamental_rows = self.assets.fundamental_history_until(asset.id, end=requested_end)
        fundamentals = [_fundamental_dict(r) for r in fundamental_rows]
        result = run_backtest(
            bars, strategy_id=strategy_id, requested_start=requested_start, requested_end=requested_end,
            initial_capital=initial_capital, fee_pct=fee_pct, slippage_pct=slippage_pct,
            risk_free_rate_pct=risk_free_rate_pct, cash_yield_rate_pct=cash_yield_rate_pct,
            apply_cash_yield=apply_cash_yield, params=params, filters=filters, fundamental_snapshots=fundamentals,
        )
        result["ticker"] = asset.ticker
        result["requested_ticker"] = requested_ticker
        result["ticker_alias"] = alias
        result["asset_name"] = asset.name
        result["asset_type"] = asset.asset_type
        result["period"] = period
        result["period_label"] = PERIOD_LABELS.get(period, "Personalizado")
        result["warmup_bars"] = warm

        if persist:
            actual_start = datetime.fromisoformat(result["actual_start"])
            actual_end = datetime.fromisoformat(result["actual_end"])
            run = self.runs.save_run(
                asset=asset, strategy_id=strategy_id, strategy_name=STRATEGIES[strategy_id].name,
                requested_start=requested_start, requested_end=requested_end, actual_start=actual_start, actual_end=actual_end,
                initial_capital=initial_capital, fee_pct=fee_pct, slippage_pct=slippage_pct,
                risk_free_rate_pct=risk_free_rate_pct, parameters={
                    "strategy": result["parameters"], "filters": result.get("filters") or {},
                    "financial": {"apply_cash_yield": bool(apply_cash_yield), "cash_yield_rate_pct": float(cash_yield_rate_pct)},
                }, metrics=result["metrics"],
                equity_curve=result["equity_curve"], trades=result["trades"], data_source="yahoo", status="valid",
            )
            result["run_id"] = str(run.id)
        return result

    def compare(self, *, ticker: str, strategy_ids: list[str], period: str, asset_type: str = "stock",
                start: datetime | None = None, end: datetime | None = None, initial_capital: float = 10000.0,
                fee_pct: float = 0.03, slippage_pct: float = 0.05, risk_free_rate_pct: float = 0.0,
                cash_yield_rate_pct: float = 0.0, apply_cash_yield: bool = False,
                filters: dict | None = None) -> list[dict]:
        if not strategy_ids:
            return []
        requested_start, requested_end = resolve_period(period, start=start, end=end)
        max_warm = max(warmup_bars(sid) for sid in strategy_ids)
        filter_warm_days = filter_warmup_calendar_days(filters)
        warmup_start = requested_start - timedelta(days=max(60, max_warm * 2, filter_warm_days))
        requested_ticker = ticker.upper().strip()
        resolved_ticker, alias = resolve_ticker_alias(requested_ticker)
        asset, rows = self.ensure_history(resolved_ticker, asset_type=asset_type, start=warmup_start, end=requested_end)
        bars = [_bar_dict(r) for r in rows]
        fundamental_rows = self.assets.fundamental_history_until(asset.id, end=requested_end)
        fundamentals = [_fundamental_dict(r) for r in fundamental_rows]
        out = []
        for sid in strategy_ids:
            result = run_backtest(
                bars, strategy_id=sid, requested_start=requested_start, requested_end=requested_end,
                initial_capital=initial_capital, fee_pct=fee_pct, slippage_pct=slippage_pct,
                risk_free_rate_pct=risk_free_rate_pct, cash_yield_rate_pct=cash_yield_rate_pct,
                apply_cash_yield=apply_cash_yield, filters=filters, fundamental_snapshots=fundamentals,
            )
            run = self.runs.save_run(
                asset=asset, strategy_id=sid, strategy_name=STRATEGIES[sid].name,
                requested_start=requested_start, requested_end=requested_end,
                actual_start=datetime.fromisoformat(result["actual_start"]), actual_end=datetime.fromisoformat(result["actual_end"]),
                initial_capital=initial_capital, fee_pct=fee_pct, slippage_pct=slippage_pct,
                risk_free_rate_pct=risk_free_rate_pct, parameters={
                    "strategy": result["parameters"], "filters": result.get("filters") or {},
                    "financial": {"apply_cash_yield": bool(apply_cash_yield), "cash_yield_rate_pct": float(cash_yield_rate_pct)},
                }, metrics=result["metrics"],
                equity_curve=result["equity_curve"], trades=result["trades"], data_source="yahoo", status="valid",
            )
            out.append({
                "run_id": str(run.id), "strategy_id": sid, "strategy_name": STRATEGIES[sid].name,
                "requested_ticker": requested_ticker, "ticker": asset.ticker, "ticker_alias": alias,
                **result["metrics"],
            })
        return out

    def basket(self, *, tickers: list[str], strategy_id: str, period: str, asset_type: str = "stock",
               start: datetime | None = None, end: datetime | None = None, initial_capital: float = 100000.0,
               fee_pct: float = 0.03, slippage_pct: float = 0.05, risk_free_rate_pct: float = 0.0,
               cash_yield_rate_pct: float = 0.0, apply_cash_yield: bool = False,
               params: dict | None = None, filters: dict | None = None) -> dict:
        requested_start, requested_end = resolve_period(period, start=start, end=end)
        normalized = []
        for ticker in tickers:
            clean = ticker.upper().strip()
            if clean and clean not in normalized:
                normalized.append(clean)
        if not normalized:
            raise ValueError("basket_requires_tickers")
        results = []
        failures = []
        seen_resolved = {}
        for requested_ticker in normalized:
            resolved_ticker, alias = resolve_ticker_alias(requested_ticker)
            if resolved_ticker in seen_resolved:
                failures.append({
                    "requested_ticker": requested_ticker, "resolved_ticker": resolved_ticker,
                    "ticker_alias": alias, "category": "duplicate",
                    "error": f"duplicado: representa o mesmo ativo que {seen_resolved[resolved_ticker]}",
                })
                continue
            seen_resolved[resolved_ticker] = requested_ticker
            try:
                with self.session.begin_nested():
                    result = self.run(
                        ticker=requested_ticker, strategy_id=strategy_id, period="custom", asset_type=asset_type,
                        start=requested_start, end=requested_end, initial_capital=10000.0,
                        fee_pct=fee_pct, slippage_pct=slippage_pct, risk_free_rate_pct=risk_free_rate_pct,
                        cash_yield_rate_pct=cash_yield_rate_pct, apply_cash_yield=apply_cash_yield,
                        params=params, filters=filters, persist=False,
                    )
                result["initial_capital"] = 10000.0
                results.append(result)
            except Exception as exc:
                failures.append({
                    "requested_ticker": requested_ticker, "resolved_ticker": resolved_ticker,
                    "ticker_alias": alias, "category": "history", "error": str(exc),
                })
        if not results:
            details = "; ".join(f"{item['requested_ticker']}: {item['error']}" for item in failures)
            raise ValueError(f"basket_no_valid_assets: nenhum ativo possui histórico válido. {details}")
        aggregated = aggregate_basket(results, initial_capital=initial_capital, risk_free_rate_pct=risk_free_rate_pct)
        aggregated.update({
            "strategy": STRATEGIES[strategy_id].as_dict(), "parameters": results[0].get("parameters") if results else (params or {}),
            "filters": results[0].get("filters") if results else (filters or {}),
            "requested_start": requested_start.isoformat(), "requested_end": requested_end.isoformat(),
            "actual_start": aggregated["portfolio_curve"][0]["timestamp"],
            "actual_end": aggregated["portfolio_curve"][-1]["timestamp"],
            "requested_tickers": normalized, "successful_tickers": [r["ticker"] for r in results],
            "failures": failures,
            "assumptions": {
                "weighting": "pesos iguais no início entre os ativos com histórico válido; sem rebalanceamento periódico",
                "failed_assets": "ativos com falha são excluídos e os pesos são redistribuídos igualmente",
                "fee_pct_per_turnover": float(fee_pct),
                "slippage_pct_per_turnover": float(slippage_pct),
                "risk_free_rate_pct_annual": float(risk_free_rate_pct),
                "cash_yield_enabled": bool(apply_cash_yield),
                "cash_yield_rate_pct_annual": float(cash_yield_rate_pct) if apply_cash_yield else 0.0,
                "open_positions": "marcadas a mercado no último pregão",
                "signal_execution": "sinal no fechamento t; execução no fechamento t+1",
            },
        })
        return aggregated
