from flask import Flask
from flask_migrate import upgrade
from sqlalchemy import inspect, text

from app.commands import register_commands
from app.extensions import migrate, sql_db


def _command_app(database_path) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{database_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["ALLOW_DB_CLEAN"] = True

    sql_db.init_app(app)
    migrate.init_app(app, sql_db)
    register_commands(app)
    return app


def test_db_clean_recovers_pre_migration_database(tmp_path):
    app = _command_app(tmp_path / "old-schema.sqlite")

    with app.app_context():
        sql_db.create_all()
        sql_db.session.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        sql_db.session.commit()

    result = app.test_cli_runner().invoke(
        args=["db-clean", "--yes"],
    )

    assert result.exit_code == 0
    assert "SQL schema removed" in result.output

    with app.app_context():
        assert inspect(sql_db.engine).get_table_names() == []

        upgrade()
        tables = set(inspect(sql_db.engine).get_table_names())
        assert {
            "alembic_version",
            "inventory",
            "orders",
            "order_items",
        } <= tables


def test_db_clean_requires_explicit_opt_in(tmp_path):
    app = _command_app(tmp_path / "production.sqlite")
    app.config["ALLOW_DB_CLEAN"] = False

    result = app.test_cli_runner().invoke(
        args=["db-clean", "--yes"],
    )

    assert result.exit_code == 1
    assert "Set ALLOW_DB_CLEAN=1" in result.output
