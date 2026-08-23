from __future__ import annotations

import math
from datetime import datetime
import pandas as pd

from .strategies import STRATEGIES, build_signal
from .filters import apply_backtest_filters

TRADING_DAYS = 252


def _safe(v):
    if v is None:
        return None
    try:
        if math.isnan(float(v)) or math.isinf(float(v)):
            return None
    except (TypeError, ValueError):
        return None
    return float(v)


def _annualized_return(start: float, end: float, years: float) -> float | None:
    if start <= 0 or end <= 0 or years <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


def _performance_metrics(equity: pd.Series, returns: pd.Series, position: pd.Series, benchmark: pd.Series,
                         benchmark_returns: pd.Series, trades: list[dict], risk_free_rate_pct: float,
                         turnover: pd.Series, cost_rate: float) -> dict:
    start = float(equity.iloc[0]); end = float(equity.iloc[-1])
    dates = equity.index
    years = max((dates[-1] - dates[0]).days / 365.25, 1 / 365.25)
    total_return = end / start - 1.0
    cagr = _annualized_return(start, end, years)
    vol = returns.std(ddof=0) * math.sqrt(TRADING_DAYS) if len(returns) > 1 else None
    rf_annual = risk_free_rate_pct / 100.0
    rf_daily = (1 + rf_annual) ** (1 / TRADING_DAYS) - 1 if rf_annual > -1 else 0.0
    excess_daily = returns - rf_daily
    std = returns.std(ddof=0)
    sharpe = excess_daily.mean() / std * math.sqrt(TRADING_DAYS) if std and std > 0 else None
    downside = excess_daily.where(excess_daily < 0, 0.0)
    downside_std = downside.std(ddof=0)
    sortino = excess_daily.mean() / downside_std * math.sqrt(TRADING_DAYS) if downside_std and downside_std > 0 else None
    drawdown = equity / equity.cummax() - 1.0
    max_dd = float(drawdown.min())
    calmar = (cagr / abs(max_dd)) if cagr is not None and max_dd < 0 else None

    b_start = float(benchmark.iloc[0]); b_end = float(benchmark.iloc[-1])
    b_total = b_end / b_start - 1.0
    b_cagr = _annualized_return(b_start, b_end, years)
    b_dd = benchmark / benchmark.cummax() - 1.0
    b_vol = benchmark_returns.std(ddof=0) * math.sqrt(TRADING_DAYS) if len(benchmark_returns) > 1 else None

    completed = [t for t in trades if t.get("exit_date") is not None and t.get("return_pct") is not None]
    open_trades = [t for t in trades if t.get("exit_date") is None and t.get("return_pct") is not None]
    trade_returns = [float(t["return_pct"]) / 100.0 for t in completed]
    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r < 0]
    profit_factor = (sum(wins) / abs(sum(losses))) if losses else (None if not wins else 999.0)
    marked_returns = [float(t["return_pct"]) / 100.0 for t in completed + open_trades]
    marked_wins = [r for r in marked_returns if r > 0]
    marked_losses = [r for r in marked_returns if r < 0]
    marked_profit_factor = (sum(marked_wins) / abs(sum(marked_losses))) if marked_losses else (None if not marked_wins else 999.0)
    avg_holding = sum(t.get("holding_days") or 0 for t in completed) / len(completed) if completed else None

    return {
        "total_return_pct": total_return * 100,
        "cagr_pct": None if cagr is None else cagr * 100,
        "annual_volatility_pct": None if vol is None else vol * 100,
        "sharpe_ratio": _safe(sharpe),
        "sortino_ratio": _safe(sortino),
        "max_drawdown_pct": max_dd * 100,
        "calmar_ratio": _safe(calmar),
        "exposure_pct": float(position.mean()) * 100,
        "turnover_events": int((turnover > 0).sum()),
        "estimated_cost_drag_pct": float(turnover.sum() * cost_rate * 100),
        "trades": len(completed),
        "closed_trades": len(completed),
        "open_trades": len(open_trades),
        "win_rate_pct": (len(wins) / len(completed) * 100) if completed else None,
        "profit_factor": _safe(profit_factor),
        "profit_factor_mark_to_market": _safe(marked_profit_factor),
        "win_rate_mark_to_market_pct": (len(marked_wins) / len(marked_returns) * 100) if marked_returns else None,
        "open_position_return_pct": _safe(open_trades[-1].get("return_pct")) if open_trades else None,
        "open_position_pnl_value": _safe(open_trades[-1].get("pnl_value")) if open_trades else None,
        "average_trade_pct": (sum(trade_returns) / len(trade_returns) * 100) if trade_returns else None,
        "best_trade_pct": (max(trade_returns) * 100) if trade_returns else None,
        "worst_trade_pct": (min(trade_returns) * 100) if trade_returns else None,
        "average_holding_days": _safe(avg_holding),
        "benchmark_total_return_pct": b_total * 100,
        "benchmark_cagr_pct": None if b_cagr is None else b_cagr * 100,
        "benchmark_annual_volatility_pct": None if b_vol is None else b_vol * 100,
        "benchmark_max_drawdown_pct": float(b_dd.min()) * 100,
        "excess_total_return_pct": (total_return - b_total) * 100,
        "years": years,
        "bars": int(len(equity)),
    }


