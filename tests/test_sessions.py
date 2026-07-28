from datetime import timedelta

import fakeredis
from flask import jsonify, session
from flask_session.redis import RedisSessionInterface

from app import create_app


def _session_app(redis_client):
    class SessionTestConfig:
        SECRET_KEY = "session-test-secret"
        MONGO_URI = "mongodb://localhost:27017/nexus_test"
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        REDIS_URL = "redis://unused:6379/0"
        SESSION_TYPE = "redis"
        SESSION_REDIS = redis_client
        SESSION_KEY_PREFIX = "nexus:test:session:"
        SESSION_PERMANENT = True
        PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
        SESSION_REFRESH_EACH_REQUEST = True
        SESSION_SERIALIZATION_FORMAT = "msgpack"
        SESSION_COOKIE_HTTPONLY = True
        SESSION_COOKIE_SAMESITE = "Lax"
        SESSION_COOKIE_SECURE = False
        PRODUCTS_PER_PAGE = 9
        ADMIN_PER_PAGE = 20
        ALLOW_DB_CLEAN = False

    app = create_app(SessionTestConfig)
    app.config["TESTING"] = True

    @app.post("/test-session")
    def set_test_session():
        session["cart"] = [
            {
                "product_id": "64b64b64b64b64b64b64b64b",
                "price": "19.90",
                "qty": 2,
            }
        ]
        return "", 204

    @app.get("/test-session")
    def get_test_session():
        return jsonify(cart=session.get("cart", []))

    @app.delete("/test-session")
    def delete_test_session():
        session.clear()
        return "", 204

    return app


def test_session_cart_is_stored_in_redis_with_expiry():
    redis_client = fakeredis.FakeRedis()
    app = _session_app(redis_client)
    client = app.test_client()

    response = client.post("/test-session")

    assert response.status_code == 204
    assert isinstance(app.session_interface, RedisSessionInterface)

    cookie = client.get_cookie(app.config["SESSION_COOKIE_NAME"])
    assert cookie is not None
    assert "64b64b64b64b64b64b64b64b" not in cookie.value

    keys = list(redis_client.scan_iter(match="nexus:test:session:*"))
    assert len(keys) == 1
    assert 0 < redis_client.ttl(keys[0]) <= 3600

    response = client.get("/test-session")
    assert response.get_json()["cart"][0] == {
        "price": "19.90",
        "product_id": "64b64b64b64b64b64b64b64b",
        "qty": 2,
    }

    result = app.test_cli_runner().invoke(args=["redis-check"])
    assert result.exit_code == 0
    assert "Redis session storage is available." in result.output


def test_session_cookie_security_attributes_and_server_side_cleanup():
    redis_client = fakeredis.FakeRedis()
    app = _session_app(redis_client)
    client = app.test_client()

    response = client.post("/test-session")

    cookie_header = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie_header
    assert "SameSite=Lax" in cookie_header
    assert "Expires=" in cookie_header
    assert list(redis_client.scan_iter(match="nexus:test:session:*"))

    response = client.delete("/test-session")

    assert response.status_code == 204
    assert list(redis_client.scan_iter(match="nexus:test:session:*")) == []
