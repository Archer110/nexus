from unittest.mock import patch

import pytest

from tests.helpers import get_csrf_token


def _session_id(client) -> str:
    cookie = client.get_cookie("session")
    if cookie is None:
        raise AssertionError("The application did not set a session cookie.")
    return cookie.value


def _login(client) -> tuple[str, str]:
    csrf_token = get_csrf_token(client)
    previous_session_id = _session_id(client)
    response = client.post(
        "/admin/login",
        data={
            "username": "test-admin",
            "password": "test-admin-password",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code == 302
    return previous_session_id, csrf_token


def test_admin_login_uses_password_hash_and_rotates_redis_session(app, client):
    old_session_id, _ = _login(client)
    new_session_id = _session_id(client)

    assert new_session_id != old_session_id
    with client.session_transaction() as session:
        assert session["admin_logged_in"] is True

    redis_client = app.config["SESSION_REDIS"]
    prefix = app.config["SESSION_KEY_PREFIX"]
    assert redis_client.exists(f"{prefix}{old_session_id}") == 0
    assert redis_client.exists(f"{prefix}{new_session_id}") == 1


def test_removed_hard_coded_credentials_no_longer_authenticate(client):
    csrf_token = get_csrf_token(client)

    response = client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": "secret",
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 200
    assert b"Invalid credentials" in response.data
    with client.session_transaction() as session:
        assert "admin_logged_in" not in session


def test_logout_is_post_only_and_rotates_the_authenticated_session(app, client):
    _, csrf_token = _login(client)
    authenticated_session_id = _session_id(client)

    assert client.get("/admin/logout").status_code == 405

    response = client.post(
        "/admin/logout",
        data={"csrf_token": csrf_token},
    )

    assert response.status_code == 302
    logged_out_session_id = _session_id(client)
    assert logged_out_session_id != authenticated_session_id
    with client.session_transaction() as session:
        assert "admin_logged_in" not in session

    redis_client = app.config["SESSION_REDIS"]
    prefix = app.config["SESSION_KEY_PREFIX"]
    assert redis_client.exists(f"{prefix}{authenticated_session_id}") == 0


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/admin/login"),
        ("post", "/admin/logout"),
        ("post", "/admin/products/add"),
        (
            "post",
            "/admin/products/update/64b64b64b64b64b64b64b64b?field=price",
        ),
        ("delete", "/admin/products/delete/64b64b64b64b64b64b64b64b"),
        ("post", "/admin/orders/update/1"),
        ("post", "/cart/add/64b64b64b64b64b64b64b64b"),
        ("post", "/cart/update/64b64b64b64b64b64b64b64b/increase"),
        ("delete", "/cart/remove/64b64b64b64b64b64b64b64b"),
        ("post", "/cart/checkout"),
    ],
)
def test_every_state_changing_route_rejects_a_missing_csrf_token(client, method, path):
    response = getattr(client, method)(path)

    assert response.status_code == 400
    assert b"CSRF token is missing" in response.data


@patch("app.routes.store.ProductService")
def test_storefront_configures_htmx_to_send_the_csrf_header(mock_service, client):
    mock_service.get_catalog.return_value = ([], 0)
    mock_service.get_facets.return_value = ([], {})

    response = client.get("/")
    csrf_script = client.get("/static/js/csrf.js")

    assert response.status_code == 200
    assert b'<meta name="csrf-token"' in response.data
    assert b"/static/js/csrf.js" in response.data
    assert b'headers["X-CSRFToken"]' in csrf_script.data


@patch("app.routes.cart.ProductService")
def test_htmx_csrf_header_reaches_the_route(mock_service, client):
    csrf_token = get_csrf_token(client)
    mock_service.get_product_details.return_value = None

    response = client.post(
        "/cart/add/64b64b64b64b64b64b64b64b",
        headers={
            "HX-Request": "true",
            "X-CSRFToken": csrf_token,
        },
    )

    assert response.status_code == 400
    mock_service.get_product_details.assert_called_once()


def test_cart_removal_no_longer_accepts_get(client):
    response = client.get("/cart/remove/64b64b64b64b64b64b64b64b")

    assert response.status_code == 405


def test_expected_checkout_validation_returns_400_and_preserves_cart(
    client, csrf_headers
):
    cart = [
        {
            "product_id": "64b64b64b64b64b64b64b64b",
            "name": "Test Product",
            "price": "10.00",
            "image": "product.png",
            "specs": {},
            "qty": 1,
        }
    ]
    with client.session_transaction() as session:
        session["cart"] = cart

    response = client.post(
        "/cart/checkout",
        data={
            "name": "Alice",
            "email": "invalid",
            "address": "123 Main St",
            "city": "Tehran",
            "zip": "12345",
        },
        headers=csrf_headers,
    )

    assert response.status_code == 400
    assert b"Enter a valid email address." in response.data
    assert b'name="csrf_token"' in response.data
    with client.session_transaction() as session:
        assert session["cart"] == cart


@patch("app.routes.cart.OrderService.create_order")
def test_unexpected_checkout_failure_is_logged_and_returns_500(
    create_order, client, csrf_headers, mocker
):
    create_order.side_effect = RuntimeError("database unavailable")
    logger = mocker.patch.object(client.application.logger, "exception")
    with client.session_transaction() as session:
        session["cart"] = [
            {
                "product_id": "64b64b64b64b64b64b64b64b",
                "name": "Test Product",
                "price": "10.00",
                "image": "product.png",
                "specs": {},
                "qty": 1,
            }
        ]

    response = client.post(
        "/cart/checkout",
        data={
            "name": "Alice",
            "email": "alice@example.com",
            "address": "123 Main St",
            "city": "Tehran",
            "zip": "12345",
        },
        headers=csrf_headers,
    )

    assert response.status_code == 500
    assert b"An error occurred processing your order" in response.data
    logger.assert_called_once_with("Unexpected checkout failure.")
    with client.session_transaction() as session:
        assert len(session["cart"]) == 1
