from datetime import timedelta

import fakeredis
from flask import jsonify, session
from flask_session.redis import RedisSessionInterface


def _session_app(app_factory, redis_client):
    app = app_factory(
        SESSION_REDIS=redis_client,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
    )

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


def test_session_cart_is_stored_in_redis_with_expiry(app_factory):
    redis_client = fakeredis.FakeRedis()
    app = _session_app(app_factory, redis_client)
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


def test_session_cookie_security_attributes_and_server_side_cleanup(app_factory):
    redis_client = fakeredis.FakeRedis()
    app = _session_app(app_factory, redis_client)
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
