import pytest

from investment_engine.core.backtesting.basket import aggregate_basket
from investment_engine.core.backtesting.aliases import resolve_ticker_alias


def _result(ticker, end_equity, end_benchmark, trades, exposure=10):
    return {
        "ticker": ticker, "requested_ticker": ticker, "initial_capital": 10000.0,
        "asset_name": ticker, "ticker_alias": None,
        "equity_curve": [
            {"timestamp":"2025-01-02T00:00:00+00:00","equity":10000,"benchmark":10000},
            {"timestamp":"2025-12-31T00:00:00+00:00","equity":end_equity,"benchmark":end_benchmark},
        ],
        "trades": trades,
        "metrics": {"max_drawdown_pct":-10,"exposure_pct":exposure,"closed_trades":sum(t.get("exit_date") is not None for t in trades),"open_trades":sum(t.get("exit_date") is None for t in trades),"profit_factor":2},
    }


def test_aliases_resolve_old_b3_codes():
    assert resolve_ticker_alias("vivt4")[0] == "VIVT3"
    assert resolve_ticker_alias("EMBR3")[0] == "EMBJ3"
    assert resolve_ticker_alias("PETR4") == ("PETR4", None)


def test_equal_weight_basket_aggregates_curve_open_positions_and_contribution():
    a=_result("AAA3",12000,13000,[{"exit_date":"2025-06-01","pnl_value":2000,"return_pct":20}])
    b=_result("BBB3",9000,11000,[{"exit_date":None,"pnl_value":-1000,"return_pct":-10}])
    out=aggregate_basket([a,b],initial_capital=100000,risk_free_rate_pct=0)
    m=out["metrics"]
    assert m["total_return_pct"] == pytest.approx(5.0)
    assert m["benchmark_total_return_pct"] == pytest.approx(20.0)
    assert m["closed_trades"] == 1 and m["open_trades"] == 1
    assert m["profit_factor_mark_to_market"] == pytest.approx(2.0)
    assert sum(x["weight_pct"] for x in out["assets"]) == pytest.approx(100.0)
    assert sum(x["contribution_pct_points"] for x in out["assets"]) == pytest.approx(5.0)
