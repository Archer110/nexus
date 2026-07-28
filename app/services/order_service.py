from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from app.extensions import mongo, sql_db
from app.models import Inventory, Order, OrderItem


class OrderService:
    """
    The 'Bank Manager'.
    Responsibility: Handle strict financial transactions and order lifecycle.
    """

    STATUS_TRANSITIONS = {
        "Processing": {"Shipped", "Cancelled"},
        "Shipped": {"Delivered"},
        "Delivered": set(),
        "Cancelled": set(),
    }

    # --- WRITES (The "Safe" Transaction) ---

    @staticmethod
    def create_order(
        customer_data: Dict[str, Any], cart_items: List[Dict[str, Any]]
    ) -> Optional[Order]:
        """
        Executes the Checkout Transaction.
        1. Validates Stock (SQL Inventory).
        2. Deducts Stock.
        3. Creates Order + OrderItems.
        4. Commits atomically.
        """
        if not cart_items:
            return None

        # Start a Session Transaction
        # Note: In Flask-SQLAlchemy, transactions are implicit on commit,
        # but we use try/except to handle rollbacks explicitly.
        try:
            total_amount: float = 0.0
            new_items: List[OrderItem] = []

            # 1. Process Items & Deduct Stock
            for item in cart_items:
                qty = int(item["qty"])
                price = float(item["price"])
                product_id = str(item["product_id"])

                # STRICT Check: Lock the inventory row for update
                # (with_for_update ensures no one else buys this last item while we are processing)
                inventory = (
                    Inventory.query.with_for_update()
                    .filter_by(product_id=product_id)
                    .first()
                )

                if not inventory or inventory.stock < qty:
                    raise ValueError(f"Product {item['name']} is out of stock!")

                # Deduct Stock
                inventory.stock -= qty

                # Create Strict Line Item
                order_item = OrderItem(
                    product_id_str=product_id,
                    quantity=qty,
                    price_at_purchase=price,  # <--- Freeze the price!
                )
                new_items.append(order_item)
                total_amount += price * qty

            # 2. Create Order Header
            new_order = Order(
                customer_name=customer_data.get("name"),
                customer_email=customer_data.get("email"),
                shipping_address=customer_data.get("address"),
                city=customer_data.get("city"),
                zip_code=customer_data.get("zip"),
                total_amount=total_amount,
                status="Processing",
                created_at=datetime.now(timezone.utc),
                items=new_items,  # SQLA handles the Foreign Keys automatically
            )

            # 3. Commit the Whole Block
            sql_db.session.add(new_order)
            sql_db.session.commit()

            return new_order

        except Exception as e:
            # If ANYTHING fails (Out of stock, DB error), we rollback.
            # No money is lost, no half-orders created.
            sql_db.session.rollback()
            raise e

    @staticmethod
    def update_status(order_id: int, new_status: str) -> Optional[Order]:
        order = sql_db.session.get(Order, order_id)
        if not order:
            return None

        if new_status == order.status:
            return order

        allowed_statuses = OrderService.STATUS_TRANSITIONS.get(order.status, set())
        if new_status not in allowed_statuses:
            raise ValueError(f"Order cannot move from {order.status} to {new_status}.")

        try:
            if new_status == "Cancelled":
                product_ids = sorted(item.product_id_str for item in order.items)
                inventory_records = (
                    Inventory.query.filter(Inventory.product_id.in_(product_ids))
                    .with_for_update()
                    .all()
                )
                inventory_by_product = {
                    inventory.product_id: inventory for inventory in inventory_records
                }

                for item in order.items:
                    inventory = inventory_by_product.get(item.product_id_str)
                    if not inventory:
                        raise ValueError(
                            f"Inventory record {item.product_id_str} is missing."
                        )
                    inventory.stock += item.quantity

            order.status = new_status
            sql_db.session.commit()
            return order
        except Exception:
            sql_db.session.rollback()
            raise

    # --- READS (The "Reverse" Hybrid Join) ---

    @staticmethod
    def _serialize_orders(orders: List[Order]) -> List[Dict[str, Any]]:
        if not orders:
            return []

        product_ids = {item.product_id_str for order in orders for item in order.items}
        object_ids = [
            ObjectId(product_id)
            for product_id in product_ids
            if ObjectId.is_valid(product_id)
        ]
        product_documents = list(mongo.db.products.find({"_id": {"$in": object_ids}}))
        products_by_id = {str(product["_id"]): product for product in product_documents}

        serialized_orders = []
        for order in orders:
            order_data = order.to_dict()
            for item_data in order_data["items"]:
                product = products_by_id.get(item_data["product_id"])
                if product:
                    item_data["name"] = product.get("name", "Unknown Product")
                    item_data["image"] = product.get("image", "/static/placeholder.png")
                    item_data["specs"] = product.get("specs", {})
                else:
                    item_data["name"] = "Archived Product"
                    item_data["image"] = "/static/placeholder.png"
                    item_data["specs"] = {}
            serialized_orders.append(order_data)

        return serialized_orders

    @staticmethod
    def get_order_with_details(order_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches the Order (SQL) and enriches items with Product Data (Mongo).
        Used for the 'Order Success' or 'Order History' page.
        """
        order = sql_db.session.get(Order, order_id)
        if not order:
            return None

        return OrderService._serialize_orders([order])[0]

    @staticmethod
    def get_orders(search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Standard Admin List Query.
        """
        query = Order.query.options(selectinload(Order.items))

        if search_query:
            term = f"%{search_query}%"
            # Search by ID, Name, or Email
            query = query.filter(
                or_(
                    Order.customer_name.ilike(term),
                    Order.customer_email.ilike(term),
                    Order.id.cast(sql_db.String).ilike(term),
                )
            )

        orders = query.order_by(Order.created_at.desc()).all()
        return OrderService._serialize_orders(orders)

    # --- ATOMIC STATS (For Dashboard) ---

    @staticmethod
    def get_total_revenue() -> float:
        """Returns revenue from all non-cancelled orders."""
        return (
            sql_db.session.query(sql_db.func.sum(Order.total_amount))
            .filter(Order.status != "Cancelled")
            .scalar()
            or 0.0
        )

    @staticmethod
    def get_recent_orders(limit: Optional[int] = 5) -> List[Order]:
        """Returns the N most recent orders."""
        return Order.query.order_by(Order.created_at.desc()).limit(limit).all()

    @staticmethod
    def count_orders() -> int:
        return Order.query.count()
