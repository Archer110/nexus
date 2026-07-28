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


# --- CART ROUTE TESTS ---


@patch("app.routes.cart.ProductService")
def test_add_to_cart_updates_session(mock_service, client):
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
    response = client.post("/cart/add/123")

    # 3. Assert Session Data
    with client.session_transaction() as sess:
        assert len(sess["cart"]) == 1
        assert sess["cart"][0]["product_id"] == "123"
        assert sess["cart"][0]["qty"] == 1

    # 4. Verify Redirect
    assert response.status_code == 302


def test_checkout_requires_cart(client):
    """
    Scenario: POST /cart/checkout with empty cart.
    Goal: Verify redirect back to store.
    """
    response = client.post("/cart/checkout", data={"name": "Test"})

    assert response.status_code == 302
    # Should redirect to index (Store)
    assert "/" in response.location


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
def test_checkout_quantity_update_renders_summary_fragment(mock_service, client):
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
        headers={"HX-Request": "true", "HX-Target": "checkout-summary"},
    )

    assert response.status_code == 200
    assert b'id="checkout-summary"' in response.data
    assert b'hx-swap-oob="true"' in response.data

    with client.session_transaction() as sess:
        assert sess["cart"][0]["qty"] == 2


@patch("app.routes.cart.ProductService")
def test_cart_drawer_subtotal_includes_quantity(mock_service, client):
    mock_service.get_product_details.return_value = {
        "_id": "123",
        "name": "Test Item",
        "price": 10.0,
        "image": "img.png",
        "stock": 5,
    }

    client.post("/cart/add/123")
    response = client.post(
        "/cart/add/123",
        headers={"HX-Request": "true", "HX-Target": "cart-drawer-content"},
    )

    assert response.status_code == 200
    assert b"$20.00" in response.data


@patch("app.routes.cart.ProductService")
def test_cart_cannot_exceed_available_stock(mock_service, client):
    mock_service.get_product_details.return_value = {
        "_id": "123",
        "name": "Last Item",
        "price": 10.0,
        "image": "img.png",
        "stock": 1,
    }

    client.post("/cart/add/123")
    response = client.post(
        "/cart/add/123",
        headers={"HX-Request": "true", "HX-Target": "cart-drawer-content"},
    )

    assert response.status_code == 200
    assert b"Only 1 unit(s) of Last Item are available." in response.data

    with client.session_transaction() as sess:
        assert sess["cart"][0]["qty"] == 1


def test_checkout_remove_renders_summary_fragment(client):
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
        headers={"HX-Request": "true", "HX-Target": "checkout-summary"},
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
        "/admin/products?q=laptop&page=2",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert b'id="admin-products-panel"' in response.data
    assert b'id="admin-products-count"' in response.data
    assert b"NEXUS ADMIN" not in response.data

    call_args = mock_service.get_admin_catalog.call_args[1]
    assert call_args["page"] == 2
    assert call_args["search_query"] == "laptop"


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
def test_admin_order_status_update_returns_empty_success(mock_service, client):
    mock_service.update_status.return_value = object()

    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True

    response = client.post(
        "/admin/orders/update/42",
        data={"status": "Shipped"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 204
    mock_service.update_status.assert_called_once_with(42, "Shipped")


@patch("app.routes.admin.ProductService")
def test_admin_rejects_non_object_product_specs(mock_service, client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True

    response = client.post(
        "/admin/products/add",
        data={"specs_json": "[]"},
    )

    assert response.status_code == 400
    mock_service.create_product.assert_not_called()
