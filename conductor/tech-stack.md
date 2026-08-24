# Technology Stack

## 1. Core Languages & Runtimes
- **Language:** Python 3.12+
- **Shell / Scripting:** POSIX Shell / Bash (strictly restricted for server-side `vpnctl` wrapper)

## 2. Frameworks & Libraries
- **Telegram Bot Framework:** `aiogram` 3.x (async Telegram bot API, FSM context, filters, middlewares)
- **Configuration Management:** `pydantic-settings` (type-safe environment configuration from `.env`)
- **Database ORM & Driver:** `SQLAlchemy` 2.x (Async Engine, declarative models) + `asyncpg`
- **Database Migrations:** `Alembic` (schema versioning and async migration runner)
- **Background Scheduling:** `APScheduler` 3.x (periodic database-driven reminder checks, expiry evaluations, outbox polling)
- **Remote Provisioning & Networking:** `paramiko` / async SSH tooling for `SSHCommandProvisioner`
- **Structured Logging:** `structlog` / JSON structured logger with secret redaction processors

## 3. Storage & Persistence
- **Primary Database:** PostgreSQL 16+
- **Architecture Pattern:** Transactional Outbox Pattern (`provisioning_jobs` and `notifications` tables) for durable background job execution without mandatory Redis dependency.

## 4. Infrastructure & Tooling
- **Containerization:** Docker & Docker Compose (isolated services: `bot`, `worker`, `scheduler`, `postgres`)
- **Code Quality & Typing:** `ruff` (linting & formatting), `mypy` (strict static type analysis), `pre-commit` hooks
- **Testing Suite:** `pytest`, `pytest-asyncio`, `pytest-mock`, `testcontainers` or mock database fixtures
- **Remote Server Provisioning Layer:** Isolated `scripts/provisioner/` containing `vpnctl`, non-root user setup, and minimal scoped `sudoers` rules.
