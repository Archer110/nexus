from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from bson.decimal128 import Decimal128

CENT = Decimal("0.01")


def money(value: Any) -> Decimal:
    """Return a finite, non-negative monetary value rounded to cents."""
    if isinstance(value, bool):
        raise ValueError("Invalid monetary value.")

    if isinstance(value, Decimal128):
        value = value.to_decimal()

    try:
        amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Invalid monetary value.") from error

    if not amount.is_finite():
        raise ValueError("Invalid monetary value.")
    if amount < 0:
        raise ValueError("Monetary values cannot be negative.")
    return amount


def money_value(value: Any) -> str:
    """Serialize money without locale formatting for forms and sessions."""
    return f"{money(value):.2f}"


def format_money(value: Any) -> str:
    """Format money consistently for human-facing templates."""
    return f"{money(value):,.2f}"


def cart_total(items: Iterable[Mapping[str, Any]]) -> Decimal:
    """Calculate a cart total without binary floating-point arithmetic."""
    return sum(
        (money(item["price"]) * int(item["qty"]) for item in items),
        start=Decimal("0.00"),
    )


def bson_money(value: Any) -> Decimal128:
    """Serialize money exactly for MongoDB."""
    return Decimal128(money(value))
