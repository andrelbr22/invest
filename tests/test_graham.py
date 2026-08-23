from investment_engine.core.valuation.graham import implied_eps, implied_book_value_per_share, graham_number, add_upside


def test_graham_number():
    eps = implied_eps(30, 10)
    bvps = implied_book_value_per_share(30, 1.5)
    result = add_upside(graham_number(eps, bvps), 30)
    assert eps == 3
    assert bvps == 20
    assert round(result.value, 4) == round((22.5 * 3 * 20) ** 0.5, 4)
    assert result.upside_pct is not None


def test_negative_eps_is_not_zeroed():
    eps = implied_eps(30, -10)
    assert eps == -3
    result = graham_number(eps, 20)
    assert result.value is None
    assert result.reason == "requires_positive_eps_and_bvps"
