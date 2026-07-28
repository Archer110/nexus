import re
from collections.abc import Mapping
from math import isfinite
from typing import Any
from urllib.parse import urljoin, urlsplit

from app.contracts import CartItem, CheckoutCustomer
from app.money import money_value

MAX_SEARCH_LENGTH = 100
MAX_SPEC_FILTERS = 20
MAX_SPEC_VALUES = 20
MAX_SPEC_KEY_LENGTH = 50
MAX_SPEC_VALUE_LENGTH = 200

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def page_number(value: object, default: int = 1) -> int:
    """Normalize an untrusted page parameter without raising a server error."""
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return max(parsed, 1)


def search_term(value: object) -> str:
    """Return a bounded search term suitable for a datastore query."""
    return str(value or "").strip()[:MAX_SEARCH_LENGTH]


def is_safe_spec_key(value: object) -> bool:
    """Reject keys that could alter a Mongo dotted-field query path."""
    key = str(value).strip()
    return (
        bool(key)
        and len(key) <= MAX_SPEC_KEY_LENGTH
        and not key.startswith("$")
        and "." not in key
        and "\x00" not in key
    )


def spec_filters(values: Mapping[str, list[str]]) -> dict[str, list[str]]:
    """Normalize bounded, Mongo-safe catalog filters from query parameters."""
    normalized: dict[str, list[str]] = {}
    for raw_key, raw_values in values.items():
        key = raw_key.strip()
        if len(normalized) >= MAX_SPEC_FILTERS or not is_safe_spec_key(key):
            continue

        clean_values = [
            value.strip()
            for value in raw_values[:MAX_SPEC_VALUES]
            if value.strip() and len(value.strip()) <= MAX_SPEC_VALUE_LENGTH
        ]
        if clean_values:
            normalized[key] = clean_values

    return normalized


def required_text(value: object, label: str, max_length: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required.")
    if len(normalized) > max_length:
        raise ValueError(f"{label} must be at most {max_length} characters.")
    return normalized


def optional_text(value: object, label: str, max_length: int) -> str:
    normalized = str(value or "").strip()
    if len(normalized) > max_length:
        raise ValueError(f"{label} must be at most {max_length} characters.")
    return normalized


def non_negative_int(value: object, label: str, maximum: int = 2_147_483_647) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a whole number.")
    try:
        normalized = int(str(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a whole number.") from error

    if normalized < 0:
        raise ValueError(f"{label} cannot be negative.")
    if normalized > maximum:
        raise ValueError(f"{label} is too large.")
    return normalized


def positive_int(value: object, label: str) -> int:
    normalized = non_negative_int(value, label)
    if normalized < 1:
        raise ValueError(f"{label} must be positive.")
    return normalized


def product_specs(value: object) -> dict[str, Any]:
    """Validate the flat, facetable specification object accepted by the admin UI."""
    if not isinstance(value, Mapping):
        raise ValueError("Product specifications must be a JSON object.")
    if len(value) > MAX_SPEC_FILTERS:
        raise ValueError(
            f"Product specifications may contain at most {MAX_SPEC_FILTERS} fields."
        )

    normalized: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        if not is_safe_spec_key(key):
            raise ValueError(
                "Specification names cannot be empty, start with '$', contain '.', "
                f"or exceed {MAX_SPEC_KEY_LENGTH} characters."
            )
        if isinstance(raw_value, float) and not isfinite(raw_value):
            raise ValueError("Specification numbers must be finite.")
        if isinstance(raw_value, bool | int | float):
            normalized[key] = raw_value
            continue
        if not isinstance(raw_value, str):
            raise ValueError("Specification values must be strings or numbers.")

        spec_value = raw_value.strip()
        if not spec_value:
            raise ValueError("Specification values cannot be empty.")
        if len(spec_value) > MAX_SPEC_VALUE_LENGTH:
            raise ValueError(
                "Specification values must be at most "
                f"{MAX_SPEC_VALUE_LENGTH} characters."
            )
        normalized[key] = spec_value

    return normalized


def checkout_customer(customer: CheckoutCustomer) -> dict[str, str]:
    normalized = {
        "customer_name": required_text(customer.get("name"), "Name", 100),
        "customer_email": required_text(customer.get("email"), "Email", 120),
        "shipping_address": required_text(
            customer.get("address"), "Shipping address", 255
        ),
        "city": required_text(customer.get("city"), "City", 100),
        "zip_code": required_text(customer.get("zip"), "ZIP / postal code", 20),
    }
    if not EMAIL_PATTERN.fullmatch(normalized["customer_email"]):
        raise ValueError("Enter a valid email address.")
    return normalized


def session_cart(value: object) -> list[CartItem]:
    """Recover the valid subset of a stale or malformed server-side cart."""
    if not isinstance(value, list):
        return []

    normalized: list[CartItem] = []
    seen_product_ids: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, Mapping):
            continue

        product_id = str(raw_item.get("product_id") or "").strip()
        if not product_id or product_id in seen_product_ids:
            continue

        try:
            quantity = positive_int(raw_item.get("qty"), "Cart quantity")
            price = money_value(raw_item.get("price"))
        except ValueError:
            continue

        specs = raw_item.get("specs")
        name = str(raw_item.get("name") or "").strip() or "Unknown Product"
        image = (
            str(raw_item.get("image") or "").strip() or "https://placehold.co/600x400"
        )
        normalized.append(
            CartItem(
                product_id=product_id,
                name=name[:200],
                price=price,
                image=image[:500],
                specs=dict(specs) if isinstance(specs, Mapping) else {},
                qty=quantity,
            )
        )
        seen_product_ids.add(product_id)

    return normalized


def safe_redirect_target(target: str | None, host_url: str, fallback: str) -> str:
    """Allow redirects only to the current request host."""
    if not target:
        return fallback

    host = urlsplit(host_url)
    candidate = urlsplit(urljoin(host_url, target))
    if candidate.scheme in {"http", "https"} and candidate.netloc == host.netloc:
        return candidate.geturl()
    return fallback
