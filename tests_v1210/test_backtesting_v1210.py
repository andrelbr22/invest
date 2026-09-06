from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest
from pydantic import ValidationError

from investment_engine.api.app import (
    BacktestFiltersRequest,
    BacktestMatrixRequest,
    BacktestTrendFilterRequest,
    _require_owner_inline_backtest,
)
from investment_engine.core.backtesting.engine import _performance_metrics, run_backtest
from investment_engine.core.backtesting.batch import BacktestBatchService
from investment_engine.core.backtesting.filters import _classic_pivots, apply_backtest_filters
from investment_engine.core.backtesting.grid import (
    DEFAULT_MAX_COMBINATIONS,
    OFFICIAL_GRID_VERSION,
    official_grid,
)
from investment_engine.core.backtesting.strategies import (
    STRATEGIES,
    _rsi,
    build_signal,
    strategy_catalog,
    validate_strategy_params,
)


def _price_frame(count=520):
    index = pd.date_range("2023-01-02", periods=count, freq="B", tz="UTC")
    price = pd.Series(
        [100 + position * 0.08 + ((position % 30) - 15) * 0.18 for position in range(count)],
        index=index,
        dtype=float,
    )
    return pd.DataFrame(
        {
            "price": price,
            "adjusted_close": price,
            "close": price,
            "adj_high": price * 1.01,
            "adj_low": price * 0.99,
            "high": price * 1.01,
            "low": price * 0.99,
            "volume": [1_000_000 + (position % 20) * 10_000 for position in range(count)],
        },
        index=index,
    )


def _bars(frame):
    return [
        {
            "timestamp": timestamp.to_pydatetime(),
            **{column: float(row[column]) for column in frame.columns if column != "price"},
        }
        for timestamp, row in frame.iterrows()
    ]


def test_strategy_catalog_has_new_auditable_families_and_parameter_schemas():
    expected = {
        "supertrend_atr",
        "dual_momentum_relative",
        "bollinger_squeeze_breakout",
        "custom_ma_cross",
    }
    assert expected.issubset(STRATEGIES)
    catalog = {item["id"]: item for item in strategy_catalog()}
    for strategy_id in expected:
        assert catalog[strategy_id]["description"]
        assert catalog[strategy_id]["rules"]
        assert catalog[strategy_id]["parameter_schema"]
    assert catalog["dual_momentum_relative"]["requires_benchmark"] is True


def test_strategy_parameters_are_typed_bounded_and_relationally_validated():
    typed = validate_strategy_params(
        "custom_ma_cross",
        {"fast_period": "9", "slow_period": "50", "fast_type": "ema", "slow_type": "sma"},
    )
    assert typed["fast_period"] == 9
    assert typed["slow_period"] == 50
    with pytest.raises(ValueError, match="unsupported_strategy_parameters"):
        validate_strategy_params("supertrend_atr", {"secret_parameter": 10})
    with pytest.raises(ValueError, match="strategy_parameter_above_maximum"):
        validate_strategy_params("supertrend_atr", {"multiplier": 99})
    with pytest.raises(ValueError, match="fast_period_must_be_lower"):
        validate_strategy_params("custom_ma_cross", {"fast_period": 50, "slow_period": 20})
    with pytest.raises(ValueError, match="lookback_must_exceed"):
        validate_strategy_params("dual_momentum_relative", {"lookback": 63, "skip_recent": 63})
    with pytest.raises(ValueError, match="strategy_parameter_is_fixed:fast_period"):
        validate_strategy_params("ema9_sma50", {"fast_period": 8})
    # Supplying the documented fixed value remains compatible with old saved grids.
    assert validate_strategy_params("ema9_sma50", {"fast_period": 9})["fast_period"] == 9
    with pytest.raises(ValueError, match="strategy_parameter_is_fixed:benchmark_ticker"):
        validate_strategy_params("dual_momentum_relative", {"benchmark_ticker": "INVALID"})
    with pytest.raises(ValueError, match="invalid_strategy_parameter:multiplier"):
        validate_strategy_params("supertrend_atr", {"multiplier": float("nan")})


def test_rsi_flat_series_is_neutral_instead_of_missing_or_extreme():
    values = pd.Series([100.0] * 40)
    result = _rsi(values, 14)
    assert result.iloc[-1] == pytest.approx(50.0)


def test_donchian_uses_adjusted_highs_and_lows_instead_of_unadjusted_split_prices():
    frame = _price_frame(80)
    frame["high"] = frame["adj_high"] * 10.0
    frame["low"] = frame["adj_low"] * 10.0
    _signal, indicators, _params = build_signal(frame, "donchian_20_10")
    expected_upper = frame["adj_high"].rolling(20, min_periods=20).max().shift(1)
    expected_lower = frame["adj_low"].rolling(10, min_periods=10).min().shift(1)
    pd.testing.assert_series_equal(
        indicators["Donchian 20 máx."], expected_upper, check_names=False,
    )
    pd.testing.assert_series_equal(
        indicators["Donchian 10 mín."], expected_lower, check_names=False,
    )


