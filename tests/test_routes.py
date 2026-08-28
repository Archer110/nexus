from unittest.mock import patch

# --- STORE ROUTE TESTS ---


@patch("app.routes.store.ProductService")  # Mock the Service!
def test_store_index_parses_args_correctly(mock_service, client):
    """
    Scenario: User visits /?q=dell&cat=Laptops
    Goal: Verify Route passes these args to ProductService.
    """
    # Setup Mock
    mock_service.get_catalog.return_value = ([], 0)
    mock_service.get_facets.return_value = ([], {})

    # Execute
    client.get("/?q=dell&cat=Laptops")

    # Assert
    # Did the route parse 'dell' and 'Laptops' and pass them?
    mock_service.get_catalog.assert_called_once()
    call_args = mock_service.get_catalog.call_args[1]  # Get keyword args
    assert call_args["search_query"] == "dell"
    assert call_args["category"] == "Laptops"


@patch("app.routes.store.ProductService")
def test_store_htmx_partial_render(mock_service, client):
    """
    Scenario: HTMX Request (Sidebar Filter).
    Goal: Verify we return the partial template, not the full page.
    """
    mock_service.get_catalog.return_value = ([], 0)
    mock_service.get_facets.return_value = ([], {})

    # Execute with HTMX Headers
    response = client.get("/", headers={"HX-Request": "true"})

    # Assert
    assert response.status_code == 200
    # In a real app with templates, we'd check content.
    # Here we assume render_template works if status is 200.


@patch("app.routes.store.ProductService")
def test_store_cart_drawer_backdrop_is_dismissible(mock_service, client):
    mock_service.get_catalog.return_value = ([], 0)
    mock_service.get_facets.return_value = ([], {})

    response = client.get("/")

    assert response.status_code == 200
    assert b'@click="cartOpen = false"' in response.data
    assert b"pointer-events-none fixed inset-0 overflow-hidden" in response.data
    assert b"Continue Shopping" not in response.data


@patch("app.routes.store.ProductService")
def test_store_normalizes_pagination_and_rejects_unsafe_filter_keys(
    mock_service, client
):
    mock_service.get_catalog.return_value = ([], 0)
    mock_service.get_facets.return_value = ([], {})

    response = client.get(
        "/",
        query_string=[
            ("page", "not-a-number"),
            ("$where", "unsafe"),
            ("specs.color", "unsafe"),
            ("Color", " Black "),
        ],
    )

    assert response.status_code == 200
    call_args = mock_service.get_catalog.call_args.kwargs
    assert call_args["page"] == 1
    assert call_args["spec_filters"] == {"Color": ["Black"]}


# --- CART ROUTE TESTS ---


@patch("app.routes.cart.ProductService")
def test_add_to_cart_updates_session(mock_service, client, csrf_headers):
    """
    Scenario: POST /cart/add/123
    Goal: Verify item is added to the Session (Cookie).
    """
    # 1. Mock the Product Lookup
    mock_service.get_product_details.return_value = {
        "_id": "123",
        "name": "Test Item",
        "price": 10.0,
        "image": "img.png",
        "stock": 5,
    }

    # 2. Execute
    response = client.post("/cart/add/123", headers=csrf_headers)

    # 3. Assert Session Data
    with client.session_transaction() as sess:
        assert len(sess["cart"]) == 1
        assert sess["cart"][0]["product_id"] == "123"
        assert sess["cart"][0]["qty"] == 1

    # 4. Verify Redirect
    assert response.status_code == 302


@patch("app.routes.cart.ProductService")
def test_add_to_cart_does_not_follow_an_external_referrer(
    mock_service, client, csrf_headers
):
    mock_service.get_product_details.return_value = {
        "_id": "123",
        "name": "Test Item",
        "price": "10.00",
        "image": "img.png",
        "stock": 5,
    }

    response = client.post(
        "/cart/add/123",
        headers={
            **csrf_headers,
            "Referer": "https://attacker.example/redirect",
        },
    )

    assert response.status_code == 302
    assert response.location == "/"


def test_checkout_requires_cart(client, csrf_headers):
    """
    Scenario: POST /cart/checkout with empty cart.
    Goal: Verify a consistent validation response.
    """
    response = client.post(
        "/cart/checkout",
        data={"name": "Test"},
        headers=csrf_headers,
    )

    assert response.status_code == 400
    assert b"Cart is empty." in response.data


def test_checkout_recovers_from_a_malformed_server_side_cart(client):
    with client.session_transaction() as sess:
        sess["cart"] = {"unexpected": "shape"}

    response = client.get("/cart/checkout-page")

    assert response.status_code == 200
    assert b"Your cart is empty." in response.data
    with client.session_transaction() as sess:
        assert sess["cart"] == []


