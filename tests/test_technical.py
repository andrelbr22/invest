from investment_engine.core.models.common import Signal, Trend
from investment_engine.core.valuation.technical import tradingview_signal, position_vs_sma, classic_pivots


def test_tv_signal_full_scale():
    assert tradingview_signal(.6) == Signal.STRONG_BUY
    assert tradingview_signal(.2) == Signal.BUY
    assert tradingview_signal(0) == Signal.NEUTRAL
    assert tradingview_signal(-.2) == Signal.SELL
    assert tradingview_signal(-.6) == Signal.STRONG_SELL


def test_trend_missing():
    assert position_vs_sma(10, None) == Trend.NO_DATA


def test_pivots():
    p = classic_pivots(12, 8, 10)
    assert p.pp == 10
    assert p.r1 == 12
    assert p.s1 == 8
