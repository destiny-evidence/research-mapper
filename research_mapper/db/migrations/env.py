from collections.abc import MutableMapping
from logging.config import fileConfig
from typing import Any

from alembic import context

from research_mapper.config import init_database, load_environment
from research_mapper.db.base import Base
from research_mapper.db.session import db_manager

import research_mapper.research.models  # noqa: F401
import research_mapper.workflow.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_name(
    name: str | None, type_: str, _parent_names: MutableMapping[Any, Any]
) -> bool:
    """Keep autogenerate away from tables pgqueuer owns."""
    return not (type_ == "table" and name is not None and name.startswith("pgqueuer"))


load_environment()
init_database()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=db_manager.engine.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    with db_manager.engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
