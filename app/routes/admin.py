import json
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

# THE CRITICAL CHANGE: 
# We import Services, NOT Models or Database extensions.
from app.services.order_service import OrderService
from app.services.product_service import ProductService

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# --- AUTH DECORATOR ---
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin.admin_login"))
        return f(*args, **kwargs)
    return decorated

# --- LOGIN/LOGOUT ---
@admin_bp.route("/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == "admin" and password == "secret":
            session["admin_logged_in"] = True
            return redirect(url_for("admin.dashboard"))
        else:
            error = "Invalid credentials"
    return render_template("admin/login.html", error=error)

@admin_bp.route("/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin.admin_login"))


# --- DASHBOARD (The "Orchestrator") ---
@admin_bp.route("/")
@admin_required
def dashboard():
    """
    Orchestrates data from multiple services to build the dashboard view.
    It doesn't know where the data comes from (SQL or Mongo).
    """
    # 1. Ask OrderService for Financials
    revenue = OrderService.get_total_revenue()
    orders_count = OrderService.count_orders()
    recent_orders = OrderService.get_recent_orders(limit=10)

    # 2. Ask ProductService for Catalog Stats
    products_count = ProductService.count_products()
    cat_stats = ProductService.get_category_breakdown()

    return render_template(
        "admin/dashboard.html",
        revenue=round(revenue, 2),
        o_count=orders_count,
        p_count=products_count,
        orders=recent_orders,
        cat_stats=cat_stats,
    )


# --- PRODUCT MANAGEMENT ---
@admin_bp.route("/products")
@admin_required
def admin_products():
    page = int(request.args.get("page", 1))
    per_page = current_app.config.get("ADMIN_PER_PAGE", 10)
    search_query = request.args.get("q", "")

    # Call the specialized Admin Catalog method
    products, total_products = ProductService.get_admin_catalog(
        page=page, 
        per_page=per_page, 
        search_query=search_query
    )

    # HTMX Support for search/pagination
    if request.headers.get("HX-Request"):
        return render_template("admin/partials/products_list.html", products=products)

    return render_template(
        "admin/products.html",
        products=products,
        page=page,
        total=total_products,
        per_page=per_page,
        q=search_query,
    )

@admin_bp.route("/products/add", methods=["POST"])
@admin_required
def admin_add_product():
    # 1. Parse JSON Specs (if any)
    try:
        specs = json.loads(request.form.get("specs_json", "{}"))
    except:
        specs = {}

    data = {
        "name": request.form.get("name"),
        "price": request.form.get("price"),
        "category": request.form.get("category"),
        "image": request.form.get("image"),
        "description": request.form.get("description"),
        "specs": specs,
    }
    stock = request.form.get("stock", 0)

    # 2. Delegate to Service
    new_product = ProductService.create_product(data, stock)

    # 3. Render Row (HTMX)
    return render_template("admin/partials/product_row.html", product=new_product)

@admin_bp.route("/products/update/<product_id>", methods=["POST"])
@admin_required
def admin_update_product(product_id):
    """
    Handles inline edits from the table (Stock, Price, etc).
    """
    field = request.args.get("field")
    value = request.form.get("value") or request.form.get(field)

    # The Service handles the logic of "Which DB do I update?"
    new_val = ProductService.update_product(product_id, field, value)

    if field == "price":
        return f"${new_val}"
    return f"{new_val}"

@admin_bp.route("/products/delete/<product_id>", methods=["DELETE"])
@admin_required
def admin_delete_product(product_id):
    ProductService.delete_product(product_id)
    return ""  # HTTP 200 OK


# --- ORDER MANAGEMENT ---
@admin_bp.route("/orders")
@admin_required
def admin_orders():
    search_query = request.args.get("q", "")

    orders = OrderService.get_orders(search_query)

    return render_template("admin/orders.html", orders=orders, q=search_query)

@admin_bp.route("/orders/update/<int:order_id>", methods=["POST"])
@admin_required
def update_order_status(order_id):
    new_status = request.form.get("status")
    
    order = OrderService.update_status(order_id, new_status)

    # Return the updated select dropdown (HTMX pattern)
    # (Simplified for brevity, assumes you have a macro or snippet for this)
    return render_template("admin/partials/order_status_select.html", order=order)
