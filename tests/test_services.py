# tests/test_services.py
from decimal import Decimal
from unittest.mock import ANY, MagicMock

import pytest
from bson import ObjectId
from bson.decimal128 import Decimal128
from flask import Flask
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import sql_db
from app.models import Order, OrderItem
from app.services.order_service import OrderService
from app.services.product_service import ProductService

# --- PRODUCT SERVICE TESTS (The "Hybrid" Logic) ---


def test_create_product_success(mocker, mock_mongo, mock_db):
    """
    Scenario: Creating a product successfully writes to Mongo AND SQL.
    """
    # 1. Setup
    data = {"name": "Test Item", "price": "100.00", "category": "Test"}
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
    assert result["price"] == "100.00"
    assert result["stock"] == 50
    assert result["description"] == "Added via Admin"
    inserted_product = mock_mongo.products.insert_one.call_args.args[0]
    assert inserted_product["price"] == Decimal128("100.00")


def test_create_product_rollback_on_sql_error(mocker, mock_mongo, mock_db):
    """
    Scenario: SQL fails (e.g., DB connection lost).
    Goal: Verify we delete the orphaned Mongo document (Rollback).
    """
    # 1. Setup
    mock_mongo.products.insert_one.return_value.inserted_id = "mongo_id_123"

    # Simulate SQL Error
    mock_db.commit.side_effect = SQLAlchemyError("SQL Connection Dead")

    # 2. Execute & Assert
    with pytest.raises(SQLAlchemyError):
        ProductService.create_product({}, 10)

    # 3. Verify Rollback
    mock_db.rollback.assert_called_once()
    # CRITICAL: Verify we cleaned up the Mongo document
    mock_mongo.products.delete_one.assert_called_with({"_id": "mongo_id_123"})


def test_get_catalog_merges_data(mock_mongo, mock_db):
    """
    Scenario: The 'Hybrid Join'.
    Goal: Verify Mongo docs are merged with SQL inventory.
    """
    # 1. Mock Mongo Return
    fake_product = {
        "_id": "prod_1",
        "name": "Laptop",
        "price": Decimal128("1499.90"),
    }

    # Mock chain: find().sort().skip().limit()
    mock_cursor = MagicMock()
    mock_cursor.skip.return_value.limit.return_value = [fake_product]
    mock_mongo.products.find.return_value.sort.return_value = mock_cursor
    mock_mongo.products.count_documents.return_value = 1

    fake_inv = MagicMock()
    fake_inv.product_id = "prod_1"
    fake_inv.stock = 99

    mock_db.scalars.return_value.all.return_value = [fake_inv]
    products, count = ProductService.get_catalog(page=1, per_page=9)

    # 4. Assert
    assert len(products) == 1
    assert products[0]["stock"] == 99  # <--- The Merge happened!
    assert products[0]["_id"] == "prod_1"
    assert products[0]["price"] == "1499.90"


def test_get_products_by_ids_normalizes_current_and_legacy_prices(mock_mongo):
    first_id = "64b64b64b64b64b64b64b64b"
    second_id = "64b64b64b64b64b64b64b64c"
    mock_mongo.products.find.return_value = [
        {
            "_id": ObjectId(first_id),
            "name": "Current",
            "price": Decimal128("19.90"),
        },
        {
            "_id": ObjectId(second_id),
            "name": "Legacy",
            "price": 10.1,
        },
    ]

    products = ProductService.get_products_by_ids([first_id, second_id])

    assert products[first_id]["price"] == "19.90"
    assert products[second_id]["price"] == "10.10"
    query = mock_mongo.products.find.call_args.args[0]
    assert set(query["_id"]["$in"]) == {ObjectId(first_id), ObjectId(second_id)}


def test_update_product_routes_correctly(mocker, mock_mongo, mock_db):
    """
    Scenario: Update 'stock' (SQL) vs 'price' (Mongo).
    """
    product_id = "64b64b64b64b64b64b64b64b"

    test_app = Flask(__name__)
    test_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    test_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    sql_db.init_app(test_app)

    with test_app.app_context():
        # Test A: Stock Update (SQL)
        mock_inventory = MagicMock(stock=10)
        mock_db.get.return_value = mock_inventory
        updated_stock = ProductService.update_product(product_id, "stock", 20)

        assert updated_stock == 20
        mock_db.commit.assert_called()

        # Test B: Price Update (Mongo)
        updated_price = ProductService.update_product(product_id, "price", "199.99")
        mock_mongo.products.update_one.assert_called_with(
            {"_id": ANY}, {"$set": {"price": Decimal128("199.99")}}
        )
        assert updated_price == "199.99"


