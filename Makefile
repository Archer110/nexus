PYTHON = .venv/bin/python
FLASK = .venv/bin/flask
UV = uv
COMPOSE = COMPOSE_DISABLE_ENV_FILE=1 docker compose

GREEN = \033[0;32m
NC = \033[0m

.PHONY: run setup admin-hash redis-check db-clean db-reset db-migrate db-upgrade seed format lint typecheck test check clean compose-config compose-build compose-admin-hash compose-up compose-down compose-destroy compose-logs compose-ps compose-db-upgrade compose-seed compose-ready

run:
	@echo "${GREEN}Starting Server...${NC}"
	$(FLASK) --app run.py run --debug

redis-check:
	$(FLASK) --app run.py redis-check

setup:
	@echo "${GREEN}Creating virtual environment with uv...${NC}"
	$(UV) venv
	@echo "${GREEN}Installing dependencies with uv...${NC}"
	$(UV) sync
	@echo "${GREEN}Creating .env file...${NC}"
	@if [ ! -f .env ]; then cp .env.example .env 2>/dev/null || touch .env; fi

admin-hash:
	@$(PYTHON) scripts/generate_admin_hash.py

db-migrate:
	$(FLASK) --app run.py db migrate -m "$(message)"

db-upgrade:
	$(FLASK) --app run.py db upgrade

db-clean:
	$(FLASK) --app run.py db-clean

db-reset: db-clean db-upgrade

seed:
	@echo "${GREEN}Resetting and seeding products...${NC}"
	$(PYTHON) seed.py

compose-config:
	$(COMPOSE) config --quiet

compose-build: compose-config
	$(COMPOSE) build app

compose-admin-hash: compose-build
	$(COMPOSE) run --rm --no-deps app python scripts/generate_admin_hash.py

compose-up: compose-config
	$(COMPOSE) up --build --detach --quiet-pull

compose-down:
	$(COMPOSE) down --remove-orphans

compose-destroy:
	@if [ "$(CONFIRM)" != "nexus" ]; then \
		echo "Refusing to delete Compose volumes. Re-run with CONFIRM=nexus."; \
		exit 1; \
	fi
	$(COMPOSE) down --volumes --remove-orphans

compose-logs:
	$(COMPOSE) logs --follow app migrate postgres mongo redis

compose-ps:
	$(COMPOSE) ps

compose-db-upgrade:
	$(COMPOSE) run --rm migrate

compose-seed:
	$(COMPOSE) run --rm app python seed.py

compose-ready:
	$(COMPOSE) exec app python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5000/health/ready').read().decode())"

format:
	$(UV) run ruff check . --fix
	$(UV) run ruff format .

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy app

test:
	$(UV) run pytest

check: lint typecheck test

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	rm -rf htmlcov
	rm -f .coverage
