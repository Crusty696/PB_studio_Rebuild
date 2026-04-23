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
    """Run migrations in 'online' mode — uses a live database connection.

    If ``sqlalchemy.url`` is explicitly set in the Alembic config (e.g. by a
    test that passes a tmp-path SQLite URL), that URL is used instead of the
    project's default engine.  This allows integration tests to run migrations
    against a throw-away DB without touching ``pb_studio.db``.
    """
    url = config.get_main_option("sqlalchemy.url", None)
    default_url = "sqlite:///pb_studio.db"

    if url and url != default_url:
        # Test (or CI) override: create a fresh engine for the given URL.
        from sqlalchemy import create_engine as _create_engine, event as _event

        connectable = _create_engine(
            url,
            connect_args={"check_same_thread": False},
        )

        @_event.listens_for(connectable, "connect")
        def _set_pragmas(dbapi_conn, _rec):  # type: ignore[misc]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
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
