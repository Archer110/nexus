from collections.abc import Callable
from typing import Any

import fakeredis
import pytest
from flask import Flask

from app import create_app
from app.extensions import sql_db
from config import TestingConfig


@pytest.fixture
def app_factory() -> Callable[..., Flask]:
    """Build test applications through the production application factory."""

    def factory(**overrides: Any) -> Flask:
        config_values = {
            "SESSION_REDIS": fakeredis.FakeRedis(),
            **overrides,
        }
        config_class = type(
            "ConfiguredTestConfig",
            (TestingConfig,),
            config_values,
        )
        return create_app(config_class)

    return factory


@pytest.fixture
def app(app_factory):
    application = app_factory()
    yield application

    with application.app_context():
        sql_db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mock_db(mocker):
    """Mock the SQLAlchemy session for focused service tests."""
    return mocker.patch("app.extensions.sql_db.session")


@pytest.fixture
def mock_mongo(mocker):
    """Mock the Mongo database handle for focused service tests."""
    return mocker.patch("app.extensions.mongo.db")
