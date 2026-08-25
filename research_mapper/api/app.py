"""The API application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from research_mapper import workflows
from research_mapper.api.routers import operations, sessions
from research_mapper.config import close_database, init_database, load_environment


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Open the database on boot."""
    load_environment()
    init_database()
    workflows.load()
    yield
    close_database()


app = FastAPI(title="research-mapper", lifespan=lifespan)
app.include_router(sessions.router)
app.include_router(operations.router)
for workflow_router in workflows.routers():
    app.include_router(workflow_router)


@app.get("/healthz", tags=["ops"])
def healthz() -> dict[str, str]:
    """Liveness. Deliberately touches nothing."""
    return {"status": "ok"}
