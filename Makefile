.PHONY: test lint migrate run-bot run-worker run-scheduler docker-up docker-down

test:
	PYTHONPATH=. .venv/bin/pytest tests/unit/ -v --cov=src/app --cov-report=term-missing

migrate:
	PYTHONPATH=. .venv/bin/alembic upgrade head

run-bot:
	PYTHONPATH=. .venv/bin/python -m src.app.bot.main

run-worker:
	PYTHONPATH=. .venv/bin/python -m src.app.worker.main

run-scheduler:
	PYTHONPATH=. .venv/bin/python -m src.app.scheduler.main

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
