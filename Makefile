SHELL := /bin/bash
COMPOSE := docker compose
WPCLI := $(COMPOSE) run --rm wpcli

# --- Django + React app config -------------------------------------------- #
# Absolute path to the virtualenv interpreter so recipes work after `cd`.
ifeq ($(OS),Windows_NT)
VENV_PY := $(CURDIR)/.venv/Scripts/python.exe
else
VENV_PY := $(CURDIR)/.venv/bin/python
endif

BACKEND_PORT ?= 8000

.PHONY: help \
	up down restart logs reset wp bootstrap dump status \
	setup venv install-backend install-frontend \
	migrate seed check backend frontend dev stop \
	test test-backend test-frontend scss fresh

help:
	@echo "WordPress source stack (Docker):"
	@echo "  up              Start db + wordpress + phpmyadmin"
	@echo "  down            Stop containers (preserve data)"
	@echo "  reset           Stop containers AND wipe DB volume (full cold start on next 'up')"
	@echo "  logs            Tail wordpress + db logs"
	@echo "  wp ARGS=\"...\" Run wp-cli inside the stack (e.g. make wp ARGS=\"plugin list\")"
	@echo "  bootstrap       One-shot: install WP core + plugins + seed all content"
	@echo "  dump            Export current DB to db/dump.sql"
	@echo "  status          Show running services"
	@echo ""
	@echo "Django + React app:"
	@echo "  setup           Create venv, install backend + frontend deps (run once)"
	@echo "  migrate         Apply Django migrations"
	@echo "  seed            Run the idempotent WordPress import"
	@echo "  check           Django system checks"
	@echo "  backend         Migrate + seed + run Django on :$(BACKEND_PORT) (blocking)"
	@echo "  frontend        Run the Vite dev server on :5173 (blocking)"
	@echo "  dev             Run Django (background) + Vite (foreground); 'make stop' ends Django"
	@echo "  stop            Stop the background Django server started by 'make dev'"
	@echo "  test            Run backend (pytest) + frontend (vitest) suites"
	@echo "  test-backend    Backend tests only"
	@echo "  test-frontend   Frontend tests only"
	@echo "  scss            Compile frontend/scss/main.scss -> static/css/theme.css"
	@echo "  fresh           Recreate the SQLite DB from scratch, migrate, and re-seed"

# ==========================================================================
# WordPress source stack (Docker) — unchanged
# ==========================================================================

up:
	$(COMPOSE) up -d db wordpress phpmyadmin

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v
	@echo "Volume wiped. Run 'make up' to start fresh from db/dump.sql"

logs:
	$(COMPOSE) logs -f wordpress db

wp:
	$(WPCLI) $(ARGS)

bootstrap:
	$(COMPOSE) run --rm --entrypoint bash wpcli /scripts/seed.sh

dump:
	@mkdir -p db
	$(COMPOSE) exec db sh -c 'mariadb-dump -u root -p"$$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 --add-drop-table --skip-extended-insert "$$MYSQL_DATABASE"' > db/dump.sql
	@echo "Wrote db/dump.sql ($$(wc -l < db/dump.sql) lines)"

status:
	$(COMPOSE) ps

# ==========================================================================
# Django + React app
# ==========================================================================

# Create the virtualenv only if it does not already exist.
.venv:
	python -m venv .venv

venv: .venv

install-backend: .venv
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r backend/requirements.txt

install-frontend:
	cd frontend && npm install

# One-shot developer setup.
setup: install-backend install-frontend
	@echo ""
	@echo "Setup complete. Next: 'make backend' and 'make frontend' (two terminals),"
	@echo "or 'make dev' to run both at once."

migrate:
	$(VENV_PY) backend/manage.py migrate

# The import is idempotent, so re-running 'seed' is always safe.
seed:
	$(VENV_PY) backend/manage.py import_wordpress

check:
	$(VENV_PY) backend/manage.py check

# Bring the backend fully up: schema + data + server. Idempotent seed means
# this is safe to run repeatedly.
backend:
	$(VENV_PY) backend/manage.py migrate
	$(VENV_PY) backend/manage.py import_wordpress
	$(VENV_PY) backend/manage.py runserver $(BACKEND_PORT)

frontend:
	cd frontend && npm run dev

# Run both servers: Django in the background (logs to .django.log), Vite in the
# foreground. Ctrl-C stops Vite; 'make stop' stops the background Django.
dev:
	@echo "Django  -> http://127.0.0.1:$(BACKEND_PORT)"
	@echo "Vite    -> http://localhost:5173"
	@echo "Ctrl-C stops Vite; run 'make stop' to stop the background Django server."
	@$(VENV_PY) backend/manage.py migrate >/dev/null
	@$(VENV_PY) backend/manage.py import_wordpress >/dev/null
	@nohup $(VENV_PY) backend/manage.py runserver $(BACKEND_PORT) > .django.log 2>&1 & echo $$! > .django.pid
	cd frontend && npm run dev

stop:
	-@[ -f .django.pid ] && kill `cat .django.pid` 2>/dev/null && rm -f .django.pid && echo "Stopped Django" || echo "No tracked Django process (.django.pid not found)"

test: test-backend test-frontend

test-backend:
	cd backend && $(VENV_PY) -m pytest -q

test-frontend:
	cd frontend && npm test

scss:
	cd frontend && npx sass scss/main.scss static/css/theme.css --no-source-map
	@echo "Compiled frontend/static/css/theme.css"

# Cold start of the app database: wipe SQLite, recreate schema, re-import.
fresh:
	-rm -f backend/db.sqlite3
	$(VENV_PY) backend/manage.py migrate
	$(VENV_PY) backend/manage.py import_wordpress
	@echo "Fresh app DB ready (5 industries, 5 brands, 8 reviewers, 60 reviews)."
