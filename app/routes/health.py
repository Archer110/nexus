from flask import Blueprint, current_app, jsonify
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import get_mongo_db, sql_db

health_bp = Blueprint("health", __name__, url_prefix="/health")


@health_bp.get("/live")
def liveness():
    """Confirm that the application process can serve HTTP requests."""
    return jsonify(status="ok")


@health_bp.get("/ready")
def readiness():
    """Report whether every datastore required by the vertical slice is reachable."""
    checks = {
        "postgres": False,
        "mongo": False,
        "redis": False,
    }

    try:
        sql_db.session.execute(text("SELECT 1"))
        checks["postgres"] = True
    except SQLAlchemyError:
        sql_db.session.rollback()

    try:
        get_mongo_db().command("ping")
        checks["mongo"] = True
    except PyMongoError:
        pass

    redis_client = current_app.config.get("SESSION_REDIS")
    try:
        checks["redis"] = bool(redis_client and redis_client.ping())
    except RedisError:
        pass

    if not all(checks.values()):
        unavailable = sorted(name for name, ready in checks.items() if not ready)
        current_app.logger.warning(
            "Readiness check failed for: %s", ", ".join(unavailable)
        )
        return jsonify(status="unavailable", checks=checks), 503

    return jsonify(status="ok", checks=checks)
