# app/models.py
from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import sql_db


class Inventory(sql_db.Model):
    __tablename__ = "inventory"
    product_id = sql_db.Column(sql_db.String(24), primary_key=True)
    stock = sql_db.Column(sql_db.Integer, nullable=False, default=0)
    last_updated = sql_db.Column(sql_db.DateTime, default=datetime.now())


class OrderSQL(sql_db.Model):
    __tablename__ = "orders"

    id = sql_db.Column(sql_db.Integer, primary_key=True)

    # Customer Info (The missing fields)
    customer_name = sql_db.Column(sql_db.String(100))
    customer_email = sql_db.Column(sql_db.String(120))
    shipping_address = sql_db.Column(sql_db.String(255))
    city = sql_db.Column(sql_db.String(100))
    zip_code = sql_db.Column(sql_db.String(20))

    # Order Details
    items = sql_db.Column(JSONB)  # <--- Stores the "Messy Specs" snapshot
    total_amount = sql_db.Column(sql_db.Float)
    status = sql_db.Column(sql_db.String(20), default="Processing")
    created_at = sql_db.Column(sql_db.DateTime, default=datetime.now())

    # Helper for the template
    @property
    def items_list(self):
        return self.items if self.items else []

    def to_dict(self):
        return {
            "id": self.id,
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "shipping_address": self.shipping_address,
            "city": self.city,
            "zip_code": self.zip_code,
            "total_amount": self.total_amount,
            "status": self.status,
            "items": self.items,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
        }
