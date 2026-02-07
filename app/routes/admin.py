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

from app.extensions import mongo, sql_db
from app.models import Inventory, OrderSQL
from app.services.order_service import OrderService
from app.services.product_service import ProductService

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def attach_stock(products_list):
    if not products_list:
        return products_list
    product_ids = [str(p["_id"]) for p in products_list]
    inventory_records = Inventory.query.filter(
        Inventory.product_id.in_(product_ids)
    ).all()
    stock_map = {inv.product_id: inv.stock for inv in inventory_records}
    for p in products_list:
        p["stock"] = stock_map.get(str(p["_id"]), 0)
    return products_list


# 1. Auth Decorator
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin.admin_login"))  # Note: admin.admin_login
        return f(*args, **kwargs)

    return decorated


# 2. Login Routes
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


# 3. Dashboard
@admin_bp.route("/")
@admin_required
def dashboard():
    # 1. Revenue & Order Counts (SQL)
    revenue = (
        sql_db.session.query(sql_db.func.sum(OrderSQL.total_amount)).scalar() or 0.0
    )
    orders_count = OrderSQL.query.count()
    recent_orders = OrderSQL.query.order_by(OrderSQL.created_at.desc()).limit(10).all()

    # 2. Product Count (Mongo)
    products_count = mongo.db.products.count_documents({})

    # 3. Category Distribution (Mongo Aggregation)
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    cat_stats = list(mongo.db.products.aggregate(pipeline))

    return render_template(
        "admin/dashboard.html",
        revenue=round(revenue, 2),
        o_count=orders_count,
        p_count=products_count,
        orders=recent_orders,
        cat_stats=cat_stats,
    )


@admin_bp.route("/products")
@admin_required
def admin_products():
    page = int(request.args.get("page", 1))
    per_page = current_app.config["ADMIN_PER_PAGE"]
    skip = (page - 1) * per_page
    search_query = request.args.get("q", "")

    # 1. Build Query (Mongo)
    query_filter = {}
    if search_query:
        query_filter["$or"] = [
            {"name": {"$regex": search_query, "$options": "i"}},
            {"description": {"$regex": search_query, "$options": "i"}},
            {"category": {"$regex": search_query, "$options": "i"}},
        ]

    # 2. Fetch & Count
    cursor = mongo.db.products.find(query_filter).sort("created_at", -1)
    total_products = mongo.db.products.count_documents(query_filter)
    products = list(cursor.skip(skip).limit(per_page))

    # 3. Attach Stock & Fix ObjectId
    if products:
        p_ids = [str(p["_id"]) for p in products]
        inventory_map = {
            inv.product_id: inv.stock
            for inv in Inventory.query.filter(Inventory.product_id.in_(p_ids)).all()
        }

        for p in products:
            # CRITICAL FIX: Convert ObjectId to string for JSON serialization
            p["_id"] = str(p["_id"])
            p["stock"] = inventory_map.get(p["_id"], 0)

    # --- HTMX RESPONSE ---
    if request.headers.get("HX-Request"):
        return render_template("admin/partials/products_list.html", products=products)

    # Full Page Load
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
    # 1. Parse Data
    try:
        specs = json.loads(request.form.get("specs_json", "{}"))
    except:
        specs = {}

    data = {
        "name": request.form.get("name"),
        "price": request.form.get("price"),
        "category": request.form.get("category"),
        "image": request.form.get("image"),
        "specs": specs,
    }
    stock = request.form.get("stock", 0)

    # 2. Call Service (The complex logic is hidden!)
    new_product = ProductService.create_product(data, stock)

    # 3. Render
    return render_template("admin/partials/product_row.html", product=new_product)


@admin_bp.route("/products/update/<product_id>", methods=["POST"])
@admin_required
def admin_update_product(product_id):
    field = request.args.get("field")
    value = request.form.get("value") or request.form.get(field)

    # Call Service
    new_val = ProductService.update_product(product_id, field, value)

    if field == "price":
        return f"${new_val}"
    return f"{new_val}"


@admin_bp.route("/products/delete/<product_id>", methods=["DELETE"])
@admin_required
def admin_delete_product(product_id):
    ProductService.delete_product(product_id)
    return ""


@admin_bp.route("/orders")
@admin_required
def admin_orders():
    search_query = request.args.get("q", "")

    # Call Service
    orders = OrderService.get_orders(search_query)

    return render_template("admin/orders.html", orders=orders, q=search_query)


@admin_bp.route("/orders/update/<int:order_id>", methods=["POST"])
@admin_required
def update_order_status(order_id):
    new_status = request.form.get("status")

    # Call Service
    OrderService.update_status(order_id, new_status)

    # ... (Return HTMX Select as before) ...
    # (You can likely keep the existing return logic for the UI here)
    return """
    <select name="status" ... >
       ... (Keep the select HTML you had) ...
    </select>
    """
