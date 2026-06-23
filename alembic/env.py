import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.models import Base

# Alembic does not put the script_location (this `alembic/` dir) on sys.path, so
# the sibling `migration_bootstrap` module isn't importable by default. Add it.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from migration_bootstrap import stamp_legacy_db_if_needed  # noqa: E402

config = context.config

# Override sqlalchemy.url with environment variable if present
# Prefer MIGRATIONS_DATABASE_URL (for local dev), fall back to DATABASE_URL
db_url = os.getenv("MIGRATIONS_DATABASE_URL") or os.getenv("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Stamp legacy create_all() DBs (no alembic_version, tables present)
        # BEFORE Alembic's own migration transaction — see helper docstring /
        # 2026-06 incident. The helper commits its own write so the baseline is
        # durable even when there are no pending migrations to run afterwards.
        stamp_legacy_db_if_needed(connection)

        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
