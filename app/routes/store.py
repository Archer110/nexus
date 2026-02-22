from flask import Blueprint, abort, render_template, request

from app.services.product_service import ProductService

store_bp = Blueprint("store", __name__)

@store_bp.route("/")
def index():
    """
    The Main Storefront.
    Architecture:
    - Acts as a 'Traffic Cop' (Controller).
    - Delegates data fetching to ProductService.
    - Handles HTMX partial rendering for the 'Modern Monolith' feel.
    """
    # 1. Parse Standard Query Params
    page = int(request.args.get("page", 1))
    query = request.args.get("q", "")
    category = request.args.get("cat", "")

    # 2. Extract Dynamic Spec Filters (The "NoSQL" Magic)
    # Any query param that isn't 'page', 'q', or 'cat' is treated as a product spec.
    # Example: ?cat=Laptops&RAM=16GB&Color=Silver
    reserved_keys = ["page", "q", "cat"]
    spec_filters = {
        key: request.args.getlist(key)
        for key in request.args.keys()
        if key not in reserved_keys
    }

    # 3. Call Service (The "Hybrid Join")
    # The route doesn't know this data comes from Mongo + SQL. It just gets a list.
    products, total_count = ProductService.get_catalog(
        page=page,
        per_page=None, # Use default from config
        search_query=query,
        category=category,
        spec_filters=spec_filters,
    )

    # 4. Call Service (Sidebar Data)
    # Facets are calculated using Mongo Aggregation
    all_categories, active_facets = ProductService.get_facets(category)

    # 5. Prepare Context
    template_ctx = {
        "products": products,
        "total_count": total_count,
        "all_categories": all_categories,
        "active_facets": active_facets,
        "page": page,
        "cat": category,
        "q": query,
        "spec_filters": spec_filters
    }

    # 6. Render (HTMX Support)
    # If the request comes from HTMX (e.g. clicking a filter), 
    # we only render the product grid, not the whole page.
    if request.headers.get("HX-Request"):
        target = request.headers.get("HX-Target")
        if target == "main-layout":
            return render_template("partials/main_layout.html", **template_ctx)
        return render_template("partials/product_list.html", **template_ctx)

    # Standard Full Page Load
    return render_template("index.html", **template_ctx)


@store_bp.route("/product/<product_id>")
def product_detail(product_id):
    """
    Single Product Page.
    Fetches the merged document (Mongo Details + SQL Stock).
    """
    product = ProductService.get_product_details(product_id)

    if not product:
        abort(404)

    return render_template("product_detail.html", product=product)
