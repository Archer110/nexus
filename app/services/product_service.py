import logging
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast

from bson import ObjectId
from bson.decimal128 import Decimal128
from flask import current_app
from sqlalchemy import select

from app.contracts import CatalogProduct
from app.extensions import get_mongo_db, sql_db
from app.models import Inventory
from app.money import bson_money, money_value
from app.validation import (
    is_safe_spec_key,
    non_negative_int,
    optional_text,
    positive_int,
    product_specs,
    required_text,
    search_term,
)
from app.validation import (
    spec_filters as normalize_spec_filters,
)

logger = logging.getLogger(__name__)


class ProductService:
    """Coordinate MongoDB catalog data with PostgreSQL inventory."""

    CATALOG_EDITABLE_FIELDS = {"name", "category", "description", "image"}
    MAX_PRICE = Decimal("9999999999.99")
    DEFAULT_IMAGE = "https://placehold.co/600x400"

    @staticmethod
    def _normalize_product(product: dict[str, Any]) -> CatalogProduct:
        normalized = dict(product)
        normalized["_id"] = str(product["_id"])
        name = str(product.get("name") or "").strip() or "Unknown Product"
        image = str(product.get("image") or "").strip() or ProductService.DEFAULT_IMAGE
        normalized["name"] = name[:200]
        normalized["price"] = money_value(product["price"])
        normalized["image"] = image[:500]
        specs = product.get("specs")
        normalized["specs"] = dict(specs) if isinstance(specs, Mapping) else {}
        return cast(CatalogProduct, normalized)

    @staticmethod
    def _normalize_if_valid(product: dict[str, Any]) -> CatalogProduct | None:
        try:
            return ProductService._normalize_product(product)
        except (KeyError, TypeError, ValueError) as error:
            logger.warning(
                "Skipping malformed catalog product %r: %s",
                product.get("_id"),
                error,
            )
            return None

    @staticmethod
    def _price(value: object) -> Decimal128:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Price is required.")
        price = bson_money(value)
        if price.to_decimal() > ProductService.MAX_PRICE:
            raise ValueError("Price is too large.")
        return price

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
    ) -> CatalogProduct:
        stock_value = non_negative_int(stock, "Stock")
        price = ProductService._price(data.get("price"))

        product_document: dict[str, Any] = {
            "name": required_text(data.get("name"), "Product name", 200),
            "price": price,
            "category": required_text(data.get("category"), "Category", 100),
            "image": optional_text(data.get("image"), "Image URL", 500)
            or ProductService.DEFAULT_IMAGE,
            "description": optional_text(data.get("description"), "Description", 5000)
            or "Added via Admin",
            "specs": product_specs(data.get("specs", {})),
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

        product = ProductService._normalize_product(
            {**product_document, "_id": product_id}
        )
        product["stock"] = stock_value
        return product

    @staticmethod
    def update_product(
        product_id: str,
        field: str | None,
        value: object,
    ) -> str | int | float | None:
        editable_fields = ProductService.CATALOG_EDITABLE_FIELDS | {"price", "stock"}
        if field not in editable_fields:
            raise ValueError("Unsupported product field.")
        if not ObjectId.is_valid(product_id):
            raise ValueError("Invalid product ID.")

        if field == "stock":
            stock = non_negative_int(value, "Stock")

            inventory = sql_db.session.get(Inventory, product_id)
            if not inventory:
                return None

            inventory.stock = stock
            inventory.last_updated = datetime.now(timezone.utc)
            sql_db.session.commit()
            return inventory.stock

        products = get_mongo_db().products
        if field == "price":
            price = ProductService._price(value)
            result = products.update_one(
                {"_id": ObjectId(product_id)},
                {"$set": {"price": price}},
            )
            if result.matched_count == 0:
                return None
            return money_value(price)

        if field in {"name", "category"}:
            maximum = 200 if field == "name" else 100
            normalized_value = required_text(value, field.title(), maximum)
        elif field == "image":
            normalized_value = (
                optional_text(value, "Image URL", 500) or ProductService.DEFAULT_IMAGE
            )
        else:
            normalized_value = optional_text(value, "Description", 5000)

        result = products.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": {field: normalized_value}},
        )
        if result.matched_count == 0:
            return None
        return normalized_value

    @staticmethod
    def delete_product(product_id: str) -> bool:
        if not ObjectId.is_valid(product_id):
            raise ValueError("Invalid product ID.")

        object_id = ObjectId(product_id)
        products = get_mongo_db().products
        product_document = products.find_one({"_id": object_id})
        if product_document is None:
            return False

        inventory = sql_db.session.get(Inventory, product_id)
        if inventory:
            sql_db.session.delete(inventory)

        mongo_deleted = False
        try:
            result = products.delete_one({"_id": object_id})
            mongo_deleted = bool(result.deleted_count)
            if not mongo_deleted:
                sql_db.session.rollback()
                return False
            if inventory:
                sql_db.session.commit()
            return True
        except Exception:
            sql_db.session.rollback()
            if mongo_deleted:
                try:
                    products.replace_one(
                        {"_id": object_id},
                        product_document,
                        upsert=True,
                    )
                except Exception:
                    logger.exception(
                        "Failed to restore catalog product %s after SQL rollback.",
                        product_id,
                    )
            raise

    @staticmethod
    def get_catalog(
        page: int = 1,
        per_page: int | None = 9,
        search_query: str | None = None,
        category: str | None = None,
        spec_filters: dict[str, list[str]] | None = None,
    ) -> tuple[list[CatalogProduct], int]:
        if per_page is None:
            per_page = int(current_app.config.get("PRODUCTS_PER_PAGE", 9))
        page = positive_int(page, "Page")
        per_page = positive_int(per_page, "Page size")
        search_query = search_term(search_query)
        category = search_term(category)

        mongo_filter: dict[str, Any] = {}
        if search_query:
            mongo_filter["name"] = {
                "$regex": re.escape(search_query),
                "$options": "i",
            }
        if category:
            mongo_filter["category"] = category

        filters = normalize_spec_filters(spec_filters or {})
        for key, values in filters.items():
            mongo_filter[f"specs.{key}"] = {"$in": values}

        products_collection = get_mongo_db().products
        total_count = products_collection.count_documents(mongo_filter)
        skip = (page - 1) * per_page
        cursor = products_collection.find(mongo_filter).sort("created_at", -1)
        products = list(cursor.skip(skip).limit(per_page))

        inventory = ProductService._inventory_by_product(
            [str(product["_id"]) for product in products]
        )
        normalized_products: list[CatalogProduct] = []
        for product in products:
            normalized = ProductService._normalize_if_valid(product)
            if normalized is None:
                continue
            product_id = normalized["_id"]
            normalized["stock"] = (
                inventory[product_id].stock if product_id in inventory else 0
            )
            normalized_products.append(normalized)

        return normalized_products, total_count

    @staticmethod
    def get_admin_catalog(
        page: int = 1,
        per_page: int | None = 9,
        search_query: str | None = "",
    ) -> tuple[list[CatalogProduct], int]:
        if per_page is None:
            per_page = int(current_app.config.get("ADMIN_PER_PAGE", 20))
        page = positive_int(page, "Page")
        per_page = positive_int(per_page, "Page size")
        search_query = search_term(search_query)

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
        normalized_products: list[CatalogProduct] = []
        for product in products:
            normalized = ProductService._normalize_if_valid(product)
            if normalized is None:
                continue
            product_id = normalized["_id"]
            normalized["stock"] = (
                inventory[product_id].stock if product_id in inventory else 0
            )
            normalized_products.append(normalized)

        return normalized_products, total_count

    @staticmethod
    def get_product_details(
        product_id: str,
    ) -> CatalogProduct | None:
        if not ObjectId.is_valid(product_id):
            return None

        product_document = get_mongo_db().products.find_one(
            {"_id": ObjectId(product_id)}
        )
        if not product_document:
            return None

        product = ProductService._normalize_if_valid(product_document)
        if product is None:
            return None
        product_id = product["_id"]
        inventory = sql_db.session.get(Inventory, product_id)
        product["stock"] = inventory.stock if inventory else 0
        return product

    @staticmethod
    def get_products_by_ids(
        product_ids: list[str],
    ) -> dict[str, CatalogProduct]:
        """Fetch authoritative catalog snapshots for cart reconciliation."""
        object_ids = [
            ObjectId(product_id)
            for product_id in set(product_ids)
            if ObjectId.is_valid(product_id)
        ]
        if not object_ids:
            return {}

        products = get_mongo_db().products.find({"_id": {"$in": object_ids}})
        normalized: dict[str, CatalogProduct] = {}
        for product_document in products:
            product = ProductService._normalize_if_valid(product_document)
            if product is None:
                continue
            normalized[product["_id"]] = product
        return normalized

    @staticmethod
    def get_facets(
        category: str | None = None,
    ) -> tuple[list[str], dict[str, list[Any]]]:
        products = get_mongo_db().products
        all_categories = sorted(
            {
                value.strip()
                for value in products.distinct("category")
                if isinstance(value, str) and value.strip()
            }
        )

        active_facets: dict[str, list[Any]] = {}
        category = search_term(category)
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
                key = result.get("_id")
                values = result.get("values")
                if (
                    not isinstance(key, str)
                    or not is_safe_spec_key(key)
                    or not isinstance(values, list)
                    or len(values) < 2
                ):
                    continue
                active_facets[key] = sorted(values, key=lambda value: str(value))

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
