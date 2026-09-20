from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from investment_engine.core.backtesting.filters import normalize_filter_config
from investment_engine.core.repositories.access import policy_dict
from investment_engine.data.providers.market_dashboard import (
    HISTORICAL_COMPARISON_ORDER,
    MarketDashboardService,
)
from investment_engine.infrastructure.db.models import UserAccessPolicyORM


ROOT = Path(__file__).resolve().parents[1]


class _MetricPrices:
    def fetch(self, symbol, *, range_="2y"):
        now = datetime(2026, 8, 30, tzinfo=timezone.utc)
        if symbol == "^IFIX":
            return [{"timestamp": now, "close": 3500.0, "adjusted_close": 3500.0}]
        return [
            {"timestamp": now - timedelta(days=offset), "close": 100 + offset, "adjusted_close": 100 + offset}
            for offset in reversed(range(370))
        ]


def test_market_additions_and_ifix_variation_proxy_are_explicit():
    service = MarketDashboardService(prices=_MetricPrices())
    ifix = service._yahoo_metric("IFIX", ["^IFIX", "XFIX11"])
    assert ifix["current"] == 3500.0
    assert all(ifix["variations"][key] is not None for key in ("1d", "1w", "1m", "1y"))
    assert ifix["proxy"] is True
    assert "XFIX11" in ifix["proxy_label"]
    quoted = service.quoted_markets()
    assert [item["label"] for item in quoted["brazil"]] == ["IBOV", "IFIX", "IBrX 100", "IBrX 50", "IDIV", "SMLL"]
    assert {item["ticker"] for item in service.crypto()} == {"BTC", "ETH", "SOL", "XRP", "BNB"}
    assert "BTC" in HISTORICAL_COMPARISON_ORDER and "ETH" in HISTORICAL_COMPARISON_ORDER


def test_super_wednesday_becomes_one_event():
    rows = MarketDashboardService._merge_super_wednesday([
        {"category": "Decisão do Copom", "event": "Copom", "date": "2027-03-17", "time": None, "url": "bcb"},
        {"category": "Decisão do Fed", "event": "Fed", "date": "2027-03-17", "time": "14:00 ET", "url": "fed"},
        {"category": "Payroll dos EUA", "event": "Payroll", "date": "2027-03-17"},
    ])
    assert len(rows) == 2
    super_event = next(item for item in rows if item["category"] == "Super Quarta")
    assert super_event["highlight"] == "super_wednesday"
    assert "Copom" in super_event["time"] and "Fed" in super_event["time"]


def test_analysis_permissions_and_alb_inheritance():
    row = UserAccessPolicyORM(
        email="investidor@example.com", status="approved", can_use_alb_analysis=True,
        can_use_graham_valuation=False, can_use_dividend_ceiling=False,
    )
    policy = policy_dict(row)
    assert policy["can_use_alb_analysis"] is True
    assert policy["can_use_graham_valuation"] is True
    assert policy["can_use_dividend_ceiling"] is True


def test_backtest_trend_supports_approved_moving_averages():
    for ma_type, period in (("sma", 8), ("ema", 9), ("sma", 21), ("sma", 50), ("sma", 200)):
        config = normalize_filter_config({"daily_trend": {"enabled": True, "ma_type": ma_type, "period": period}})
        assert config["daily_trend"]["ma_type"] == ma_type
        assert config["daily_trend"]["period"] == period
    fallback = normalize_filter_config({"daily_trend": {"enabled": True, "ma_type": "ema", "period": 21}})
    assert (fallback["daily_trend"]["ma_type"], fallback["daily_trend"]["period"]) == ("sma", 21)


def test_r2_interface_exposes_requested_controls_and_hides_30_year_curve():
    script = (ROOT / "investment_engine/web/static/app.js").read_text(encoding="utf-8")
    html = (ROOT / "investment_engine/web/index.html").read_text(encoding="utf-8")
    backend = "\n".join([
        (ROOT / "investment_engine/api/app.py").read_text(encoding="utf-8"),
        (ROOT / "investment_engine/data/providers/market_dashboard.py").read_text(encoding="utf-8"),
    ])
    for marker in (
        "IBrX 100", "IBrX 50", "IDIV", "SMLL", "Ripple (XRP)", "10 principais manchetes",
        "Prazo até o vencimento (anos)", "Taxa anual (%)", "MMS 8", "MME 9", "MMS 200",
        "sector_override", "segment_override", "can_use_fdi_analysis", "can_use_alb_analysis",
    ):
        assert marker in script or marker in html or marker in backend
    assert '[30,"30 anos"]' not in script
    assert '>FDI</button>' in html
