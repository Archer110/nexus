# tests/test_integration.py
from datetime import datetime

import pytest
from flask import Flask

from app.extensions import sql_db
from app.models import Inventory, Order, OrderItem


@pytest.fixture
def db_app():
    """
    Creates a real Flask app with an In-Memory SQLite Database.
    This is NOT a mock. It is a real SQL engine.
    """
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["TESTING"] = True

    sql_db.init_app(app)

    with app.app_context():
        sql_db.create_all() # Create real tables
        yield app
        sql_db.session.remove()
        sql_db.drop_all()

def test_inventory_model_persistence(db_app):
    """
    Goal: Can we save and retrieve Inventory?
    """
    # 1. Insert
    inv = Inventory(product_id="mongo_id_555", stock=100)
    sql_db.session.add(inv)
    sql_db.session.commit()

    # 2. Retrieve
    fetched = Inventory.query.get("mongo_id_555")
    assert fetched is not None
    assert fetched.stock == 100
    assert isinstance(fetched.last_updated, datetime)

def test_order_relationships_and_cascades(db_app):
    """
    Goal: Test 1-to-Many relationship and Cascade Delete.
    """
    # 1. Create Order
    order = Order(
        customer_name="John Doe",
        customer_email="john@test.com",
        shipping_address="123 Main St",
        city="New York",
        zip_code="10001",
        total_amount=50.0
    )
    
    # 2. Add Items
    item1 = OrderItem(product_id_str="p1", quantity=1, price_at_purchase=25.0)
    item2 = OrderItem(product_id_str="p2", quantity=1, price_at_purchase=25.0)
    order.items.append(item1)
    order.items.append(item2)

    sql_db.session.add(order)
    sql_db.session.commit()

    # 3. Verify Foreign Keys
    assert order.id is not None
    assert item1.order_id == order.id  # Auto-assigned?

    # 4. Test Cascade Delete
    # If we delete the Order, items should vanish
    order_id = order.id
    sql_db.session.delete(order)
    sql_db.session.commit()

    # Verify items are gone from DB
    assert OrderItem.query.filter_by(order_id=order_id).count() == 0

def test_order_constraints_enforcement(db_app):
    """
    Goal: Verify NOT NULL constraints work.
    """
    # Try to create order without a name (should fail)
    bad_order = Order(
        customer_email="anon@test.com", # Missing Name!
        total_amount=10.0
    )
    sql_db.session.add(bad_order)

    # Assert that SQLite rejects this
    with pytest.raises(Exception): # SQLAlchemy raises IntegrityError
        sql_db.session.commit()
