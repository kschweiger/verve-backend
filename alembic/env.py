import os
import sys
from logging.config import fileConfig

from sqlalchemy import text

from alembic import context

# 1. Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2. Import SQLModel, Settings, and your custom engine creator
from sqlmodel import SQLModel

from verve_backend import models  # noqa
from verve_backend.core.config import settings
from verve_backend.core.db import get_engine  # <--- Import your engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the URL for offline mode fallback
config.set_main_option("sqlalchemy.url", str(settings.SQLALCHEMY_DATABASE_URI))

target_metadata = SQLModel.metadata


# Ignore PostGIS internal tables
def include_object(object, name, type_, reflected, compare_to) -> bool:
    if type_ == "table" and name == "spatial_ref_sys":
        return False

    # Ignore Alembic's own version table (prevents accidental drops)
    if type_ == "table" and name == "alembic_version":  # noqa: SIM103
        return False

    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    # NOTE: Offline mode generates SQL scripts.
    # To ensure they run in the right schema, we can explicitly add the schema to the
    # version table.
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        # Store the version table in your custom schema
        version_table_schema=settings.POSTGRES_SCHEMA,
    )

    with context.begin_transaction():
        # Optional: Emit a command to set search path in the generated SQL
        context.execute(f"SET search_path TO {settings.POSTGRES_SCHEMA},public")
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    # --- CRITICAL CHANGE ---
    # Instead of engine_from_config, we use your app's get_engine().
    # This ensures connect_args={"options": f"-csearch_path={settings.POSTGRES_SCHEMA},public"}  # noqa: E501
    # is applied to the Alembic connection.
    connectable = get_engine()

    with connectable.connect() as connection:
        connection.execute(
            text(f"CREATE SCHEMA IF NOT EXISTS {settings.POSTGRES_SCHEMA}")
        )
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            # Store the version table in 'verve' instead of 'public'
            version_table_schema=settings.POSTGRES_SCHEMA,
        )

        with context.begin_transaction():
            # Ensure the search path is active for the transaction
            context.execute(
                text(f"SET search_path TO {settings.POSTGRES_SCHEMA},public")
            )
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
