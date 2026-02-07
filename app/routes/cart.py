from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.services.order_service import OrderService
from app.services.product_service import ProductService

cart_bp = Blueprint("cart", __name__, url_prefix="/cart")


@cart_bp.route("/add/<product_id>", methods=["POST"])
def add_to_cart(product_id):
    if "cart" not in session:
        session["cart"] = []

    cart = session["cart"]
    found = False

    # 1. Update Existing
    for item in cart:
        if item["product_id"] == product_id:
            item["qty"] += 1
            found = True
            break

    # 2. Add New
    if not found:
        p = ProductService.get_product_by_id(product_id)
        if p:
            cart.append(
                {
                    "product_id": str(p["_id"]),
                    "name": p["name"],
                    "price": p["price"],
                    "image": p["image"],
                    "specs": p.get("specs", {}),
                    "qty": 1,
                }
            )

    session.modified = True

    # --- HTMX RESPONSE ---
    # Return the drawer HTML so it can be swapped in place
    if request.headers.get("HX-Request"):
        return render_template("partials/cart_drawer.html", cart=cart)

    # Fallback
    return redirect(request.referrer or url_for("store.index"))


@cart_bp.route("/remove/<product_id>", methods=["DELETE", "GET"])
def remove_from_cart(product_id):
    if "cart" in session:
        session["cart"] = [
            item for item in session["cart"] if item["product_id"] != product_id
        ]
        session.modified = True

    # --- HTMX RESPONSE ---
    if request.headers.get("HX-Request"):
        return render_template("partials/cart_drawer.html", cart=session["cart"])

    return redirect(url_for("store.index"))


@cart_bp.route("/checkout-page")
def checkout_page():
    cart = session.get("cart", [])

    # Prepare data for the template
    items = []
    total = 0

    for item in cart:
        subtotal = item["price"] * item["qty"]
        total += subtotal

        # Create a view-model for the template
        items.append(
            {
                "product_id": item["product_id"],
                "name": item["name"],
                "image": item["image"],
                "qty": item["qty"],
                "price": item["price"],
                "subtotal": subtotal,
                "specs": item.get("specs", {}),
            }
        )

    return render_template("checkout.html", items=items, total=total)


@cart_bp.route("/checkout", methods=["POST"])
def checkout():
    cart = session.get("cart", [])
    if not cart:
        flash("Cart is empty", "error")
        return redirect(url_for("store.index"))

    customer_data = {
        "name": request.form.get("name"),
        "email": request.form.get("email"),
        "address": request.form.get("address"),
        "city": request.form.get("city"),
        "zip": request.form.get("zip"),
    }

    new_order = OrderService.create_order(customer_data, cart)
    session.pop("cart", None)

    return render_template("success.html", order=new_order)


@cart_bp.route("/update/<product_id>/<action>", methods=["POST"])
def update_quantity(product_id, action):
    cart = session.get("cart", [])

    for item in cart:
        if item["product_id"] == product_id:
            if action == "increase":
                item["qty"] += 1
            elif action == "decrease":
                item["qty"] -= 1
                if item["qty"] < 1:
                    item["qty"] = 1  # Prevent negative, use delete button to remove
            break

    session.modified = True

    # SMART RESPONSE:
    # If the request comes from the Drawer (HTMX), just refresh the drawer.
    # Otherwise (Checkout page), redirect to refresh the whole page (totals, etc).
    if request.headers.get("HX-Target") == "cart-drawer-content":
        return render_template("partials/cart_drawer.html", cart=cart)

    return redirect(request.referrer or url_for("store.index"))
