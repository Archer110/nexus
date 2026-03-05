# tests/test_services.py
import pytest
from unittest.mock import MagicMock, ANY
import app
from app.services.order_service import OrderService
from app.services.product_service import ProductService

# --- PRODUCT SERVICE TESTS (The "Hybrid" Logic) ---

def test_create_product_success(mocker, mock_mongo, mock_db):
    """
    Scenario: Creating a product successfully writes to Mongo AND SQL.
    """
    # 1. Setup
    data = {"name": "Test Item", "price": 100.0, "category": "Test"}
    stock = 50

    # Mock Mongo Insert
    mock_mongo.products.insert_one.return_value.inserted_id = "mongo_id_123"

    # 2. Execute
    result = ProductService.create_product(data, stock)

    # 3. Assert
    # Verify Mongo was called
    mock_mongo.products.insert_one.assert_called_once()
    # Verify SQL was called (Inventory creation)
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    
    assert result["_id"] == "mongo_id_123"
    assert result["stock"] == 50

def test_create_product_rollback_on_sql_error(mocker, mock_mongo, mock_db):
    """
    Scenario: SQL fails (e.g., DB connection lost). 
    Goal: Verify we delete the orphaned Mongo document (Rollback).
    """
    # 1. Setup
    mock_mongo.products.insert_one.return_value.inserted_id = "mongo_id_123"
    
    # Simulate SQL Error
    mock_db.commit.side_effect = Exception("SQL Connection Dead")

    # 2. Execute & Assert
    with pytest.raises(Exception):
        ProductService.create_product({}, 10)

    # 3. Verify Rollback
    mock_db.session.rollback.assert_called_once()
    # CRITICAL: Verify we cleaned up the Mongo document
    mock_mongo.products.delete_one.assert_called_with({"_id": "mongo_id_123"})

def test_get_catalog_merges_data(mocker, mock_mongo):
    """
    Scenario: The 'Hybrid Join'. 
    Goal: Verify Mongo docs are merged with SQL inventory.
    """
    # 1. Mock Mongo Return
    fake_product = {"_id": "prod_1", "name": "Laptop"}
    
    # Mock chain: find().sort().skip().limit()
    mock_cursor = MagicMock()
    mock_cursor.skip.return_value.limit.return_value = [fake_product]
    mock_mongo.products.find.return_value.sort.return_value = mock_cursor

    # 2. Mock SQL Return (Inventory)
    # Patch the 'Inventory.query' inside the service module
    mock_inventory_query = mocker.patch("app.services.product_service.Inventory.query")
    
    fake_inv = MagicMock()
    fake_inv.product_id = "prod_1"
    fake_inv.stock = 99

    with app.app_context():
        mock_inventory_query.filter.return_value.all.return_value = [fake_inv]

        # 3. Execute
        products, count = ProductService.get_catalog(page=1)

    # 4. Assert
    assert len(products) == 1
    assert products[0]["stock"] == 99  # <--- The Merge happened!
    assert products[0]["_id"] == "prod_1"

def test_update_product_routes_correctly(mocker, mock_mongo, mock_db):
    """
    Scenario: Update 'stock' (SQL) vs 'price' (Mongo).
    """
    # Test A: Stock Update (SQL)
    mock_inventory = MagicMock()
    mocker.patch("app.services.product_service.Inventory.query.get", return_value=mock_inventory)
    
    ProductService.update_product("prod_1", "stock", 20)
    assert mock_inventory.stock == 20
    mock_db.commit.assert_called()

    # Test B: Price Update (Mongo)
    ProductService.update_product("prod_1", "price", 199.99)
    mock_mongo.products.update_one.assert_called_with(
        {"_id": ANY}, {"$set": {"price": 199.99}}
    )

# --- ORDER SERVICE TESTS (The "Strict" Logic) ---

def test_create_order_happy_path(mocker, mock_db):
    """
    Scenario: Standard Checkout.
    """
    # 1. Setup
    cart = [{"product_id": "prod_1", "qty": 2, "price": 100}]
    customer = {"name": "Alice", "email": "alice@test.com"}

    # Mock Inventory (Stock = 10)
    mock_inv = MagicMock(stock=10)
    mock_query = mocker.patch("app.services.order_service.Inventory.query")
    mock_query.with_for_update.return_value.filter_by.return_value.first.return_value = mock_inv

    # 2. Execute
    order = OrderService.create_order(customer, cart)

    # 3. Assert
    assert order is not None
    assert mock_inv.stock == 8  # Deducted 2
    mock_db.add.assert_called() # Order added
    mock_db.commit.assert_called() # Transaction committed

def test_create_order_out_of_stock(mocker, mock_db):
    """
    Scenario: Race Condition / Insufficient Stock.
    """
    cart = [{"product_id": "prod_1", "qty": 5, "price": 100, "name": "Test Product"}]
    
    # Mock Inventory (Stock = 1) - Too low!
    mock_inv = MagicMock(stock=1)
    mock_query = mocker.patch("app.services.order_service.Inventory.query")
    mock_query.with_for_update.return_value.filter_by.return_value.first.return_value = mock_inv

    # Execute & Expect Error
    with pytest.raises(ValueError, match="is out of stock"):
        OrderService.create_order({}, cart)

    # Assert Safety
    mock_db.commit.assert_not_called() # Ensure no partial order saved
    mock_db.rollback.assert_called()   # Ensure transaction rolled back

def test_get_order_details_merges_mongo(mocker, mock_mongo):
    """
    Scenario: Viewing an Order Receipt (Reverse Hybrid Join).
    Goal: Verify we fetch Product Names from Mongo using IDs from SQL.
    """
    # 1. Mock SQL Order
    mock_order = MagicMock()
    mock_order.to_dict.return_value = {
        "id": 1, 
        "items": [{"product_id": "prod_1", "qty": 1, "price": 50}]
    }
    # Mock items relationship for ID extraction
    mock_item_obj = MagicMock()
    mock_item_obj.product_id_str = "prod_1"
    mock_order.items = [mock_item_obj]

    mocker.patch("app.services.order_service.Order.query.get", return_value=mock_order)

    # 2. Mock Mongo Product Lookup
    # The service queries Mongo for these IDs
    mock_mongo.products.find.return_value = [
        {"_id": "prod_1", "name": "Super Widget", "image": "img.jpg"}
    ]

    # 3. Execute
    result = OrderService.get_order_with_details(1)

    # 4. Assert
    # The SQL data ("items") should now have Mongo data ("name") attached
    item = result["items"][0]
    assert item["name"] == "Super Widget"
    assert item["image"] == "img.jpg"