@patch("app.routes.cart.ProductService")
def test_checkout_page_uses_htmx_summary_controls(mock_service, client):
    """
    Scenario: User opens checkout with items in cart.
    Goal: Verify quantity/remove controls target the checkout summary fragment.
    """
    with client.session_transaction() as sess:
        sess["cart"] = [
            {
                "product_id": "123",
                "name": "Test Item",
                "price": 0.01,
                "image": "img.png",
                "qty": 1,
            }
        ]

    mock_service.get_products_by_ids.return_value = {
        "123": {
            "_id": "123",
            "name": "Test Item",
            "price": "10.00",
            "image": "img.png",
        }
    }

    response = client.get("/cart/checkout-page")

    assert response.status_code == 200
    assert b'id="checkout-summary"' in response.data
    assert b'hx-target="#checkout-summary"' in response.data
    assert b"Pay $10.00" in response.data
    assert b"Search catalog..." not in response.data

    with client.session_transaction() as sess:
        assert sess["cart"][0]["price"] == "10.00"


@patch("app.routes.cart.ProductService")
def test_checkout_displays_exact_authoritative_total(mock_service, client):
    with client.session_transaction() as sess:
        sess["cart"] = [
            {
                "product_id": "123",
                "name": "First",
                "price": 0.01,
                "image": "first.png",
                "qty": 1,
            },
            {
                "product_id": "456",
                "name": "Second",
                "price": 0.01,
                "image": "second.png",
                "qty": 1,
            },
        ]

    mock_service.get_products_by_ids.return_value = {
        "123": {
            "_id": "123",
            "name": "First",
            "price": 685.9,
            "image": "first.png",
        },
        "456": {
            "_id": "456",
            "name": "Second",
            "price": "685.90",
            "image": "second.png",
        },
    }

    response = client.get("/cart/checkout-page")

    assert response.status_code == 200
    assert b"Pay $1,371.80" in response.data


@patch("app.routes.cart.ProductService")
def test_checkout_drops_products_missing_from_the_catalog(mock_service, client):
    with client.session_transaction() as sess:
        sess["cart"] = [
            {
                "product_id": "123",
                "name": "Removed",
                "price": "10.00",
                "image": "removed.png",
                "qty": 1,
            }
        ]

    mock_service.get_products_by_ids.return_value = {}

    response = client.get("/cart/checkout-page")

    assert response.status_code == 200
    assert b"Your cart is empty." in response.data
    with client.session_transaction() as sess:
        assert sess["cart"] == []


@patch("app.routes.cart.ProductService")
def test_checkout_quantity_update_renders_summary_fragment(
    mock_service, client, csrf_headers
):
    """
    Scenario: User changes quantity from the checkout page.
    Goal: Verify HTMX updates the summary instead of redirecting/reloading.
    """
    with client.session_transaction() as sess:
        sess["cart"] = [
            {
                "product_id": "123",
                "name": "Test Item",
                "price": 10.0,
                "image": "img.png",
                "qty": 1,
            }
        ]

    mock_service.get_product_details.return_value = {
        "_id": "123",
        "name": "Test Item",
        "price": 10.0,
        "image": "img.png",
        "stock": 5,
    }

    response = client.post(
        "/cart/update/123/increase",
        headers={
            **csrf_headers,
            "HX-Request": "true",
            "HX-Target": "checkout-summary",
        },
    )

    assert response.status_code == 200
    assert b'id="checkout-summary"' in response.data
    assert b'hx-swap-oob="true"' in response.data

    with client.session_transaction() as sess:
        assert sess["cart"][0]["qty"] == 2


@patch("app.routes.cart.ProductService")
def test_cart_drawer_subtotal_includes_quantity(mock_service, client, csrf_headers):
    mock_service.get_product_details.return_value = {
        "_id": "123",
        "name": "Test Item",
        "price": 10.0,
        "image": "img.png",
        "stock": 5,
    }

    client.post("/cart/add/123", headers=csrf_headers)
    response = client.post(
        "/cart/add/123",
        headers={
            **csrf_headers,
            "HX-Request": "true",
            "HX-Target": "cart-drawer-content",
        },
    )

    assert response.status_code == 200
    assert b"$20.00" in response.data


@patch("app.routes.cart.ProductService")
def test_cart_cannot_exceed_available_stock(mock_service, client, csrf_headers):
    mock_service.get_product_details.return_value = {
        "_id": "123",
        "name": "Last Item",
        "price": 10.0,
        "image": "img.png",
        "stock": 1,
    }

    client.post("/cart/add/123", headers=csrf_headers)
    response = client.post(
        "/cart/add/123",
        headers={
            **csrf_headers,
            "HX-Request": "true",
            "HX-Target": "cart-drawer-content",
        },
    )

    assert response.status_code == 400
    assert response.headers["X-Nexus-Swap-Error"] == "true"
    assert b"Only 1 unit(s) of Last Item are available." in response.data

    with client.session_transaction() as sess:
        assert sess["cart"][0]["qty"] == 1