# --- ORDER SERVICE TESTS (The "Strict" Logic) ---


def test_create_order_happy_path(mocker, mock_db):
    """
    Scenario: Standard Checkout.
    """
    # 1. Setup
    cart = [
        {
            "product_id": "prod_1",
            "name": "Untrusted Session Name",
            "image": "untrusted.png",
            "specs": {"color": "Untrusted"},
            "qty": 2,
            "price": "0.01",
        }
    ]
    customer = {
        "name": "Alice",
        "email": "alice@test.com",
        "address": "123 Main St",
        "city": "Tehran",
        "zip": "12345",
    }

    # Mock Inventory (Stock = 10)
    mock_inv = MagicMock(stock=10)
    mock_inv.product_id = "prod_1"
    mock_db.scalars.return_value.all.return_value = [mock_inv]
    catalog = mocker.patch(
        "app.services.order_service.ProductService.get_products_by_ids"
    )
    catalog.return_value = {
        "prod_1": {
            "_id": "prod_1",
            "name": "Test Product",
            "image": "product.png",
            "specs": {"color": "Black"},
            "price": "100.00",
        }
    }

    # 2. Execute
    order = OrderService.create_order(customer, cart)

    # 3. Assert
    assert order is not None
    assert mock_inv.stock == 8  # Deducted 2
    assert order.total_amount == Decimal("200.00")
    assert order.items[0].product_name == "Test Product"
    assert order.items[0].product_specs == {"color": "Black"}
    mock_db.add.assert_called()
    mock_db.commit.assert_called()


def test_create_order_out_of_stock(mocker, mock_db):
    """
    Scenario: Race Condition / Insufficient Stock.
    """
    cart = [{"product_id": "prod_1", "qty": 5, "price": 100, "name": "Test Product"}]
    customer = {
        "name": "Alice",
        "email": "alice@test.com",
        "address": "123 Main St",
        "city": "Tehran",
        "zip": "12345",
    }

    # Mock Inventory (Stock = 1) - Too low!
    mock_inv = MagicMock(stock=1)
    mock_inv.product_id = "prod_1"
    mock_db.scalars.return_value.all.return_value = [mock_inv]
    catalog = mocker.patch(
        "app.services.order_service.ProductService.get_products_by_ids"
    )
    catalog.return_value = {
        "prod_1": {
            "_id": "prod_1",
            "name": "Test Product",
            "price": "100.00",
        }
    }

    # Execute & Expect Error
    with pytest.raises(ValueError, match="is out of stock"):
        OrderService.create_order(customer, cart)

    # Assert Safety
    mock_db.commit.assert_not_called()  # Ensure no partial order saved
    mock_db.rollback.assert_called()  # Ensure transaction rolled back


def test_get_order_details_uses_purchase_snapshot():
    """
    Scenario: Viewing an Order Receipt (Reverse Hybrid Join).
    Goal: Verify we fetch Product Names from Mongo using IDs from SQL.
    """
    test_app = Flask(__name__)
    test_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    test_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    sql_db.init_app(test_app)

    with test_app.app_context():
        sql_db.create_all()

        order = Order(
            customer_name="Alice",
            customer_email="alice@test.com",
            shipping_address="123 Main St",
            city="New York",
            zip_code="10001",
            total_amount=Decimal("50.00"),
        )
        order.items.append(
            OrderItem(
                product_id_str="prod_1",
                product_name="Super Widget",
                product_image="img.jpg",
                product_specs={"color": "Black"},
                quantity=1,
                price_at_purchase=Decimal("50.00"),
            )
        )
        sql_db.session.add(order)
        sql_db.session.commit()

        # 3. Execute
        result = OrderService.get_order_with_details(order.id)

    item = result["items"][0]
    assert item["name"] == "Super Widget"
    assert item["image"] == "img.jpg"
    assert item["specs"] == {"color": "Black"}
    assert result["shipping_address"] == "123 Main St"
