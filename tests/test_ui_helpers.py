import pytest

from investment_engine.ui_helpers import format_brl_price_input, parse_brl_price_input


def test_price_input_uses_exactly_two_decimal_places():
    assert format_brl_price_input(27.4) == "27,40"
    assert format_brl_price_input(None) == ""


def test_price_input_accepts_brazilian_and_machine_formats():
    assert parse_brl_price_input("27,45") == 27.45
    assert parse_brl_price_input("27.45") == 27.45
    assert parse_brl_price_input("1.234,56") == 1234.56
    assert parse_brl_price_input("") is None


def test_price_input_rejects_invalid_text():
    with pytest.raises(ValueError, match="formato 12,34"):
        parse_brl_price_input("abc")
