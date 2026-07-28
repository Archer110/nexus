from datetime import timedelta

import pytest
from flask_session.redis import RedisSessionInterface

from config import ProductionConfig


def test_application_factory_registers_complete_application_wiring(app):
    assert isinstance(app.session_interface, RedisSessionInterface)
    assert "money" in app.jinja_env.filters
    assert "cart_total" in app.jinja_env.filters
    assert {
        "store.index",
        "cart.checkout",
        "admin.dashboard",
    } <= {rule.endpoint for rule in app.url_map.iter_rules()}


def test_application_factory_rejects_missing_required_settings(app_factory):
    with pytest.raises(
        RuntimeError,
        match="Missing required configuration: SECRET_KEY",
    ):
        app_factory(SECRET_KEY=None)


def test_application_factory_rejects_invalid_session_lifetime(app_factory):
    with pytest.raises(
        RuntimeError,
        match="PERMANENT_SESSION_LIFETIME must be a positive duration",
    ):
        app_factory(PERMANENT_SESSION_LIFETIME=timedelta())


def test_production_profile_enforces_secure_session_cookies():
    assert ProductionConfig.SESSION_COOKIE_SECURE is True
    assert ProductionConfig.ALLOW_DB_CLEAN is False
