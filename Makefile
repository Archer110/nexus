# Makefile

# Variables
# We use the python executable inside the .venv created by uv
PYTHON = .venv/bin/python
FLASK = .venv/bin/flask
UV = uv

# Colors for pretty printing
GREEN = \033[0;32m
NC = \033[0m # No Color

.PHONY: run setup db-migrate db-upgrade seed lint test clean

# 1. THE "START" COMMAND
# Runs the Flask server in debug mode
run:
	@echo "${GREEN}Starting Server...${NC}"
	$(FLASK) run --debug

# 2. THE "SETUP" COMMAND (UV EDITION)
# Creates venv, installs packages via uv, and sets up .env
setup:
	@echo "${GREEN}Creating virtual environment with uv...${NC}"
	$(UV) venv
	@echo "${GREEN}Installing dependencies with uv...${NC}"
	$(UV) sync
	@echo "${GREEN}Creating .env file...${NC}"
	@if [ ! -f .env ]; then cp .env.example .env 2>/dev/null || touch .env; fi

# 3. DATABASE COMMANDS
db-init:
	$(FLASK) db init

db-migrate:
	@echo "${GREEN}Generating migration...${NC}"
	$(FLASK) db migrate -m "Auto-migration"

db-upgrade:
	@echo "${GREEN}Applying migration...${NC}"
	$(FLASK) db upgrade

# 4. THE "SEED" COMMAND (FULL)
# Runs product seeding first, then order seeding
seed:
	@echo "${GREEN}Seeding Products...${NC}"
	$(PYTHON) seed.py
	@echo "${GREEN}Seeding Orders...${NC}"
	$(PYTHON) seed_orders.py
	@echo "${GREEN}Database Seeded Successfully!${NC}"

# 5. CODE QUALITY (Ruff)
lint:
	@echo "${GREEN}Checking code style...${NC}"
	$(UV) run ruff check . --fix
	$(UV) run ruff format .

# 6. TESTING
test:
	@echo "${GREEN}Running Tests...${NC}"
	$(UV) run pytest

# 7. CLEANUP
# Removes cache files but keeps the venv
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
