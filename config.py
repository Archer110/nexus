import os
from datetime import timedelta
from typing import Any, Mapping

from dotenv import load_dotenv

# Load variables from .env file into the environment
load_dotenv()


class BaseConfig:
    """Configuration shared by every application environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY")
    MONGO_URI = os.environ.get("MONGO_URI")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_TYPE = "redis"
    SESSION_KEY_PREFIX = "nexus:session:"
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(
        hours=int(os.environ.get("SESSION_TTL_HOURS", 24))
    )
    SESSION_REFRESH_EACH_REQUEST = True
    SESSION_SERIALIZATION_FORMAT = "msgpack"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"

    PRODUCTS_PER_PAGE = int(os.environ.get("PRODUCTS_PER_PAGE", 9))
    ADMIN_PER_PAGE = int(os.environ.get("ADMIN_PER_PAGE", 20))


class DevelopmentConfig(BaseConfig):
    """Local configuration loaded from environment variables and `.env`."""

    ALLOW_DB_CLEAN = os.environ.get("ALLOW_DB_CLEAN", "0") == "1"


class TestingConfig(BaseConfig):
    """Safe defaults for isolated application tests."""

    TESTING = True
    SECRET_KEY = "nexus-test-secret"
    MONGO_URI = "mongodb://localhost:27017/nexus_test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SESSION_KEY_PREFIX = "nexus:test:session:"
    SESSION_COOKIE_SECURE = False
    ALLOW_DB_CLEAN = False


class ProductionConfig(BaseConfig):
    """Production defaults; secrets and datastore URLs remain environment-owned."""

    SESSION_COOKIE_SECURE = True
    ALLOW_DB_CLEAN = False


class Config(DevelopmentConfig):
    """Default configuration used by the local entry point."""


REQUIRED_SETTINGS = (
    "SECRET_KEY",
    "MONGO_URI",
    "SQLALCHEMY_DATABASE_URI",
    "REDIS_URL",
)


def validate_config(config: Mapping[str, Any]) -> None:
    """Fail at startup with a useful message when configuration is incomplete."""
    missing = [setting for setting in REQUIRED_SETTINGS if not config.get(setting)]
    if missing:
        joined_settings = ", ".join(missing)
        raise RuntimeError(f"Missing required configuration: {joined_settings}.")

    lifetime = config.get("PERMANENT_SESSION_LIFETIME")
    if not isinstance(lifetime, timedelta) or lifetime.total_seconds() <= 0:
        raise RuntimeError("PERMANENT_SESSION_LIFETIME must be a positive duration.")
