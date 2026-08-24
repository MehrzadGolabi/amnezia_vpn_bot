.PHONY: test lint format typecheck migrate run-bot run-worker run-scheduler build up down clean

VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
PYTEST ?= $(VENV)/bin/pytest

test:
	PYTHONPATH=. $(PYTEST) tests/unit tests/e2e -v --cov=src/app --cov-report=term-missing

test-unit:
	PYTHONPATH=. $(PYTEST) tests/unit -v

migrate:
	$(PYTHON) -m alembic -c src/app/db/alembic.ini upgrade head

run-bot:
	$(PYTHON) -m src.app.bot.main

run-worker:
	$(PYTHON) -m src.app.worker.main

run-scheduler:
	$(PYTHON) -m src.app.scheduler.main

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
