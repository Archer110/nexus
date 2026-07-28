from decimal import Decimal
from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import selectinload

from app.contracts import CartItem, CheckoutCustomer
from app.extensions import sql_db
from app.models import (
    ORDER_STATUS_TRANSITIONS,
    Inventory,
    Order,
    OrderItem,
    OrderStatus,
)
from app.money import money
from app.services.product_service import ProductService
from app.validation import checkout_customer, positive_int, search_term


class OrderService:
    """Manage transactional inventory and order state."""

    MAX_ORDER_TOTAL = Decimal("9999999999.99")

    @staticmethod
    def create_order(
        customer_data: CheckoutCustomer,
        cart_items: list[CartItem],
    ) -> Order | None:
        if not cart_items:
            return None

        normalized_customer = checkout_customer(customer_data)

        product_ids = sorted({str(item["product_id"]) for item in cart_items})

        try:
            products_by_id = ProductService.get_products_by_ids(product_ids)
            inventory_statement = (
                select(Inventory)
                .where(Inventory.product_id.in_(product_ids))
                .order_by(Inventory.product_id)
                .with_for_update()
            )
            inventory_records = sql_db.session.scalars(inventory_statement).all()
            inventory_by_product = {
                inventory.product_id: inventory for inventory in inventory_records
            }

            total_amount = Decimal("0.00")
            order_items: list[OrderItem] = []

            for item in cart_items:
                quantity = positive_int(item["qty"], "Cart quantity")

                product_id = str(item["product_id"])
                product = products_by_id.get(product_id)
                if not product:
                    raise ValueError("A product in your cart is no longer available.")

                product_name = str(product.get("name") or "Unknown Product")
                inventory = inventory_by_product.get(product_id)
                if not inventory or inventory.stock < quantity:
                    raise ValueError(f"Product {product_name} is out of stock!")

                price = money(product["price"])
                inventory.stock -= quantity
                order_items.append(
                    OrderItem(
                        product_id_str=product_id,
                        product_name=product_name,
                        product_image=product.get("image"),
                        product_specs=dict(product.get("specs") or {}),
                        quantity=quantity,
                        price_at_purchase=price,
                    )
                )
                total_amount += price * quantity
                if total_amount > OrderService.MAX_ORDER_TOTAL:
                    raise ValueError("Order total exceeds the supported limit.")

            order = Order(
                **normalized_customer,
                total_amount=total_amount,
                status=OrderStatus.PROCESSING,
                items=order_items,
            )
            sql_db.session.add(order)
            sql_db.session.commit()
            return order
        except Exception:
            sql_db.session.rollback()
            raise

    @staticmethod
    def update_status(order_id: int, new_status: str) -> Order | None:
        order = sql_db.session.get(Order, order_id)
        if not order:
            return None

        try:
            requested_status = OrderStatus(new_status)
        except ValueError as error:
            raise ValueError(f"Unknown order status {new_status!r}.") from error

        if requested_status == order.status:
            return order

        if requested_status not in ORDER_STATUS_TRANSITIONS[order.status]:
            raise ValueError(
                f"Order cannot move from {order.status.value} "
                f"to {requested_status.value}."
            )

        try:
            if requested_status is OrderStatus.CANCELLED:
                product_ids = sorted(item.product_id_str for item in order.items)
                inventory_statement = (
                    select(Inventory)
                    .where(Inventory.product_id.in_(product_ids))
                    .order_by(Inventory.product_id)
                    .with_for_update()
                )
                inventory_records = sql_db.session.scalars(inventory_statement).all()
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

            order.status = requested_status
            sql_db.session.commit()
            return order
        except Exception:
            sql_db.session.rollback()
            raise

    @staticmethod
    def get_order_with_details(
        order_id: int,
    ) -> dict[str, Any] | None:
        order = sql_db.session.get(Order, order_id)
        return order.to_dict() if order else None

    @staticmethod
    def get_orders(
        search_query: str | None = None,
    ) -> list[dict[str, Any]]:
        statement = select(Order).options(selectinload(Order.items))
        search_query = search_term(search_query)

        if search_query:
            term = f"%{search_query}%"
            statement = statement.where(
                or_(
                    Order.customer_name.ilike(term),
                    Order.customer_email.ilike(term),
                    cast(Order.id, String).ilike(term),
                )
            )

        statement = statement.order_by(Order.created_at.desc())
        orders = sql_db.session.scalars(statement).all()
        return [order.to_dict() for order in orders]

    @staticmethod
    def get_total_revenue() -> Decimal:
        statement = select(func.sum(Order.total_amount)).where(
            Order.status != OrderStatus.CANCELLED
        )
        return sql_db.session.scalar(statement) or Decimal("0.00")

    @staticmethod
    def get_recent_orders(limit: int = 5) -> list[Order]:
        statement = select(Order).order_by(Order.created_at.desc()).limit(limit)
        return list(sql_db.session.scalars(statement))

    @staticmethod
    def count_orders() -> int:
        return sql_db.session.scalar(select(func.count(Order.id))) or 0
