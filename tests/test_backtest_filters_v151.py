from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest

from investment_engine.core.backtesting.filters import (
    _combine_trends, _trend_condition, apply_backtest_filters, filter_warmup_calendar_days,
    normalize_filter_config,
)
from investment_engine.core.backtesting.engine import run_backtest
from investment_engine.api.app import BacktestBasketRequest, BacktestCompareRequest


def _df(prices):
    idx=pd.date_range("2024-01-02", periods=len(prices), freq="B", tz="UTC")
    p=pd.Series(prices,index=idx,dtype=float)
    return pd.DataFrame({"price":p,"close":p,"adj_high":p*1.01,"adj_low":p*0.99,"volume":1000.0},index=idx)


def _bars(prices):
    start=datetime(2020,1,1,tzinfo=timezone.utc)
    return [{"timestamp":start+timedelta(days=i),"open":p,"high":p*1.01,"low":p*0.99,"close":p,"adjusted_close":p,"volume":1000} for i,p in enumerate(prices)]


def test_daily_uptrend_filter_allows_only_after_sma_is_formed():
    df=_df([100+i for i in range(80)])
    base=pd.Series(1.0,index=df.index)
    out,_,cfg,diag=apply_backtest_filters(
        df,base,{"daily_trend":{"enabled":True,"direction":"up","period":21}},
        requested_start=df.index[0].to_pydatetime(),requested_end=df.index[-1].to_pydatetime(),
    )
    assert out.iloc[:20].isna().all() or (out.iloc[:20].fillna(0)==0).all()
    assert out.iloc[-1] == 1
    assert diag["conditions"]["Tendência diária"]["period"] == 21


def test_monthly_50_filter_requests_long_warmup():
    days=filter_warmup_calendar_days({"monthly_trend":{"enabled":True,"direction":"up","period":50}})
    assert days >= 1600


def test_fundamental_filter_refuses_missing_point_in_time_history():
    df=_df([100+i*0.1 for i in range(120)])
    base=pd.Series(1.0,index=df.index)
    with pytest.raises(ValueError,match="insufficient_point_in_time_fundamental_history"):
        apply_backtest_filters(
            df,base,{"fundamental_entry":{"pbv":{"max":1.0}}},
            requested_start=df.index[20].to_pydatetime(),requested_end=df.index[-1].to_pydatetime(),
            fundamental_snapshots=[],
        )


def test_compare_request_accepts_all_ten_catalog_strategies():
    ids=["ema9_sma50","ema9_sma40","sma3_ema9_sma21","sma50_sma200","macd_12_26_9","donchian_20_10","momentum_12m","rsi14_sma200","bollinger_rsi_trend","custom_ma_cross"]
    req=BacktestCompareRequest(ticker="BBAS3",strategy_ids=ids)
    assert len(req.strategy_ids)==10


def test_basket_request_accepts_multiple_assets_and_optional_cash_yield():
    req=BacktestBasketRequest(tickers=["VIVT4","EMBR3","PETR4"],strategy_id="bollinger_rsi_trend",apply_cash_yield=True,cash_yield_rate_pct=10)
    assert len(req.tickers)==3
    assert req.apply_cash_yield is True


def test_bollinger_zero_trade_result_contains_diagnostics_instead_of_looking_like_missing_data():
    prices=[100+i*0.15 for i in range(400)]
    bars=_bars(prices)
    result=run_backtest(
        bars,strategy_id="bollinger_rsi_trend",requested_start=bars[230]["timestamp"],requested_end=bars[-1]["timestamp"],
        fee_pct=0,slippage_pct=0,
    )
    assert result["signal_diagnostics"]["price_bars_loaded"] > 100
    assert "bollinger" in result["signal_diagnostics"]
    assert result["signal_diagnostics"]["bollinger"]["all_entry_conditions_bars"] >= 0


def test_filter_config_is_returned_for_auditable_backtest():
    prices=[100+i*0.2 for i in range(200)]
    bars=_bars(prices)
    result=run_backtest(
        bars,strategy_id="ema9_sma40",requested_start=bars[80]["timestamp"],requested_end=bars[-1]["timestamp"],
        fee_pct=0,slippage_pct=0,filters={"daily_trend":{"enabled":True,"direction":"up","period":21}},
    )
    assert result["filters"]["daily_trend"]["enabled"] is True
    assert result["filter_diagnostics"]["active"] is True


def test_trend_modes_price_slope_or_and():
    idx=pd.date_range("2024-01-01",periods=4,freq="D",tz="UTC")
    price=pd.Series([9,11,9,11],index=idx,dtype=float)
    ma=pd.Series([10,10,10,10],index=idx,dtype=float)
    previous=pd.Series([9,9,11,11],index=idx,dtype=float)
    expected={
        "price_above":[False,True,False,True],
        "sma_rising":[True,True,False,False],
        "price_above_or_sma_rising":[True,True,False,True],
        "price_above_and_sma_rising":[False,True,False,False],
    }
    for mode,wanted in expected.items():
        passed,valid,_=_trend_condition(price,ma,previous,mode=mode,direction="up")
        assert valid.all()
        assert passed.tolist()==wanted


def test_trend_combination_all_any_and_majority_rules():
    idx=pd.RangeIndex(3)
    a=pd.Series([True,True,False],index=idx)
    b=pd.Series([True,False,False],index=idx)
    c=pd.Series([False,True,False],index=idx)
    assert _combine_trends([a,b,c],"all",idx).tolist()==[False,False,False]
    assert _combine_trends([a,b,c],"any",idx).tolist()==[True,True,False]
    assert _combine_trends([a,b,c],"majority",idx).tolist()==[True,True,False]
    assert _combine_trends([a,b],"majority",idx).tolist()==[True,False,False]


def test_trend_diagnostics_count_each_timeframe_and_combination():
    df=_df([100+i for i in range(100)])
    base=pd.Series(0.0,index=df.index); base.iloc[40]=1.0; base.iloc[41]=0.0; base.iloc[80]=1.0
    _,_,cfg,diag=apply_backtest_filters(
        df,base,{"daily_trend":{"enabled":True,"period":21,"mode":"sma_rising","slope_lookback":5},"trend_combination":"majority"},
        requested_start=df.index[0].to_pydatetime(),requested_end=df.index[-1].to_pydatetime(),
    )
    assert cfg["trend_combination"]=="majority"
    assert diag["conditions"]["Tendência diária"]["candidate_signals"]==2
    assert diag["trend_combination"]["signals_passed"]==2


def test_legacy_trend_payload_keeps_price_above_behavior():
    cfg=normalize_filter_config({"daily_trend":{"enabled":True,"direction":"up","period":21}})
    assert cfg["daily_trend"]["mode"]=="price_above"
    assert cfg["trend_combination"]=="all"
