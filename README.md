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

## Docker Compose development

Docker Compose is the recommended cold-clone workflow. It builds the Flask image,
starts PostgreSQL, MongoDB, and Redis with persistent named volumes, waits for
the datastores to become healthy, applies the SQL migration, and then starts the
application.

```bash
cp .env.compose.example .env.compose
make compose-admin-hash
# Replace ADMIN_PASSWORD_HASH in .env.compose with the generated value exactly.
make compose-up
make compose-seed
```

Open <http://localhost:5000>. If port 5000 is already occupied, prefix Compose
commands with an alternative, for example `APP_PORT=5001 make compose-up`. The
migration container is safe to run repeatedly; it applies only revisions that
have not yet been recorded in PostgreSQL.

Compose reads application credentials from `.env.compose` in raw mode, so
Werkzeug password hashes containing dollar signs do not need quoting or escaping.
The Make targets deliberately prevent Compose from interpreting the separate
host-development `.env` file. Service addresses are supplied only inside the
Compose network.

Useful inspection commands:

```bash
make compose-ps
make compose-ready
make compose-logs
make compose-down
```

`compose-down` preserves PostgreSQL, MongoDB, and Redis data. The explicitly
guarded `make compose-destroy CONFIRM=nexus` command also removes those named
volumes and cannot be undone. Rebuild the application image after source or
dependency changes with `make compose-build`.

The Compose environment uses pinned PostgreSQL 17, MongoDB 8.2, Redis 8, Python
3.12, and uv images. Datastore ports are intentionally private to the Compose
network; use the Compose Make targets or
`COMPOSE_DISABLE_ENV_FILE=1 docker compose exec` when direct inspection is
needed.

## Host-based development

PostgreSQL, MongoDB, and Redis must be running locally. Create the PostgreSQL
database referenced by `DATABASE_URL` before starting the application. The
default Redis URL is `redis://localhost:6379/0`; verify the configured service
with `make redis-check`.

```bash
make setup
# Generate an admin password hash, then copy it into .env.
make admin-hash
# Edit .env with the hash and valid local database credentials.
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

The admin password is never stored in plaintext. `ADMIN_PASSWORD_HASH` must
contain the output of `make admin-hash`; the application fails at startup when
the admin username or password hash is missing.

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

The Dockerfile and Compose setup are development/reviewer infrastructure, not a
claim of production deployment readiness. A public deployment would additionally
need TLS, production serving, secret management, backups, and operational
monitoring.
