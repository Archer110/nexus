from typing import Any

from flask_migrate import Migrate  # type: ignore[import-untyped]
from flask_pymongo import PyMongo
from flask_session import Session  # type: ignore[import-untyped]
from flask_sqlalchemy import SQLAlchemy
from pymongo.database import Database
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


mongo = PyMongo()
sql_db = SQLAlchemy(model_class=Base)
migrate = Migrate()
server_session = Session()


def get_mongo_db() -> Database[dict[str, Any]]:
    database = mongo.db
    if database is None:
        raise RuntimeError("MongoDB has not been initialized.")
    return database
