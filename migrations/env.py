
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base
from app.models import entities  # noqa: F401


# Alembic configuration
config = context.config

# Use the database URL loaded from .env through Pydantic Settings.
# Escape percent signs for ConfigParser compatibility.
config.set_main_option(
    "sqlalchemy.url",
    settings.database_url.replace("%", "%%"),
)

# Configure logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Register SQLAlchemy models for migration autogeneration.
target_metadata = Base.metadata


def get_connect_args() -> dict:
    """Return connection arguments required by the database."""
    if (
        settings.database_ssl_required
        or "supabase" in settings.database_url.lower()
    ):
        return {"sslmode": "require"}

    return {}


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using a live database connection."""
    connectable = engine_from_config(
        {"sqlalchemy.url": settings.database_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=get_connect_args(),
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
