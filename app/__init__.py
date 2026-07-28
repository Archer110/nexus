from flask import Flask
from redis import Redis
from redis.backoff import ExponentialBackoff
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError
from redis.retry import Retry

from app.extensions import migrate, mongo, server_session, sql_db
from config import BaseConfig, Config, validate_config


def create_app(config_class: type[BaseConfig] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)
    validate_config(app.config)

    # 1. Initialize Extensions
    mongo.init_app(app)
    sql_db.init_app(app)
    migrate.init_app(app, sql_db)
    if app.config["SESSION_TYPE"] == "redis" and not app.config.get("SESSION_REDIS"):
        app.config["SESSION_REDIS"] = Redis.from_url(
            app.config["REDIS_URL"],
            retry=Retry(ExponentialBackoff(), 3),
            retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError],
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
    server_session.init_app(app)

    # 2. Register CLI Commands
    from app.commands import register_commands

    register_commands(app)

    # 3. Register Global Template Utilities
    # This allows us to use toggle_url() in any template (for filters)
    from app.money import cart_total, format_money
    from app.utils import toggle_url

    app.add_template_global(toggle_url, "toggle_url")
    app.add_template_filter(format_money, "money")
    app.add_template_filter(cart_total, "cart_total")

    # 4. Register Blueprints
    from app.routes.admin import admin_bp
    from app.routes.cart import cart_bp
    from app.routes.store import store_bp

    app.register_blueprint(store_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(cart_bp)

    return app
