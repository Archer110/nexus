import click
from flask import Flask, current_app
from sqlalchemy import inspect, text

from app.extensions import Base, sql_db


def register_commands(app: Flask) -> None:
    @app.cli.command("db-clean")
    @click.option(
        "--yes",
        is_flag=True,
        help="Skip the destructive-action confirmation.",
    )
    def db_clean(yes: bool) -> None:
        """Drop application SQL tables and Alembic revision state."""
        if not current_app.config.get("ALLOW_DB_CLEAN", False):
            raise click.ClickException(
                "db-clean is disabled. Set ALLOW_DB_CLEAN=1 only in "
                "a development environment."
            )

        if not yes and not click.confirm(
            "Drop all NEXUS SQL tables and migration state?"
        ):
            raise click.Abort()

        engine = sql_db.engine
        existing_tables = set(inspect(engine).get_table_names())

        with engine.begin() as connection:
            Base.metadata.drop_all(bind=connection)
            if "alembic_version" in existing_tables:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

        click.echo("SQL schema removed. Run `make db-upgrade` to recreate it.")
