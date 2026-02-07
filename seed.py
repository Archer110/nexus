import random
from datetime import datetime, timedelta

import requests
from faker import Faker

from app import create_app
from app.extensions import mongo, sql_db
from app.models import Inventory

fake = Faker()
app = create_app()

# --- CONFIGURATION ---
API_URL = "https://dummyjson.com/products?limit=0"
TARGET_COUNT = 1500  # <--- The Goal

# --- 1. SPEC GENERATORS (The "Justification" for MongoDB) ---
# We define different data shapes for different types of products.


def gen_tech_specs(base_specs):
    # Enriches tech items with more nerdy details
    return {
        **base_specs,
        "processor": random.choice(["Snapdragon 8 Gen 3", "M3", "Intel i9", "A17 Pro"]),
        "ram": random.choice(["8GB", "16GB", "32GB"]),
        "storage": random.choice(["256GB", "512GB", "1TB"]),
        "warranty": "2 Year Manufacturer",
        "connectivity": ["Bluetooth 5.3", "WiFi 6E", "NFC"],
    }


def gen_fashion_specs(base_specs):
    return {
        **base_specs,
        "material": random.choice(["Cotton", "Polyester", "Leather", "Silk", "Denim"]),
        "gender": random.choice(["Unisex", "Men", "Women"]),
        "care_instructions": random.choice(
            ["Machine Wash", "Dry Clean Only", "Hand Wash"]
        ),
        "season": random.choice(["SS26", "FW25", "All-Season"]),
        "sizes_available": ["XS", "S", "M", "L", "XL"],
    }


def gen_beauty_specs(base_specs):
    return {
        **base_specs,
        "ingredients": ["Aqua", "Glycerin", "Vitamin C", "Hyaluronic Acid", "Retinol"],
        "skin_type": random.choice(["All", "Oily", "Dry", "Sensitive"]),
        "volume": f"{random.randint(30, 250)}ml",
        "cruelty_free": random.choice([True, False]),
        "organic": random.choice([True, False]),
    }


def gen_home_specs(base_specs):
    return {
        **base_specs,
        "material_primary": random.choice(
            ["Oak Wood", "Stainless Steel", "Ceramic", "Glass"]
        ),
        "assembly_required": random.choice([True, False]),
        "dimensions_cm": f"{random.randint(10, 200)}x{random.randint(10, 200)}x{random.randint(10, 100)}",
        "weight_kg": round(random.uniform(0.5, 50.0), 2),
    }


def gen_grocery_specs(base_specs):
    return {
        **base_specs,
        "calories": random.randint(50, 800),
        "expiry_date": (
            datetime.now() + timedelta(days=random.randint(7, 365))
        ).strftime("%Y-%m-%d"),
        "allergens": random.sample(
            ["Nuts", "Dairy", "Soy", "Gluten", "None"], k=random.randint(0, 2)
        ),
        "dietary": random.choice(["Vegan", "Vegetarian", "Keto", "Standard"]),
        "origin": random.choice(["USA", "Italy", "Mexico", "Local Farm"]),
    }


def gen_vehicle_specs(base_specs):
    return {
        **base_specs,
        "engine": random.choice(["V8", "Electric", "Hybrid", "V6 Turbo"]),
        "horsepower": f"{random.randint(100, 800)} HP",
        "fuel_capacity": f"{random.randint(40, 100)}L",
        "transmission": random.choice(["Automatic", "Manual", "CVT"]),
        "year": random.randint(2022, 2026),
    }


# --- 2. CATEGORY DISPATCHER ---
# Determines which Spec Generator to use based on the API Category
def get_specs_for_category(category_name, base_specs={}):
    cat = category_name.lower()

    # Map API categories to our Generators
    if any(x in cat for x in ["laptop", "phone", "tablet", "watch", "mobile", "tech"]):
        return gen_tech_specs(base_specs)

    elif any(
        x in cat
        for x in ["shirt", "dress", "shoe", "bag", "jewel", "fashion", "sunglass"]
    ):
        return gen_fashion_specs(base_specs)

    elif any(x in cat for x in ["beauty", "skin", "fragrance", "lip", "mascara"]):
        return gen_beauty_specs(base_specs)

    elif any(x in cat for x in ["home", "furniture", "decor", "light", "kitchen"]):
        return gen_home_specs(base_specs)

    elif any(x in cat for x in ["grocer", "food", "snack"]):
        return gen_grocery_specs(base_specs)

    elif any(x in cat for x in ["vehicle", "motor", "car", "auto"]):
        return gen_vehicle_specs(base_specs)

    # Fallback
    return {**base_specs, "type": "General Merchandise", "condition": "New"}