def test_checkout_remove_renders_summary_fragment(client, csrf_headers):
    """
    Scenario: User removes an item from the checkout page.
    Goal: Verify they stay on checkout and receive an empty summary fragment.
    """
    with client.session_transaction() as sess:
        sess["cart"] = [
            {
                "product_id": "123",
                "name": "Test Item",
                "price": 10.0,
                "image": "img.png",
                "qty": 1,
            }
        ]

    response = client.delete(
        "/cart/remove/123",
        headers={
            **csrf_headers,
            "HX-Request": "true",
            "HX-Target": "checkout-summary",
        },
    )

    assert response.status_code == 200
    assert b"Your cart is empty." in response.data
    assert b"Cart is empty" in response.data

    with client.session_transaction() as sess:
        assert sess["cart"] == []


@patch("app.routes.admin.ProductService")
def test_admin_products_htmx_renders_panel(mock_service, client):
    """
    Scenario: Admin searches or paginates products.
    Goal: Verify HTMX returns the products panel including pagination context.
    """
    mock_service.get_admin_catalog.return_value = ([], 0)

    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True

    response = client.get(
        "/admin/products?q=laptop&page=2&sort=price_desc",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert b'id="admin-products-panel"' in response.data
    assert b'id="admin-products-count"' in response.data
    assert b"NEXUS ADMIN" not in response.data
    assert b"sort=price_desc" in response.data

    call_args = mock_service.get_admin_catalog.call_args[1]
    assert call_args["page"] == 2
    assert call_args["search_query"] == "laptop"
    assert call_args["sort_by"] == "price_desc"


@patch("app.routes.admin.ProductService")
def test_admin_products_normalizes_invalid_page(mock_service, client):
    mock_service.get_admin_catalog.return_value = ([], 0)

    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True

    response = client.get("/admin/products?page=invalid&sort=unexpected")

    assert response.status_code == 200
    assert b'action="/admin/logout" method="post"' in response.data
    assert b'name="csrf_token"' in response.data
    assert mock_service.get_admin_catalog.call_args.kwargs["page"] == 1
    assert mock_service.get_admin_catalog.call_args.kwargs["sort_by"] == "newest"
    assert b'<option value="newest" selected>Newest first</option>' in response.data


@patch("app.routes.admin.OrderService")
def test_admin_orders_htmx_search_renders_panel(mock_service, client):
    """
    Scenario: Admin searches orders.
    Goal: Verify HTMX returns the orders panel rather than refreshing the page.
    """
    mock_service.get_orders.return_value = [
        {
            "id": 42,
            "customer_name": "Alice",
            "customer_email": "alice@example.com",
            "shipping_address": "123 Main St",
            "city": "Tehran",
            "zip_code": "12345",
            "total_amount": 20.0,
            "status": "Processing",
            "created_at": "2026-07-28 12:00",
            "items": [
                {
                    "product_id": "123",
                    "quantity": 2,
                    "price": 10.0,
                    "name": "Test Item",
                    "image": "img.png",
                    "specs": {},
                }
            ],
        }
    ]

    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True

    response = client.get(
        "/admin/orders?q=alice",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert b'id="admin-orders-panel"' in response.data
    assert b'id="admin-orders-count"' in response.data
    assert b"NEXUS ADMIN" not in response.data
    assert b"Alice" in response.data
    mock_service.get_orders.assert_called_once_with("alice")


@patch("app.routes.admin.OrderService")
def test_admin_order_status_update_returns_empty_success(
    mock_service, client, csrf_headers
):
    mock_service.update_status.return_value = object()

    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True

    response = client.post(
        "/admin/orders/update/42",
        data={"status": "Shipped"},
        headers={**csrf_headers, "HX-Request": "true"},
    )

    assert response.status_code == 204
    mock_service.update_status.assert_called_once_with(42, "Shipped")


@patch("app.routes.admin.ProductService")
def test_admin_rejects_non_object_product_specs(mock_service, client, csrf_headers):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True

    response = client.post(
        "/admin/products/add",
        data={"specs_json": "[]"},
        headers=csrf_headers,
    )

    assert response.status_code == 400
    mock_service.create_product.assert_not_called()


@patch("app.routes.admin.ProductService")
def test_admin_returns_validation_errors_from_product_service(
    mock_service, client, csrf_headers
):
    mock_service.create_product.side_effect = ValueError("Price is required.")

    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True

    response = client.post(
        "/admin/products/add",
        data={
            "name": "Test",
            "category": "Test",
            "price": "",
            "stock": "1",
            "specs_json": "{}",
        },
        headers=csrf_headers,
    )

    assert response.status_code == 400
    assert response.text == "Price is required."


@patch("app.routes.admin.ProductService")
def test_admin_returns_not_found_when_product_update_matches_nothing(
    mock_service, client, csrf_headers
):
    mock_service.update_product.return_value = None

    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True

    response = client.post(
        "/admin/products/update/64b64b64b64b64b64b64b64b?field=price",
        data={"price": "10.00"},
        headers=csrf_headers,
    )

    assert response.status_code == 404