def test_legacy_adjusted_close_only_history_remains_supported():
    frame = _price_frame(300)
    bars = [
        {"timestamp": timestamp.to_pydatetime(), "adjusted_close": float(row["adjusted_close"])}
        for timestamp, row in frame.iterrows()
    ]
    result = run_backtest(
        bars,
        strategy_id="ema9_sma50",
        requested_start=frame.index[100].to_pydatetime(),
        requested_end=frame.index[-1].to_pydatetime(),
    )
    assert result["metrics"]["bars"] == 200


def test_dual_momentum_requires_and_uses_a_point_in_time_benchmark():
    frame = _price_frame()
    with pytest.raises(ValueError, match="benchmark_history_required"):
        build_signal(frame, "dual_momentum_relative")
    benchmark = frame["price"] * pd.Series(
        [1.0 - position * 0.0001 for position in range(len(frame))],
        index=frame.index,
    )
    signal, indicators, params = build_signal(
        frame,
        "dual_momentum_relative",
        {"lookback": 126, "skip_recent": 21},
        benchmark_price=benchmark,
    )
    assert params["lookback"] == 126
    assert {"Momentum absoluto %", "Momentum benchmark %", "Momentum excedente %"}.issubset(indicators)
    assert signal.notna().sum() > 0


def test_external_signal_reference_does_not_change_the_legacy_buy_and_hold_benchmark():
    frame = _price_frame()
    benchmark = frame.copy()
    benchmark["adjusted_close"] = pd.Series(
        [300.0 - position * 0.1 for position in range(len(frame))],
        index=frame.index,
    )
    benchmark["close"] = benchmark["adjusted_close"]
    result = run_backtest(
        _bars(frame),
        strategy_id="dual_momentum_relative",
        params={"lookback": 126, "skip_recent": 21},
        benchmark_bars=_bars(benchmark),
        requested_start=frame.index[150].to_pydatetime(),
        requested_end=frame.index[-1].to_pydatetime(),
    )
    first = frame.loc[frame.index[150], "adjusted_close"]
    last = frame.loc[frame.index[-1], "adjusted_close"]
    assert result["metrics"]["benchmark_total_return_pct"] == pytest.approx((last / first - 1) * 100)
    assert result["assumptions"]["benchmark_series"] == "buy-and-hold do próprio ativo"
    assert result["assumptions"]["signal_reference_series"] == "benchmark externo alinhado por pregão"


def test_pivots_use_only_the_previous_adjusted_bar():
    index = pd.date_range("2026-01-01", periods=3, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {"price": [9.0, 10.0, 200.0], "adj_high": [10.0, 12.0, 999.0], "adj_low": [8.0, 8.0, 1.0]},
        index=index,
    )
    pivots = _classic_pivots(frame, frame["price"])
    # On day three the calculation can only see day two: H=12, L=8, C=10.
    assert pivots["pp"].iloc[2] == pytest.approx(10.0)
    assert pivots["r1"].iloc[2] == pytest.approx(12.0)
    assert pivots["s1"].iloc[2] == pytest.approx(8.0)


def test_all_supported_trend_averages_and_extended_filters_are_validated():
    for ma_type, period in (("sma", 8), ("ema", 9), ("sma", 21), ("sma", 50), ("sma", 200)):
        value = BacktestTrendFilterRequest(enabled=True, ma_type=ma_type, period=period)
        assert value.period == period
    with pytest.raises(ValidationError):
        BacktestTrendFilterRequest(enabled=True, ma_type="ema", period=21)
    filters = BacktestFiltersRequest(
        macd_condition="cross_up",
        bollinger_percent_b_min=-0.2,
        bollinger_percent_b_max=1.2,
        bollinger_bandwidth_min=1.0,
        relative_strength_min=2.5,
        relative_strength_lookback=126,
        pivot_zone="s1_pp",
        near_pivot_level="s1",
        daily_liquidity_min=1_000_000,
    )
    assert filters.macd_condition == "cross_up"
    with pytest.raises(ValidationError):
        BacktestFiltersRequest(rsi_min=70, rsi_max=30)