# --- 3. SYNTHETIC ENRICHMENT (Filtering Data) ---
# These are fields we want on EVERYTHING for the search bar later.
COLORS = [
    "Midnight Black",
    "Clean White",
    "Cyber Silver",
    "Neon Blue",
    "Crimson Red",
    "Gold",
    "Natural",
]


def add_global_specs(specs):
    specs.update(
        {
            "color": random.choice(COLORS),
            "shipping_weight_g": random.randint(50, 5000),
            "eco_friendly_packaging": random.choice([True, False]),
            "release_year": random.randint(2023, 2026),
        }
    )
    return specs


# --- MAIN SEEDER ---
def seed_data():
    with app.app_context():
        print("☢️  NUKE PROTOCOL: Wiping all data...")
        mongo.db.products.delete_many({})
        sql_db.drop_all()
        sql_db.create_all()

        # A. FETCH BASE DATA
        print("🌍 Fetching Global Catalog (DummyJSON)...")
        try:
            resp = requests.get(API_URL).json()
            source_products = resp.get("products", [])
            print(f"   - Retrieved {len(source_products)} base templates.")
        except Exception as e:
            print(f"❌ Critical Error: Could not fetch API. {e}")
            return

        # B. CLONING LAB
        print(f"🧬 Cloning & Mutating to reach {TARGET_COUNT} units...")

        products_to_insert = []

        while len(products_to_insert) < TARGET_COUNT:
            # 1. Pick a random parent
            parent = random.choice(source_products)

            # 2. Mutate Name (e.g., "Essence Mascara" -> "Essence Mascara [Waterproof Bundle]")
            suffixes = [
                "Pro",
                "Max",
                "Mini",
                "Bundle",
                "Refurbished",
                "Limited Edition",
                "V2",
                "Pack",
                "Travel Size",
            ]
            is_variant = random.random() > 0.3  # 70% chance to be a variant

            new_name = parent["title"]
            if is_variant:
                new_name = f"{parent['title']} {random.choice(suffixes)}"

            # 3. Mutate Price (Swing -30% to +30%)
            price_swing = random.uniform(0.7, 1.3)
            new_price = round(float(parent["price"]) * price_swing, 2)

            # 4. Generate The Specs
            # We strip existing meta from API if we want, or keep it.
            # Here we build fresh specs to ensure uniformity in our chaos.
            category = parent["category"]

            # Base specs from API
            base_specs = {
                "brand": parent.get("brand", "Generic"),
                "sku": f"SKU-{random.randint(10000, 99999)}",
            }

            # Generate Category Specifics
            poly_specs = get_specs_for_category(category, base_specs)

            # Add Global Search Filters
            final_specs = add_global_specs(poly_specs)

            products_to_insert.append(
                {
                    "name": new_name,
                    "price": new_price,
                    "description": parent["description"],
                    "category": category.replace(
                        "-", " "
                    ).title(),  # Clean up "smart-phones" -> "Smart Phones"
                    "image": parent["thumbnail"],
                    "rating": round(random.uniform(3.5, 5.0), 1),
                    "reviews_count": random.randint(0, 1000),
                    "created_at": datetime.now()
                    - timedelta(days=random.randint(0, 365)),
                    "specs": final_specs,  # <--- The Schema-less magic
                }
            )

        # C. INSERTION
        print(f"💾 Committing {len(products_to_insert)} records to MongoDB...")

        sql_inventory = []

        # Insert in chunks is better, but loop is safer for ID capture in this specific hybrid setup
        for i, p_doc in enumerate(products_to_insert):
            res = mongo.db.products.insert_one(p_doc)

            # Random Stock Generation
            stock_qty = 0 if random.random() < 0.1 else random.randint(1, 300)

            inv = Inventory(
                product_id=str(res.inserted_id),
                stock=stock_qty,
                last_updated=datetime.utcnow(),
            )
            sql_inventory.append(inv)

            if i > 0 and i % 200 == 0:
                print(f"   ... Processed {i} items")

        print("⚡ Syncing PostgreSQL Ledger...")
        sql_db.session.bulk_save_objects(sql_inventory)
        sql_db.session.commit()

        print("\n✅ OMNI-STORE ONLINE.")
        print(f"   - Total Inventory: {len(products_to_insert)}")
        print("   - Spec Diversity: High")


if __name__ == "__main__":
    seed_data()
