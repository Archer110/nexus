from pathlib import Path

from flask import Flask
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect

from app.extensions import migrate, sql_db

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[1] / "migrations"


def test_initial_migration_upgrades_and_downgrades(tmp_path):
    database_path = tmp_path / "migration.sqlite"
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{database_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    sql_db.init_app(app)
    migrate.init_app(app, sql_db)

    with app.app_context():
        upgrade(directory=str(MIGRATIONS_DIRECTORY))
        tables = set(inspect(sql_db.engine).get_table_names())
        assert {"alembic_version", "inventory", "orders", "order_items"} <= tables

        downgrade(
            revision="base",
            directory=str(MIGRATIONS_DIRECTORY),
        )
        tables = set(inspect(sql_db.engine).get_table_names())
        assert tables == {"alembic_version"}
