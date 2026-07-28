import pytest

from app.validation import (
    checkout_customer,
    page_number,
    product_specs,
    safe_redirect_target,
    session_cart,
    spec_filters,
)


def test_page_number_recovers_from_invalid_and_negative_values():
    assert page_number("invalid") == 1
    assert page_number("-5") == 1
    assert page_number("3") == 3


def test_spec_filters_exclude_unsafe_mongo_paths_and_empty_values():
    filters = spec_filters(
        {
            "$where": ["unsafe"],
            "nested.key": ["unsafe"],
            "Color": [" Black ", ""],
        }
    )

    assert filters == {"Color": ["Black"]}


def test_session_cart_keeps_only_normalized_unique_items():
    cart = session_cart(
        [
            {
                "product_id": "product-1",
                "name": " Product ",
                "price": 10.1,
                "image": "",
                "qty": "2",
            },
            {
                "product_id": "product-1",
                "name": "Duplicate",
                "price": "10.10",
                "qty": 1,
            },
            {"product_id": "bad-price", "price": "NaN", "qty": 1},
            {"product_id": "bad-quantity", "price": "1.00", "qty": 0},
            "not-an-item",
        ]
    )

    assert cart == [
        {
            "product_id": "product-1",
            "name": "Product",
            "price": "10.10",
            "image": "https://placehold.co/600x400",
            "specs": {},
            "qty": 2,
        }
    ]


def test_checkout_customer_enforces_database_lengths_and_email_shape():
    valid_customer = {
        "name": " Alice ",
        "email": "alice@example.com",
        "address": "123 Main St",
        "city": "Tehran",
        "zip": "12345",
    }

    assert checkout_customer(valid_customer)["customer_name"] == "Alice"

    with pytest.raises(ValueError, match="valid email"):
        checkout_customer({**valid_customer, "email": "not-an-email"})

    with pytest.raises(ValueError, match="at most 100"):
        checkout_customer({**valid_customer, "name": "a" * 101})


def test_product_specs_reject_mongo_path_keys_and_nested_values():
    with pytest.raises(ValueError, match="cannot be empty"):
        product_specs({"nested.key": "value"})

    with pytest.raises(ValueError, match="strings or numbers"):
        product_specs({"Color": {"name": "Black"}})


def test_safe_redirect_target_allows_only_the_current_host():
    fallback = "/"

    assert (
        safe_redirect_target(
            "http://localhost/product/1",
            "http://localhost/",
            fallback,
        )
        == "http://localhost/product/1"
    )
    assert (
        safe_redirect_target(
            "https://attacker.example/redirect",
            "http://localhost/",
            fallback,
        )
        == fallback
    )
