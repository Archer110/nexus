from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.services.order_service import OrderService
from app.services.product_service import ProductService

cart_bp = Blueprint("cart", __name__, url_prefix="/cart")

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

    cart = session["cart"]
    found = False

    # 1. Check if already in cart (Update Qty)
    for item in cart:
        if item["product_id"] == product_id:
            item["qty"] += 1
            found = True
            break

    # 2. Add New Item (Fetch details from DB)
    if not found:
        p = ProductService.get_product_details(product_id)
        if p:
            # We store a "Snapshot" of the product in the session.
            # This makes rendering the cart fast (no DB queries needed).
            cart.append({
                "product_id": str(p["_id"]),
                "name": p["name"],
                "price": p["price"],      # Store price for display (Checkout will re-verify)
                "image": p["image"],
                "specs": p.get("specs", {}),
                "qty": 1,
            })

    session.modified = True

    # --- HTMX RESPONSE ---
    # Return the 'cart_drawer.html' fragment to update the sidebar instantly
    if request.headers.get("HX-Request"):
        return render_template("partials/cart_drawer.html", cart=cart)

    return redirect(request.referrer or url_for("store.index"))


@cart_bp.route("/update/<product_id>/<action>", methods=["POST"])
def update_quantity(product_id, action):
    """
    Increments/Decrements quantity in session.
    """
    cart = session.get("cart", [])

    for item in cart:
        if item["product_id"] == product_id:
            if action == "increase":
                item["qty"] += 1
            elif action == "decrease":
                item["qty"] -= 1
                if item["qty"] < 1:
                    item["qty"] = 1 # Use 'remove' to delete
            break

    session.modified = True

    # Smart Response: Update the Drawer OR the Checkout Page depending on source
    if request.headers.get("HX-Target") == "cart-drawer-content":
        return render_template("partials/cart_drawer.html", cart=cart)
    
    # If on checkout page, refresh to update totals
    return redirect(request.referrer or url_for("store.index"))


@cart_bp.route("/remove/<product_id>", methods=["DELETE", "GET"])
def remove_from_cart(product_id):
    if "cart" in session:
        session["cart"] = [
            item for item in session["cart"] 
            if item["product_id"] != product_id
        ]
        session.modified = True

    if request.headers.get("HX-Request"):
        return render_template("partials/cart_drawer.html", cart=session.get("cart", []))

    return redirect(url_for("store.index"))


@cart_bp.route("/checkout-page")
def checkout_page():
    """
    Renders the Checkout UI.
    Calculates totals on the fly from the session data.
    """
    cart = session.get("cart", [])
    total = sum(item["price"] * item["qty"] for item in cart)

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
