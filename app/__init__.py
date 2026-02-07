from flask import Flask

from app.extensions import migrate, mongo, sql_db
from config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 1. Initialize Extensions
    mongo.init_app(app)
    sql_db.init_app(app)
    migrate.init_app(app, sql_db)

    # 2. Register Global Template Utilities
    # This allows us to use toggle_url() in any template (for filters)
    from app.utils import toggle_url

    app.add_template_global(toggle_url, "toggle_url")

    # 3. Register Blueprints
    from app.routes.admin import admin_bp
    from app.routes.cart import cart_bp
    from app.routes.store import store_bp

    app.register_blueprint(store_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(cart_bp)

    # 4. Create SQL Tables (Dev Mode)
    # In production, you would use Flask-Migrate
    with app.app_context():
        sql_db.create_all()

    return app
