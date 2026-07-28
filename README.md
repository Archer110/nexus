# NEXUS

NEXUS is a focused e-commerce demo built to explore polyglot data ownership.
MongoDB owns the flexible product catalog, PostgreSQL owns inventory and the
transactional order ledger, and Redis owns expiring server-side sessions and
shopping carts. Flask services coordinate the three data stores for the
storefront and administration interface.

The project intentionally limits its product scope to catalog browsing,
faceted search, a cart, checkout, and basic product/order administration.

## Stack

- Python 3.12 and Flask
- PostgreSQL with SQLAlchemy
- MongoDB with PyMongo
- Redis with Flask-Session
- Jinja, HTMX, Alpine.js, and Tailwind CSS
- uv, Ruff, MyPy, and Pytest

## Local development

PostgreSQL, MongoDB, and Redis must be running locally. Create the PostgreSQL
database referenced by `DATABASE_URL` before starting the application. The
default Redis URL is `redis://localhost:6379/0`; verify the configured service
with `make redis-check`.

```bash
make setup
# Edit .env with valid local database credentials.
make db-upgrade
make run
```

`uv sync` installs the development and seed dependency groups by default. A
runtime-only environment can use `uv sync --no-default-groups`.

The development server is available at <http://localhost:5000>.

Cart and login state are stored in Redis under the `nexus:session:` key prefix.
The browser receives only an opaque session identifier. Sessions expire after
24 hours by default and refresh their expiration while active; configure this
with `SESSION_TTL_HOURS`. Set `SESSION_COOKIE_SECURE=1` whenever the application
is served over HTTPS.

To reset the databases and seed a synthetic product catalog:

```bash
make seed
```

The seed command is destructive: it replaces the product catalog and clears
the SQL inventory and order ledger. Apply migrations before seeding.

For a database created by the earlier pre-migration version, run:

```bash
make db-reset
make seed
```

`db-reset` asks for confirmation, removes only NEXUS-managed SQL tables and
Alembic state, then reapplies every migration. It requires the explicit
development setting `ALLOW_DB_CLEAN=1`. MongoDB is reset separately by
`make seed`.

## Quality checks

```bash
make lint
make typecheck
make test
```

The Docker environment and production deployment will be added after the
application model and behavior are stabilized.
