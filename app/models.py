from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.extensions import sql_db

# --- MONGODB MODELS (Documentation & Type Hinting) ---
# MongoDB is schema-less, but we define this Data Class so 
# developers know what a "Product" document looks like.

@dataclass
class ProductDocument:
    """
    Defines the shape of the MongoDB 'products' document.
    This is not an ORM model; it is a reference for the application layer.
    """
    _id: str
    name: str
    price: float
    category: str
    image: str
    description: str
    specs: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


# --- SQLALCHEMY MODELS (Strict Schema Enforcement) ---

class Inventory(sql_db.Model):
    """
    The 'Bridge' Table.
    Maps a MongoDB Product ID (string) to a SQL Stock Count (integer).
    """
    __tablename__ = "inventory"

    # We use String(24) because MongoDB ObjectIds are 24-char hex strings
    product_id: str = sql_db.Column(sql_db.String(24), primary_key=True)
    stock: int = sql_db.Column(sql_db.Integer, nullable=False, default=0)
    last_updated: datetime = sql_db.Column(sql_db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<Inventory {self.product_id}: {self.stock}>"


class OrderItem(sql_db.Model):
    """
    The 'Ledger' Lines.
    Stores the specific items in an order.
    CRITICAL: We freeze the price here so future price changes don't affect history.
    """
    __tablename__ = "order_items"

    id: int = sql_db.Column(sql_db.Integer, primary_key=True)
    
    # Link to Parent Order
    order_id: int = sql_db.Column(sql_db.Integer, sql_db.ForeignKey("orders.id"), nullable=False)

    # Link to MongoDB Product (Logical Reference)
    # This is the "Polyglot Key"
    product_id_str: str = sql_db.Column(sql_db.String(24), nullable=False)

    # Transaction Snapshot
    quantity: int = sql_db.Column(sql_db.Integer, nullable=False)
    price_at_purchase: float = sql_db.Column(sql_db.Float, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id_str,
            "quantity": self.quantity,
            "price": self.price_at_purchase
        }


class Order(sql_db.Model):
    """
    The 'Ledger' Header.
    Stores the WHO, WHEN, and HOW MUCH.
    """
    __tablename__ = "orders"

    id: int = sql_db.Column(sql_db.Integer, primary_key=True)

    # Customer Data (Strictly Typed)
    customer_name: str = sql_db.Column(sql_db.String(100), nullable=False)
    customer_email: str = sql_db.Column(sql_db.String(120), nullable=False)
    shipping_address: str = sql_db.Column(sql_db.String(255), nullable=False)
    city: str = sql_db.Column(sql_db.String(100), nullable=False)
    zip_code: str = sql_db.Column(sql_db.String(20), nullable=False)

    # Financial Data
    total_amount: float = sql_db.Column(sql_db.Float, nullable=False)
    status: str = sql_db.Column(sql_db.String(20), default="Processing")
    created_at: datetime = sql_db.Column(sql_db.DateTime, default=datetime.now)

    # Relationship: One Order has Many Items
    # cascade="all, delete-orphan" means if we delete the Order, the Items die too.
    items: List[OrderItem] = sql_db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "total_amount": self.total_amount,
            "status": self.status,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
            "items": [item.to_dict() for item in self.items]
        }
