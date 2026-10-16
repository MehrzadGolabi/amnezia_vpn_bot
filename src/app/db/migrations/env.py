import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import make_url
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from src.app.config.settings import get_settings
from src.app.db.models.base import Base
# Import all models so metadata includes them
import src.app.db.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url():
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        settings = get_settings()
        url = settings.DATABASE_URL.get_secret_value()
    return url


def is_async_url(url: str) -> bool:
    # Async drivers (asyncpg, aiosqlite) need an async engine; "sqlite+aiosqlite" has no "async" in it.
    return make_url(url).get_dialect().is_async


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = get_url()
    if is_async_url(url):
        configuration = config.get_section(config.config_ini_section, {})
        configuration["sqlalchemy.url"] = url
        connectable = async_engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

        await connectable.dispose()
    else:
        from sqlalchemy import create_engine
        connectable = create_engine(url, poolclass=pool.NullPool)
        with connectable.connect() as connection:
            do_run_migrations(connection)


def run_migrations_online() -> None:
    url = get_url()
    if is_async_url(url):
        asyncio.run(run_async_migrations())
    else:
        from sqlalchemy import create_engine
        connectable = create_engine(url, poolclass=pool.NullPool)
        with connectable.connect() as connection:
            do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
