from decimal import Decimal
from typing import Any, NotRequired, TypedDict


class ProductSnapshot(TypedDict):
    """Catalog-owned fields copied into carts and completed orders."""

    _id: str
    name: str
    price: str
    image: str
    specs: dict[str, Any]


class CatalogProduct(ProductSnapshot, total=False):
    """Normalized product returned to storefront and admin consumers."""

    category: str
    description: str
    stock: int
    created_at: Any
    rating: float
    reviews_count: int


class CartItem(TypedDict):
    """Redis-owned cart snapshot plus the user's requested quantity."""

    product_id: str
    name: str
    price: str
    image: str
    specs: dict[str, Any]
    qty: int


class CartViewItem(CartItem):
    """Cart item enriched with an exact request-time subtotal."""

    subtotal: Decimal


class CheckoutCustomer(TypedDict):
    """Unvalidated checkout fields accepted at the HTTP boundary."""

    name: NotRequired[str | None]
    email: NotRequired[str | None]
    address: NotRequired[str | None]
    city: NotRequired[str | None]
    zip: NotRequired[str | None]
