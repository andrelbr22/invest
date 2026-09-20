from __future__ import annotations

import math
import pandas as pd

from .engine import TRADING_DAYS, _safe


def _profit_factor(values: list[float]) -> float | None:
    wins = sum(v for v in values if v > 0)
    losses = abs(sum(v for v in values if v < 0))
    if losses:
        return wins / losses
    return 999.0 if wins else None


def aggregate_basket(results: list[dict], *, initial_capital: float, risk_free_rate_pct: float = 0.0) -> dict:
    if not results:
        raise ValueError("basket_has_no_successful_assets")
    allocation = float(initial_capital) / len(results)
    series = []
    benchmark_series = []
    asset_rows = []
    closed_pnls: list[float] = []
    marked_pnls: list[float] = []
    closed_wins = marked_wins = 0
    closed_count = open_count = 0

    for result in results:
        curve = pd.DataFrame(result.get("equity_curve") or [])
        if curve.empty:
            continue
        curve["timestamp"] = pd.to_datetime(curve["timestamp"], utc=True)
        curve = curve.set_index("timestamp").sort_index()
        run_initial = float(result.get("initial_capital") or 10000.0)
        equity = pd.to_numeric(curve["equity"], errors="coerce") / run_initial * allocation
        benchmark = pd.to_numeric(curve["benchmark"], errors="coerce") / run_initial * allocation
        series.append(equity.rename(result["ticker"]))
        benchmark_series.append(benchmark.rename(result["ticker"]))

        scale = allocation / run_initial
        trades = result.get("trades") or []
        for trade in trades:
            pnl = float(trade.get("pnl_value") or 0.0) * scale
            marked_pnls.append(pnl)
            if pnl > 0:
                marked_wins += 1
            if trade.get("exit_date") is None:
                open_count += 1
            else:
                closed_count += 1
                closed_pnls.append(pnl)
                if pnl > 0:
                    closed_wins += 1

        metrics = result.get("metrics") or {}
        final_equity = float(equity.dropna().iloc[-1])
        asset_return = (final_equity / allocation - 1.0) * 100.0
        contribution = (final_equity - allocation) / initial_capital * 100.0
        asset_rows.append({
            "requested_ticker": result.get("requested_ticker", result.get("ticker")),
            "ticker": result.get("ticker"), "asset_name": result.get("asset_name"),
            "ticker_alias": result.get("ticker_alias"), "weight_pct": 100.0 / len(results),
            "initial_capital": allocation, "final_equity": final_equity,
            "return_pct": asset_return, "contribution_pct_points": contribution,
            "max_drawdown_pct": metrics.get("max_drawdown_pct"),
            "exposure_pct": metrics.get("exposure_pct"),
            "closed_trades": metrics.get("closed_trades", metrics.get("trades", 0)),
            "open_trades": metrics.get("open_trades", 0),
            "profit_factor_closed": metrics.get("profit_factor"),
            "profit_factor_mark_to_market": metrics.get("profit_factor_mark_to_market", metrics.get("profit_factor")),
        })

    if not series:
        raise ValueError("basket_has_no_equity_curves")
    union = series[0].index
    for item in series[1:] + benchmark_series:
        union = union.union(item.index)
    union = union.sort_values()

    def aligned_total(items: list[pd.Series]) -> pd.Series:
        aligned = []
        for item in items:
            # Before an asset's first available bar its allocation remains in cash at nominal value.
            aligned.append(item.reindex(union).ffill().fillna(allocation))
        return pd.concat(aligned, axis=1).sum(axis=1)

    equity = aligned_total(series)
    benchmark = aligned_total(benchmark_series)
    returns = equity.pct_change().fillna(0.0)
    benchmark_returns = benchmark.pct_change().fillna(0.0)
    years = max((union[-1] - union[0]).days / 365.25, 1 / 365.25)
    total_return = equity.iloc[-1] / initial_capital - 1.0
    benchmark_total = benchmark.iloc[-1] / initial_capital - 1.0
    cagr = (equity.iloc[-1] / initial_capital) ** (1.0 / years) - 1.0 if equity.iloc[-1] > 0 else None
    benchmark_cagr = (benchmark.iloc[-1] / initial_capital) ** (1.0 / years) - 1.0 if benchmark.iloc[-1] > 0 else None
    drawdown = equity / equity.cummax() - 1.0
    benchmark_drawdown = benchmark / benchmark.cummax() - 1.0
    vol = returns.std(ddof=0) * math.sqrt(TRADING_DAYS)
    benchmark_vol = benchmark_returns.std(ddof=0) * math.sqrt(TRADING_DAYS)
    rf_daily = (1 + risk_free_rate_pct / 100.0) ** (1 / TRADING_DAYS) - 1 if risk_free_rate_pct > -100 else 0.0
    excess = returns - rf_daily
    downside = excess.where(excess < 0, 0.0)
    std = returns.std(ddof=0)
    downside_std = downside.std(ddof=0)
    sharpe = excess.mean() / std * math.sqrt(TRADING_DAYS) if std > 0 else None
    sortino = excess.mean() / downside_std * math.sqrt(TRADING_DAYS) if downside_std > 0 else None
    positive = sorted((r for r in asset_rows if r["contribution_pct_points"] > 0), key=lambda x: x["contribution_pct_points"], reverse=True)
    positive_total = sum(r["contribution_pct_points"] for r in positive)
    top1_share = positive[0]["contribution_pct_points"] / positive_total * 100 if positive_total and positive else None
    top2_share = sum(r["contribution_pct_points"] for r in positive[:2]) / positive_total * 100 if positive_total and positive else None
    exposure_values = [float(r["exposure_pct"]) for r in asset_rows if r.get("exposure_pct") is not None]

    portfolio_curve = [{
        "timestamp": idx.isoformat(), "equity": _safe(equity.loc[idx]),
        "benchmark": _safe(benchmark.loc[idx]), "drawdown_pct": _safe(drawdown.loc[idx] * 100.0),
    } for idx in union]
    metrics = {
        "asset_count": len(asset_rows), "initial_capital": float(initial_capital),
        "final_equity": _safe(equity.iloc[-1]), "total_return_pct": total_return * 100.0,
        "cagr_pct": None if cagr is None else cagr * 100.0,
        "max_drawdown_pct": float(drawdown.min()) * 100.0,
        "annual_volatility_pct": float(vol) * 100.0, "sharpe_ratio": _safe(sharpe), "sortino_ratio": _safe(sortino),
        "average_exposure_pct": sum(exposure_values) / len(exposure_values) if exposure_values else None,
        "closed_trades": closed_count, "open_trades": open_count,
        "win_rate_closed_pct": closed_wins / closed_count * 100.0 if closed_count else None,
        "win_rate_mark_to_market_pct": marked_wins / len(marked_pnls) * 100.0 if marked_pnls else None,
        "profit_factor_closed": _safe(_profit_factor(closed_pnls)),
        "profit_factor_mark_to_market": _safe(_profit_factor(marked_pnls)),
        "positive_assets": sum(1 for r in asset_rows if r["return_pct"] > 0),
        "negative_assets": sum(1 for r in asset_rows if r["return_pct"] < 0),
        "top_1_profit_concentration_pct": _safe(top1_share), "top_2_profit_concentration_pct": _safe(top2_share),
        "benchmark_total_return_pct": benchmark_total * 100.0,
        "benchmark_cagr_pct": None if benchmark_cagr is None else benchmark_cagr * 100.0,
        "benchmark_max_drawdown_pct": float(benchmark_drawdown.min()) * 100.0,
        "benchmark_annual_volatility_pct": float(benchmark_vol) * 100.0,
        "excess_total_return_pct": (total_return - benchmark_total) * 100.0,
        "years": years,
    }
    return {"metrics": metrics, "assets": asset_rows, "portfolio_curve": portfolio_curve}