def _extract_trades(frame: pd.DataFrame, initial_capital: float, cost_rate: float) -> list[dict]:
    trades = []
    # execution_state changes at the close of the bar AFTER the signal was generated.
    # The next close-to-close return then uses the new state, so there is no same-close fill.
    execution = frame["execution_state"].astype(int)
    prev = execution.shift(1).fillna(0).astype(int)
    entries = frame.index[(execution == 1) & (prev == 0)]
    exits = frame.index[(execution == 0) & (prev == 1)]
    exits_list = list(exits)
    for entry in entries:
        exit_date = next((x for x in exits_list if x > entry), None)
        entry_price = float(frame.loc[entry, "price"])
        entry_equity = float(frame.loc[entry, "equity"])
        if exit_date is not None:
            exit_price = float(frame.loc[exit_date, "price"])
            gross = exit_price / entry_price - 1.0
            net = gross - 2 * cost_rate
            days = (exit_date - entry).days
            trades.append({
                "entry_date": entry.to_pydatetime(), "entry_price": entry_price,
                "exit_date": exit_date.to_pydatetime(), "exit_price": exit_price,
                "return_pct": net * 100, "pnl_value": entry_equity * net,
                "holding_days": days, "exit_reason": "signal",
            })
        else:
            last = frame.index[-1]; last_price = float(frame.iloc[-1]["price"])
            gross = last_price / entry_price - 1.0
            net = gross - cost_rate  # entry cost only; open position not charged an artificial exit cost
            trades.append({
                "entry_date": entry.to_pydatetime(), "entry_price": entry_price,
                "exit_date": None, "exit_price": None,
                "return_pct": net * 100, "pnl_value": entry_equity * net,
                "holding_days": (last - entry).days, "exit_reason": "open",
            })
    return trades


