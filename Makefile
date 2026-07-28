PYTHON = .venv/bin/python
FLASK = .venv/bin/flask
UV = uv

GREEN = \033[0;32m
NC = \033[0m

.PHONY: run setup redis-check db-clean db-reset db-migrate db-upgrade seed format lint typecheck test check clean

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
