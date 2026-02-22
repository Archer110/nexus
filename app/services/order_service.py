from datetime import datetime

from bson import ObjectId
from sqlalchemy import or_

from app.extensions import mongo, sql_db
from app.models import Inventory, Order, OrderItem


class OrderService:
    """
    The 'Bank Manager'.
    Responsibility: Handle strict financial transactions and order lifecycle.
    """

    # --- WRITES (The "Safe" Transaction) ---

    @staticmethod
    def create_order(customer_data: dict, cart_items: list):
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
            total_amount = 0.0
            new_items = []

            # 1. Process Items & Deduct Stock
            for item in cart_items:
                product_id = item["product_id"]
                qty = int(item["qty"])
                price = float(item["price"])

                # STRICT Check: Lock the inventory row for update
                # (with_for_update ensures no one else buys this last item while we are processing)
                inventory = Inventory.query.with_for_update().filter_by(product_id=product_id).first()

                if not inventory or inventory.stock < qty:
                    raise ValueError(f"Product {item['name']} is out of stock!")

                # Deduct Stock
                inventory.stock -= qty
                
                # Create Strict Line Item
                order_item = OrderItem(
                    product_id_str=product_id,
                    quantity=qty,
                    price_at_purchase=price  # <--- Freeze the price!
                )
                new_items.append(order_item)
                total_amount += (price * qty)

            # 2. Create Order Header
            new_order = Order(
                customer_name=customer_data.get("name"),
                customer_email=customer_data.get("email"),
                shipping_address=customer_data.get("address"),
                city=customer_data.get("city"),
                zip_code=customer_data.get("zip"),
                total_amount=total_amount,
                status="Processing",
                created_at=datetime.utcnow(),
                items=new_items  # SQLA handles the Foreign Keys automatically
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
    def update_status(order_id, new_status):
        order = Order.query.get(order_id)
        if order:
            order.status = new_status
            sql_db.session.commit()
        return order

    # --- READS (The "Reverse" Hybrid Join) ---

    @staticmethod
    def get_order_with_details(order_id):
        """
        Fetches the Order (SQL) and enriches items with Product Data (Mongo).
        Used for the 'Order Success' or 'Order History' page.
        """
        order = Order.query.get(order_id)
        if not order:
            return None

        # 1. Extract IDs from the SQL Line Items
        # We need to know WHICH documents to fetch from Mongo
        product_ids_str = [item.product_id_str for item in order.items]
        
        # 2. Batch Fetch from Mongo (1 Query)
        # Convert strings to ObjectIds for the Mongo query
        oids = [ObjectId(pid) for pid in product_ids_str if ObjectId.is_valid(pid)]
        mongo_docs = list(mongo.db.products.find({"_id": {"$in": oids}}))
        
        # 3. Create a Lookup Map for speed
        # { "65c...": { "name": "Laptop", "image": "..." } }
        product_map = {str(doc["_id"]): doc for doc in mongo_docs}

        # 4. Construct the View Model
        # We don't modify the SQL model directly; we create a dictionary for the template.
        order_dict = order.to_dict()
        
        # Enrich the items
        for item_data in order_dict["items"]:
            pid = item_data["product_id"]
            if pid in product_map:
                product = product_map[pid]
                item_data["name"] = product.get("name", "Unknown Product")
                item_data["image"] = product.get("image", "/static/placeholder.png")
                # We could even show the 'specs' here if we wanted!
            else:
                item_data["name"] = "Archived Product"
                item_data["image"] = "/static/placeholder.png"

        return order_dict

    @staticmethod
    def get_orders(search_query=None):
        """
        Standard Admin List Query.
        """
        query = Order.query

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

        return query.order_by(Order.created_at.desc()).all()

    # --- ATOMIC STATS (For Dashboard) ---

    @staticmethod
    def get_total_revenue():
        """Returns the sum of all confirmed orders."""
        return sql_db.session.query(sql_db.func.sum(Order.total_amount)).scalar() or 0.0

    @staticmethod
    def get_recent_orders(limit=5):
        """Returns the N most recent orders."""
        return Order.query.order_by(Order.created_at.desc()).limit(limit).all()

    @staticmethod
    def count_orders():
        return Order.query.count()
