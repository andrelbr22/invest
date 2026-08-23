from datetime import datetime, timedelta, timezone
import math
import pytest

from investment_engine.core.backtesting.engine import _performance_metrics, run_backtest
from investment_engine.core.backtesting.service import resolve_period
from investment_engine.core.backtesting.strategies import build_signal, strategy_catalog
import pandas as pd


def bars_from_prices(prices):
    start = datetime(2020,1,1,tzinfo=timezone.utc)
    return [{"timestamp":start+timedelta(days=i),"close":p,"adjusted_close":p,"open":p,"high":p,"low":p,"volume":1000} for i,p in enumerate(prices)]


def test_catalog_contains_requested_strategies():
    ids={x["id"] for x in strategy_catalog()}
    assert {"ema9_sma50","ema9_sma40","sma3_ema9_sma21"}.issubset(ids)


def test_resolve_twenty_year_period():
    end=datetime(2026,8,22,tzinfo=timezone.utc)
    start,_=resolve_period("20y",end=end)
    assert start.year == 2006 and start.month == 8 and start.day == 22


def test_ma_signal_has_warmup_and_no_immediate_future_signal():
    prices=[100+i*0.2 for i in range(100)]
    df=pd.DataFrame({"price":prices})
    sig,_,_=build_signal(df,"ema9_sma40")
    assert sig.iloc[:38].isna().all()
    assert sig.dropna().iloc[-1] == 1


def test_backtest_trending_market_generates_result_and_benchmark():
    prices=[100+i*0.15 for i in range(320)]
    bars=bars_from_prices(prices)
    result=run_backtest(bars,strategy_id="ema9_sma40",requested_start=bars[60]["timestamp"],requested_end=bars[-1]["timestamp"],initial_capital=10000,fee_pct=0,slippage_pct=0)
    m=result["metrics"]
    assert m["bars"] > 200
    assert m["total_return_pct"] > 0
    assert m["benchmark_total_return_pct"] > 0
    assert "execução no fechamento t+1" in result["assumptions"]["signal_execution"]


def test_transaction_costs_reduce_return():
    # Oscillating data creates turnovers, making the cost impact observable.
    prices=[100 + (5 if i%20<10 else -5) + i*0.02 for i in range(320)]
    bars=bars_from_prices(prices)
    kw=dict(strategy_id="ema9_sma40",requested_start=bars[60]["timestamp"],requested_end=bars[-1]["timestamp"],initial_capital=10000)
    free=run_backtest(bars,fee_pct=0,slippage_pct=0,**kw)
    costly=run_backtest(bars,fee_pct=0.2,slippage_pct=0.2,**kw)
    assert costly["metrics"]["total_return_pct"] <= free["metrics"]["total_return_pct"]


def test_custom_ma_rejects_fast_not_lower_than_slow():
    df=pd.DataFrame({"price":[100+i for i in range(50)]})
    with pytest.raises(ValueError,match="fast_period_must_be_lower"):
        build_signal(df,"custom_ma_cross",{"fast_period":40,"slow_period":20})


def test_donchian_uses_prior_channel():
    prices=[100.0]*25+[110.0,111.0,112.0]
    df=pd.DataFrame({"price":prices})
    sig,ind,_=build_signal(df,"donchian_20_10")
    # Breakout on the first 110 bar is possible because the channel is based on prior bars.
    assert sig.iloc[25] == 1
    assert ind.iloc[25,0] == 100


def test_open_position_is_separated_from_closed_trade_metrics():
    idx=pd.date_range("2026-01-01",periods=3,freq="D",tz="UTC")
    equity=pd.Series([10000,10500,9000],index=idx,dtype=float)
    returns=equity.pct_change().fillna(0)
    benchmark=pd.Series([10000,10000,10000],index=idx,dtype=float)
    trades=[
        {"exit_date":idx[1].to_pydatetime(),"return_pct":10.0,"pnl_value":1000.0,"holding_days":1},
        {"exit_date":None,"return_pct":-20.0,"pnl_value":-2000.0,"holding_days":1},
    ]
    m=_performance_metrics(equity,returns,pd.Series([0,1,1],index=idx),benchmark,benchmark.pct_change().fillna(0),trades,0,pd.Series([0,1,0],index=idx),0)
    assert m["closed_trades"]==1
    assert m["open_trades"]==1
    assert m["profit_factor"]==999.0
    assert m["profit_factor_mark_to_market"]==0.5
    assert m["open_position_return_pct"]==-20.0


def test_cash_yield_is_applied_only_when_enabled_and_out_of_market():
    prices=[100.0]*320
    bars=bars_from_prices(prices)
    kw=dict(strategy_id="ema9_sma40",requested_start=bars[60]["timestamp"],requested_end=bars[-1]["timestamp"],initial_capital=10000,fee_pct=0,slippage_pct=0)
    idle=run_backtest(bars,apply_cash_yield=False,cash_yield_rate_pct=10,**kw)
    remunerated=run_backtest(bars,apply_cash_yield=True,cash_yield_rate_pct=10,**kw)
    assert abs(idle["metrics"]["total_return_pct"]) < 0.001
    assert remunerated["metrics"]["total_return_pct"] > 9.0
    assert remunerated["assumptions"]["cash_yield_enabled"] is True
