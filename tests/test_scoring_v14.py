from types import SimpleNamespace
from datetime import datetime, timezone

from investment_engine.core.scoring.sector_models import detect_profile, stock_quality_score, fii_quality_score, PROFILES
from investment_engine.core.scoring.market import technical_score, risk_score, liquidity_score, weighted_alb
from investment_engine.core.services_v14 import calculate_asset_intelligence


def test_bank_profile_does_not_use_industrial_metrics_as_required():
    p=detect_profile("stock","Finance","Major Banks")
    assert p.key=="bank"
    s=stock_quality_score({"roe_pct":20,"net_margin_pct":25,"earnings_cagr_5y_pct":10,"revenue_cagr_5y_pct":8,"ebit_margin_pct":None,"roic_pct":None},p)
    assert s.score is not None and s.coverage==100


def test_fii_has_own_quality_model():
    s=fii_quality_score({"ffo_yield_pct":10,"cap_rate_pct":9,"vacancy_pct":5,"ltv_pct":20,"wale_years":6})
    assert s.score is not None and s.score>70


def test_technical_score_requires_available_signals_not_fake_zero():
    s=technical_score({})
    assert s.score is None and s.coverage==0


def test_risk_bank_ignores_net_debt_ebitda():
    s=risk_score({"net_debt_to_ebitda":99},{"volatility_annual_pct":20,"max_drawdown_1y_pct":-15},"bank")
    assert s.score is not None and "net_debt_ebitda" not in s.details


def test_liquidity_score_stock():
    s=liquidity_score({}, {"daily_liquidity":20_000_000}, "stock")
    assert s.score==100


def test_weighted_alb_reports_coverage():
    q=stock_quality_score({"roe_pct":20,"net_margin_pct":20,"earnings_cagr_5y_pct":10,"revenue_cagr_5y_pct":8},PROFILES["bank"])
    t=technical_score({})
    alb,cov,_=weighted_alb({"quality":q,"technical":t},{"quality":.7,"technical":.3})
    assert alb is not None and 69 < cov < 71


def test_service_bank_returns_sector_aware_profile_and_no_false_quality_zero():
    asset=SimpleNamespace(asset_type="stock",sector="Finance",industry="Major Banks",segment=None)
    fund=SimpleNamespace(
        price=18.43,pe=4.5,pbv=.8,dividend_yield_pct=8,ev_ebitda=None,ebit_margin_pct=None,net_margin_pct=25,
        current_ratio=None,roe_pct=20,roic_pct=None,gross_debt_to_equity=None,net_debt_to_ebitda=None,
        revenue_cagr_5y_pct=8,earnings_cagr_5y_pct=10,ffo_yield_pct=None,cap_rate_pct=None,vacancy_pct=None,
        financial_vacancy_pct=None,ltv_pct=None,wale_years=None,daily_liquidity=None,reference_date=datetime.now(timezone.utc),
    )
    tech=SimpleNamespace(score_tv=None,market_cap=None,daily_liquidity=100_000_000,sma20=18,sma50=17,sma200=15,high=None,low=None,close=18.43,rsi14=55,bb_lower=None,bb_upper=None,bb_middle=None,macd=.2,atr14=None,volatility_annual_pct=22,max_drawdown_1y_pct=-18,return_1m_pct=2,return_3m_pct=8,return_12m_pct=15)
    x=calculate_asset_intelligence(asset,fund,tech)
    assert x["profile"].key=="bank"
    assert x["quality"].score is not None and x["quality"].score>0
    assert x["technical"].score is not None
    assert x["risk"].score is not None
    assert x["liquidity"].score is not None
    assert x["alb_score"] is not None
