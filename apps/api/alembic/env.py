import asyncio
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  Registers every table on Base.metadata for autogenerate.
from app.config import get_settings
from app.database import Base

config = context.config
settings = get_settings()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
logger = logging.getLogger("alembic.env")


def _migration_url() -> str:
    """Build a clean asyncpg URL without relying on ConfigParser.

    ``set_main_option('sqlalchemy.url', ...)`` mangles passwords that contain
    ``%`` (ConfigParser interpolation). Passing the URL straight into
    ``create_async_engine`` avoids that. SSL is handled via connect_args.
    """

    url = make_url(settings.database_url)
    # Drop libpq/asyncpg SSL query flags — we set TLS on the connect args.
    drop = {"ssl", "sslmode", "channel_binding"}
    query = {k: v for k, v in url.query.items() if k.lower() not in drop}
    return url.set(query=query).render_as_string(hide_password=False)


def _connect_args() -> dict:
    if settings.uses_sqlite:
        return {"check_same_thread": False}
    return {"ssl": True}


def run_migrations_offline() -> None:
    context.configure(
        url=_migration_url(),
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
    url = make_url(settings.database_url)
    # Safe diagnostics — never log the password.
    logger.warning(
        "Migrating database host=%r database=%r driver=%s",
        url.host,
        url.database,
        url.drivername,
    )
    if not url.host:
        raise RuntimeError(
            "DATABASE_URL has no hostname. On Render, set it without quotes, like: "
            "postgresql+asyncpg://USER:PASSWORD@HOST/neondb"
        )

    connectable = create_async_engine(
        _migration_url(),
        poolclass=pool.NullPool,
        connect_args=_connect_args(),
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
