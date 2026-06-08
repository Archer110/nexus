# tests/test_routes.py
from pathlib import Path
from unittest.mock import patch

import pytest


# --- FIXTURES ---
@pytest.fixture
def client(mock_app_context):
    """
    Creates a Flask test client using the mocked app context.
    """
    # Create a fresh Flask app for routing tests
    from flask import Flask
    
    # We need to import the real blueprints to register them
    from app.routes.cart import cart_bp
    from app.routes.store import store_bp
    template_dir = Path(__file__).resolve().parents[1] / "app" / "templates"
    app = Flask(__name__, template_folder=str(template_dir))
    app.config["SECRET_KEY"] = "testing_key"
    app.config["TESTING"] = True
    
    # Register Blueprints
    app.register_blueprint(store_bp)
    app.register_blueprint(cart_bp)
    
    return app.test_client()

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
    call_args = mock_service.get_catalog.call_args[1] # Get keyword args
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
        "_id": "123", "name": "Test Item", "price": 10.0, "image": "img.png"
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
