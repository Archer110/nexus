from datetime import datetime

from sqlalchemy import or_

from app.extensions import sql_db
from app.models import Inventory, OrderSQL


class OrderService:
    @staticmethod
    def get_orders(search_query=None):
        query = OrderSQL.query

        if search_query:
            term = f"%{search_query}%"
            query = query.filter(
                or_(
                    OrderSQL.customer_name.ilike(term),
                    OrderSQL.customer_email.ilike(term),
                    OrderSQL.id.cast(sql_db.String).ilike(term),
                )
            )

        return query.order_by(OrderSQL.created_at.desc()).all()

    @staticmethod
    def update_status(order_id, new_status):
        order = OrderSQL.query.get_or_404(order_id)
        order.status = new_status
        sql_db.session.commit()
        return order

    @staticmethod
    def create_order(customer_data: dict, cart_items: list):
        """
        1. Calculates total
        2. Deducts stock (SQL)
        3. Creates Order (SQL)
        4. Commits transaction
        """
        if not cart_items:
            return None

        # 1. Calculate Total
        total_amount = sum(item["price"] * item["qty"] for item in cart_items)

        # 2. Update Inventory
        # We loop through items to deduct stock.
        # (In a real app, you'd want to handle 'Out of Stock' errors here)
        for item in cart_items:
            inventory = Inventory.query.filter_by(product_id=item["product_id"]).first()
            if inventory and inventory.stock >= item["qty"]:
                inventory.stock -= item["qty"]

        # 3. Create Order
        new_order = OrderSQL(
            customer_name=customer_data.get("name"),
            customer_email=customer_data.get("email"),
            shipping_address=customer_data.get("address"),
            city=customer_data.get("city"),
            zip_code=customer_data.get("zip"),
            items=cart_items,
            total_amount=total_amount,
            status="Processing",
            created_at=datetime.now(),
        )

        sql_db.session.add(new_order)
        sql_db.session.commit()

        return new_order
