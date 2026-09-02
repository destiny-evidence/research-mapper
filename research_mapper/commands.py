"""Application entry points."""

import asyncio
import os
import sys
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from pgqueuer.executors import DatabaseRetryEntrypointExecutor
from pgqueuer.errors import RetryRequested
import uvicorn

from dotenv import set_key

from research_mapper import local_destiny_auth
from research_mapper.config import (
    configure_dspy,
    init_database,
    init_destiny_client,
    load_environment,
)
from research_mapper.db.session import db_manager
from research_mapper.engine import queue, runner
from research_mapper import workflows

HEARTBEAT_TIMEOUT = timedelta(minutes=5)
DEQUEUE_TIMEOUT = timedelta(seconds=5)
MAX_RETRIES = 1
BUSY_RETRY_DELAY = timedelta(seconds=30)


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
        try:
            await asyncio.to_thread(
                runner.run_operation,
                operation_id,
                db_manager.session,
                workflows.context,
            )
        except runner.SessionBusy as exc:
            raise RetryRequested(delay=BUSY_RETRY_DELAY, reason=str(exc)) from exc

    await manager.run(
        dequeue_timeout=DEQUEUE_TIMEOUT, heartbeat_timeout=HEARTBEAT_TIMEOUT
    )


def worker() -> None:
    """Run the operation worker."""
    init_database()
    configure_dspy()
    init_destiny_client()
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


def login() -> None:
    """Log in to DESTINY and store a refresh token for local development."""
    load_environment()
    env = os.environ.get("MAPPER_DESTINY_ENV")
    if not env:
        print("Set MAPPER_DESTINY_ENV")
        sys.exit(1)
    token = local_destiny_auth.login(env)
    if not token.refresh_token:
        raise SystemExit("Destiny issued no refresh token")

    path = Path(".env")
    set_key(
        str(path),
        local_destiny_auth.REFRESH_TOKEN_VAR,
        token.refresh_token,
        quote_mode="never",
    )
    print(
        f"wrote {local_destiny_auth.REFRESH_TOKEN_VAR} to {path.resolve()}",
        file=sys.stderr,
    )


COMMANDS: dict[str, Callable[..., None]] = {
    "api": api,
    "login": login,
    "worker": worker,
    "migrate": migrate,
}
