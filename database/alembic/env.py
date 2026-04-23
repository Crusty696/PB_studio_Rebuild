"""Alembic environment configuration for PB Studio.

Supports both online (connected) and offline (SQL script) migration modes.
Uses the project's existing engine and model metadata so migrations stay
in sync with the ORM definitions.
"""
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

from database.models import Base
from database.session import get_raw_engine

# Alembic Config object — provides access to alembic.ini values
config = context.config

# Set up loggers from alembic.ini — nur wenn die Host-App noch kein Logging
# konfiguriert hat. Sonst wuerde fileConfig den RotatingFileHandler aus
# main.setup_logging() entfernen und die Datei-Logs blind machen.
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# The target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without a live connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — uses a live database connection."""
    # M-45 Fix: Allow providing an engine via the config object (useful for testing)
    # Check if an engine was passed in the config attributes
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        # Fallback: check if we should use the project's raw engine or create a new one from URL
        url = config.get_main_option("sqlalchemy.url")
        if url and "test_migration_roundtrip.db" in url:
            from sqlalchemy import create_engine
            connectable = create_engine(url)
        else:
            connectable = get_raw_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Required for SQLite ALTER TABLE support
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
