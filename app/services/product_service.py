from datetime import datetime

from bson import ObjectId
from flask import current_app

from sqlalchemy.exc import SQLAlchemyError
from typing import Any, Dict, List, Optional, Tuple, Union

from app.extensions import mongo, sql_db
from app.models import Inventory


class ProductService:
    """
    The 'General Manager' for Products.
    Responsibility: Orchestrate data between MongoDB (Catalog) and PostgreSQL (Inventory).
    """

    # --- WRITES (The "Dual-Write" Logic) ---

    @staticmethod
    def create_product(data: Dict[str, Any], stock: int) -> Dict[str, Any]:
        """
        Creates a product in the Catalog (Mongo) and initializes Inventory (SQL).
        """
        # 1. Prepare Mongo Document (Flexible Schema)
        product_doc: Dict[str, Any] = {
            "name": data.get("name"),
            "price": float(data.get("price", 0)),
            "category": data.get("category"),
            "image": data.get("image") or "https://placehold.co/600x400",
            "description": data.get("description", "Added via Admin"),
            "specs": data.get("specs", {}),  # <--- The 'Messy' Data
            "created_at": datetime.now()
        }

        # 2. Insert into Mongo (Primary)
        result = mongo.db.products.insert_one(product_doc)
        new_id = str(result.inserted_id)

        # 3. Insert into SQL (Secondary - Strict)
        # We try/except here because if SQL fails, we technically have a "Ghost Product".
        try:
            new_inventory = Inventory(
                product_id=new_id, 
                stock=int(stock), 
                last_updated=datetime.now()
            )
            sql_db.session.add(new_inventory)
            sql_db.session.commit()
        except SQLAlchemyError as e:
            # Rollback Strategy: In a real production app, we would delete the 
            # Mongo document here to ensure consistency.
            sql_db.session.rollback()
            mongo.db.products.delete_one({"_id": result.inserted_id})
            raise e

        return {**product_doc, "_id": new_id, "stock": stock}

    @staticmethod
    def update_product(product_id: str, field: str, value: Union[str, int, float]) -> Union[str, int, float]:
        """
        Updates data in the correct database based on the field.
        - 'stock' -> Updates SQL
        - 'price/name/etc' -> Updates Mongo
        """
        # A. Inventory Update (Strict Transaction)
        if field == "stock":
            inventory = Inventory.query.get(product_id)
            if inventory:
                inventory.stock = int(value)
                inventory.last_updated = datetime.utcnow()
                sql_db.session.commit()
                return inventory.stock
            return None

        # B. Catalog Update (Flexible Document)
        elif field == "price":
            new_price = float(value)
            mongo.db.products.update_one(
                {"_id": ObjectId(product_id)}, 
                {"$set": {"price": new_price}}
            )
            return new_price
        
        # Generic Mongo Update
        else:
            mongo.db.products.update_one(
                {"_id": ObjectId(product_id)}, 
                {"$set": {field: value}}
            )
            return value

    @staticmethod
    def delete_product(product_id: str) -> bool:
        """
        Removes the product from BOTH worlds.
        """
        # 1. Remove Strict Record First (SQL)
        Inventory.query.filter_by(product_id=product_id).delete()
        sql_db.session.commit()

        # 2. Remove Flexible Record (Mongo)
        mongo.db.products.delete_one({"_id": ObjectId(product_id)})
        return True

    # --- READS (The "Hybrid Join" Logic) ---

    @staticmethod
    def get_catalog(
            page: int = 1,
            per_page: Optional[int] = 9,
            search_query: Optional[str] = None,
            category: Optional[str] = None,
            spec_filters: Optional[Dict[str, List[str]]] = None
        ) -> Tuple[List[Dict[str, Any]], int]:
        """
        The Master Query.
        1. Filters documents in Mongo.
        2. Fetches matching Inventory from SQL.
        3. Merges them into a single list.
        """
        if per_page is None:
            per_page = current_app.config.get("PRODUCTS_PER_PAGE", 9)

        # 1. Build MongoDB Query
        mongo_filter: Dict[str, Any] = {}
        if search_query:
            mongo_filter["name"] = {"$regex": search_query, "$options": "i"}
        if category:
            mongo_filter["category"] = category
        
        # Add Dynamic Spec Filters (The "NoSQL Superpower")
        if spec_filters:
            for key, values in spec_filters.items():
                if values:
                    # Logic: specs.RAM IN ['16GB', '32GB']
                    mongo_filter[f"specs.{key}"] = {"$in": values}

        # 2. Fetch from Mongo (Pagination)
        total_count: int = mongo.db.products.count_documents(mongo_filter)
        skip: int = (page - 1) * per_page
        
        cursor: Any = mongo.db.products.find(mongo_filter).sort("created_at", -1)
        products: List[Dict[str, Any]] = list(cursor.skip(skip).limit(per_page))

        # 3. The "Application-Side Join"
        if products:
            # A. Extract IDs
            p_ids = [str(p["_id"]) for p in products]
            
            # B. Query SQL (One fast query, not N+1)
            inventory_records = Inventory.query.filter(Inventory.product_id.in_(p_ids)).all()
            inventory_map = {inv.product_id: inv.stock for inv in inventory_records}

            # C. Merge
            for p in products:
                p["_id"] = str(p["_id"])
                p["stock"] = inventory_map.get(p["_id"], 0)

        return products, total_count

    @staticmethod
    def get_admin_catalog(
            page: int = 1,
            per_page: Optional[int] = 9,
            search_query: Optional[str] = ""
        ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Dedicated Admin Query. 
        Broader search (Name OR Desc OR Category) + Automatic Stock Attach.
        """
        # 1. Build Broad Query
        query_filter = {}
        if search_query:
            query_filter["$or"] = [
                {"name": {"$regex": search_query, "$options": "i"}},
                {"description": {"$regex": search_query, "$options": "i"}},
                {"category": {"$regex": search_query, "$options": "i"}},
            ]

        # 2. Fetch Mongo
        total_count = mongo.db.products.count_documents(query_filter)
        skip = (page - 1) * per_page
        cursor = mongo.db.products.find(query_filter).sort("created_at", -1)
        products = list(cursor.skip(skip).limit(per_page))

        # 3. Attach Stock (Reuse Logic)
        if products:
            p_ids = [str(p["_id"]) for p in products]
            inventory_records = Inventory.query.filter(Inventory.product_id.in_(p_ids)).all()
            stock_map = {inv.product_id: inv.stock for inv in inventory_records}
            
            for p in products:
                p["_id"] = str(p["_id"])
                p["stock"] = stock_map.get(p["_id"], 0)

        return products, total_count

    @staticmethod
    def get_product_details(product_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches a single product by ID, merging data from both DBs.
        """
        try:
            oid = ObjectId(product_id)
        except:
            return None

        # 1. Fetch Mongo Document
        product = mongo.db.products.find_one({"_id": oid})
        if not product:
            return None

        # 2. Fetch SQL Record
        pid_str = str(product["_id"])
        inventory = Inventory.query.get(pid_str)

        # 3. Merge
        product["_id"] = pid_str
        product["stock"] = inventory.stock if inventory else 0

        return product

    @staticmethod
    def get_facets(category=None) -> Tuple[List[str], Dict[str, List[str]]]:
        """
        Returns available categories and dynamic spec filters for the sidebar.
        This uses Mongo Aggregation pipelines.
        """
        # 1. All Categories
        all_categories = sorted(mongo.db.products.distinct("category"))

        # 2. Dynamic Specs (Only if a category is selected)
        active_facets = {}
        if category:
            pipeline = [
                {"$match": {"category": category}},
                {"$project": {"specs": {"$objectToArray": "$specs"}}},
                {"$unwind": "$specs"},
                {"$group": {"_id": "$specs.k", "values": {"$addToSet": "$specs.v"}}},
            ]
            results = mongo.db.products.aggregate(pipeline)

            for r in results:
                if len(r["values"]) > 1:
                    active_facets[r["_id"]] = sorted(list(r["values"]))

        return all_categories, active_facets

    # --- ATOMIC STATS (For Dashboard) ---
    
    @staticmethod
    def count_products() -> int:
        return mongo.db.products.count_documents({})

    @staticmethod
    def get_category_breakdown() -> List[Dict[str, Any]]:
        pipeline = [
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        return list(mongo.db.products.aggregate(pipeline))