def run_backtest(bars: list[dict], *, strategy_id: str, requested_start: datetime, requested_end: datetime,
                 initial_capital: float = 10000.0, fee_pct: float = 0.03, slippage_pct: float = 0.05,
                 risk_free_rate_pct: float = 0.0, cash_yield_rate_pct: float = 0.0,
                 apply_cash_yield: bool = False, params: dict | None = None, filters: dict | None = None,
                 fundamental_snapshots: list[dict] | None = None) -> dict:
    if strategy_id not in STRATEGIES:
        raise ValueError("strategy_not_found")
    if initial_capital <= 0:
        raise ValueError("initial_capital_must_be_positive")
    if fee_pct < 0 or slippage_pct < 0:
        raise ValueError("costs_must_be_non_negative")
    if cash_yield_rate_pct <= -100:
        raise ValueError("cash_yield_rate_must_be_greater_than_minus_100")

    df = pd.DataFrame(bars)
    if df.empty or "timestamp" not in df:
        raise ValueError("insufficient_price_history")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").drop_duplicates("timestamp", keep="last").set_index("timestamp")
    adj = pd.to_numeric(df.get("adjusted_close"), errors="coerce") if "adjusted_close" in df else pd.Series(index=df.index, dtype=float)
    close = pd.to_numeric(df.get("close"), errors="coerce") if "close" in df else pd.Series(index=df.index, dtype=float)
    df["price"] = adj.fillna(close)
    df = df[df["price"].notna() & (df["price"] > 0)].copy()
    if len(df) < 20:
        raise ValueError("insufficient_price_history")

    # Yahoo OHLC can be unadjusted while adjusted_close reflects splits/dividends.
    # Scale high/low to the same basis as the price series before ATR/ADX/Bollinger touch filters.
    raw_close = pd.to_numeric(df.get("close"), errors="coerce")
    factor = df["price"] / raw_close.replace(0, pd.NA)
    raw_high = pd.to_numeric(df.get("high"), errors="coerce")
    raw_low = pd.to_numeric(df.get("low"), errors="coerce")
    df["adj_high"] = raw_high * factor
    df["adj_low"] = raw_low * factor

    base_signal, indicators, effective_params = build_signal(df, strategy_id, params)
    signal, filter_indicators, effective_filters, filter_diagnostics = apply_backtest_filters(
        df, base_signal, filters, requested_start=requested_start, requested_end=requested_end,
        fundamental_snapshots=fundamental_snapshots,
    )
    if not filter_indicators.empty:
        indicators = pd.concat([indicators, filter_indicators.loc[:, ~filter_indicators.columns.isin(indicators.columns)]], axis=1)
    df["base_signal"] = base_signal
    df["raw_signal"] = signal
    # Signal is known only at the close of bar t. To avoid a same-close fill, the order is
    # executed at the close of bar t+1. Exposure to close-to-close return begins after that fill.
    df["execution_state"] = signal.shift(1).fillna(0.0).clip(0, 1)
    df["position"] = df["execution_state"].shift(1).fillna(0.0).clip(0, 1)
    df["asset_return"] = df["price"].pct_change().fillna(0.0)

    start = pd.Timestamp(requested_start)
    end = pd.Timestamp(requested_end)
    if start.tzinfo is None: start = start.tz_localize("UTC")
    else: start = start.tz_convert("UTC")
    if end.tzinfo is None: end = end.tz_localize("UTC")
    else: end = end.tz_convert("UTC")
    bt = df.loc[(df.index >= start) & (df.index <= end)].copy()
    indicators = indicators.reindex(bt.index)
    if len(bt) < 10:
        raise ValueError("insufficient_price_history_for_requested_period")
    # Portfolio starts on the first requested bar, not on the warm-up return into that bar.
    bt.iloc[0, bt.columns.get_loc("asset_return")] = 0.0

    prev_exec = bt["execution_state"].shift(1).fillna(0.0)
    # Turnover/cost occurs on the execution bar, not when the next return is realized.
    turnover = (bt["execution_state"] - prev_exec).abs()
    if bt.iloc[0]["execution_state"] == 1:
        turnover.iloc[0] = 1.0
    cost_rate = (fee_pct + slippage_pct) / 100.0
    cash_daily = (1.0 + cash_yield_rate_pct / 100.0) ** (1.0 / TRADING_DAYS) - 1.0 if apply_cash_yield else 0.0
    bt["turnover"] = turnover
    bt["cash_return"] = (1.0 - bt["position"]) * cash_daily
    bt["strategy_return"] = bt["position"] * bt["asset_return"] + bt["cash_return"] - bt["turnover"] * cost_rate
    bt["equity"] = initial_capital * (1.0 + bt["strategy_return"]).cumprod()
    bt["benchmark"] = initial_capital * (1.0 + bt["asset_return"]).cumprod()
    bt["drawdown_pct"] = (bt["equity"] / bt["equity"].cummax() - 1.0) * 100.0

    trades = _extract_trades(bt, initial_capital, cost_rate)
    metrics = _performance_metrics(
        bt["equity"], bt["strategy_return"], bt["position"], bt["benchmark"], bt["asset_return"],
        trades, risk_free_rate_pct, bt["turnover"], cost_rate,
    )

    curve = []
    for idx, row in bt.iterrows():
        item = {
            "timestamp": idx.isoformat(), "price": _safe(row["price"]), "position": int(row["position"]),
            "equity": _safe(row["equity"]), "benchmark": _safe(row["benchmark"]),
            "drawdown_pct": _safe(row["drawdown_pct"]),
        }
        for col in indicators.columns:
            item[col] = _safe(indicators.loc[idx, col])
        curve.append(item)

    # Diagnostics distinguish "no data" from a valid backtest that simply generated no entry.
    base_bt = df.loc[(df.index >= start) & (df.index <= end), "base_signal"]
    filtered_bt = df.loc[(df.index >= start) & (df.index <= end), "raw_signal"]
    base_prev = base_bt.fillna(0).shift(1).fillna(0)
    filtered_prev = filtered_bt.fillna(0).shift(1).fillna(0)
    signal_diagnostics = {
        "price_bars_loaded": int(len(bt)),
        "base_valid_signal_bars": int(base_bt.notna().sum()),
        "base_entry_signals": int(((base_bt.fillna(0) > 0) & (base_prev <= 0)).sum()),
        "filtered_entry_signals": int(((filtered_bt.fillna(0) > 0) & (filtered_prev <= 0)).sum()),
    }
    if strategy_id == "bollinger_rsi_trend":
        lower = indicators.reindex(bt.index).get("Bollinger inferior")
        rsi = indicators.reindex(bt.index).get("RSI")
        trend_col = f"SMA {int(effective_params.get('trend_period', 200))}"
        trend = indicators.reindex(bt.index).get(trend_col)
        trigger_col = indicators.reindex(bt.index).get("Gatilho banda inferior")
        trend_gate = indicators.reindex(bt.index).get("Filtro estrutural Bollinger")
        if lower is not None and rsi is not None and trend is not None and trigger_col is not None and trend_gate is not None:
            valid = lower.notna() & rsi.notna() & trend_gate.notna()
            band_ok = trigger_col.fillna(0) > 0
            rsi_ok = rsi <= float(effective_params.get("entry_rsi", 35))
            trend_ok = trend_gate.fillna(0) > 0
            band_rsi = valid & band_ok & rsi_ok
            band_trend = valid & band_ok & trend_ok
            rsi_trend = valid & rsi_ok & trend_ok
            all_ok = band_rsi & trend_ok
            blocked = band_rsi & ~trend_ok
            blocked_dates = [idx.date().isoformat() for idx in bt.index[blocked][:12]]
            signal_diagnostics["bollinger"] = {
                "valid_bars": int(valid.sum()),
                "band_trigger_bars": int((valid & band_ok).sum()),
                "rsi_entry_bars": int((valid & rsi_ok).sum()),
                "trend_filter_bars": int((valid & trend_ok).sum()),
                "band_and_rsi_bars": int(band_rsi.sum()),
                "band_and_trend_bars": int(band_trend.sum()),
                "rsi_and_trend_bars": int(rsi_trend.sum()),
                "all_entry_conditions_bars": int(all_ok.sum()),
                "band_rsi_blocked_by_trend_bars": int(blocked.sum()),
                "blocked_candidate_dates": blocked_dates,
                "band_trigger": effective_params.get("band_trigger", "close"),
                "rsi_period": int(effective_params.get("rsi_period", 14)),
                "entry_rsi": float(effective_params.get("entry_rsi", 35)),
                "trend_period": int(effective_params.get("trend_period", 200)),
                "trend_filter_mode": effective_params.get("trend_filter_mode", "price_above"),
                "trend_slope_lookback": int(effective_params.get("trend_slope_lookback", 20)),
            }

    events = []
    exe = bt["execution_state"].astype(int); prev = exe.shift(1).fillna(0).astype(int)
    for idx in bt.index[(exe == 1) & (prev == 0)]:
        events.append({"timestamp": idx.isoformat(), "type": "buy", "price": float(bt.loc[idx, "price"])})
    for idx in bt.index[(exe == 0) & (prev == 1)]:
        events.append({"timestamp": idx.isoformat(), "type": "sell", "price": float(bt.loc[idx, "price"])})

    completed_signal = filtered_bt.dropna()
    current_signal = "neutral"
    signal_reason = "sem mudança de estado no último pregão concluído"
    if not completed_signal.empty:
        latest_state = int(float(completed_signal.iloc[-1]) > 0)
        previous_state = int(float(completed_signal.iloc[-2]) > 0) if len(completed_signal) > 1 else 0
        if latest_state == 1 and previous_state == 0:
            current_signal = "buy"
            signal_reason = "as condições de entrada foram atendidas no último fechamento"
        elif latest_state == 0 and previous_state == 1:
            current_signal = "sell"
            signal_reason = "as condições de saída foram atendidas no último fechamento"
    signal_snapshot = {
        "status": current_signal,
        "as_of": bt.index[-1].isoformat(),
        "reason": signal_reason,
        "execution": "ordem no pregão seguinte ao sinal",
    }

    return {
        "strategy": STRATEGIES[strategy_id].as_dict(),
        "parameters": effective_params,
        "requested_start": start.isoformat(), "requested_end": end.isoformat(),
        "actual_start": bt.index[0].isoformat(), "actual_end": bt.index[-1].isoformat(),
        "metrics": metrics, "equity_curve": curve, "trades": trades, "events": events,
        "current_signal": signal_snapshot,
        "filters": effective_filters, "filter_diagnostics": filter_diagnostics, "signal_diagnostics": signal_diagnostics,
        "assumptions": {
            "positioning": "long_only",
            "signal_execution": "sinal no fechamento t; execução no fechamento t+1; exposição a partir do retorno seguinte (sem preenchimento no mesmo fechamento)",
            "price_series": "adjusted_close quando disponível; close como fallback",
            "fee_pct_per_turnover": fee_pct,
            "slippage_pct_per_turnover": slippage_pct,
            "risk_free_rate_pct_annual": float(risk_free_rate_pct),
            "cash_yield_enabled": bool(apply_cash_yield),
            "cash_yield_rate_pct_annual": float(cash_yield_rate_pct) if apply_cash_yield else 0.0,
            "cash_yield_convention": "taxa anual constante convertida para 252 pregões; aplicada somente quando fora da posição",
            "taxes": "não incluídos",
        },
    }
