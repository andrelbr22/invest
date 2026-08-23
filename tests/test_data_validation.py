from investment_engine.data.ingestion.validation import validate_stock, validate_fii, validate_technical


def test_missing_fii_vacancy_reduces_quality_but_is_not_zero_or_invalid():
    result = validate_fii({
        "ticker": "TEST11", "price": 100, "pbv": .9, "dividend_yield_pct": 10,
        "ffo_yield_pct": 9, "cap_rate_pct": 8, "vacancy_pct": None, "daily_liquidity": 1_000_000,
    })
    assert result.valid is True
    assert result.quality_score < 100


def test_non_positive_price_is_rejected():
    result = validate_stock({"ticker": "TEST3", "price": 0})
    assert result.valid is False
    assert "price_non_positive" in result.errors


def test_technical_rsi_outlier_is_warning_not_silent():
    result = validate_technical({"ticker": "TEST3", "rsi14": 110})
    assert result.valid is True
    assert "rsi_out_of_range" in result.warnings
