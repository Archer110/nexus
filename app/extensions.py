# app/extensions.py
from flask_migrate import Migrate
from flask_pymongo import PyMongo
from flask_sqlalchemy import SQLAlchemy

# We create the instances here, but we don't connect them yet.
mongo = PyMongo()
sql_db = SQLAlchemy()
migrate = Migrate()
