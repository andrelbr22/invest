import pytest

from investment_engine.ui_helpers import format_brl_price_input, merge_purchase_position, parse_brl_price_input


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


def test_purchase_is_added_with_weighted_average():
    quantity,average=merge_purchase_position(100,10,50,16)
    assert quantity == 150
    assert average == 12


def test_first_purchase_uses_its_own_price():
    quantity,average=merge_purchase_position(0,None,100,27.45)
    assert quantity == 100
    assert average == 27.45
