import os

from dotenv import load_dotenv

# Load variables from .env file into the environment
load_dotenv()


class Config:
    # 1. SECRETS (Read from env, fail or warn if missing)
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # 2. DATABASES (Read from env, provide dev default)
    MONGO_URI = os.environ.get("MONGO_URI")

    # This ensures that if you change the DB URL in .env, Flask picks it up instantly
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 3. APP SETTINGS (Safe to hardcode defaults here, or override via env)
    PRODUCTS_PER_PAGE = int(os.environ.get("PRODUCTS_PER_PAGE", 9))
    ADMIN_PER_PAGE = int(os.environ.get("ADMIN_PER_PAGE", 20))
