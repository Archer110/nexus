from decimal import Decimal
from typing import cast

from flask import (
    Blueprint,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.contracts import CartItem, CartViewItem, CheckoutCustomer
from app.money import money, money_value
from app.services.order_service import OrderService
from app.services.product_service import ProductService
from app.validation import safe_redirect_target, session_cart

cart_bp = Blueprint("cart", __name__, url_prefix="/cart")


def _store_redirect():
    return redirect(
        safe_redirect_target(
            request.referrer,
            request.host_url,
            url_for("store.index"),
        )
    )


def _session_cart() -> list[CartItem]:
    raw_cart = session.get("cart", [])
    cart = session_cart(raw_cart)
    if isinstance(raw_cart, list) and raw_cart == cart:
        return cast(list[CartItem], raw_cart)

    session["cart"] = cart
    session.modified = True
    return cart


def _cart_context() -> tuple[list[CartViewItem], Decimal]:
    cart: list[CartViewItem] = []
    total = Decimal("0.00")

    for session_item in _session_cart():
        item = cast(CartViewItem, dict(session_item))
        item["subtotal"] = money(item["price"]) * item["qty"]
        total += item["subtotal"]
        cart.append(item)

    return cart, total


def _refresh_cart_from_catalog() -> None:
    cart = _session_cart()
    product_ids = [str(item["product_id"]) for item in cart]
    products = ProductService.get_products_by_ids(product_ids)

    refreshed_cart: list[CartItem] = []
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
        refreshed_cart.append(item)

    if cart:
        session["cart"] = refreshed_cart
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
        response = make_response(
            render_template(
                "partials/checkout_summary.html",
                items=cart,
                total=total,
                oob=True,
                cart_error=message,
            ),
            400,
        )
        response.headers["X-Nexus-Swap-Error"] = "true"
        return response
    if request.headers.get("HX-Request"):
        response = make_response(_render_cart_drawer(error=message), 400)
        response.headers["X-Nexus-Swap-Error"] = "true"
        return response

    return message, 400


def _render_checkout_error(message: str, status_code: int):
    cart, total = _cart_context()
    return (
        render_template(
            "checkout.html",
            items=cart,
            total=total,
            errors=[message],
        ),
        status_code,
    )


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

    cart = _session_cart()
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
        # Redis owns this session snapshot; checkout still refreshes it from MongoDB.
        cart.append(
            CartItem(
                product_id=str(product["_id"]),
                name=product["name"],
                price=product_price,
                image=product["image"],
                specs=product.get("specs", {}),
                qty=1,
            )
        )

    session.modified = True

    # --- HTMX RESPONSE ---
    # Return the 'cart_drawer.html' fragment to update the sidebar instantly
    if request.headers.get("HX-Request"):
        return _render_cart_drawer()

    return _store_redirect()


@cart_bp.route("/update/<product_id>/<action>", methods=["POST"])
def update_quantity(product_id, action):
    """
    Increments/Decrements quantity in session.
    """
    if action not in {"increase", "decrease"}:
        return _render_cart_error("Invalid cart action.")

    cart = _session_cart()

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
    return _store_redirect()


@cart_bp.route("/remove/<product_id>", methods=["DELETE"])
def remove_from_cart(product_id):
    if "cart" in session:
        session["cart"] = [
            item for item in _session_cart() if item["product_id"] != product_id
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
    cart = _session_cart()
    if not cart:
        return _render_checkout_error("Cart is empty.", 400)

    # 1. Parse Form Data
    customer_data = CheckoutCustomer(
        name=request.form.get("name"),
        email=request.form.get("email"),
        address=request.form.get("address"),
        city=request.form.get("city"),
        zip=request.form.get("zip"),
    )

    # 2. Call Service (The "Atomic" Operation)
    try:
        new_order = OrderService.create_order(customer_data, cart)

        # 3. Success! Clear Cart
        session.pop("cart", None)
        return render_template("success.html", order=new_order)

    except ValueError as error:
        return _render_checkout_error(str(error), 400)

    except Exception:
        current_app.logger.exception("Unexpected checkout failure.")
        return _render_checkout_error(
            "An error occurred processing your order. Please try again.",
            500,
        )
