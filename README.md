# NEXUS

NEXUS is a focused e-commerce demo built to explore polyglot persistence.
MongoDB owns the flexible product catalog, while PostgreSQL owns inventory and
the transactional order ledger. Flask services join the two data models for the
storefront and administration interface.

The project intentionally limits its product scope to catalog browsing,
faceted search, a cart, checkout, and basic product/order administration.

## Stack

- Python 3.12 and Flask
- PostgreSQL with SQLAlchemy
- MongoDB with PyMongo
- Jinja, HTMX, Alpine.js, and Tailwind CSS
- uv, Ruff, MyPy, and Pytest

## Local development

PostgreSQL and MongoDB must be running locally. Create the PostgreSQL database
referenced by `DATABASE_URL` before starting the application.

```bash
make setup
# Edit .env with valid local database credentials.
make db-upgrade
make run
```

The development server is available at <http://localhost:5000>.

To reset the databases and seed a synthetic product catalog:

```bash
make seed
```

The seed command is destructive: it replaces the product catalog and clears
the SQL inventory and order ledger. Apply migrations before seeding.

Databases created by the earlier pre-migration version should be recreated once
before applying the initial migration.

## Quality checks

```bash
make lint
make typecheck
make test
```

The Docker environment and production deployment will be added after the
application model and behavior are stabilized.