def test_relative_strength_filter_fails_closed_without_reference_and_exposes_diagnostics():
    frame = _price_frame(300)
    base_signal = pd.Series(1.0, index=frame.index)
    config = {"relative_strength_min": 0.0, "relative_strength_lookback": 63}
    with pytest.raises(ValueError, match="benchmark_history_required_for_relative_strength"):
        apply_backtest_filters(
            frame, base_signal, config,
            requested_start=frame.index[100].to_pydatetime(),
            requested_end=frame.index[-1].to_pydatetime(),
        )
    benchmark = pd.Series(
        [100.0 + position * 0.01 for position in range(len(frame))],
        index=frame.index,
    )
    filtered, indicators, effective, diagnostics = apply_backtest_filters(
        frame, base_signal, config, benchmark_price=benchmark,
        requested_start=frame.index[100].to_pydatetime(),
        requested_end=frame.index[-1].to_pydatetime(),
    )
    assert effective["relative_strength_lookback"] == 63
    assert "Força relativa 63 pregões %" in indicators
    assert diagnostics["conditions"]["Força relativa"]["bars_valid"] > 0
    assert filtered.notna().sum() > 0


def test_matrix_request_carries_separate_parameters_for_each_strategy():
    request = BacktestMatrixRequest(
        tickers=["PETR4", "VALE3"],
        strategy_ids=["custom_ma_cross", "supertrend_atr"],
        strategy_params={
            "custom_ma_cross": {"fast_period": 9, "slow_period": 50},
            "supertrend_atr": {"atr_period": 10, "multiplier": 3},
        },
        execution_mode="combined",
        combination_rule="majority",
    )
    assert request.strategy_params["supertrend_atr"]["multiplier"] == 3
    assert request.execution_mode == "combined"


def test_official_grid_is_balanced_deterministic_unique_and_covers_every_strategy():
    first = official_grid(DEFAULT_MAX_COMBINATIONS)
    second = official_grid(DEFAULT_MAX_COMBINATIONS)
    assert first == second
    assert len(first) == DEFAULT_MAX_COMBINATIONS
    assert {row["strategy_id"] for row in first} == set(STRATEGIES)
    assert {row["grid_version"] for row in first} == {OFFICIAL_GRID_VERSION}
    fingerprints = {
        repr((row["strategy_id"], sorted(row["params"].items()), row["filters"]))
        for row in first
    }
    assert len(fingerprints) == len(first)
    counts = pd.Series([row["strategy_id"] for row in first]).value_counts()
    assert counts.max() - counts.min() <= 1
    assert any(row["filters"].get("macd_condition") == "above" for row in first)
    assert any(row["filters"].get("relative_strength_min") == 0 for row in first)
    for row in first:
        assert validate_strategy_params(row["strategy_id"], row["params"])


def _official_batch_harness(monkeypatch, reference_history):
    frame = _price_frame(300)
    price_rows = [
        SimpleNamespace(
            timestamp=timestamp.to_pydatetime(), open=row["close"], high=row["high"],
            low=row["low"], close=row["close"], volume=row["volume"],
            adjusted_close=row["adjusted_close"],
        )
        for timestamp, row in frame.iterrows()
    ]
    service = BacktestBatchService.__new__(BacktestBatchService)
    service.session = SimpleNamespace(begin_nested=lambda: nullcontext())
    service.assets = SimpleNamespace(fundamental_history_until=lambda *_args, **_kwargs: [])
    service.service = SimpleNamespace(
        ensure_history=lambda *_args, **_kwargs: (
            SimpleNamespace(id=uuid4(), ticker="PETR4", name="Petrobras", asset_type="stock"),
            price_rows,
        ),
    )
    # The production object delegates these two helpers to BacktestService.
    from investment_engine.core.backtesting.service import BacktestService
    service.service._needs_benchmark = BacktestService._needs_benchmark
    service.service._benchmark_history = reference_history
    service.service._configuration_hash = lambda **_kwargs: "configuration"
    service.backtests = SimpleNamespace(
        find_daily_cached=lambda **_kwargs: None,
        save_run=lambda **_kwargs: SimpleNamespace(id=uuid4()),
    )
    captured = []
    def fake_run(_bars_value, **kwargs):
        captured.append(kwargs)
        return {
            "parameters": kwargs["params"], "filters": kwargs["filters"],
            "actual_start": frame.index[100].isoformat(),
            "actual_end": frame.index[-1].isoformat(), "metrics": {},
            "equity_curve": [], "trades": [],
            "current_signal": {"status": "neutral", "as_of": frame.index[-1].isoformat()},
            "ranking_score": 0.0, "sample_status": "insufficient",
        }
    monkeypatch.setattr("investment_engine.core.backtesting.batch.run_backtest", fake_run)
    monkeypatch.setattr("investment_engine.core.backtesting.batch.enrich_result", lambda _result: None)
    return service, captured, frame


