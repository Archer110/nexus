import os
from datetime import timedelta

from dotenv import load_dotenv

# Load variables from .env file into the environment
load_dotenv()


class Config:
    # 1. SECRETS (Read from env, fail or warn if missing)
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # 2. DATABASES (Read from env, provide dev default)
    MONGO_URI = os.environ.get("MONGO_URI")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # This ensures that if you change the DB URL in .env, Flask picks it up instantly
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 3. SERVER-SIDE SESSION SETTINGS
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

    # 4. APP SETTINGS (Safe to hardcode defaults here, or override via env)
    PRODUCTS_PER_PAGE = int(os.environ.get("PRODUCTS_PER_PAGE", 9))
    ADMIN_PER_PAGE = int(os.environ.get("ADMIN_PER_PAGE", 20))
    ALLOW_DB_CLEAN = os.environ.get("ALLOW_DB_CLEAN", "0") == "1"
