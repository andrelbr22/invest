from datetime import datetime, timedelta, timezone

from investment_engine.core.screening.advanced import (
    pivot_points,
    technical_features,
    technical_filters_pass,
    filter_row,
)


def test_pivot_points_exact_user_formula():
    p = pivot_points(110, 90, 100)
    assert round(p["pp"], 8) == 100
    assert round(p["r1"], 8) == 110
    assert round(p["s1"], 8) == 90
    assert round(p["r2"], 8) == 120
    assert round(p["s2"], 8) == 80
    assert round(p["r3"], 8) == 130
    assert round(p["s3"], 8) == 70


def test_technical_features_support_21_period_daily_weekly_monthly_trends():
    start = datetime(2023, 1, 2, tzinfo=timezone.utc)
    bars = []
    price = 50.0
    # 760 calendar days provide more than 21 completed monthly buckets.
    for i in range(760):
        ts = start + timedelta(days=i)
        if ts.weekday() >= 5:
            continue
        price += 0.05
        bars.append({"timestamp": ts, "open": price - 0.2, "high": price + 0.5, "low": price - 0.5,
                     "close": price, "adjusted_close": price, "volume": 100000})
    x = technical_features(bars, trend_period=21, pivot_timeframe="daily")
    assert x["trend_daily"] == "up"
    assert x["trend_weekly"] == "up"
    assert x["trend_monthly"] == "up"
    assert x["sma_daily"] is not None
    assert x["sma_weekly"] is not None
    assert x["sma_monthly"] is not None
    assert x["pp"] is not None


def test_combined_fundamental_and_score_filters_require_all_active_rules():
    fund = {"pe": 8, "pbv": 0.9, "roe_pct": 18, "dividend_yield_pct": 7}
    scores = {"alb_score": 72, "data_quality_score": 90}
    assert filter_row(
        fund, scores,
        fundamental_filters={"pe": {"min": 0, "max": 10}, "roe_pct": {"min": 15}},
        score_filters={"alb_score": {"min": 70}},
        valuation_flags={"below_graham": True, "below_barsi_6pct": True},
    )
    assert not filter_row(fund, scores, fundamental_filters={"roe_pct": {"min": 25}})


def test_technical_filters_combine_trend_rsi_and_pivot_zone():
    features = {
        "current_price": 105, "trend_daily": "up", "trend_weekly": "up", "trend_monthly": "up",
        "rsi14": 55, "s3": 70, "s2": 80, "s1": 90, "pp": 100, "r1": 110, "r2": 120, "r3": 130,
    }
    assert technical_filters_pass(features, {
        "daily_trend": "up", "weekly_trend": "up", "monthly_trend": "up",
        "rsi14": {"min": 40, "max": 65}, "pivot_zone": "pp_r1",
    })
    assert not technical_filters_pass(features, {"monthly_trend": "down"})


def test_advanced_screen_repository_integration_sqlite():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from investment_engine.infrastructure.db.base import Base
    from investment_engine.core.repositories.assets import AssetRepository
    from investment_engine.core.screening.advanced import advanced_screen

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = AssetRepository(session)
        a = repo.upsert_asset(ticker="TEST3", asset_type="stock", name="Teste", sector="Utilities")
        now = datetime(2026, 8, 21, tzinfo=timezone.utc)
        repo.upsert_fundamentals(
            a, source="test", reference_date=now, retrieved_at=now, status="valid", quality_score=100,
            data={"price":100,"pe":8,"pbv":1,"roe_pct":20,"dividend_yield_pct":7,"daily_liquidity":2_000_000}, raw_payload={},
        )
        prices=[]
        for i in range(80):
            ts=now-timedelta(days=100-i)
            if ts.weekday()<5:
                prices.append({"timestamp":ts,"timeframe":"1D","source":"test","open":90+i,"high":91+i,"low":89+i,"close":90+i,"adjusted_close":90+i,"volume":1000})
        repo.bulk_upsert_price_bars(a,prices,retrieved_at=now)
        session.commit()
        result=advanced_screen(repo,asset_type="stock",fundamental_filters={"roe_pct":{"min":15}},technical_filters={"daily_trend":"up"},trend_period=21,pivot_timeframe="daily",limit=10)
        assert result["meta"]["returned"] == 1
        assert result["rows"][0]["ticker"] == "TEST3"
        assert result["rows"][0]["pp"] is not None
