from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from investment_engine.api.app import BacktestCompareRequest, BacktestMatrixRequest, _alb_stock_rows
from investment_engine.core.screening.advanced import (
    pivot_points,
    row_from_orm,
    technical_features,
    technical_filters_pass,
)


def _bar(year, month, day, *, high, low, close, volume):
    return {
        "timestamp": datetime(year, month, day, tzinfo=timezone.utc),
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "adjusted_close": close,
        "volume": volume,
    }


def test_classic_pivot_formulas_match_requested_method():
    values = pivot_points(120, 90, 105)
    assert values == {
        "pp": 105,
        "r1": 120,
        "s1": 90,
        "r2": 135,
        "s2": 75,
        "r3": 150,
        "s3": 60,
    }


def test_daily_and_monthly_volume_use_previous_nine_completed_observations():
    bars = []
    for month in range(1, 13):
        bars.append(_bar(2025, month, 15, high=110, low=90, close=100 + month, volume=100))
    bars.extend([
        _bar(2026, 1, 13, high=120, low=100, close=110, volume=100),
        _bar(2026, 1, 14, high=121, low=101, close=111, volume=100),
        _bar(2026, 1, 15, high=122, low=102, close=112, volume=200),
    ])
    features = technical_features(bars, pivot_timeframe="daily")
    assert features["volume_daily"] == 200
    assert features["volume_daily_ma9"] == pytest.approx(100)
    assert features["volume_daily_ratio"] == pytest.approx(2)
    assert technical_filters_pass(features, {"volume_daily_above_ma9": True}) is True
    assert features["pp"] == pytest.approx((121 + 101 + 111) / 3)


def test_barsi_ceiling_is_current_annual_dividend_divided_by_six_percent():
    asset = SimpleNamespace(
        id=uuid4(), ticker="TEST3", name="Teste", asset_type="stock",
        sector="utilities", industry=None, segment=None,
        market_cap_category="large", metadata_json={},
    )
    fund = SimpleNamespace(price=20, pe=8, pbv=1.2, dividend_yield_pct=9, daily_liquidity=2_000_000)
    result = row_from_orm(asset, fund, None, None)
    assert result["fundamentals"]["barsi_ceiling_price"] == pytest.approx(30)
    assert result["fundamentals"]["barsi_upside_pct"] == pytest.approx(50)


def test_alb_shortlist_relaxes_only_when_needed_and_caps_at_twenty():
    primary = [(SimpleNamespace(id=uuid4()), None, None) for _ in range(2)]
    relaxed = primary + [(SimpleNamespace(id=uuid4()), None, None) for _ in range(9)]

    class Repo:
        calls = 0

        def screen_latest_stocks(self, _filters, **_kwargs):
            self.calls += 1
            return primary if self.calls == 1 else relaxed

    repo = Repo()
    rows = _alb_stock_rows(repo, limit=100)
    assert len(rows) == 11
    assert repo.calls == 2


def test_backtest_comparison_accepts_three_strategies_and_thirty_assets_only():
    valid = BacktestMatrixRequest(
        tickers=[f"TEST{index}" for index in range(30)],
        strategy_ids=["ema9_sma50", "rsi14_sma200", "custom_ma_cross"],
    )
    assert len(valid.tickers) == 30
    with pytest.raises(ValidationError):
        BacktestCompareRequest(
            ticker="BBAS3",
            strategy_ids=["ema9_sma50", "rsi14_sma200", "custom_ma_cross", "momentum_12m"],
        )
