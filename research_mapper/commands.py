import asyncio
from collections.abc import Callable
from datetime import timedelta
from uuid import UUID

from pgqueuer.executors import DatabaseRetryEntrypointExecutor
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
import uvicorn

from research_mapper.config import configure_dspy, init_database
from research_mapper.db.session import SessionFactory, db_manager
from research_mapper.workflows.evidence_map.context import EvidenceMapContext
from research_mapper.engine import queue, runner
from research_mapper import workflows

HEARTBEAT_TIMEOUT = timedelta(minutes=45)
DEQUEUE_TIMEOUT = timedelta(seconds=5)
MAX_RETRIES = 1


def _context(operation_id: UUID, session_factory: SessionFactory) -> EvidenceMapContext:
    return EvidenceMapContext(operation_id, session_factory)


async def _worker() -> None:
    workflows.load()
    manager = await queue.queue_manager()

    @manager.entrypoint(
        queue.ENTRYPOINT,
        concurrency_limit=1,
        on_failure="hold",
        executor_factory=lambda parameters: DatabaseRetryEntrypointExecutor(
            parameters, max_attempts=MAX_RETRIES
        ),
    )
    async def _run(job) -> None:
        operation_id = UUID(job.payload.decode())
        await asyncio.to_thread(
            runner.run_operation, operation_id, db_manager.session, _context
        )

    await manager.run(
        dequeue_timeout=DEQUEUE_TIMEOUT, heartbeat_timeout=HEARTBEAT_TIMEOUT
    )


def worker() -> None:
    """Run the operation worker."""
    init_database()
    configure_dspy()
    asyncio.run(_worker())


def api() -> None:
    """Serve the HTTP API."""

    uvicorn.run("research_mapper.api.app:app", host="0.0.0.0", port=8080)


def migrate() -> None:
    """Apply any outstanding migrations."""
    from alembic import command
    from alembic.config import Config

    init_database()
    command.upgrade(Config("alembic.ini"), "head")


def sql(statement: str) -> None:
    """Run one statement against the database and print any rows."""
    init_database()
    with db_manager.session() as db:
        result = db.execute(text(statement))
        if isinstance(result, CursorResult) and result.returns_rows:
            for row in result:
                print(row)
        db.commit()


COMMANDS: dict[str, Callable[..., None]] = {
    "api": api,
    "worker": worker,
    "migrate": migrate,
    "sql": sql,
}
