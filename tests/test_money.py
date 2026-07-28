from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128

from app.money import bson_money, cart_total, format_money, money, money_value


def test_money_rounds_and_formats_exactly():
    assert money(1371.8000000000002) == Decimal("1371.80")
    assert money_value(Decimal128("1371.8")) == "1371.80"
    assert format_money("1371.8") == "1,371.80"
    assert bson_money("19.999") == Decimal128("20.00")


def test_cart_total_uses_decimal_arithmetic():
    cart = [
        {"price": 685.9, "qty": 1},
        {"price": "685.90", "qty": 1},
    ]

    assert cart_total(cart) == Decimal("1371.80")


@pytest.mark.parametrize("value", ["NaN", "Infinity", -1, True, None])
def test_money_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        money(value)
