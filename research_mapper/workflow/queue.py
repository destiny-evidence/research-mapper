from uuid import UUID

import psycopg
from pgqueuer.adapters.drivers.psycopg import PsycopgDriver
from pgqueuer.adapters.persistence import qb
from pgqueuer.qm import QueueManager
from pgqueuer.queries import Queries

from research_mapper.db.session import db_password, db_settings

ENTRYPOINT = "operation"


async def connect() -> psycopg.AsyncConnection:
    """Open a connection for pgqueuer, taking a fresh credential as we go."""
    settings = db_settings()
    conninfo = psycopg.conninfo.make_conninfo(
        user=settings.user,
        host=settings.host,
        dbname=settings.db_name,
        password=db_password(settings),
        sslmode="require",
    )
    return await psycopg.AsyncConnection.connect(conninfo, autocommit=True)


async def queries() -> tuple[Queries, psycopg.AsyncConnection]:
    """Build a pgqueuer repository and the connection it owns."""
    connection = await connect()
    return Queries(PsycopgDriver(connection)), connection


async def enqueue(operation_id: UUID) -> None:
    """Queue an operation for a worker to pick up."""
    repository, connection = await queries()
    try:
        await repository.enqueue(
            ENTRYPOINT,
            str(operation_id).encode(),
            dedupe_key=str(operation_id),
        )
    finally:
        await connection.close()


def install_ddl(create_schema: bool = False) -> str:
    """The DDL that creates pgqueuer's schema."""
    return qb.QueryBuilderEnvironment().build_install_query(create_schema=create_schema)


def upgrade_ddl() -> list[str]:
    """The statements that migrate an older pgqueuer schema to this version."""
    return list(qb.QueryBuilderEnvironment().build_upgrade_queries())


def uninstall_ddl() -> str:
    """The DDL that drops pgqueuer's schema."""
    return qb.QueryBuilderEnvironment().build_uninstall_query()


async def queue_manager() -> QueueManager:
    """Build a QueueManager on its own connection."""
    repository, _ = await queries()
    return QueueManager(repository)
