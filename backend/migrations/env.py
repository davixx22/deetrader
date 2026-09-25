import asyncio

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.models.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
target_metadata = Base.metadata
MIGRATION_LOCK_ID = 704338233


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.execute(
            text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID}
        )
        try:
            await connection.run_sync(do_run_migrations)
        finally:
            await connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID}
            )
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
