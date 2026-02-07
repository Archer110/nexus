from datetime import datetime

from bson import ObjectId
from flask import current_app

from app.extensions import mongo, sql_db
from app.models import Inventory


class ProductService:
    @staticmethod
    def create_product(data: dict, stock: int):
        """
        Creates a product in MongoDB and initializes inventory in SQL.
        """
        # 1. Prepare Mongo Document
        product_doc = {
            "name": data.get("name"),
            "price": float(data.get("price", 0)),
            "category": data.get("category"),
            "image": data.get("image") or "https://placehold.co/600x400",
            "description": data.get("description", "Added via Admin"),
            "specs": data.get("specs", {}),
            "created_at": datetime.now(),
        }

        # 2. Insert into Mongo
        result = mongo.db.products.insert_one(product_doc)
        new_id = str(result.inserted_id)

        # 3. Insert into SQL (Inventory)
        new_inventory = Inventory(
            product_id=new_id, stock=int(stock), last_updated=datetime.now()
        )
        sql_db.session.add(new_inventory)
        sql_db.session.commit()

        return {**product_doc, "_id": result.inserted_id, "stock": stock}

    @staticmethod
    def update_product(product_id: str, field: str, value):
        """
        Updates either SQL (stock) or Mongo (price/meta) based on field.
        """
        if field == "stock":
            inventory = Inventory.query.filter_by(product_id=product_id).first()
            if inventory:
                inventory.stock = int(value)
                inventory.last_updated = datetime.now()
                sql_db.session.commit()
                return inventory.stock

        elif field == "price":
            new_price = float(value)
            mongo.db.products.update_one(
                {"_id": ObjectId(product_id)}, {"$set": {"price": new_price}}
            )
            return new_price

        return None

    @staticmethod
    def delete_product(product_id: str):
        """
        Removes product from both databases.
        """
        # 1. Remove from SQL
        Inventory.query.filter_by(product_id=product_id).delete()
        sql_db.session.commit()

        # 2. Remove from Mongo
        mongo.db.products.delete_one({"_id": ObjectId(product_id)})
        return True

    @staticmethod
    def get_product_by_id(product_id: str):
        """
        Fetches a product from Mongo by ID.
        Returns None if not found or invalid ID.
        """
        try:
            oid = ObjectId(product_id)
        except:
            return None

        return mongo.db.products.find_one({"_id": oid})

    @staticmethod
    def get_catalog(
        page=1, per_page=9, search_query=None, category=None, spec_filters=None
    ):
        """
        Retrieves a paginated, filtered list of products with stock info.
        """

        if per_page is None:
            per_page = current_app.config["PRODUCTS_PER_PAGE"]

        # 1. Build MongoDB Query
        mongo_filter = {}

        if search_query:
            mongo_filter["name"] = {"$regex": search_query, "$options": "i"}

        if category:
            mongo_filter["category"] = category

        # Add Dynamic Spec Filters (e.g., {'ram': ['16GB', '32GB']})
        if spec_filters:
            for key, values in spec_filters.items():
                if len(values) > 1:
                    mongo_filter[f"specs.{key}"] = {"$in": values}
                elif len(values) == 1:
                    mongo_filter[f"specs.{key}"] = values[0]

        # 2. Count Total (For Pagination)
        total_count = mongo.db.products.count_documents(mongo_filter)

        # 3. Fetch Products (Mongo)
        skip = (page - 1) * per_page
        cursor = mongo.db.products.find(mongo_filter).sort("created_at", -1)
        products = list(cursor.skip(skip).limit(per_page))

        # 4. Attach Stock (SQL)
        # We manually join because data is split across DBs
        if products:
            p_ids = [str(p["_id"]) for p in products]
            inventory_map = {
                inv.product_id: inv.stock
                for inv in Inventory.query.filter(Inventory.product_id.in_(p_ids)).all()
            }

            for p in products:
                p["_id"] = str(p["_id"])  # Serialize ObjectId
                p["stock"] = inventory_map.get(p["_id"], 0)

        return products, total_count

    @staticmethod
    def get_product_details(product_id: str):
        """
        Fetches full product details + stock.
        Returns None if not found.
        """
        try:
            oid = ObjectId(product_id)
        except:
            return None

        product = mongo.db.products.find_one({"_id": oid})
        if not product:
            return None

        # Attach Stock
        pid_str = str(product["_id"])
        inventory = Inventory.query.filter_by(product_id=pid_str).first()

        product["_id"] = pid_str
        product["stock"] = inventory.stock if inventory else 0

        return product

    @staticmethod
    def get_facets(category=None):
        """
        Returns available categories and dynamic specs for the sidebar.
        """
        # 1. All Categories
        all_categories = sorted(mongo.db.products.distinct("category"))

        # 2. Dynamic Specs (Only if a category is selected)
        active_facets = {}
        if category:
            # Aggregation pipeline to find most common keys in this category
            pipeline = [
                {"$match": {"category": category}},
                {"$project": {"specs": {"$objectToArray": "$specs"}}},
                {"$unwind": "$specs"},
                {"$group": {"_id": "$specs.k", "values": {"$addToSet": "$specs.v"}}},
            ]
            results = mongo.db.products.aggregate(pipeline)

            for r in results:
                # Only show facets that have at least 2 options (otherwise no point filtering)
                if len(r["values"]) > 1:
                    active_facets[r["_id"]] = sorted(list(r["values"]))

        return all_categories, active_facets
