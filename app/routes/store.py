from flask import Blueprint, abort, render_template, request

from app.services.product_service import ProductService

store_bp = Blueprint("store", __name__)


@store_bp.route("/")
def index():
    # 1. Parse Query Params
    page = int(request.args.get("page", 1))
    query = request.args.get("q", "")
    category = request.args.get("cat", "")

    # 2. Extract Spec Filters
    # (Everything in args that isn't a reserved keyword is a spec filter)
    spec_filters = {}
    reserved_keys = ["page", "q", "cat"]
    for key in request.args.keys():
        if key not in reserved_keys:
            spec_filters[key] = request.args.getlist(key)

    # 3. Call Service (Get Catalog)
    products, total_count = ProductService.get_catalog(
        page=page,
        per_page=None,
        search_query=query,
        category=category,
        spec_filters=spec_filters,
    )

    # 4. Call Service (Get Sidebar Data)
    all_categories, active_facets = ProductService.get_facets(category)

    # 5. Render
    template_ctx = {
        "products": products,
        "total_count": total_count,
        "all_categories": all_categories,
        "active_facets": active_facets,
        "page": page,
        "cat": category,
        "q": query,
        # Note: 'toggle_url' is now globally available!
    }

    # HTMX Handling
    if request.headers.get("HX-Request"):
        target = request.headers.get("HX-Target")
        if target == "main-layout":
            return render_template("partials/main_layout.html", **template_ctx)
        return render_template("partials/product_list.html", **template_ctx)

    return render_template("index.html", **template_ctx)


@store_bp.route("/product/<product_id>")
def product_detail(product_id):
    product = ProductService.get_product_details(product_id)

    if not product:
        abort(404)

    return render_template("product_detail.html", product=product)