def test_official_batch_supplies_one_benchmark_to_relative_rows(monkeypatch):
    reference = _bars(_price_frame(300))
    benchmark_calls = []
    def reference_history(**kwargs):
        benchmark_calls.append(kwargs)
        return reference, "^BVSP"
    service, captured, _frame = _official_batch_harness(monkeypatch, reference_history)
    configuration = {
        "strategy_id": "dual_momentum_relative",
        "params": validate_strategy_params("dual_momentum_relative", {"lookback": 126}),
        "filters": {"relative_strength_min": 0.0},
    }
    completed, failed, errors = service._run_asset("PETR4", [configuration], uuid4())
    assert (completed, failed, errors) == (1, 0, [])
    assert len(benchmark_calls) == 1
    assert captured[0]["benchmark_bars"] is reference


def test_official_batch_keeps_independent_rows_when_reference_provider_is_down(monkeypatch):
    def unavailable_reference(**_kwargs):
        raise ValueError("benchmark_history_unavailable")
    service, captured, _frame = _official_batch_harness(monkeypatch, unavailable_reference)
    configurations = [
        {
            "strategy_id": "ema9_sma50",
            "params": validate_strategy_params("ema9_sma50"),
            "filters": {},
        },
        {
            "strategy_id": "dual_momentum_relative",
            "params": validate_strategy_params("dual_momentum_relative"),
            "filters": {},
        },
    ]
    completed, failed, errors = service._run_asset("PETR4", configurations, uuid4())
    assert (completed, failed) == (1, 1)
    assert len(captured) == 1
    assert captured[0]["strategy_id"] == "ema9_sma50"
    assert errors[0]["strategy_id"] == "dual_momentum_relative"
    assert "benchmark_history_unavailable" in errors[0]["error"]


def test_backtest_exposes_action_separately_from_position_and_records_assumptions():
    frame = _price_frame()
    result = run_backtest(
        _bars(frame),
        strategy_id="custom_ma_cross",
        params={"fast_period": 9, "slow_period": 50},
        requested_start=frame.index[100].to_pydatetime(),
        requested_end=frame.index[-1].to_pydatetime(),
    )
    assert result["action_signal"]["status"] in {"buy", "sell", "neutral"}
    assert result["position_state"]["status"] in {"invested", "out"}
    assert result["current_signal"] == result["action_signal"]
    assert "execução no fechamento t+1" in result["assumptions"]["signal_execution"]
    assert result["assumptions"]["price_series"].startswith("adjusted_close")


def test_new_signal_on_final_close_is_buy_while_position_remains_out_until_execution(monkeypatch):
    frame = _price_frame(120)
    def final_bar_entry(data, _strategy_id, _params=None):
        signal = pd.Series(0.0, index=data.index)
        signal.iloc[-1] = 1.0
        return signal, pd.DataFrame(index=data.index), {}
    monkeypatch.setattr("investment_engine.core.backtesting.engine.build_signal", final_bar_entry)
    result = run_backtest(
        _bars(frame), strategy_id="ema9_sma50",
        requested_start=frame.index[20].to_pydatetime(),
        requested_end=frame.index[-1].to_pydatetime(),
    )
    assert result["action_signal"]["status"] == "buy"
    assert result["position_state"]["status"] == "out"


def test_profit_factor_is_money_weighted_not_a_sum_of_percentages():
    index = pd.date_range("2026-01-01", periods=3, freq="B", tz="UTC")
    equity = pd.Series([1000.0, 1100.0, 1075.0], index=index)
    returns = equity.pct_change().fillna(0)
    benchmark = pd.Series([1000.0, 1000.0, 1000.0], index=index)
    metrics = _performance_metrics(
        equity,
        returns,
        pd.Series([0.0, 1.0, 0.0], index=index),
        benchmark,
        benchmark.pct_change().fillna(0),
        [
            {"exit_date": index[1], "return_pct": 50.0, "pnl_value": 100.0, "holding_days": 1},
            {"exit_date": index[2], "return_pct": -50.0, "pnl_value": -25.0, "holding_days": 1},
        ],
        0.0,
        pd.Series([0.0, 1.0, 1.0], index=index),
        0.0,
    )
    assert metrics["profit_factor"] == pytest.approx(4.0)
    assert metrics["profit_factor_percentage_aux"] == pytest.approx(1.0)
    assert metrics["profit_factor_mark_to_market"] == pytest.approx(4.0)


def test_regular_accounts_cannot_bypass_queue_and_limits_through_legacy_endpoint():
    with pytest.raises(Exception) as error:
        _require_owner_inline_backtest({"is_owner": False})
    assert getattr(error.value, "status_code", None) == 403
    _require_owner_inline_backtest({"is_owner": True})
