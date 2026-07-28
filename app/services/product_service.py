import re
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from flask import current_app
from sqlalchemy import select

from app.extensions import get_mongo_db, sql_db
from app.models import Inventory


class ProductService:
    """Coordinate MongoDB catalog data with PostgreSQL inventory."""

    CATALOG_EDITABLE_FIELDS = {"name", "category", "description", "image"}

    @staticmethod
    def _inventory_by_product(product_ids: list[str]) -> dict[str, Inventory]:
        if not product_ids:
            return {}

        statement = select(Inventory).where(Inventory.product_id.in_(product_ids))
        records = sql_db.session.scalars(statement).all()
        return {record.product_id: record for record in records}

    @staticmethod
    def create_product(
        data: dict[str, Any],
        stock: int | str,
    ) -> dict[str, Any]:
        stock_value = int(stock)
        price = float(data.get("price", 0))
        if stock_value < 0:
            raise ValueError("Stock cannot be negative.")
        if price < 0:
            raise ValueError("Price cannot be negative.")

        product_document: dict[str, Any] = {
            "name": data.get("name"),
            "price": price,
            "category": data.get("category"),
            "image": data.get("image") or "https://placehold.co/600x400",
            "description": data.get("description") or "Added via Admin",
            "specs": data.get("specs", {}),
            "created_at": datetime.now(timezone.utc),
        }

        products = get_mongo_db().products
        result = products.insert_one(product_document)
        product_id = str(result.inserted_id)

        try:
            sql_db.session.add(Inventory(product_id=product_id, stock=stock_value))
            sql_db.session.commit()
        except Exception:
            sql_db.session.rollback()
            products.delete_one({"_id": result.inserted_id})
            raise

        return {
            **product_document,
            "_id": product_id,
            "stock": stock_value,
        }

    @staticmethod
    def update_product(
        product_id: str,
        field: str,
        value: str | int | float,
    ) -> str | int | float | None:
        if field == "stock":
            stock = int(value)
            if stock < 0:
                raise ValueError("Stock cannot be negative.")

            inventory = sql_db.session.get(Inventory, product_id)
            if not inventory:
                return None

            inventory.stock = stock
            inventory.last_updated = datetime.now(timezone.utc)
            sql_db.session.commit()
            return inventory.stock

        if not ObjectId.is_valid(product_id):
            raise ValueError("Invalid product ID.")

        products = get_mongo_db().products
        if field == "price":
            price = float(value)
            if price < 0:
                raise ValueError("Price cannot be negative.")
            products.update_one(
                {"_id": ObjectId(product_id)},
                {"$set": {"price": price}},
            )
            return price

        if field not in ProductService.CATALOG_EDITABLE_FIELDS:
            raise ValueError(f"Product field {field!r} cannot be edited.")

        products.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": {field: value}},
        )
        return value

    @staticmethod
    def delete_product(product_id: str) -> bool:
        if not ObjectId.is_valid(product_id):
            raise ValueError("Invalid product ID.")

        inventory = sql_db.session.get(Inventory, product_id)
        if inventory:
            sql_db.session.delete(inventory)
            sql_db.session.commit()

        get_mongo_db().products.delete_one({"_id": ObjectId(product_id)})
        return True

    @staticmethod
    def get_catalog(
        page: int = 1,
        per_page: int | None = 9,
        search_query: str | None = None,
        category: str | None = None,
        spec_filters: dict[str, list[str]] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if per_page is None:
            per_page = int(current_app.config.get("PRODUCTS_PER_PAGE", 9))

        mongo_filter: dict[str, Any] = {}
        if search_query:
            mongo_filter["name"] = {
                "$regex": re.escape(search_query),
                "$options": "i",
            }
        if category:
            mongo_filter["category"] = category

        if spec_filters:
            for key, values in spec_filters.items():
                if values:
                    mongo_filter[f"specs.{key}"] = {"$in": values}

        products_collection = get_mongo_db().products
        total_count = products_collection.count_documents(mongo_filter)
        skip = (page - 1) * per_page
        cursor = products_collection.find(mongo_filter).sort("created_at", -1)
        products = list(cursor.skip(skip).limit(per_page))

        inventory = ProductService._inventory_by_product(
            [str(product["_id"]) for product in products]
        )
        for product in products:
            product_id = str(product["_id"])
            product["_id"] = product_id
            product["stock"] = (
                inventory[product_id].stock if product_id in inventory else 0
            )

        return products, total_count

    @staticmethod
    def get_admin_catalog(
        page: int = 1,
        per_page: int | None = 9,
        search_query: str | None = "",
    ) -> tuple[list[dict[str, Any]], int]:
        if per_page is None:
            per_page = int(current_app.config.get("ADMIN_PER_PAGE", 20))

        query_filter: dict[str, Any] = {}
        if search_query:
            escaped_query = re.escape(search_query)
            query_filter["$or"] = [
                {"name": {"$regex": escaped_query, "$options": "i"}},
                {
                    "description": {
                        "$regex": escaped_query,
                        "$options": "i",
                    }
                },
                {
                    "category": {
                        "$regex": escaped_query,
                        "$options": "i",
                    }
                },
            ]

        products_collection = get_mongo_db().products
        total_count = products_collection.count_documents(query_filter)
        skip = (page - 1) * per_page
        cursor = products_collection.find(query_filter).sort("created_at", -1)
        products = list(cursor.skip(skip).limit(per_page))

        inventory = ProductService._inventory_by_product(
            [str(product["_id"]) for product in products]
        )
        for product in products:
            product_id = str(product["_id"])
            product["_id"] = product_id
            product["stock"] = (
                inventory[product_id].stock if product_id in inventory else 0
            )

        return products, total_count

    @staticmethod
    def get_product_details(
        product_id: str,
    ) -> dict[str, Any] | None:
        if not ObjectId.is_valid(product_id):
            return None

        product = get_mongo_db().products.find_one({"_id": ObjectId(product_id)})
        if not product:
            return None

        product_id = str(product["_id"])
        inventory = sql_db.session.get(Inventory, product_id)
        product["_id"] = product_id
        product["stock"] = inventory.stock if inventory else 0
        return product

    @staticmethod
    def get_facets(
        category: str | None = None,
    ) -> tuple[list[str], dict[str, list[Any]]]:
        products = get_mongo_db().products
        all_categories = sorted(products.distinct("category"))

        active_facets: dict[str, list[Any]] = {}
        if category:
            pipeline: list[dict[str, Any]] = [
                {"$match": {"category": category}},
                {"$project": {"specs": {"$objectToArray": "$specs"}}},
                {"$unwind": "$specs"},
                {
                    "$group": {
                        "_id": "$specs.k",
                        "values": {"$addToSet": "$specs.v"},
                    }
                },
            ]
            for result in products.aggregate(pipeline):
                if len(result["values"]) > 1:
                    active_facets[result["_id"]] = sorted(result["values"])

        return all_categories, active_facets

    @staticmethod
    def count_products() -> int:
        return get_mongo_db().products.count_documents({})

    @staticmethod
    def get_category_breakdown() -> list[dict[str, Any]]:
        pipeline: list[dict[str, Any]] = [
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        return list(get_mongo_db().products.aggregate(pipeline))
