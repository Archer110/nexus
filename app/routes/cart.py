from decimal import Decimal
from typing import Any

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.money import money, money_value
from app.services.order_service import OrderService
from app.services.product_service import ProductService

cart_bp = Blueprint("cart", __name__, url_prefix="/cart")


def _cart_context() -> tuple[list[dict[str, Any]], Decimal]:
    cart: list[dict[str, Any]] = []
    total = Decimal("0.00")

    for session_item in session.get("cart", []):
        item = dict(session_item)
        item["price"] = money(item["price"])
        item["subtotal"] = item["price"] * int(item["qty"])
        total += item["subtotal"]
        cart.append(item)

    return cart, total


def _refresh_cart_from_catalog() -> None:
    cart = session.get("cart", [])
    product_ids = [str(item["product_id"]) for item in cart]
    products = ProductService.get_products_by_ids(product_ids)

    for item in cart:
        product = products.get(str(item["product_id"]))
        if not product:
            continue
        item.update(
            {
                "name": product["name"],
                "price": money_value(product["price"]),
                "image": product["image"],
                "specs": product.get("specs", {}),
            }
        )

    if cart:
        session.modified = True


def _render_checkout_summary():
    cart, total = _cart_context()
    return render_template(
        "partials/checkout_summary.html",
        items=cart,
        total=total,
        oob=True,
    )


def _render_cart_drawer(error=None):
    cart, total = _cart_context()
    return render_template(
        "partials/cart_drawer.html",
        cart=cart,
        total=total,
        cart_error=error,
    )


def _render_cart_error(message):
    target = request.headers.get("HX-Target")
    if target == "checkout-summary":
        cart, total = _cart_context()
        return render_template(
            "partials/checkout_summary.html",
            items=cart,
            total=total,
            oob=True,
            cart_error=message,
        )
    if request.headers.get("HX-Request"):
        return _render_cart_drawer(error=message)

    flash(message, "error")
    return redirect(request.referrer or url_for("store.index"))


@cart_bp.route("/add/<product_id>", methods=["POST"])
def add_to_cart(product_id):
    """
    Adds an item to the Server-Side Session Cart.
    Architecture:
    - Fetches authoritative data from ProductService (Price/Name).
    - NEVER trusts the client to send the price.
    """
    if "cart" not in session:
        session["cart"] = []

    product = ProductService.get_product_details(product_id)
    if not product:
        return _render_cart_error("This product is no longer available.")

    available_stock = int(product.get("stock", 0))
    if available_stock < 1:
        return _render_cart_error(f"{product['name']} is out of stock.")

    cart = session["cart"]
    product_price = money_value(product["price"])
    found = False

    # 1. Check if already in cart (Update Qty)
    for item in cart:
        if item["product_id"] == product_id:
            if item["qty"] >= available_stock:
                return _render_cart_error(
                    f"Only {available_stock} unit(s) of {product['name']} are available."
                )
            item["qty"] += 1
            item.update(
                {
                    "name": product["name"],
                    "price": product_price,
                    "image": product["image"],
                    "specs": product.get("specs", {}),
                }
            )
            found = True
            break

    # 2. Add New Item (Fetch details from DB)
    if not found:
        # This snapshot remains temporary until carts move to Redis.
        cart.append(
            {
                "product_id": str(product["_id"]),
                "name": product["name"],
                "price": product_price,
                "image": product["image"],
                "specs": product.get("specs", {}),
                "qty": 1,
            }
        )

    session.modified = True

    # --- HTMX RESPONSE ---
    # Return the 'cart_drawer.html' fragment to update the sidebar instantly
    if request.headers.get("HX-Request"):
        return _render_cart_drawer()

    return redirect(request.referrer or url_for("store.index"))


@cart_bp.route("/update/<product_id>/<action>", methods=["POST"])
def update_quantity(product_id, action):
    """
    Increments/Decrements quantity in session.
    """
    if action not in {"increase", "decrease"}:
        return _render_cart_error("Invalid cart action.")

    cart = session.get("cart", [])

    for item in cart:
        if item["product_id"] == product_id:
            if action == "increase":
                product = ProductService.get_product_details(product_id)
                if not product:
                    return _render_cart_error("This product is no longer available.")
                available_stock = int(product.get("stock", 0))
                if item["qty"] >= available_stock:
                    return _render_cart_error(
                        f"Only {available_stock} unit(s) of {product['name']} are available."
                    )
                item["qty"] += 1
            elif action == "decrease":
                item["qty"] -= 1
                if item["qty"] < 1:
                    item["qty"] = 1  # Use 'remove' to delete
            break

    session.modified = True

    # Smart Response: Update the Drawer OR the Checkout Page depending on source
    target = request.headers.get("HX-Target")
    if target == "cart-drawer-content":
        return _render_cart_drawer()
    if target == "checkout-summary":
        return _render_checkout_summary()

    # Non-HTMX fallback for regular form posts.
    return redirect(request.referrer or url_for("store.index"))


@cart_bp.route("/remove/<product_id>", methods=["DELETE", "GET"])
def remove_from_cart(product_id):
    if "cart" in session:
        session["cart"] = [
            item for item in session["cart"] if item["product_id"] != product_id
        ]
        session.modified = True

    target = request.headers.get("HX-Target")
    if target == "checkout-summary":
        return _render_checkout_summary()
    if request.headers.get("HX-Request"):
        return _render_cart_drawer()

    return redirect(url_for("store.index"))


@cart_bp.route("/checkout-page")
def checkout_page():
    """
    Renders the Checkout UI.
    Calculates totals on the fly from the session data.
    """
    _refresh_cart_from_catalog()
    cart, total = _cart_context()

    return render_template("checkout.html", items=cart, total=total)


@cart_bp.route("/checkout", methods=["POST"])
def checkout():
    """
    The Final Commit.
    Passes the session cart to the OrderService for the ACID transaction.
    """
    cart = session.get("cart", [])
    if not cart:
        flash("Cart is empty", "error")
        return redirect(url_for("store.index"))

    # 1. Parse Form Data
    customer_data = {
        "name": request.form.get("name"),
        "email": request.form.get("email"),
        "address": request.form.get("address"),
        "city": request.form.get("city"),
        "zip": request.form.get("zip"),
    }

    # 2. Call Service (The "Atomic" Operation)
    try:
        new_order = OrderService.create_order(customer_data, cart)

        # 3. Success! Clear Cart
        session.pop("cart", None)
        return render_template("success.html", order=new_order)

    except ValueError as e:
        # Catch "Out of Stock" or Logic Errors
        flash(str(e), "error")
        return redirect(url_for("cart.checkout_page"))

    except Exception:
        # Catch unexpected DB errors
        flash("An error occurred processing your order. Please try again.", "error")
        return redirect(url_for("cart.checkout_page"))
