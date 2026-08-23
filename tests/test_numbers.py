from investment_engine.data.normalization.numbers import parse_br_number


def test_parse_br_number():
    assert parse_br_number("1.234,56%") == 1234.56
    assert parse_br_number("0,00") == 0.0
    assert parse_br_number("N/D") is None
    assert parse_br_number("-") is None
