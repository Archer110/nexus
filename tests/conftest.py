# tests/conftest.py
import os
import sys
from unittest.mock import MagicMock

import pytest

# Add the project root to python path so we can import 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def mock_app_context(mocker):
    """
    Mocks the Flask 'current_app' and application context.
    """
    mock_app = MagicMock()
    mock_app.config = {"PRODUCTS_PER_PAGE": 9, "ADMIN_PER_PAGE": 10}

    # Patch 'current_app' in the services modules
    mocker.patch("app.services.product_service.current_app", mock_app)
    return mock_app


@pytest.fixture
def mock_db(mocker):
    """Mocks the SQLAlchemy database session."""
    return mocker.patch("app.extensions.sql_db.session")


@pytest.fixture
def mock_mongo(mocker):
    """Mocks the PyMongo database object."""
    return mocker.patch("app.extensions.mongo.db")
