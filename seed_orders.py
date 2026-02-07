import random
from datetime import datetime, timedelta

from faker import Faker

from app import create_app
from app.extensions import mongo, sql_db
from app.models import OrderSQL

fake = Faker()
app = create_app()

STATUSES = ["Processing", "Shipped", "Delivered", "Cancelled"]
WEIGHTS = [0.3, 0.3, 0.3, 0.1]  # 10% chance of cancellation


def seed_orders():
    with app.app_context():
        print("📦 GENERATING ORDER HISTORY...")

        # 1. Get real products from Mongo to make orders realistic
        # We need their IDs, Images, and Specs
        products = list(
            mongo.db.products.find(
                {}, {"_id": 1, "name": 1, "price": 1, "image": 1, "specs": 1}
            ).limit(100)
        )

        if not products:
            print("❌ No products found! Run 'seed_polyglot.py' first.")
            return

        # 2. Create Orders
        new_orders = []

        for i in range(20):  # Generate 20 Orders
            # Random Customer
            cust_name = fake.name()
            cust_email = fake.email()

            # Random Cart (1 to 5 items)
            cart_items = []
            order_total = 0

            num_items = random.randint(1, 5)
            selected_products = random.sample(products, num_items)

            for p in selected_products:
                qty = random.randint(1, 3)
                price = p["price"]
                subtotal = price * qty
                order_total += subtotal

                # SNAPSHOT THE SPECS (The "Messy Data" part)
                # We save the specs into the SQL JSON so the warehouse knows exactly what was ordered
                # even if the product changes later.
                cart_items.append(
                    {
                        "product_id": str(p["_id"]),
                        "name": p["name"],
                        "image": p["image"],
                        "price": price,
                        "qty": qty,
                        "specs": p.get("specs", {}),  # <--- Critical for Admin View
                    }
                )

            # Random Date (Past 30 days)
            order_date = datetime.now() - timedelta(days=random.randint(0, 30))

            # Create SQL Object
            order = OrderSQL(
                customer_name=cust_name,
                customer_email=cust_email,
                shipping_address=fake.address().replace("\n", ", "),
                city=fake.city(),
                zip_code=fake.zipcode(),
                items=cart_items,  # JSON Column
                total_amount=round(order_total, 2),
                status=random.choices(STATUSES, weights=WEIGHTS)[0],
                created_at=order_date,
            )
            new_orders.append(order)

        # 3. Commit
        # We don't wipe the table first, so you can run this multiple times to pile up orders.
        sql_db.session.bulk_save_objects(new_orders)
        sql_db.session.commit()

        print(f"✅ Successfully injected {len(new_orders)} orders into PostgreSQL.")


if __name__ == "__main__":
    seed_orders()
